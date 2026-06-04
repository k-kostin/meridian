from django.conf import settings

from .demo import has_business_data
from .permissions import can_manage_references, can_operate_stock, can_reset_demo, get_user_role, role_label
from .version import APP_VERSION_LABEL


def app_context(request):
    role = get_user_role(request.user)
    role_display = role_label(role) if request.user.is_authenticated else "Локальный режим"
    return {
        "app_demo_mode": settings.DEMO_MODE,
        "app_has_core_data": has_business_data() if settings.DEMO_MODE else False,
        "app_version_label": APP_VERSION_LABEL,
        "app_user_role": role,
        "app_user_role_label": role_display,
        "app_can_manage_references": can_manage_references(request.user),
        "app_can_operate_stock": can_operate_stock(request.user),
        "app_can_reset_demo": can_reset_demo(request.user),
    }
