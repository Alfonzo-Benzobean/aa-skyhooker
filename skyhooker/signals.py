"""
Alliance Auth menu integration.
Adds Skyhooker to the AA navigation menu.
"""
from django.utils.translation import gettext_lazy as _

try:
    from allianceauth import hooks
    from allianceauth.services.hooks import MenuItemHook, UrlHook

    class SkyhookerMenuItem(MenuItemHook):
        def __init__(self):
            super().__init__(
                _("Skyhooker"),
                "fas fa-satellite",  # Font Awesome icon
                "skyhooker:dashboard",
                navactive=["skyhooker:"],
            )

        def render(self, request):
            if request.user.has_perm("skyhooker.view_skyhook"):
                return super().render(request)
            return ""

    @hooks.register("menu_item_hook")
    def register_menu():
        return SkyhookerMenuItem()

    @hooks.register("url_hook")
    def register_urls():
        return UrlHook("skyhooker.urls", "skyhooker", r"^skyhooker/", excluded_views=["skyhooker.views.api_resolve_alert"])

except ImportError:
    # allianceauth not available (e.g. during testing)
    pass
