from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from .models import UserProfile, UserRole


def get_user_role(user) -> str:
    if not user.is_authenticated:
        return UserRole.ADMIN
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile.role


def role_label(role: str) -> str:
    return dict(UserRole.choices).get(role, "Локальный режим")


def can_manage_references(user) -> bool:
    return get_user_role(user) == UserRole.ADMIN


def can_operate_stock(user) -> bool:
    return get_user_role(user) in {UserRole.ADMIN, UserRole.OPERATOR}


def can_reset_demo(user) -> bool:
    return get_user_role(user) == UserRole.ADMIN


def require_reference_manager(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not can_manage_references(request.user):
            raise PermissionDenied("Недостаточно прав для изменения справочников.")
        return view_func(request, *args, **kwargs)

    return wrapper


def require_stock_operator(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not can_operate_stock(request.user):
            raise PermissionDenied("Недостаточно прав для складских операций.")
        return view_func(request, *args, **kwargs)

    return wrapper


def require_demo_admin(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if not can_reset_demo(request.user):
            raise PermissionDenied("Недостаточно прав для перезагрузки демо-данных.")
        return view_func(request, *args, **kwargs)

    return wrapper
