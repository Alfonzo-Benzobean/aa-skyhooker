"""
ESI API client for skyhooker.

Uses django-esi's Token model to make authenticated requests.
All ESI calls are made via requests directly (not bravado/openapi client)
to avoid version compatibility issues with the skyhook-specific endpoints
which may be newer than the ESI spec bundled with django-esi.
"""
from allianceauth.services.hooks import get_extension_logger
from datetime import datetime, timezone

import requests
from esi.models import Token

logger = get_extension_logger(__name__)

ESI_BASE = "https://esi.evetech.net"
ESI_COMPATIBILITY_DATE = "2026-05-19"
SKYHOOK_SCOPE = "esi-structures.read_corporation.v1"

# Type ID for magmatic gas (Zeolites family) — main skyhook reagent
# type_id 81143 = Magmatic Gas (confirmed from API response)


def get_corp_token(corporation_id: int, character_id: int = None):
    """
    Retrieve a valid ESI token for the given corporation.
    Optionally filter by character_id.
    Raises Token.DoesNotExist if no valid token is found.
    """
    tokens = Token.objects.filter(
        character_id=character_id,
    ).require_scopes(SKYHOOK_SCOPE) if character_id else \
        Token.objects.require_scopes(SKYHOOK_SCOPE)

    token = tokens.first()
    if not token:
        raise Token.DoesNotExist(
            f"No token with scope {SKYHOOK_SCOPE} found"
            + (f" for character {character_id}" if character_id else "")
        )
    return token


def _auth_header(token: Token) -> dict:
    """Return headers for an authenticated ESI request."""
    return {
        "Authorization": f"Bearer {token.valid_access_token()}",
        "Accept": "application/json",
        "X-Compatibility-Date": ESI_COMPATIBILITY_DATE,
    }

def fetch_corporation_skyhook_list(corporation_id: int, token: Token) -> list:
    """
    GET /corporations/{corporation_id}/structures/skyhooks/
    Returns list of skyhook structure IDs for the corporation.
    """
    url = f"{ESI_BASE}/corporations/{corporation_id}/structures/skyhooks"
    try:
        resp = requests.get(
            url,
            headers=_auth_header(token),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return [s["id"] for s in data.get("skyhooks", [])]
    except requests.HTTPError as e:
        logger.error(
            "ESI error fetching skyhook list for corp %s: %s",
            corporation_id, e
        )
        raise
    except requests.RequestException as e:
        logger.error(
            "Network error fetching skyhook list for corp %s: %s",
            corporation_id, e
        )
        raise


def fetch_skyhook_detail(
    corporation_id: int,
    skyhook_id: int,
    token: Token
) -> dict:
    """
    GET /corporations/{corporation_id}/structures/skyhooks/{skyhook_id}/
    Returns full detail dict for a single skyhook.
    """
    url = (
        f"{ESI_BASE}/corporations/{corporation_id}"
        f"/structures/skyhooks/{skyhook_id}"
    )
    try:
        resp = requests.get(
            url,
            headers=_auth_header(token),
            timeout=30,
        )
        if resp.status_code == 304:
            # ETag cache hit — caller should use cached value
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        logger.error(
            "ESI error fetching skyhook %s for corp %s: %s",
            skyhook_id, corporation_id, e
        )
        raise
    except requests.RequestException as e:
        logger.error(
            "Network error fetching skyhook %s: %s",
            skyhook_id, e
        )
        raise


def fetch_type_name(type_id: int) -> str:
    """
    GET /universe/types/{type_id}/ (public endpoint, no auth needed)
    Returns the human-readable name for a type ID.
    """
    url = f"{ESI_BASE}/universe/types/{type_id}/"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json().get("name", f"Type {type_id}")
    except Exception as e:
        logger.warning("Could not resolve type_id %s: %s", type_id, e)
        return f"Type {type_id}"


def parse_esi_datetime(dt_str: str):
    """Parse ESI ISO datetime string to timezone-aware datetime."""
    if not dt_str:
        return None
    try:
        # ESI returns e.g. "2026-06-04T00:33:55Z" or with nanoseconds
        # Strip nanoseconds if present
        if "." in dt_str:
            dt_str = dt_str.split(".")[0] + "Z"
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as e:
        logger.warning("Could not parse datetime '%s': %s", dt_str, e)
        return None
