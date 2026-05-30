from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.messaging.views import (
    ApprovalTicketViewSet,
    ChannelConversationViewSet,
    InterAgentMessageViewSet,
    discord_webhook,
    discord_bot_status,
    discord_bot_start,
    discord_bot_stop,
)

router = DefaultRouter()
router.register(r"messages", InterAgentMessageViewSet, basename="messages")
router.register(r"approvals", ApprovalTicketViewSet, basename="approvals")
router.register(r"conversations", ChannelConversationViewSet, basename="conversations")

urlpatterns = [
    path("", include(router.urls)),
    path("channels/discord/webhook", discord_webhook, name="discord-webhook"),
    path("channels/discord/bot/status", discord_bot_status, name="discord-bot-status"),
    path("channels/discord/bot/start", discord_bot_start, name="discord-bot-start"),
    path("channels/discord/bot/stop", discord_bot_stop, name="discord-bot-stop"),
]
