from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from esi.decorators import token_required
from esi.models import Token
from datetime import timedelta

from .models import AlertLog, Skyhook, SkyhookCorporation, SkyhookSnapshot

SKYHOOK_SCOPE = "esi-structures.read_corporation.v1"


@login_required
@permission_required("skyhooker.view_skyhook", raise_exception=True)
def dashboard(request):
    """Main dashboard — overview of all skyhooks."""
    now = timezone.now()

    latest_snapshot_id = (
        SkyhookSnapshot.objects
        .filter(skyhook=OuterRef("pk"))
        .order_by("-polled_at")
        .values("id")[:1]
    )

    skyhooks = (
        Skyhook.objects
        .filter(is_active=True)
        .select_related("corporation")
        .annotate(latest_snapshot_id=Subquery(latest_snapshot_id))
        .order_by("solar_system_name", "planet_name")
    )

    snapshot_ids = [s.latest_snapshot_id for s in skyhooks if s.latest_snapshot_id]
    snapshots_by_id = {
        s.id: s
        for s in SkyhookSnapshot.objects.filter(id__in=snapshot_ids)
    }
    for skyhook in skyhooks:
        skyhook.latest_snap = snapshots_by_id.get(skyhook.latest_snapshot_id)

    vulnerable_now = [s for s in skyhooks if s.is_vulnerable_now]
    upcoming_vuln = [
        s for s in skyhooks
        if s.vuln_start
        and s.vuln_start > now
        and s.vuln_start <= now + timedelta(hours=24)
        and not s.is_vulnerable_now
    ]
    normal = [
        s for s in skyhooks
        if not s.is_vulnerable_now and s not in upcoming_vuln
    ]

    recent_alerts = AlertLog.objects.select_related("skyhook").order_by("-fired_at")[:20]
    corps = SkyhookCorporation.objects.filter(is_active=True)

    # Find which corps have a valid token registered
    for corp in corps:
        corp.has_token = Token.objects.filter(
            character_id=corp.token_character_id
        ).require_scopes(SKYHOOK_SCOPE).exists()

    context = {
        "vulnerable_now": vulnerable_now,
        "upcoming_vuln": upcoming_vuln,
        "normal_skyhooks": normal,
        "recent_alerts": recent_alerts,
        "corps": corps,
        "now": now,
    }
    return render(request, "skyhooker/dashboard.html", context)


@login_required
@permission_required("skyhooker.view_skyhook", raise_exception=True)
def skyhook_detail(request, structure_id):
    """Detail view for a single skyhook with snapshot history."""
    skyhook = get_object_or_404(Skyhook, structure_id=structure_id)
    snapshots = skyhook.snapshots.order_by("-polled_at")[:144]
    alerts = skyhook.alerts.order_by("-fired_at")[:20]

    context = {
        "skyhook": skyhook,
        "snapshots": snapshots,
        "alerts": alerts,
    }
    return render(request, "skyhooker/skyhook_detail.html", context)


@login_required
@permission_required("skyhooker.add_skyhookcorporation", raise_exception=True)
@token_required(scopes=[SKYHOOK_SCOPE])
def register_token(request, token):
    """
    ESI token registration view.
    Uses django-esi's @token_required decorator to handle the SSO flow.
    The decorator redirects to EVE SSO, gets the token, then calls this
    view with the token as an argument.

    The Director selects which corporation to associate the token with.
    """
    # token is injected by @token_required after SSO completes
    corp_id = request.GET.get("corp_id")

    if corp_id:
        corp = get_object_or_404(SkyhookCorporation, corporation_id=corp_id)
        corp.token_character_id = token.character_id
        corp.token_character_name = token.character_name
        corp.save(update_fields=["token_character_id", "token_character_name"])
        messages.success(
            request,
            f"Token for {token.character_name} registered for "
            f"{corp.corporation_name}. Skyhooks will be polled on the next cycle."
        )
        return redirect("skyhooker:dashboard")

    # No corp_id — show selection form
    corps = SkyhookCorporation.objects.filter(is_active=True)
    context = {
        "token": token,
        "corps": corps,
    }
    return render(request, "skyhooker/register_token.html", context)


