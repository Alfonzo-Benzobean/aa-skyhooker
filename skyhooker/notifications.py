"""
Discord notifications for Skyhooker — via Discord webhook.

Configure in local.py:
    SKYHOOKER_DISCORD_WEBHOOK = "https://discord.com/api/webhooks/..."
"""
import requests
from django.conf import settings
from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)


def send_discord_alert(message: str, **kwargs) -> bool:
    """
    Send an alert to Discord via a configured webhook URL.
    Returns True on success, False if unconfigured or on error.
    """
    webhook_url = getattr(settings, "SKYHOOKER_DISCORD_WEBHOOK", None)
    if not webhook_url:
        logger.warning("Skyhooker: SKYHOOKER_DISCORD_WEBHOOK not configured — alert suppressed.")
        return False

    try:
        resp = requests.post(
            webhook_url,
            json={"content": message},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Skyhooker: Alert posted to Discord webhook.")
        return True
    except requests.HTTPError as e:
        logger.error("Skyhooker: Webhook HTTP error: %s", e)
    except requests.RequestException as e:
        logger.error("Skyhooker: Webhook request failed: %s", e)

    return False
