"""
Discord notifications for Skyhooker — via Discord webhook.

Configure the webhook URL in Django Admin under Skyhooker > Configuration.
"""
import requests
from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)


def _get_webhook_url() -> str | None:
    """Read webhook URL from the database configuration."""
    try:
        from .models import SkyhookerConfiguration
        config = SkyhookerConfiguration.objects.first()
        return config.discord_webhook if config and config.discord_webhook else None
    except Exception:
        return None


def send_discord_alert(message: str, **kwargs) -> bool:
    """
    Send an alert to Discord via the configured webhook URL.
    Returns True on success, False if unconfigured or on error.
    """
    webhook_url = _get_webhook_url()
    if not webhook_url:
        logger.warning("Skyhooker: No Discord webhook configured — alert suppressed.")
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
