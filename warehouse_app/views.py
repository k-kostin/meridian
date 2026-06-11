from datetime import date
import logging
import os
from pathlib import Path
import threading
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .activity import (
    get_document_timeline,
    get_inventory_timeline,
    record_demo_data_reset,
    record_item_import_committed,
    record_manual_backup_created,
    record_opening_inventory_import_committed,
    record_reference_record_changed,
)
from .backups import BackupError, configured_backup_paths, create_local_backup
from .forms import (
    InventoryDocumentForm,
    InventoryLineFormSet,
    ItemCategoryForm,
    ItemForm,
    ItemImportPreviewForm,
    OpeningInventoryImportForm,
    StockDocumentForm,
    StockLineFormSet,
    UnitForm,
    WarehouseForm,
)
from .imports import (
    ItemImportResult,
    OpeningInventoryImportResult,
    commit_items_import,
    commit_opening_inventory_import,
    parse_items_import_workbook,
    parse_opening_inventory_import_workbook,
    validate_items_import_result,
    validate_opening_inventory_import_result,
)
from .demo import has_business_data, seed_demo_data
from .models import (
    BackupRecord,
    DocumentStatus,
    InventoryDocument,
    InventoryLine,
    InventoryScope,
    Item,
    ItemCategory,
    SavedViewScope,
    StockDocument,
    StockDocumentLine,
    StockDocumentType,
    Unit,
    UserSavedView,
    Warehouse,
)
from .permissions import (
    can_manage_references,
    require_backup_manager,
    require_demo_admin,
    require_reference_manager,
    require_stock_operator,
)
from .services import (
    PRESENTATION_BY_WAREHOUSE,
    PRESENTATION_CONSOLIDATED,
    _month_end,
    _month_start,
    WorkbookExport,
    build_daily_ledger,
    build_monthly_ledger,
    build_period_report,
    export_balances_xlsx,
    export_daily_ledger_xlsx,
    export_inventories_xlsx,
    export_items_xlsx,
    export_monthly_ledger_xlsx,
    export_movements_xlsx,
    export_period_analysis_xlsx,
    filter_balance_rows,
    get_balance_rows,
    normalize_presentation,
    resolve_period,
)


PERIOD_MODE_LABELS = {
    "day": "День",
    "month": "Месяц",
    "year": "Год",
    "custom": "Период",
}
logger = logging.getLogger(__name__)
PAGE_SIZE_OPTIONS = (10, 25, 50, 100)
DOCUMENT_PRESETS = {
    "drafts": {"status": DocumentStatus.DRAFT},
    "posted": {"status": DocumentStatus.POSTED},
    "receipts": {"document_type": StockDocumentType.RECEIPT},
    "issues": {"document_type": StockDocumentType.ISSUE},
    "transfers": {"document_type": StockDocumentType.TRANSFER},
}
BALANCE_PRESETS = {
    "by_warehouse": {"presentation": PRESENTATION_BY_WAREHOUSE},
    "consolidated": {"presentation": PRESENTATION_CONSOLIDATED},
    "with_zero": {"include_zero": "1"},
    "nonzero": {"include_zero": ""},
}
SAVED_VIEW_LIST_ROUTES = {
    SavedViewScope.DOCUMENTS: "document_list",
    SavedViewScope.BALANCES: "balance_report",
}
SAVED_VIEW_ALLOWED_KEYS = {
    SavedViewScope.DOCUMENTS: {"q", "warehouse", "document_type", "status", "date_from", "date_to", "preset", "category"},
    SavedViewScope.BALANCES: {"q", "warehouse", "presentation", "include_zero", "preset", "category"},
}


def _preset_value(request: HttpRequest, key: str, preset_filters: dict[str, str]) -> str:
    if key in request.GET:
        return request.GET.get(key, "")
    return preset_filters.get(key, "")


def _document_preset_filters(request: HttpRequest) -> tuple[str, dict[str, str]]:
    preset = request.GET.get("preset", "")
    return preset, DOCUMENT_PRESETS.get(preset, {})


def _balance_preset_filters(request: HttpRequest) -> tuple[str, dict[str, str]]:
    preset = request.GET.get("preset", "")
    return preset, BALANCE_PRESETS.get(preset, {})


def _saved_views_for_user(request: HttpRequest, scope: str):
    if not request.user.is_authenticated:
        return []
    return UserSavedView.objects.filter(user=request.user, scope=scope)


def authenticated_actor(request: HttpRequest):
    return request.user if request.user.is_authenticated else None


def _get_clean_id(request: HttpRequest, key: str) -> str | None:
    value = request.GET.get(key)
    return value if value and value.isdigit() else None


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def _schedule_process_exit(delay_seconds: float = 0.2) -> None:
    timer = threading.Timer(delay_seconds, lambda: os._exit(0))
    timer.daemon = True
    timer.start()


@csrf_exempt
@require_POST
def shutdown(request: HttpRequest) -> JsonResponse:
    if not getattr(settings, "DESKTOP_SHUTDOWN_ENABLED", False):
        raise Http404("Not found.")
    expected_token = getattr(settings, "DESKTOP_SHUTDOWN_TOKEN", "")
    if not expected_token or request.headers.get("X-Warehouse-Shutdown-Token") != expected_token:
        raise PermissionDenied("Invalid shutdown token.")
    _schedule_process_exit()
    return JsonResponse({"status": "shutting_down"})


def _get_page_size(request: HttpRequest, default: int = 25) -> int:
    try:
        page_size = int(request.GET.get("page_size", default))
    except (TypeError, ValueError):
        return default
    return page_size if page_size in PAGE_SIZE_OPTIONS else default


