"""discord_bot.py — True two-way Discord gateway via discord.py.

The bot runs inside a persistent background daemon thread with its own
asyncio event loop so it never blocks Django's synchronous request handling.

Usage (Django management command or startup hook):

    from services.channels.discord_bot import bot_gateway
    bot_gateway.start(token=os.environ["DISCORD_BOT_TOKEN"])
    bot_gateway.join()          # block until SIGINT
    bot_gateway.stop()

Outbound sends from anywhere in the Django process:

    from services.channels.discord_bot import bot_gateway
    bot_gateway.send_to_channel_sync(channel_id=1234567890, content="Hello!")

Set DISCORD_PROVIDER=bot in the environment to activate this path.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

LOG = logging.getLogger(__name__)

# discord.py is an optional dependency; guard the import so the rest of
# the Django project loads fine even when the package is absent.
try:
    import discord as _discord  # noqa: F401

    _DISCORD_AVAILABLE = True
except ImportError:  # pragma: no cover
    _discord = None  # type: ignore[assignment]
    _DISCORD_AVAILABLE = False


class DiscordBotGateway:
    """Manages a discord.py ``Client`` in a long-lived background thread.

    The thread owns a dedicated asyncio event loop.  All inbound Discord
    events are handled there; outbound sends from Django's sync threads
    use :meth:`send_to_channel_sync` which schedules a coroutine on that
    loop via ``asyncio.run_coroutine_threadsafe``.
    """

    def __init__(self) -> None:
        self._token: str = ""
        self._target_agent: str = "ConciergeAgent"
        self._client: _discord.Client | None = None  # type: ignore[name-defined]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, token: str, target_agent: str = "ConciergeAgent") -> None:
        """Start the bot in a background thread.  Returns immediately."""
        if not _DISCORD_AVAILABLE:
            raise RuntimeError(
                "discord.py is not installed. "
                "Add 'discord.py>=2.3' to your dependencies and reinstall."
            )
        if self.is_running():
            LOG.warning("Discord bot gateway is already running; ignoring duplicate start()")
            return

        self._token = token
        self._target_agent = target_agent
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="discord-bot-gateway",
        )
        self._thread.start()
        LOG.info("Discord bot gateway thread started (target_agent=%s)", target_agent)

    def stop(self) -> None:
        """Signal the bot to disconnect and wait for its thread to exit."""
        if self._client and self._loop and not self._client.is_closed():
            future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
            try:
                future.result(timeout=10)
            except Exception:
                LOG.exception("Error while closing Discord client")
        if self._thread:
            self._thread.join(timeout=15)
        self._client = None
        self._loop = None
        self._thread = None
        LOG.info("Discord bot gateway stopped")

    def join(self) -> None:
        """Block the calling thread until the bot thread exits.

        Intended for management commands that want to keep the process alive
        until the bot disconnects or is interrupted.
        """
        if self._thread:
            self._thread.join()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return bool(
            self._client
            and not self._client.is_closed()
            and self._thread
            and self._thread.is_alive()
        )

    def get_status(self) -> dict:
        if not _DISCORD_AVAILABLE:
            return {"running": False, "reason": "discord_py_not_installed"}
        if not self._thread or not self._thread.is_alive():
            return {"running": False, "reason": "not_started"}
        if not self._client or self._client.is_closed():
            return {"running": False, "reason": "disconnected"}
        return {
            "running": True,
            "user": str(self._client.user),
            "latency_ms": round(self._client.latency * 1000, 1),
            "guilds": len(self._client.guilds),
        }

    # ------------------------------------------------------------------
    # Outbound send  (safe to call from any thread)
    # ------------------------------------------------------------------

    def send_to_channel_sync(self, channel_id: int, content: str) -> dict:
        """Thread-safe: send *content* to the Discord channel *channel_id*.

        Schedules the coroutine on the bot's event loop and blocks for up
        to 15 seconds waiting for the result.  Call from Django views or
        the ingest pipeline.
        """
        if not self.is_running():
            return {"ok": False, "error": "bot_not_running"}
        assert self._loop is not None  # is_running() guarantees this
        future = asyncio.run_coroutine_threadsafe(
            self._send_to_channel(channel_id, content),
            self._loop,
        )
        try:
            future.result(timeout=15)
            return {"ok": True}
        except Exception as exc:
            LOG.exception("send_to_channel_sync failed for channel_id=%s", channel_id)
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal asyncio methods  (bot event loop only)
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start_client())  # type: ignore[arg-type]
        except Exception:
            LOG.exception("Discord bot event loop exited with an error")

    async def _start_client(self) -> None:
        intents = _discord.Intents.default()  # type: ignore[union-attr]
        intents.message_content = True

        self._client = _discord.Client(intents=intents)  # type: ignore[union-attr]

        @self._client.event
        async def on_ready() -> None:  # type: ignore[misc]
            LOG.info(
                "Discord bot ready: %s (id=%s)",
                self._client.user,  # type: ignore[union-attr]
                self._client.user.id,  # type: ignore[union-attr]
            )

        @self._client.event
        async def on_message(message: _discord.Message) -> None:  # type: ignore[misc,name-defined]
            if message.author == self._client.user:
                return  # do not process own messages
            if message.author.bot:
                return  # ignore other bots
            await self._dispatch_message(message)

        await self._client.start(self._token)  # type: ignore[union-attr]

    async def _dispatch_message(self, message: _discord.Message) -> None:  # type: ignore[name-defined]
        """Hand the Discord message off to the Django ingest pipeline."""
        user_id = str(message.author.id)
        body = message.content
        channel_id = message.channel.id

        # Run synchronous Django ORM code in the default thread-pool executor
        # so the bot event loop is never blocked.
        loop = asyncio.get_running_loop()
        try:
            result: dict = await loop.run_in_executor(
                None,
                lambda: _ingest_sync(
                    external_user_id=user_id,
                    body=body,
                    channel_id=channel_id,
                    target_agent=self._target_agent,
                ),
            )
        except Exception as exc:
            LOG.exception("Ingest pipeline raised an exception for user=%s", user_id)
            await message.channel.send(f"\u26a0\ufe0f Internal error: {exc}")
            return

        if not result.get("processed"):
            error = result.get("error", "unknown error")
            await message.channel.send(f"\u26a0\ufe0f {error}")

    async def _send_to_channel(self, channel_id: int, content: str) -> None:
        """Fetch the channel and post *content*.  (bot event loop only)"""
        assert self._client is not None
        channel = self._client.get_channel(channel_id)
        if channel is None:
            channel = await self._client.fetch_channel(channel_id)
        await channel.send(content)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Module-level singleton — shared by the channel module and management command
# ---------------------------------------------------------------------------

bot_gateway = DiscordBotGateway()


# ---------------------------------------------------------------------------
# Helper: sync ingest wrapper (called from executor thread)
# ---------------------------------------------------------------------------

def _ingest_sync(
    *,
    external_user_id: str,
    body: str,
    channel_id: int,
    target_agent: str,
) -> dict:
    """Import and call ``ingest_message`` lazily inside the executor thread.

    Lazy import avoids a circular import at module load time.
    """
    from services.channels.discord import ingest_message  # noqa: PLC0415

    return ingest_message(
        external_user_id=external_user_id,
        body=body,
        target_agent_name=target_agent,
        discord_channel_id=channel_id,
    )
