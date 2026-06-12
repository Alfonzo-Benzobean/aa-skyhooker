"""
Celery tasks for Skyhooker.

Task schedule (added to CELERYBEAT_SCHEDULE in local.py):
  - skyhooker_poll_all_skyhooks     every 30 minutes
  - skyhooker_check_vuln_alerts     every 15 minutes
"""
from allianceauth.services.hooks import get_extension_logger
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .esi_client import (
    fetch_corporation_skyhook_list,
    fetch_skyhook_detail,
    fetch_type_name,
    get_corp_token,
    parse_esi_datetime,
)
from .models import AlertLog, Skyhook, SkyhookCorporation, SkyhookSnapshot
from .notifications import send_discord_alert

logger = get_extension_logger(__name__)

ESI_THROTTLE_SECONDS = getattr(settings, "SKYHOOKER_ESI_THROTTLE", 4)
VULN_ALERT_HOURS_BEFORE = getattr(settings, "SKYHOOKER_VULN_ALERT_HOURS", 2)
THEFT_THRESHOLD = getattr(settings, "SKYHOOKER_THEFT_THRESHOLD", 100)


@shared_task(name="skyhooker_poll_all_skyhooks", bind=True, max_retries=3)
def poll_all_skyhooks(self):
    corps = SkyhookCorporation.objects.filter(is_active=True)
    if not corps.exists():
        logger.info("Skyhooker: No active corporations configured.")
        return

    for corp in corps:
        logger.info(
            "Skyhooker: Queuing skyhook polls for %s (%s)",
            corp.corporation_name, corp.corporation_id
        )
        try:
            token = get_corp_token(corp.token_character_id)
        except Exception as e:
            logger.error(
                "Skyhooker: No valid ESI token for corp %s: %s",
                corp.corporation_id, e
            )
            continue

        try:
            skyhook_ids = fetch_corporation_skyhook_list(corp.corporation_id, token)
        except Exception as e:
            logger.error(
                "Skyhooker: Failed to fetch skyhook list for corp %s: %s",
                corp.corporation_id, e
            )
            continue

        logger.info(
            "Skyhooker: Found %d skyhooks for %s",
            len(skyhook_ids), corp.corporation_name
        )

        # Dispatch per-skyhook tasks with staggered countdowns to throttle ESI calls
        # without blocking this worker thread.
        for i, skyhook_id in enumerate(skyhook_ids):
            _poll_skyhook_task.apply_async(
                args=[corp.pk, skyhook_id],
                countdown=i * ESI_THROTTLE_SECONDS,
            )

        corp.last_updated = timezone.now()
        corp.save(update_fields=["last_updated"])


@shared_task(name="skyhooker_poll_single_skyhook")
def _poll_skyhook_task(corp_pk: int, skyhook_id: int):
    try:
        corp = SkyhookCorporation.objects.get(pk=corp_pk)
    except SkyhookCorporation.DoesNotExist:
        logger.error(
            "Skyhooker: Corporation pk=%s not found when polling skyhook %s",
            corp_pk, skyhook_id
        )
        return
    try:
        token = get_corp_token(corp.token_character_id)
    except Exception as e:
        logger.error(
            "Skyhooker: No valid ESI token for corp %s: %s",
            corp.corporation_id, e
        )
        return
    try:
        _poll_single_skyhook(corp, skyhook_id, token)
    except Exception as e:
        logger.error("Skyhooker: Error polling skyhook %s: %s", skyhook_id, e)


def _resolve_planet_names(skyhook):
    """
    Populate planet_name and solar_system_name using eveuniverse.
    Fetches from ESI if not already cached in eveuniverse.
    """
    if skyhook.planet_name or not skyhook.planet_id:
        return
    try:
        from eveuniverse.models import EvePlanet
        planet, _ = EvePlanet.objects.get_or_create_esi(id=skyhook.planet_id)
        skyhook.planet_name = planet.name
        skyhook.solar_system_id = planet.eve_solar_system_id
        skyhook.solar_system_name = planet.eve_solar_system.name
    except Exception as e:
        logger.warning(
            "Skyhooker: Could not resolve planet %s: %s",
            skyhook.planet_id, e
        )


def _poll_single_skyhook(corp: SkyhookCorporation, skyhook_id: int, token):
    data = fetch_skyhook_detail(corp.corporation_id, skyhook_id, token)
    if data is None:
        logger.debug("Skyhooker: Skyhook %s not modified (304)", skyhook_id)
        return

    skyhook, created = Skyhook.objects.get_or_create(
        structure_id=skyhook_id,
        defaults={"corporation": corp, "planet_id": data.get("planet_id", 0)},
    )

    if created:
        logger.info("Skyhooker: Discovered new skyhook %s", skyhook_id)
        reagents = data.get("reagents", [])
        if reagents:
            type_id = reagents[0].get("type_id")
            if type_id:
                skyhook.reagent_type_id = type_id
                skyhook.reagent_type_name = fetch_type_name(type_id)

    # Resolve planet/system names via eveuniverse (no extra ESI tokens needed)
    skyhook.planet_id = data.get("planet_id", skyhook.planet_id)
    _resolve_planet_names(skyhook)

    skyhook.current_state = data.get("state", "Unknown")
    skyhook.is_active = data.get("is_active", True)

    vuln = data.get("theft_vulnerability", {})
    new_vuln_start = parse_esi_datetime(vuln.get("start"))
    new_vuln_end = parse_esi_datetime(vuln.get("end"))

    if new_vuln_start != skyhook.vuln_start:
        skyhook.vuln_alert_sent = False

    skyhook.vuln_start = new_vuln_start
    skyhook.vuln_end = new_vuln_end
    skyhook.last_polled = timezone.now()
    skyhook.save()

    reagents = data.get("reagents", [])
    if reagents:
        r = reagents[0]
        snapshot = SkyhookSnapshot(
            skyhook=skyhook,
            state=data.get("state", "Unknown"),
            secured_stock=r.get("secured_stock", 0),
            unsecured_stock=r.get("unsecured_stock", 0),
            last_cycle=parse_esi_datetime(r.get("last_cycle")),
        )
        snapshot.save()
        _check_for_theft(skyhook, snapshot)