def _pagination_query(request: HttpRequest) -> str:
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def _paginate_collection(collection, request: HttpRequest, default: int = 25):
    page_size = _get_page_size(request, default=default)
    page_obj = Paginator(collection, page_size).get_page(request.GET.get("page"))
    return page_obj, page_size, _pagination_query(request)


def _workbook_response(export_payload: WorkbookExport) -> HttpResponse:
    response = HttpResponse(
        export_payload.buffer.getvalue(),
        content_type=export_payload.content_type,
    )
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True,
        filename=export_payload.filename,
    )
    return response


def _query_string_for_keys(request: HttpRequest, *keys: str) -> str:
    params = []
    for key in keys:
        value = request.GET.get(key)
        if value not in ("", None):
            params.append((key, value))
    return urlencode(params)


def _query_string_for_keys_preserve_empty(request: HttpRequest, *keys: str) -> str:
    params = []
    for key in keys:
        if key in request.GET:
            params.append((key, request.GET.get(key, "")))
    return urlencode(params)


def _encode_query_params(**params: object) -> str:
    encoded = []
    for key, value in params.items():
        if value not in ("", None):
            encoded.append((key, value))
    return urlencode(encoded)


def _shift_month(value: date, delta: int) -> date:
    month_index = value.month - 1 + delta
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    last_day = _month_end(date(year, month, 1)).day
    return date(year, month, min(value.day, last_day))


def dashboard(request: HttpRequest) -> HttpResponse:
    balances = get_balance_rows()[:12]
    has_posted_activity = StockDocument.objects.filter(status=DocumentStatus.POSTED).exists() or InventoryDocument.objects.filter(
        status=DocumentStatus.POSTED
    ).exists()
    context = {
        "items_count": Item.objects.count(),
        "warehouses_count": Warehouse.objects.count(),
        "draft_documents_count": StockDocument.objects.filter(status=DocumentStatus.DRAFT).count(),
        "draft_inventories_count": InventoryDocument.objects.filter(status=DocumentStatus.DRAFT).count(),
        "balances": balances,
        "recent_documents": StockDocument.objects.select_related("warehouse").order_by("-created_at")[:6],
        "setup_ready": Unit.objects.exists() and Warehouse.objects.exists() and Item.objects.exists(),
        "has_posted_activity": has_posted_activity,
    }
    return render(request, "warehouse_app/dashboard.html", context)


def setup_view(request: HttpRequest) -> HttpResponse:
    context = {
        "units_count": Unit.objects.count(),
        "warehouses_count": Warehouse.objects.count(),
        "items_count": Item.objects.count(),
        "opening_hint_ready": Unit.objects.exists() and Warehouse.objects.exists() and Item.objects.exists(),
    }
    return render(request, "warehouse_app/setup.html", context)


def unit_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    units = Unit.objects.order_by("name", "code")
    if query:
        units = units.filter(Q(code__icontains=query) | Q(name__icontains=query))
    page_obj, page_size, pagination_query = _paginate_collection(units, request)

    form = UnitForm(request.POST or None)
    if request.method == "POST" and not can_manage_references(request.user):
        raise PermissionDenied("Недостаточно прав для изменения справочников.")
    if request.method == "POST" and form.is_valid():
        unit = form.save()
        record_reference_record_changed(instance=unit, action="created", actor=authenticated_actor(request))
        messages.success(request, "Единица измерения добавлена.")
        return redirect("unit_list")
    return render(
        request,
        "warehouse_app/unit_list.html",
        {
            "form": form,
            "units": page_obj,
            "page_obj": page_obj,
            "page_size": page_size,
            "page_size_options": PAGE_SIZE_OPTIONS,
            "pagination_query": pagination_query,
            "query": query,
        },
    )


@require_reference_manager
def unit_update(request: HttpRequest, pk: int) -> HttpResponse:
    unit = get_object_or_404(Unit, pk=pk)
    form = UnitForm(request.POST or None, instance=unit)
    if request.method == "POST" and form.is_valid():
        unit = form.save()
        record_reference_record_changed(instance=unit, action="updated", actor=authenticated_actor(request))
        messages.success(request, "Единица измерения обновлена.")
        return redirect("unit_list")
    return render(
        request,
        "warehouse_app/simple_form.html",
        {"form": form, "title": "Редактирование единицы", "back_url": reverse("unit_list")},
    )


def warehouse_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    warehouses = Warehouse.objects.order_by("name", "code")
    if query:
        warehouses = warehouses.filter(Q(code__icontains=query) | Q(name__icontains=query))
    page_obj, page_size, pagination_query = _paginate_collection(warehouses, request)

    form = WarehouseForm(request.POST or None)
    if request.method == "POST" and not can_manage_references(request.user):
        raise PermissionDenied("Недостаточно прав для изменения справочников.")
    if request.method == "POST" and form.is_valid():
        warehouse = form.save()
        record_reference_record_changed(instance=warehouse, action="created", actor=authenticated_actor(request))
        messages.success(request, "Склад добавлен.")
        return redirect("warehouse_list")
    return render(
        request,
        "warehouse_app/warehouse_list.html",
        {
            "form": form,
            "warehouses": page_obj,
            "page_obj": page_obj,
            "page_size": page_size,
            "page_size_options": PAGE_SIZE_OPTIONS,
            "pagination_query": pagination_query,
            "query": query,
        },
    )


