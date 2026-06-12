from django.db import models
from django.utils import timezone


class SkyhookCorporation(models.Model):
    """
    A corporation whose skyhooks we are tracking.
    Linked to an ESI token character who has Director role.
    """
    corporation_id = models.IntegerField(unique=True)
    corporation_name = models.CharField(max_length=255, blank=True)
    token_character_id = models.IntegerField(
        help_text="Character ID of the Director whose ESI token is used for polling"
    )
    token_character_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tracked Corporation"
        verbose_name_plural = "Tracked Corporations"

    def __str__(self):
        return f"{self.corporation_name} ({self.corporation_id})"


class Skyhook(models.Model):
    """A single skyhook structure."""

    STATE_CHOICES = [
        ("Anchoring", "Anchoring"),
        ("Unanchoring", "Unanchoring"),
        ("ShieldVulnerable", "Shield Vulnerable"),
        ("PartiallyShieldVulnerable", "Partially Shield Vulnerable"),
        ("ShieldReinforced", "Shield Reinforced"),
        ("ArmorReinforced", "Armor Reinforced"),
        ("HullReinforced", "Hull Reinforced"),
        ("HullVulnerable", "Hull Vulnerable"),
        ("Online", "Online"),
        ("Unknown", "Unknown"),
    ]

    structure_id = models.BigIntegerField(unique=True)
    corporation = models.ForeignKey(
        SkyhookCorporation,
        on_delete=models.CASCADE,
        related_name="skyhooks",
    )
    planet_id = models.IntegerField()
    planet_name = models.CharField(max_length=255, blank=True)
    solar_system_id = models.IntegerField(null=True, blank=True)
    solar_system_name = models.CharField(max_length=255, blank=True)
    reagent_type_id = models.IntegerField(null=True, blank=True)
    reagent_type_name = models.CharField(max_length=255, blank=True)
    current_state = models.CharField(
        max_length=50, choices=STATE_CHOICES, default="Unknown"
    )
    is_active = models.BooleanField(default=True)
    # Vulnerability window (from last poll)
    vuln_start = models.DateTimeField(null=True, blank=True)
    vuln_end = models.DateTimeField(null=True, blank=True)
    # Alert sent flag - reset each cycle
    vuln_alert_sent = models.BooleanField(default=False)
    last_polled = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Skyhook"
        verbose_name_plural = "Skyhooks"
        ordering = ["solar_system_name", "planet_name"]
        permissions = [
            ("view_skyhook", "Can view skyhooks and dashboard"),
        ]

    def __str__(self):
        return (
            f"{self.solar_system_name} - {self.planet_name} "
            f"({self.structure_id})"
        )

    @property
    def is_vulnerable_now(self):
        now = timezone.now()
        if self.vuln_start and self.vuln_end:
            return self.vuln_start <= now <= self.vuln_end
        return False

    @property
    def latest_snapshot(self):
        return self.snapshots.order_by("-polled_at").first()


class SkyhookSnapshot(models.Model):
    """
    A point-in-time record of a skyhook's stock levels.
    Diffs between snapshots reveal theft or legitimate retrieval.
    """
    skyhook = models.ForeignKey(
        Skyhook,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    polled_at = models.DateTimeField(default=timezone.now, db_index=True)
    state = models.CharField(max_length=50, blank=True)
    secured_stock = models.BigIntegerField(default=0)
    unsecured_stock = models.BigIntegerField(default=0)
    last_cycle = models.DateTimeField(null=True, blank=True)

    # Derived fields — calculated on save
    secured_delta = models.BigIntegerField(
        null=True, blank=True,
        help_text="Change in secured stock vs previous snapshot (negative = retrieved)"
    )
    unsecured_delta = models.BigIntegerField(
        null=True, blank=True,
        help_text="Change in unsecured stock vs previous snapshot (negative = possible theft)"
    )

    class Meta:
        verbose_name = "Skyhook Snapshot"
        verbose_name_plural = "Skyhook Snapshots"
        ordering = ["-polled_at"]
        indexes = [
            models.Index(fields=["skyhook", "-polled_at"]),
        ]

    def __str__(self):
        return f"{self.skyhook} @ {self.polled_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        # Calculate deltas against previous snapshot before saving
        if not self.pk:
            prev = (
                SkyhookSnapshot.objects
                .filter(skyhook=self.skyhook)
                .order_by("-polled_at")
                .first()
            )
            if prev:
                self.secured_delta = self.secured_stock - prev.secured_stock
                self.unsecured_delta = self.unsecured_stock - prev.unsecured_stock
        super().save(*args, **kwargs)


class AlertLog(models.Model):
    """
    Tracks alerts that have been fired to avoid duplicate Discord pings.
    """
    ALERT_VULN_WINDOW = "vuln_window"
    ALERT_THEFT = "theft"
    ALERT_SECURED_DROP = "secured_drop"

    ALERT_TYPES = [
        (ALERT_VULN_WINDOW, "Vulnerability Window Approaching"),
        (ALERT_THEFT, "Possible Theft Detected"),
        (ALERT_SECURED_DROP, "Secured Stock Drop"),
    ]

    skyhook = models.ForeignKey(
        Skyhook,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    fired_at = models.DateTimeField(default=timezone.now)
    message = models.TextField(blank=True)
    # Dedup key — e.g. vuln window start time as string
    dedup_key = models.CharField(max_length=100, blank=True, db_index=True)
    discord_message_id = models.CharField(max_length=64, blank=True, db_index=True)
    amount_delta = models.BigIntegerField(null=True, blank=True, help_text="Units dropped at time of alert")

    class Meta:
        verbose_name = "Alert Log"
        verbose_name_plural = "Alert Logs"
        ordering = ["-fired_at"]
        permissions = [
            ("view_alertlog", "Can view and resolve theft alerts"),
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()} — {self.skyhook} @ {self.fired_at:%Y-%m-%d %H:%M}"


class AlertResolution(models.Model):
    """
    Resolution record for a theft alert — classified by a corp member via Discord reaction.
    """
    STATUS_THEFT = "theft"
    STATUS_RECOVERED = "recovered"
    STATUS_FALSE_ALARM = "false_alarm"

    STATUS_CHOICES = [
        (STATUS_THEFT, "Confirmed Theft"),
        (STATUS_RECOVERED, "Recovered"),
        (STATUS_FALSE_ALARM, "False Alarm"),
    ]

    alert = models.OneToOneField(
        AlertLog,
        on_delete=models.CASCADE,
        related_name="resolution",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    amount = models.BigIntegerField(
        help_text="Units lost or recovered (from the alert delta)"
    )
    resolved_by_discord_id = models.CharField(max_length=64, blank=True)
    resolved_by_name = models.CharField(max_length=255, blank=True)
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alert Resolution"
        verbose_name_plural = "Alert Resolutions"
        ordering = ["-resolved_at"]

    def __str__(self):
        return f"{self.get_status_display()} — {self.alert}"


class SkyhookerConfiguration(models.Model):
    """
    Singleton configuration model. Edit via Django Admin under Skyhooker > Configuration.
    """
    discord_webhook = models.URLField(
        blank=True,
        verbose_name="Discord Webhook URL",
        help_text="Discord webhook URL for alert notifications. Leave blank to disable Discord alerts.",
    )

    class Meta:
        verbose_name = "Configuration"
        verbose_name_plural = "Configuration"

    def __str__(self):
        return "Skyhooker Configuration"
