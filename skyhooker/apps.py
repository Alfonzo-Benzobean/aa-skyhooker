from django.apps import AppConfig


class SkyhookerConfig(AppConfig):
    name = "skyhooker"
    label = "skyhooker"
    verbose_name = "Skyhooker"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        import skyhooker.signals  # noqa: F401
