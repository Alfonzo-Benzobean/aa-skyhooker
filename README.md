# aa-skyhooker

An [Alliance Auth](https://allianceauth.readthedocs.io/) plugin for monitoring EVE Online skyhook structures. Tracks stock levels across polls, detects possible theft via inventory deltas, and fires alerts for upcoming vulnerability windows.

## Features

- Monitors skyhook structures across multiple corporations via ESI
- Detects possible theft by comparing unsecured stock between polls
- Alerts for upcoming vulnerability windows (configurable lead time)
- Discord alerts via webhook
- In-app theft resolution workflow (confirm theft / recovered / false alarm)
- Theft report with per-reagent charts (Chart.js)
- Deduplication of alerts to prevent repeat pings

## Screenshots

*(coming soon)*

## Requirements

- Alliance Auth >= 5.0.0
- Python >= 3.10
- [django-eveuniverse](https://pypi.org/project/django-eveuniverse/)

## Installation

### 1. Install the package

```bash
pip install aa-skyhooker
```

### 2. Add to `INSTALLED_APPS` in `local.py`

```python
INSTALLED_APPS += [
    "eveuniverse",  # if not already present
    "skyhooker",
]
```

### 3. Add Celery beat schedules to `local.py`

```python
CELERYBEAT_SCHEDULE["skyhooker_poll_all_skyhooks"] = {
    "task": "skyhooker_poll_all_skyhooks",
    "schedule": 1800,  # every 30 minutes
}
CELERYBEAT_SCHEDULE["skyhooker_check_vuln_alerts"] = {
    "task": "skyhooker_check_vuln_alerts",
    "schedule": 900,  # every 15 minutes
}
```

### 4. Run migrations

```bash
python manage.py migrate skyhooker
python manage.py collectstatic
```

### 5. Restart services

```bash
docker compose restart allianceauth_worker allianceauth_beat
```

## Configuration

### Discord webhook

Create a webhook in your Discord server (Channel Settings → Integrations → Webhooks), copy the URL, then go to **Django Admin → Skyhooker → Configuration** and paste it in.

If no webhook is configured, alerts are logged but not sent to Discord — the plugin will still function normally for in-app monitoring.

### Optional `local.py` tuning

These settings are optional and can be added to `local.py` to override the defaults:

| Setting | Default | Description |
|---|---|---|
| `SKYHOOKER_ESI_THROTTLE` | `4` | Seconds to wait between ESI calls per corp poll |
| `SKYHOOKER_VULN_ALERT_HOURS` | `2` | Hours before vuln window opens to fire alert |
| `SKYHOOKER_THEFT_THRESHOLD` | `100` | Minimum unit drop to trigger a theft alert |

## Permissions

Assign these permissions in Alliance Auth to control access:

| Permission | Description |
|---|---|
| `skyhooker.view_skyhook` | View the dashboard, skyhook detail, and theft report |
| `skyhooker.view_alertlog` | View and resolve unresolved theft alerts |
| `skyhooker.add_skyhookcorporation` | Register corporations and ESI director tokens |

## Setting up corporations

1. In Django Admin, go to **Skyhooker → Tracked Corporations** and add each corporation you want to monitor (corporation ID and name).
2. In the Skyhooker dashboard, click **Register Director Token** and complete the EVE SSO flow with a character that has the Director role in that corporation.
3. Skyhooker will begin polling on the next Celery beat cycle.

The required ESI scope is `esi-structures.read_corporation.v1`.

## Changelog

### 1.0.0

- Initial public release
- Structure polling via ESI with per-corp director tokens
- Theft detection via unsecured stock delta
- Vulnerability window alerts with configurable lead time
- In-app resolution workflow (confirm / recovered / false alarm)
- Discord webhook integration (optional, configured via Django Admin)
- Theft report with Chart.js visualizations