@login_required
@permission_required("skyhooker.view_alertlog", raise_exception=True)
def unresolved_alerts(request):
    """List of theft alerts pending resolution."""
    alerts = (
        AlertLog.objects
        .filter(alert_type=AlertLog.ALERT_THEFT)
        .exclude(resolution__isnull=False)
        .select_related("skyhook")
        .order_by("-fired_at")
    )
    context = {
        "alerts": alerts,
    }
    return render(request, "skyhooker/unresolved_alerts.html", context)


@login_required
@permission_required("skyhooker.add_skyhookcorporation", raise_exception=True)
def resolve_alert(request, alert_id):
    """Manually resolve a theft alert from the AA UI."""
    from .models import AlertResolution
    alert = get_object_or_404(AlertLog, pk=alert_id, alert_type=AlertLog.ALERT_THEFT)

    if request.method == "POST":
        status = request.POST.get("status")
        if status in [AlertResolution.STATUS_THEFT, AlertResolution.STATUS_RECOVERED, AlertResolution.STATUS_FALSE_ALARM]:
            AlertResolution.objects.update_or_create(
                alert=alert,
                defaults={
                    "status": status,
                    "amount": alert.amount_delta or 0,
                    "resolved_by_name": request.user.username,
                }
            )
            # Add reaction to Discord message if we have a message_id
            if alert.discord_message_id:
                from django.conf import settings
                import requests as req
                emoji_map = {
                    "theft": "✅",
                    "recovered": "🔄",
                    "false_alarm": "❌",
                }
                bot_url = getattr(settings, "SKYHOOKER_BOT_URL", None)
                api_key = getattr(settings, "SKYHOOKER_INTERNAL_API_KEY", None)
                if bot_url:
                    headers = {"Content-Type": "application/json"}
                    if api_key:
                        headers["X-Internal-Key"] = api_key
                    try:
                        req.post(
                            f"{bot_url}/react",
                            headers=headers,
                            json={"message_id": alert.discord_message_id, "emoji": emoji_map[status], "structure_id": str(alert.skyhook.structure_id)},
                            timeout=5,
                        )
                    except Exception:
                        pass
            messages.success(request, f"Alert resolved as {status}.")
            return redirect("skyhooker:unresolved_alerts")

    context = {"alert": alert}
    return render(request, "skyhooker/resolve_alert.html", context)


from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json


