from django.conf import settings

from .demo import has_business_data


def app_context(_request):
    return {
        "app_demo_mode": settings.DEMO_MODE,
        "app_has_core_data": has_business_data() if settings.DEMO_MODE else False,
    }
