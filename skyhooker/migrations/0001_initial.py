from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SkyhookCorporation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("corporation_id", models.IntegerField(unique=True)),
                ("corporation_name", models.CharField(blank=True, max_length=255)),
                ("token_character_id", models.IntegerField(
                    help_text="Character ID of the Director whose ESI token is used for polling"
                )),
                ("token_character_name", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("last_updated", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Tracked Corporation", "verbose_name_plural": "Tracked Corporations"},
        ),
        migrations.CreateModel(
            name="Skyhook",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("structure_id", models.BigIntegerField(unique=True)),
                ("corporation", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="skyhooks",
                    to="skyhooker.skyhookcorporation",
                )),
                ("planet_id", models.IntegerField()),
                ("planet_name", models.CharField(blank=True, max_length=255)),
                ("solar_system_id", models.IntegerField(blank=True, null=True)),
                ("solar_system_name", models.CharField(blank=True, max_length=255)),
                ("reagent_type_id", models.IntegerField(blank=True, null=True)),
                ("reagent_type_name", models.CharField(blank=True, max_length=255)),
                ("current_state", models.CharField(default="Unknown", max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("vuln_start", models.DateTimeField(blank=True, null=True)),
                ("vuln_end", models.DateTimeField(blank=True, null=True)),
                ("vuln_alert_sent", models.BooleanField(default=False)),
                ("last_polled", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Skyhook",
                "verbose_name_plural": "Skyhooks",
                "ordering": ["solar_system_name", "planet_name"],
            },
        ),
        migrations.CreateModel(
            name="SkyhookSnapshot",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("skyhook", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="snapshots",
                    to="skyhooker.skyhook",
                )),
                ("polled_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("state", models.CharField(blank=True, max_length=50)),
                ("secured_stock", models.BigIntegerField(default=0)),
                ("unsecured_stock", models.BigIntegerField(default=0)),
                ("last_cycle", models.DateTimeField(blank=True, null=True)),
                ("secured_delta", models.BigIntegerField(blank=True, null=True)),
                ("unsecured_delta", models.BigIntegerField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Skyhook Snapshot",
                "verbose_name_plural": "Skyhook Snapshots",
                "ordering": ["-polled_at"],
            },
        ),
        migrations.AddIndex(
            model_name="skyhooksnapshot",
            index=models.Index(fields=["skyhook", "-polled_at"], name="skyhooker_snap_idx"),
        ),
        migrations.CreateModel(
            name="AlertLog",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("skyhook", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="alerts",
                    to="skyhooker.skyhook",
                )),
                ("alert_type", models.CharField(max_length=30, choices=[
                    ("vuln_window", "Vulnerability Window Approaching"),
                    ("theft", "Possible Theft Detected"),
                    ("secured_drop", "Secured Stock Drop"),
                ])),
                ("fired_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("message", models.TextField(blank=True)),
                ("dedup_key", models.CharField(blank=True, db_index=True, max_length=100)),
            ],
            options={
                "verbose_name": "Alert Log",
                "verbose_name_plural": "Alert Logs",
                "ordering": ["-fired_at"],
            },
        ),
    ]