@csrf_exempt
def api_resolve_alert(request):
    """Internal API endpoint — called by WR0NGy bot when a reaction is added."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    from django.conf import settings
    api_key = getattr(settings, "SKYHOOKER_INTERNAL_API_KEY", None)
    if api_key and request.headers.get("X-Internal-Key") != api_key:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message_id = data.get("message_id")
    status = data.get("status")
    discord_user_id = str(data.get("discord_user_id", ""))
    discord_username = data.get("discord_username", "")

    if not message_id or not status:
        return JsonResponse({"error": "message_id and status required"}, status=400)

    from .models import AlertResolution
    if status not in [AlertResolution.STATUS_THEFT, AlertResolution.STATUS_RECOVERED, AlertResolution.STATUS_FALSE_ALARM]:
        return JsonResponse({"error": "Invalid status"}, status=400)

    try:
        alert = AlertLog.objects.get(discord_message_id=message_id)
    except AlertLog.DoesNotExist:
        return JsonResponse({"error": "Alert not found for message_id"}, status=404)

    resolution, created = AlertResolution.objects.update_or_create(
        alert=alert,
        defaults={
            "status": status,
            "amount": alert.amount_delta or 0,
            "resolved_by_discord_id": discord_user_id,
            "resolved_by_name": discord_username,
        }
    )

    return JsonResponse({
        "ok": True,
        "created": created,
        "alert_id": alert.id,
        "status": status,
    })


@login_required
@permission_required("skyhooker.view_skyhook", raise_exception=True)
def report(request):
    """Theft report with charts."""
    from django.db.models import Sum
    from .models import AlertResolution
    now = timezone.now()

    # Get all reagent types that have been involved in theft alerts
    reagent_types = (
        AlertResolution.objects
        .exclude(alert__skyhook__reagent_type_name='')
        .values_list('alert__skyhook__reagent_type_name', flat=True)
        .distinct()
        .order_by('alert__skyhook__reagent_type_name')
    )
    reagent_types = list(reagent_types)

    # Shades of red for lost, shades of green for recovered — one shade per reagent
    lost_shades = ['#dc3545', '#a71d2a', '#6f1119', '#e4606d', '#f1959b']
    recovered_shades = ['#198754', '#0d5c38', '#09361f', '#28a96a', '#5bc896']
    reagent_lost_colors = {r: lost_shades[i % len(lost_shades)] for i, r in enumerate(reagent_types)}
    reagent_recovered_colors = {r: recovered_shades[i % len(recovered_shades)] for i, r in enumerate(reagent_types)}

    # This month stats per reagent
    month_data = {}
    for reagent in reagent_types:
        qs = AlertResolution.objects.filter(
            alert__fired_at__year=now.year,
            alert__fired_at__month=now.month,
            alert__skyhook__reagent_type_name=reagent,
        )
        month_data[reagent] = {
            'lost': qs.filter(status='theft').aggregate(t=Sum('amount'))['t'] or 0,
            'recovered': qs.filter(status='recovered').aggregate(t=Sum('amount'))['t'] or 0,
            'false_alarms': qs.filter(status='false_alarm').count(),
            'lost_color': reagent_lost_colors[reagent],
            'recovered_color': reagent_recovered_colors[reagent],
        }

    month_lost = sum(d['lost'] for d in month_data.values())
    month_recovered = sum(d['recovered'] for d in month_data.values())
    month_false_alarms = sum(d['false_alarms'] for d in month_data.values())

    # Unresolved count
    unresolved_count = (
        AlertLog.objects
        .filter(alert_type=AlertLog.ALERT_THEFT)
        .exclude(resolution__isnull=False)
        .count()
    )

    # Monthly history - last 6 months per reagent
    months = []
    for i in range(5, -1, -1):
        if now.month - i <= 0:
            month_num = now.month - i + 12
            year = now.year - 1
        else:
            month_num = now.month - i
            year = now.year
        months.append({'label': f"{year}-{month_num:02d}", 'year': year, 'month': month_num})

    monthly_history = []
    for m in months:
        entry = {'label': m['label'], 'reagents': {}}
        for reagent in reagent_types:
            qs = AlertResolution.objects.filter(
                alert__fired_at__year=m['year'],
                alert__fired_at__month=m['month'],
                alert__skyhook__reagent_type_name=reagent,
            )
            entry['reagents'][reagent] = {
                'lost': qs.filter(status='theft').aggregate(t=Sum('amount'))['t'] or 0,
                'recovered': qs.filter(status='recovered').aggregate(t=Sum('amount'))['t'] or 0,
            }
        monthly_history.append(entry)

    # Recent resolutions
    recent_resolutions = (
        AlertResolution.objects
        .select_related('alert', 'alert__skyhook')
        .order_by('-resolved_at')[:20]
    )

    import json
    # Serialize chart data for JS
    pie_chart_data = {
        'labels': [],
        'data': [],
        'colors': [],
    }
    for reagent, d in month_data.items():
        if d['lost'] > 0:
            pie_chart_data['labels'].append(f"{reagent} (lost)")
            pie_chart_data['data'].append(d['lost'])
            pie_chart_data['colors'].append(d['lost_color'])
        if d['recovered'] > 0:
            pie_chart_data['labels'].append(f"{reagent} (rec.)")
            pie_chart_data['data'].append(d['recovered'])
            pie_chart_data['colors'].append(d['recovered_color'])

    bar_datasets = []
    for reagent in reagent_types:
        bar_datasets.append({
            'label': f"{reagent} lost",
            'data': [m['reagents'][reagent]['lost'] for m in monthly_history],
            'backgroundColor': reagent_lost_colors[reagent],
            'stack': 'lost',
        })
        bar_datasets.append({
            'label': f"{reagent} rec.",
            'data': [m['reagents'][reagent]['recovered'] for m in monthly_history],
            'backgroundColor': reagent_recovered_colors[reagent],
            'stack': 'recovered',
        })

    bar_labels = [m['label'] for m in monthly_history]

    context = {
        'month_lost': month_lost,
        'month_recovered': month_recovered,
        'month_false_alarms': month_false_alarms,
        'unresolved_count': unresolved_count,
        'reagent_types': reagent_types,
        'month_data': month_data,
        'recent_resolutions': recent_resolutions,
        'pie_chart_json': json.dumps(pie_chart_data),
        'bar_labels_json': json.dumps(bar_labels),
        'bar_datasets_json': json.dumps(bar_datasets),
    }
    return render(request, 'skyhooker/report.html', context)