@require_reference_manager
def warehouse_update(request: HttpRequest, pk: int) -> HttpResponse:
    warehouse = get_object_or_404(Warehouse, pk=pk)
    form = WarehouseForm(request.POST or None, instance=warehouse)
    if request.method == "POST" and form.is_valid():
        warehouse = form.save()
        record_reference_record_changed(instance=warehouse, action="updated", actor=authenticated_actor(request))
        messages.success(request, "Склад обновлен.")
        return redirect("warehouse_list")
    return render(
        request,
        "warehouse_app/simple_form.html",
        {"form": form, "title": "Редактирование склада", "back_url": reverse("warehouse_list")},
    )


def category_list(request: HttpRequest) -> HttpResponse:
    form = ItemCategoryForm(request.POST or None)
    if request.method == "POST" and not can_manage_references(request.user):
        raise PermissionDenied("Недостаточно прав для изменения справочников.")
    if request.method == "POST" and form.is_valid():
        category = form.save()
        record_reference_record_changed(instance=category, action="created", actor=authenticated_actor(request))
        messages.success(request, "Категория добавлена.")
        return redirect("category_list")
    categories = ItemCategory.objects.annotate(items_count=Count("items", distinct=True)).order_by("name", "code")
    return render(
        request,
        "warehouse_app/category_list.html",
        {"form": form, "categories": categories},
    )


@require_reference_manager
def category_update(request: HttpRequest, pk: int) -> HttpResponse:
    category = get_object_or_404(ItemCategory, pk=pk)
    form = ItemCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        record_reference_record_changed(instance=category, action="updated", actor=authenticated_actor(request))
        messages.success(request, "Категория обновлена.")
        return redirect("category_list")
    return render(
        request,
        "warehouse_app/simple_form.html",
        {"form": form, "title": "Редактирование категории", "back_url": reverse("category_list")},
    )


def item_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    category_id = _get_clean_id(request, "category")
    items = Item.objects.select_related("unit", "category").order_by("name", "sku")
    if query:
        items = items.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    if category_id:
        items = items.filter(category_id=category_id)
    page_obj, page_size, pagination_query = _paginate_collection(items, request)

    form = ItemForm(request.POST or None)
    if request.method == "POST" and not can_manage_references(request.user):
        raise PermissionDenied("Недостаточно прав для изменения справочников.")
    if request.method == "POST" and form.is_valid():
        item = form.save()
        record_reference_record_changed(instance=item, action="created", actor=authenticated_actor(request))
        messages.success(request, "Номенклатура добавлена.")
        return redirect("item_list")

    return render(
        request,
        "warehouse_app/item_list.html",
        {
            "form": form,
            "items": page_obj,
            "page_obj": page_obj,
            "page_size": page_size,
            "page_size_options": PAGE_SIZE_OPTIONS,
            "pagination_query": pagination_query,
            "query": query,
            "categories": ItemCategory.objects.filter(is_active=True).order_by("name", "code"),
            "selected_category": category_id or "",
        },
    )


@require_reference_manager
def item_import_preview(request: HttpRequest) -> HttpResponse:
    form = ItemImportPreviewForm(request.POST or None, request.FILES or None)
    result = None
    has_preview = False
    validation_errors = []
    action = request.POST.get("action", "preview")

    if request.method == "POST" and form.is_valid():
        try:
            parsed_result = parse_items_import_workbook(form.cleaned_data["workbook"])
            import_mode = form.cleaned_data["import_mode"]
            auto_create_units = form.cleaned_data.get("auto_create_units", False)
            if action == "commit":
                commit_result = commit_items_import(
                    parsed_result,
                    import_mode=import_mode,
                    auto_create_units=auto_create_units,
                )
                result = ItemImportResult(rows=parsed_result.rows, errors=commit_result.errors)
                if not commit_result.errors:
                    record_item_import_committed(
                        created_count=commit_result.created_count,
                        updated_count=commit_result.updated_count,
                        import_mode=import_mode,
                        auto_create_units=auto_create_units,
                        actor=authenticated_actor(request),
                    )
                    if commit_result.created_count:
                        messages.success(request, f"Импортировано позиций: {commit_result.created_count}.")
                    if commit_result.updated_count:
                        messages.success(request, f"Импорт обновил позиций: {commit_result.updated_count}.")
                    return redirect("item_list")
            else:
                validation_errors = validate_items_import_result(
                    parsed_result,
                    import_mode=import_mode,
                    auto_create_units=auto_create_units,
                )
                result = ItemImportResult(rows=parsed_result.rows, errors=validation_errors)
            has_preview = True
        except Exception:
            form.add_error(None, "Не удалось прочитать Excel-файл. Проверьте формат .xlsx.")

    return render(
        request,
        "warehouse_app/item_import_preview.html",
        {
            "form": form,
            "result": result,
            "has_preview": has_preview,
            "can_commit": bool(result and result.rows and not result.errors),
        },
    )


@require_reference_manager
def item_update(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Item, pk=pk)
    form = ItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        record_reference_record_changed(instance=item, action="updated", actor=authenticated_actor(request))
        messages.success(request, "Позиция обновлена.")
        return redirect("item_list")
    return render(
        request,
        "warehouse_app/simple_form.html",
        {"form": form, "title": "Редактирование номенклатуры", "back_url": reverse("item_list")},
    )


@require_POST
def saved_view_create(request: HttpRequest, scope: str) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("login")
    if scope not in SAVED_VIEW_LIST_ROUTES:
        raise PermissionDenied("Unknown saved view scope.")

    redirect_route = SAVED_VIEW_LIST_ROUTES[scope]
    name = request.POST.get("name", "").strip()[:80]
    if not name:
        messages.error(request, "Укажите название представления.")
        return redirect(redirect_route)

    allowed_keys = SAVED_VIEW_ALLOWED_KEYS[scope]
    query_params = {
        key: request.POST.get(key, "")
        for key in allowed_keys
        if key in request.POST
    }
    UserSavedView.objects.update_or_create(
        user=request.user,
        scope=scope,
        name=name,
        defaults={"query_params": query_params},
    )
    messages.success(request, "Представление сохранено.")
    return redirect(redirect_route)


