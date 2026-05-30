from django.apps import AppConfig


class MessagingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.messaging"

    def ready(self) -> None:
        from services.channels.discord_startup import autostart_discord_bot

        autostart_discord_bot()
