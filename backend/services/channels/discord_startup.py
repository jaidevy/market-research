from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

LOG = logging.getLogger(__name__)
_BOT_LOCK_HANDLE = None


def _discord_bot_lock_path() -> Path:
    token_hint = os.environ.get("DISCORD_BOT_TOKEN", "")[:12] or "default"
    safe_hint = "".join(ch for ch in token_hint if ch.isalnum()) or "default"
    return Path(tempfile.gettempdir()) / f"market_research_discord_bot_{safe_hint}.lock"


def _release_discord_bot_lock() -> None:
    global _BOT_LOCK_HANDLE
    if _BOT_LOCK_HANDLE is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            _BOT_LOCK_HANDLE.seek(0)
            msvcrt.locking(_BOT_LOCK_HANDLE.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_BOT_LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        _BOT_LOCK_HANDLE.close()
    finally:
        _BOT_LOCK_HANDLE = None


def _acquire_discord_bot_lock() -> bool:
    global _BOT_LOCK_HANDLE
    if _BOT_LOCK_HANDLE is not None:
        return True
    handle = _discord_bot_lock_path().open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _BOT_LOCK_HANDLE = handle
    import atexit

    atexit.register(_release_discord_bot_lock)
    return True


def should_autostart_discord_bot() -> bool:
    if os.environ.get("DISCORD_BOT_AUTOSTART", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    if os.environ.get("DJANGO_SETTINGS_MODULE", "").startswith("tests."):
        return False
    if "pytest" in {os.path.basename(arg).lower() for arg in sys.argv}:
        return False
    if not any(arg == "runserver" for arg in sys.argv):
        return False
    if os.environ.get("RUN_MAIN") == "true":
        return True
    return any(arg == "--noreload" for arg in sys.argv)


def autostart_discord_bot() -> dict[str, object]:
    if not should_autostart_discord_bot():
        return {"started": False, "reason": "autostart_not_applicable"}

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        LOG.info("Discord bot autostart skipped: DISCORD_BOT_TOKEN is not configured.")
        return {"started": False, "reason": "missing_discord_bot_token"}

    target_agent = os.environ.get("DISCORD_BOT_TARGET_AGENT", "ConciergeAgent").strip() or "ConciergeAgent"
    from services.channels.discord_bot import bot_gateway  # noqa: PLC0415

    if bot_gateway.is_running():
        return {"started": False, "reason": "already_running", "target_agent": target_agent}
    if not _acquire_discord_bot_lock():
        LOG.info("Discord bot autostart skipped: another backend process owns the bot lock.")
        return {"started": False, "reason": "bot_lock_held", "target_agent": target_agent}

    try:
        bot_gateway.start(token=token, target_agent=target_agent)
    except RuntimeError as exc:
        _release_discord_bot_lock()
        LOG.warning("Discord bot autostart failed: %s", exc)
        return {"started": False, "reason": str(exc), "target_agent": target_agent}

    LOG.info("Discord bot autostart requested for target_agent=%s", target_agent)
    return {"started": True, "target_agent": target_agent}