from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("skyhooker", "0003_alertlog_amount_delta_alertlog_discord_message_id_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SkyhookerConfiguration",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "discord_webhook",
                    models.URLField(
                        blank=True,
                        help_text="Discord webhook URL for alert notifications. Leave blank to disable Discord alerts.",
                        verbose_name="Discord Webhook URL",
                    ),
                ),
            ],
            options={
                "verbose_name": "Configuration",
                "verbose_name_plural": "Configuration",
            },
        ),
    ]
