from django.contrib import admin
from django.utils.html import format_html

from .models import AlertLog, AlertResolution, Skyhook, SkyhookCorporation, SkyhookSnapshot
from .tasks import poll_all_skyhooks


@admin.register(SkyhookCorporation)
class SkyhookCorporationAdmin(admin.ModelAdmin):
    list_display = [
        "corporation_name", "corporation_id",
        "token_character_name", "is_active", "last_updated"
    ]
    list_filter = ["is_active"]
    actions = ["trigger_poll"]

    @admin.action(description="Trigger ESI poll now")
    def trigger_poll(self, request, queryset):
        poll_all_skyhooks.delay()
        self.message_user(request, "Poll task queued.")


@admin.register(Skyhook)
class SkyhookAdmin(admin.ModelAdmin):
    list_display = [
        "structure_id", "corporation", "solar_system_name",
        "planet_name", "reagent_type_name", "current_state",
        "is_active", "vuln_start", "vuln_end", "last_polled"
    ]
    list_filter = ["is_active", "current_state", "corporation"]
    search_fields = ["solar_system_name", "planet_name", "structure_id"]
    readonly_fields = ["last_polled", "created_at"]


@admin.register(SkyhookSnapshot)
class SkyhookSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "skyhook", "polled_at", "state",
        "secured_stock", "unsecured_stock",
        "secured_delta", "unsecured_delta"
    ]
    list_filter = ["skyhook__corporation"]
    readonly_fields = [
        "skyhook", "polled_at", "state",
        "secured_stock", "unsecured_stock",
        "secured_delta", "unsecured_delta", "last_cycle"
    ]

    def has_add_permission(self, request):
        return False  # Snapshots are created by tasks only


@admin.register(AlertLog)
class AlertLogAdmin(admin.ModelAdmin):
    list_display = ["skyhook", "alert_type", "fired_at", "dedup_key"]
    list_filter = ["alert_type"]
    readonly_fields = ["skyhook", "alert_type", "fired_at", "message", "dedup_key"]

    def has_add_permission(self, request):
        return False



@admin.register(AlertResolution)
class AlertResolutionAdmin(admin.ModelAdmin):
    list_display = ["alert", "status", "amount", "resolved_by_name", "resolved_at"]
    list_filter = ["status"]
    ordering = ["-resolved_at"]
