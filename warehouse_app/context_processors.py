from django.conf import settings

from .demo import has_business_data
from .version import APP_VERSION_LABEL


def app_context(_request):
    return {
        "app_demo_mode": settings.DEMO_MODE,
        "app_has_core_data": has_business_data() if settings.DEMO_MODE else False,
        "app_version_label": APP_VERSION_LABEL,
    }