@require_POST
def saved_view_delete(request: HttpRequest, pk: int) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("login")
    saved_view = get_object_or_404(UserSavedView, pk=pk, user=request.user)
    redirect_route = SAVED_VIEW_LIST_ROUTES.get(saved_view.scope, "dashboard")
    saved_view.delete()
    messages.success(request, "Представление удалено.")
    return redirect(redirect_route)


def document_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse")
    preset, preset_filters = _document_preset_filters(request)
    document_type = _preset_value(request, "document_type", preset_filters)
    status = _preset_value(request, "status", preset_filters)
    date_from = parse_date(request.GET.get("date_from", "")) if request.GET.get("date_from") else None
    date_to = parse_date(request.GET.get("date_to", "")) if request.GET.get("date_to") else None
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    documents = StockDocument.objects.select_related("warehouse", "destination_warehouse").annotate(lines_count=Count("lines", distinct=True))
    if query:
        documents = documents.filter(
            Q(number__icontains=query)
            | Q(comment__icontains=query)
            | Q(warehouse__name__icontains=query)
            | Q(warehouse__code__icontains=query)
            | Q(destination_warehouse__name__icontains=query)
            | Q(destination_warehouse__code__icontains=query)
            | Q(lines__item__name__icontains=query)
            | Q(lines__item__sku__icontains=query)
        ).distinct()
    if warehouse_id:
        documents = documents.filter(Q(warehouse_id=warehouse_id) | Q(destination_warehouse_id=warehouse_id))
    if document_type:
        documents = documents.filter(document_type=document_type)
    if status:
        documents = documents.filter(status=status)
    if date_from:
        documents = documents.filter(operation_date__gte=date_from)
    if date_to:
        documents = documents.filter(operation_date__lte=date_to)

    page_obj, page_size, pagination_query = _paginate_collection(
        documents.order_by("-operation_date", "-created_at"),
        request,
    )

    context = {
        "documents": page_obj,
        "page_obj": page_obj,
        "page_size": page_size,
        "page_size_options": PAGE_SIZE_OPTIONS,
        "pagination_query": pagination_query,
        "query": query,
        "warehouses": Warehouse.objects.order_by("name"),
        "selected_warehouse": warehouse_id or "",
        "selected_type": document_type or "",
        "selected_status": status or "",
        "selected_preset": preset if preset in DOCUMENT_PRESETS else "",
        "selected_date_from": date_from.isoformat() if date_from else "",
        "selected_date_to": date_to.isoformat() if date_to else "",
        "movements_query_string": _query_string_for_keys_preserve_empty(
            request,
            "preset",
            "warehouse",
            "document_type",
            "status",
            "date_from",
            "date_to",
        ),
        "document_types": StockDocumentType.choices,
        "statuses": DocumentStatus.choices,
        "saved_views": _saved_views_for_user(request, SavedViewScope.DOCUMENTS),
    }
    return render(request, "warehouse_app/document_list.html", context)


@require_stock_operator
def document_create(request: HttpRequest) -> HttpResponse:
    initial = {}
    requested_type = request.GET.get("type")
    if requested_type in {choice[0] for choice in StockDocumentType.choices}:
        initial["document_type"] = requested_type

    if request.method == "POST":
        form = StockDocumentForm(request.POST, initial=initial)
        formset = StockLineFormSet(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                document = form.save(commit=False)
                actor = authenticated_actor(request)
                if actor:
                    document.created_by = actor
                    document.updated_by = actor
                document.save()
                _save_stock_lines(document, formset)
            messages.success(request, "Документ сохранен как черновик.")
            return redirect("document_detail", pk=document.pk)
    else:
        form = StockDocumentForm(initial=initial)
        formset = StockLineFormSet(prefix="lines")

    return render(
        request,
        "warehouse_app/document_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Новый документ движения",
            "back_url": reverse("document_list"),
        },
    )


