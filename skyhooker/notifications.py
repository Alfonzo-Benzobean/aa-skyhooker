"""
Discord notifications for Skyhooker — via WR0NGy bot.

Configure in local.py:
    SKYHOOKER_BOT_URL = "http://wr0ngy_bot:9000"
    SKYHOOKER_INTERNAL_API_KEY = os.environ.get("SKYHOOKER_INTERNAL_API_KEY")
"""

from allianceauth.services.hooks import get_extension_logger
import requests
from django.conf import settings

logger = get_extension_logger(__name__)


def _bot_url() -> str | None:
    return getattr(settings, "SKYHOOKER_BOT_URL", None)


def _api_key() -> str | None:
    return getattr(settings, "SKYHOOKER_INTERNAL_API_KEY", None)


def send_discord_alert(message: str, thread_name: str = "Skyhook Alert", structure_id: str = "") -> bool:
    """
    Send an alert to Discord via WR0NGy bot.
    Each skyhook gets a persistent thread identified by structure_id.
    """
    url = _bot_url()
    if not url:
        logger.warning("Skyhooker: SKYHOOKER_BOT_URL not configured — alert suppressed.")
        return False

    headers = {"Content-Type": "application/json"}
    api_key = _api_key()
    if api_key:
        headers["X-Internal-Key"] = api_key

    payload = {
        "message": message,
        "thread_name": thread_name,
        "structure_id": str(structure_id),
    }

    try:
        resp = requests.post(f"{url}/alert", headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        logger.info("Skyhooker: Alert posted (thread=%s skyhook=%s)", data.get("thread_id"), structure_id)
        return data
    except requests.HTTPError as e:
        logger.error("Skyhooker: WR0NGy HTTP error: %s", e)
    except requests.RequestException as e:
        logger.error("Skyhooker: WR0NGy request failed: %s", e)

    return False