def _check_for_theft(skyhook: Skyhook, snapshot: SkyhookSnapshot):
    if snapshot.unsecured_delta is None:
        return
    if snapshot.unsecured_delta >= 0:
        return

    drop = abs(snapshot.unsecured_delta)
    if drop < THEFT_THRESHOLD:
        return

    dedup_key = f"theft_{skyhook.structure_id}_{snapshot.polled_at.strftime('%Y%m%d%H%M')}"
    if AlertLog.objects.filter(dedup_key=dedup_key).exists():
        return

    msg = (
        f"@here\n"
        f"⚠️ **Possible Theft Detected**\n"
        f"**Skyhook:** {skyhook.solar_system_name} — {skyhook.planet_name}\n"
        f"**Reagent:** {skyhook.reagent_type_name}\n"
        f"**Unsecured stock dropped by:** {drop:,} units\n"
        f"**Current unsecured:** {snapshot.unsecured_stock:,}\n"
        f"**Current secured:** {snapshot.secured_stock:,}\n"
        f"**Time:** <t:{int(snapshot.polled_at.timestamp())}:F> (<t:{int(snapshot.polled_at.timestamp())}:R>)"
    )

    alert = AlertLog.objects.create(
        skyhook=skyhook,
        alert_type=AlertLog.ALERT_THEFT,
        message=msg,
        dedup_key=dedup_key,
        amount_delta=drop,
    )
    thread_name = f"{skyhook.solar_system_name} — {skyhook.planet_name}"
    result = send_discord_alert(msg, thread_name=thread_name, structure_id=skyhook.structure_id)
    if isinstance(result, dict) and result.get("message_id"):
        alert.discord_message_id = result["message_id"]
        alert.save(update_fields=["discord_message_id"])
    logger.warning("Skyhooker: Theft alert fired for skyhook %s", skyhook.structure_id)


@shared_task(name="skyhooker_check_vuln_alerts")
def check_vulnerability_alerts():
    now = timezone.now()
    alert_horizon = now + timedelta(hours=VULN_ALERT_HOURS_BEFORE)

    upcoming = Skyhook.objects.filter(
        is_active=True,
        vuln_alert_sent=False,
        vuln_start__isnull=False,
        vuln_end__isnull=False,
        vuln_start__gte=now,
        vuln_start__lte=alert_horizon,
    ).select_related("corporation")

    for skyhook in upcoming:
        dedup_key = f"vuln_{skyhook.structure_id}_{skyhook.vuln_start.strftime('%Y%m%d%H%M')}"
        if AlertLog.objects.filter(dedup_key=dedup_key).exists():
            continue

        latest = skyhook.latest_snapshot
        unsecured = latest.unsecured_stock if latest else 0

        if unsecured == 0:
            skyhook.vuln_alert_sent = True
            skyhook.save(update_fields=["vuln_alert_sent"])
            continue

        msg = (
            f"@here\n"
            f"🔔 **Skyhook Vulnerability Window Approaching**\n"
            f"**Skyhook:** {skyhook.solar_system_name} — {skyhook.planet_name}\n"
            f"**Corporation:** {skyhook.corporation.corporation_name}\n"
            f"**Reagent:** {skyhook.reagent_type_name}\n"
            f"**Unsecured stock at risk:** {unsecured:,} units\n"
            f"**Window opens:** <t:{int(skyhook.vuln_start.timestamp())}:F> (<t:{int(skyhook.vuln_start.timestamp())}:R>)\n"
            f"**Window closes:** <t:{int(skyhook.vuln_end.timestamp())}:F> (<t:{int(skyhook.vuln_end.timestamp())}:R>)\n"
        )

        alert = AlertLog.objects.create(
            skyhook=skyhook,
            alert_type=AlertLog.ALERT_VULN_WINDOW,
            message=msg,
            dedup_key=dedup_key,
        )
        thread_name = f"{skyhook.solar_system_name} — {skyhook.planet_name}"
        result = send_discord_alert(msg, thread_name=thread_name, structure_id=skyhook.structure_id)
        if isinstance(result, dict) and result.get("message_id"):
            alert.discord_message_id = result["message_id"]
            alert.save(update_fields=["discord_message_id"])
        skyhook.vuln_alert_sent = True
        skyhook.save(update_fields=["vuln_alert_sent"])

        logger.info(
            "Skyhooker: Vuln window alert fired for skyhook %s",
            skyhook.structure_id
        )