@require_stock_operator
def document_update(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(StockDocument.objects.prefetch_related("lines__item"), pk=pk)
    if document.status != DocumentStatus.DRAFT:
        messages.error(request, "Редактировать можно только черновик.")
        return redirect("document_detail", pk=document.pk)

    if request.method == "POST":
        form = StockDocumentForm(request.POST, instance=document)
        formset = StockLineFormSet(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                document = form.save(commit=False)
                actor = authenticated_actor(request)
                if actor:
                    document.updated_by = actor
                document.save()
                document.lines.all().delete()
                _save_stock_lines(document, formset)
            messages.success(request, "Черновик документа обновлен.")
            return redirect("document_detail", pk=document.pk)
    else:
        form = StockDocumentForm(instance=document)
        formset = StockLineFormSet(initial=_stock_formset_initial(document), prefix="lines")

    return render(
        request,
        "warehouse_app/document_form.html",
        {
            "form": form,
            "formset": formset,
            "title": f"Редактирование {document.number}",
            "back_url": reverse("document_detail", kwargs={"pk": document.pk}),
        },
    )


def document_detail(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(
        StockDocument.objects.select_related(
            "warehouse",
            "destination_warehouse",
            "source_inventory",
            "created_by",
            "updated_by",
            "posted_by",
        ).prefetch_related("lines__item__unit"),
        pk=pk,
    )
    return render(
        request,
        "warehouse_app/document_detail.html",
        {
            "document": document,
            "timeline_events": get_document_timeline(document),
        },
    )


@require_POST
@require_stock_operator
def document_post(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(StockDocument, pk=pk)
    try:
        document.post(posted_by=authenticated_actor(request))
        messages.success(request, "Документ проведен.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("document_detail", pk=document.pk)


def inventory_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse")
    status = request.GET.get("status")
    inventories = InventoryDocument.objects.select_related("warehouse").annotate(lines_count=Count("lines", distinct=True))
    if query:
        inventories = inventories.filter(
            Q(number__icontains=query)
            | Q(comment__icontains=query)
            | Q(warehouse__name__icontains=query)
            | Q(warehouse__code__icontains=query)
            | Q(lines__item__name__icontains=query)
            | Q(lines__item__sku__icontains=query)
        ).distinct()
    if warehouse_id:
        inventories = inventories.filter(warehouse_id=warehouse_id)
    if status:
        inventories = inventories.filter(status=status)
    page_obj, page_size, pagination_query = _paginate_collection(
        inventories.order_by("-inventory_date", "-created_at"),
        request,
    )
    context = {
        "inventories": page_obj,
        "page_obj": page_obj,
        "page_size": page_size,
        "page_size_options": PAGE_SIZE_OPTIONS,
        "pagination_query": pagination_query,
        "query": query,
        "warehouses": Warehouse.objects.order_by("name"),
        "selected_warehouse": warehouse_id or "",
        "selected_status": status or "",
        "statuses": DocumentStatus.choices,
    }
    return render(request, "warehouse_app/inventory_list.html", context)


@require_stock_operator
def opening_inventory_import_preview(request: HttpRequest) -> HttpResponse:
    form = OpeningInventoryImportForm(request.POST or None, request.FILES or None)
    result = None
    has_preview = False
    action = request.POST.get("action", "preview")

    if request.method == "POST" and form.is_valid():
        try:
            parsed_result = parse_opening_inventory_import_workbook(form.cleaned_data["workbook"])
            if action == "commit":
                commit_result = commit_opening_inventory_import(parsed_result)
                result = OpeningInventoryImportResult(rows=parsed_result.rows, errors=commit_result.errors)
                if commit_result.inventory and not commit_result.errors:
                    record_opening_inventory_import_committed(
                        inventory=commit_result.inventory,
                        created_lines_count=commit_result.created_lines_count,
                        actor=authenticated_actor(request),
                    )
                    messages.success(
                        request,
                        f"Создан черновик инвентаризации {commit_result.inventory.number}. "
                        f"Строк: {commit_result.created_lines_count}.",
                    )
                    return redirect("inventory_detail", pk=commit_result.inventory.pk)
            else:
                validation_errors = validate_opening_inventory_import_result(parsed_result)
                result = OpeningInventoryImportResult(rows=parsed_result.rows, errors=validation_errors)
            has_preview = True
        except Exception:
            form.add_error(None, "Не удалось прочитать Excel-файл. Проверьте формат .xlsx.")

    return render(
        request,
        "warehouse_app/opening_inventory_import_preview.html",
        {
            "form": form,
            "result": result,
            "has_preview": has_preview,
            "can_commit": bool(result and result.rows and not result.errors),
        },
    )


@require_stock_operator
def inventory_create(request: HttpRequest) -> HttpResponse:
    opening_mode = request.GET.get("opening") == "1"
    initial = {}
    if opening_mode:
        initial["scope"] = InventoryScope.FULL
        initial["comment"] = "Первичная фиксация остатков"

    if request.method == "POST":
        form = InventoryDocumentForm(request.POST, initial=initial)
        formset = InventoryLineFormSet(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                inventory = form.save(commit=False)
                actor = authenticated_actor(request)
                if actor:
                    inventory.created_by = actor
                    inventory.updated_by = actor
                inventory.save()
                _save_inventory_lines(inventory, formset)
            messages.success(request, "Инвентаризация сохранена как черновик.")
            return redirect("inventory_detail", pk=inventory.pk)
    else:
        form = InventoryDocumentForm(initial=initial)
        formset = InventoryLineFormSet(prefix="lines")

    return render(
        request,
        "warehouse_app/inventory_form.html",
        {
            "form": form,
            "formset": formset,
            "title": "Новая инвентаризация",
            "opening_mode": opening_mode,
            "back_url": reverse("inventory_list"),
        },
    )


@require_stock_operator
def inventory_update(request: HttpRequest, pk: int) -> HttpResponse:
    inventory = get_object_or_404(InventoryDocument.objects.prefetch_related("lines__item"), pk=pk)
    if inventory.status != DocumentStatus.DRAFT:
        messages.error(request, "Редактировать можно только черновик.")
        return redirect("inventory_detail", pk=inventory.pk)

    opening_mode = False
    if request.method == "POST":
        form = InventoryDocumentForm(request.POST, instance=inventory)
        formset = InventoryLineFormSet(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                inventory = form.save(commit=False)
                actor = authenticated_actor(request)
                if actor:
                    inventory.updated_by = actor
                inventory.save()
                inventory.lines.all().delete()
                _save_inventory_lines(inventory, formset)
            messages.success(request, "Черновик инвентаризации обновлен.")
            return redirect("inventory_detail", pk=inventory.pk)
    else:
        form = InventoryDocumentForm(instance=inventory)
        formset = InventoryLineFormSet(initial=_inventory_formset_initial(inventory), prefix="lines")

    return render(
        request,
        "warehouse_app/inventory_form.html",
        {
            "form": form,
            "formset": formset,
            "title": f"Редактирование {inventory.number}",
            "opening_mode": opening_mode,
            "back_url": reverse("inventory_detail", kwargs={"pk": inventory.pk}),
        },
    )


def inventory_detail(request: HttpRequest, pk: int) -> HttpResponse:
    inventory = get_object_or_404(
        InventoryDocument.objects.select_related(
            "warehouse",
            "created_by",
            "updated_by",
            "posted_by",
        ).prefetch_related("lines__item__unit", "generated_documents"),
        pk=pk,
    )
    adjustment = inventory.generated_documents.order_by("id").first()
    return render(
        request,
        "warehouse_app/inventory_detail.html",
        {
            "inventory": inventory,
            "adjustment": adjustment,
            "timeline_events": get_inventory_timeline(inventory),
        },
    )


@require_POST
@require_stock_operator
def inventory_post(request: HttpRequest, pk: int) -> HttpResponse:
    inventory = get_object_or_404(InventoryDocument, pk=pk)
    try:
        inventory.post(posted_by=authenticated_actor(request))
        messages.success(request, "Инвентаризация проведена, корректировка создана автоматически.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("inventory_detail", pk=inventory.pk)


@require_backup_manager
def backup_list(request: HttpRequest) -> HttpResponse:
    paths = configured_backup_paths()
    records = BackupRecord.objects.select_related("created_by")[:50]
    return render(
        request,
        "warehouse_app/backup_list.html",
        {
            "records": records,
            "database_path": paths.database_path,
            "backup_dir": paths.backup_dir,
        },
    )


@require_backup_manager
def backup_create(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("backup_list")

    try:
        record = create_local_backup(message="Manual backup created from web UI.", created_by=request.user)
    except BackupError as exc:
        messages.error(request, str(exc))
    else:
        try:
            record_manual_backup_created(backup_record=record, actor=authenticated_actor(request))
        except Exception:
            logger.exception("Failed to record manual backup activity event for backup %s.", record.pk)
        messages.success(request, "Резервная копия создана.")

    return redirect("backup_list")


@require_backup_manager
def backup_download(request: HttpRequest, pk: int) -> FileResponse:
    record = get_object_or_404(BackupRecord, pk=pk)
    path = Path(record.backup_path)
    if not path.exists() or not path.is_file():
        raise Http404("Backup file not found.")
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


def balance_report(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    preset, preset_filters = _balance_preset_filters(request)
    include_zero_value = request.GET.get("include_zero")
    include_zero = (
        include_zero_value == "1"
        if include_zero_value is not None
        else preset_filters.get("include_zero") == "1"
    )
    presentation = normalize_presentation(
        request.GET.get("presentation") or preset_filters.get("presentation"),
        default=PRESENTATION_BY_WAREHOUSE,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    balances = filter_balance_rows(
        get_balance_rows(
            warehouse=warehouse,
            presentation=presentation,
            include_zero=include_zero,
            category_id=category_id,
        ),
        query=query,
        presentation=presentation,
    )
    page_obj, page_size, pagination_query = _paginate_collection(balances, request)
    context = {
        "balances": page_obj,
        "page_obj": page_obj,
        "page_size": page_size,
        "page_size_options": PAGE_SIZE_OPTIONS,
        "pagination_query": pagination_query,
        "query": query,
        "warehouses": Warehouse.objects.order_by("name"),
        "categories": ItemCategory.objects.filter(is_active=True).order_by("name", "code"),
        "selected_warehouse": warehouse_id or "",
        "selected_category": category_id or "",
        "selected_presentation": presentation,
        "selected_include_zero": include_zero,
        "selected_preset": preset if preset in BALANCE_PRESETS else "",
        "saved_views": _saved_views_for_user(request, SavedViewScope.BALANCES),
    }
    return render(request, "warehouse_app/balances.html", context)


def daily_ledger_report(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    presentation = normalize_presentation(
        request.GET.get("presentation"),
        default=PRESENTATION_CONSOLIDATED,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    anchor_date = parse_date(request.GET.get("anchor_date", "")) if request.GET.get("anchor_date") else None
    resolved = resolve_period(mode="month", anchor_date=anchor_date)
    report = build_daily_ledger(
        warehouse=warehouse,
        period_start=resolved["start"],
        period_end=resolved["end"],
        presentation=presentation,
        category_id=category_id,
    )
    prev_anchor_date = _shift_month(resolved["start"], -1)
    next_anchor_date = _shift_month(resolved["start"], 1)
    page_obj, page_size, pagination_query = _paginate_collection(report["rows"], request, default=50)
    context = {
        "report": report,
        "rows": page_obj,
        "page_obj": page_obj,
        "page_size": page_size,
        "page_size_options": PAGE_SIZE_OPTIONS,
        "pagination_query": pagination_query,
        "period": resolved,
        "warehouses": Warehouse.objects.order_by("name"),
        "categories": ItemCategory.objects.filter(is_active=True).order_by("name", "code"),
        "selected_warehouse": warehouse_id or "",
        "selected_category": category_id or "",
        "selected_presentation": presentation,
        "selected_anchor_date": (anchor_date or resolved["start"]).isoformat(),
        "prev_period_query": _encode_query_params(
            anchor_date=prev_anchor_date.isoformat(),
            warehouse=warehouse_id or "",
            category=category_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
        "next_period_query": _encode_query_params(
            anchor_date=next_anchor_date.isoformat(),
            warehouse=warehouse_id or "",
            category=category_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
    }
    return render(request, "warehouse_app/daily_ledger.html", context)


def monthly_ledger_report(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    presentation = normalize_presentation(
        request.GET.get("presentation"),
        default=PRESENTATION_CONSOLIDATED,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    date_from = parse_date(request.GET.get("date_from", "")) if request.GET.get("date_from") else None
    date_to = parse_date(request.GET.get("date_to", "")) if request.GET.get("date_to") else None
    year_period = resolve_period("year")
    period_start = _month_start(date_from or year_period["start"])
    period_end = _month_end(date_to or year_period["end"])
    if period_start > period_end:
        period_start, period_end = period_end, period_start
    report = build_monthly_ledger(
        warehouse=warehouse,
        period_start=period_start,
        period_end=period_end,
        presentation=presentation,
        category_id=category_id,
    )
    prev_period_start = _month_start(_shift_month(period_start, -1))
    prev_period_end = _month_end(_shift_month(period_end, -1))
    next_period_start = _month_start(_shift_month(period_start, 1))
    next_period_end = _month_end(_shift_month(period_end, 1))
    page_obj, page_size, pagination_query = _paginate_collection(report["rows"], request, default=50)
    context = {
        "report": report,
        "rows": page_obj,
        "page_obj": page_obj,
        "page_size": page_size,
        "page_size_options": PAGE_SIZE_OPTIONS,
        "pagination_query": pagination_query,
        "period": report["period"],
        "warehouses": Warehouse.objects.order_by("name"),
        "categories": ItemCategory.objects.filter(is_active=True).order_by("name", "code"),
        "selected_warehouse": warehouse_id or "",
        "selected_category": category_id or "",
        "selected_presentation": presentation,
        "selected_date_from": period_start.isoformat(),
        "selected_date_to": period_end.isoformat(),
        "prev_period_query": _encode_query_params(
            date_from=prev_period_start.isoformat(),
            date_to=prev_period_end.isoformat(),
            warehouse=warehouse_id or "",
            category=category_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
        "next_period_query": _encode_query_params(
            date_from=next_period_start.isoformat(),
            date_to=next_period_end.isoformat(),
            warehouse=warehouse_id or "",
            category=category_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
    }
    return render(request, "warehouse_app/monthly_ledger.html", context)


def analytics_report(request: HttpRequest) -> HttpResponse:
    mode = request.GET.get("mode", "day")
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    presentation = normalize_presentation(
        request.GET.get("presentation"),
        default=PRESENTATION_CONSOLIDATED,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    anchor_date = parse_date(request.GET.get("anchor_date", "")) if request.GET.get("anchor_date") else None
    date_from = parse_date(request.GET.get("date_from", "")) if request.GET.get("date_from") else None
    date_to = parse_date(request.GET.get("date_to", "")) if request.GET.get("date_to") else None

    resolved = resolve_period(mode=mode, anchor_date=anchor_date, date_from=date_from, date_to=date_to)
    report = build_period_report(
        warehouse=warehouse,
        period_start=resolved["start"],
        period_end=resolved["end"],
        presentation=presentation,
        category_id=category_id,
    )

    context = {
        "report": report,
        "period": resolved,
        "warehouses": Warehouse.objects.order_by("name"),
        "categories": ItemCategory.objects.filter(is_active=True).order_by("name", "code"),
        "selected_warehouse": warehouse_id or "",
        "selected_category": category_id or "",
        "selected_presentation": presentation,
        "selected_mode": mode,
        "selected_anchor_date": resolved["start"].isoformat() if mode == "day" else (anchor_date or resolved["start"]).isoformat(),
        "selected_date_from": resolved["start"].isoformat() if mode == "custom" else (date_from.isoformat() if date_from else ""),
        "selected_date_to": resolved["end"].isoformat() if mode == "custom" else (date_to.isoformat() if date_to else ""),
        "query_string": request.GET.urlencode(),
    }
    return render(request, "warehouse_app/analytics.html", context)


def export_items(request: HttpRequest) -> HttpResponse:
    return _workbook_response(export_items_xlsx())


def export_balances(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    _, preset_filters = _balance_preset_filters(request)
    include_zero_value = request.GET.get("include_zero")
    include_zero = (
        include_zero_value == "1"
        if include_zero_value is not None
        else preset_filters.get("include_zero") == "1"
    )
    presentation = normalize_presentation(
        request.GET.get("presentation") or preset_filters.get("presentation"),
        default=PRESENTATION_BY_WAREHOUSE,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    return _workbook_response(
        export_balances_xlsx(
            warehouse=warehouse,
            presentation=presentation,
            query=query,
            include_zero=include_zero,
            category_id=category_id,
        )
    )


def export_daily_ledger(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    presentation = normalize_presentation(
        request.GET.get("presentation"),
        default=PRESENTATION_CONSOLIDATED,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    anchor_date = parse_date(request.GET.get("anchor_date", "")) if request.GET.get("anchor_date") else None
    resolved = resolve_period(mode="month", anchor_date=anchor_date)
    return _workbook_response(
        export_daily_ledger_xlsx(
            warehouse=warehouse,
            period_start=resolved["start"],
            period_end=resolved["end"],
            presentation=presentation,
            category_id=category_id,
        )
    )


def export_movements(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    _, preset_filters = _document_preset_filters(request)
    document_type = _preset_value(request, "document_type", preset_filters)
    status = _preset_value(request, "status", preset_filters)
    date_from = parse_date(request.GET.get("date_from", "")) if request.GET.get("date_from") else None
    date_to = parse_date(request.GET.get("date_to", "")) if request.GET.get("date_to") else None
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return _workbook_response(
        export_movements_xlsx(
            warehouse=warehouse,
            date_from=date_from,
            date_to=date_to,
            document_type=document_type,
            status=status,
        )
    )


def export_inventories(request: HttpRequest) -> HttpResponse:
    return _workbook_response(export_inventories_xlsx())


def export_analysis(request: HttpRequest) -> HttpResponse:
    mode = request.GET.get("mode", "day")
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    presentation = normalize_presentation(
        request.GET.get("presentation"),
        default=PRESENTATION_CONSOLIDATED,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    anchor_date = parse_date(request.GET.get("anchor_date", "")) if request.GET.get("anchor_date") else None
    date_from = parse_date(request.GET.get("date_from", "")) if request.GET.get("date_from") else None
    date_to = parse_date(request.GET.get("date_to", "")) if request.GET.get("date_to") else None
    resolved = resolve_period(mode=mode, anchor_date=anchor_date, date_from=date_from, date_to=date_to)
    return _workbook_response(
        export_period_analysis_xlsx(
            warehouse=warehouse,
            period_start=resolved["start"],
            period_end=resolved["end"],
            label=resolved["label"],
            presentation=presentation,
            mode_label=PERIOD_MODE_LABELS.get(mode, "День"),
            category_id=category_id,
        )
    )


def export_monthly_ledger(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
    category_id = _get_clean_id(request, "category")
    presentation = normalize_presentation(
        request.GET.get("presentation"),
        default=PRESENTATION_CONSOLIDATED,
    )
    warehouse = Warehouse.objects.filter(pk=warehouse_id).first() if warehouse_id else None
    date_from = parse_date(request.GET.get("date_from", "")) if request.GET.get("date_from") else None
    date_to = parse_date(request.GET.get("date_to", "")) if request.GET.get("date_to") else None
    year_period = resolve_period("year")
    period_start = _month_start(date_from or year_period["start"])
    period_end = _month_end(date_to or year_period["end"])
    if period_start > period_end:
        period_start, period_end = period_end, period_start
    return _workbook_response(
        export_monthly_ledger_xlsx(
            warehouse=warehouse,
            period_start=period_start,
            period_end=period_end,
            presentation=presentation,
            category_id=category_id,
        )
    )


@require_POST
@require_demo_admin
def demo_load(request: HttpRequest) -> HttpResponse:
    requested_next = request.POST.get("next")

    if not settings.DEMO_MODE:
        messages.error(request, "Демо-режим отключен в настройках приложения.")
        return redirect(_resolve_demo_redirect(requested_next))

    try:
        had_data = has_business_data()
        summary = seed_demo_data(force_reset=had_data)
        record_demo_data_reset(
            summary=summary,
            reset_performed=had_data,
            actor=authenticated_actor(request),
        )
        redirect_to = _resolve_demo_redirect(requested_next, reset_performed=had_data)
        prefix = "Демо-данные перезагружены: " if had_data else "Демо-данные загружены: "
        message_text = (
            prefix
            + f"{summary['warehouses']} склад(а), "
            + f"{summary['items']} позиций, "
            + f"{summary['documents']} документов движения, "
            + f"{summary['inventories']} инвентаризаций."
        )
        messages.success(
            request,
            message_text,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        redirect_to = _resolve_demo_redirect(requested_next)
    return redirect(redirect_to)


def _save_stock_lines(document: StockDocument, formset: StockLineFormSet):
    normalized_lines = []
    for line_form in formset:
        if not line_form.cleaned_data or line_form.cleaned_data.get("DELETE"):
            continue
        quantity = line_form.cleaned_data["quantity"]
        if document.document_type == StockDocumentType.RECEIPT:
            quantity = abs(quantity)
        elif document.document_type == StockDocumentType.ISSUE:
            quantity = -abs(quantity)
        elif document.document_type == StockDocumentType.TRANSFER:
            quantity = abs(quantity)
        line = StockDocumentLine(
            document=document,
            item=line_form.cleaned_data["item"],
            quantity=quantity,
            comment=line_form.cleaned_data.get("comment", ""),
        )
        line.full_clean()
        normalized_lines.append(line)

    StockDocumentLine.objects.bulk_create(normalized_lines)


def _stock_formset_initial(document: StockDocument):
    initial = []
    for line in document.lines.select_related("item").order_by("id"):
        quantity = abs(line.quantity) if document.document_type in {StockDocumentType.ISSUE, StockDocumentType.TRANSFER} else line.quantity
        initial.append(
            {
                "item": line.item,
                "quantity": quantity,
                "comment": line.comment,
            }
        )
    return initial


def _save_inventory_lines(inventory: InventoryDocument, formset: InventoryLineFormSet):
    lines = []
    for line_form in formset:
        if not line_form.cleaned_data or line_form.cleaned_data.get("DELETE"):
            continue
        line = InventoryLine(
            inventory=inventory,
            item=line_form.cleaned_data["item"],
            actual_quantity=line_form.cleaned_data["actual_quantity"],
            comment=line_form.cleaned_data.get("comment", ""),
        )
        line.full_clean()
        lines.append(line)
    InventoryLine.objects.bulk_create(lines)


def _inventory_formset_initial(inventory: InventoryDocument):
    return [
        {
            "item": line.item,
            "actual_quantity": line.actual_quantity,
            "comment": line.comment,
        }
        for line in inventory.lines.select_related("item").order_by("id")
    ]


def _resolve_demo_redirect(raw_next, reset_performed=False):
    if not raw_next:
        return reverse("dashboard")
    if not raw_next.startswith("/"):
        return reverse("dashboard")

    path = urlsplit(raw_next).path
    if not path:
        return reverse("dashboard")

    if reset_performed:
        try:
            match = resolve(path)
        except Resolver404:
            return reverse("dashboard")
        if match.url_name in {"document_detail", "inventory_detail"}:
            return reverse("dashboard")
    return raw_next
