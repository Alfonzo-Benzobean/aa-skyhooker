from django import template
from django.utils import timezone
import pytz

register = template.Library()

@register.filter
def localtime_for_user(value, user):
    """
    Convert a UTC datetime to the user's configured timezone.
    Usage: {{ some_datetime|localtime_for_user:request.user }}
    """
    if not value:
        return value
    try:
        tz_name = user.profile.timezone
        if tz_name:
            tz = pytz.timezone(str(tz_name))
            return value.astimezone(tz)
    except Exception:
        pass
    return value
