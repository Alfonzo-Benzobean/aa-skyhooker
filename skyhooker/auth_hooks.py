from django.utils.translation import gettext_lazy as _
from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook
from allianceauth.services.hooks import get_extension_logger

from . import urls
from .models import AlertLog

logger = get_extension_logger(__name__)


class SkyhookerMenuHook(MenuItemHook):
    def render(self, request):
        if request.user.has_perm("skyhooker.view_alertlog"):
            self.count = (
                AlertLog.objects.filter(
                    alert_type=AlertLog.ALERT_THEFT,
                    resolution__isnull=True,
                ).count() or None
            )
        return super().render(request)


@hooks.register("menu_item_hook")
def register_menu():
    return SkyhookerMenuHook(
        _("Skyhooker"),
        "fas fa-satellite fa-fw",
        "skyhooker:dashboard",
        order=1100,
        navactive=["skyhooker:"],
    )


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "skyhooker", r"^skyhooker/")
