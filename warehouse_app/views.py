from datetime import date
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST

from .activity import get_document_timeline, get_inventory_timeline
from .forms import (
    InventoryDocumentForm,
    InventoryLineFormSet,
    ItemForm,
    StockDocumentForm,
    StockLineFormSet,
    UnitForm,
    WarehouseForm,
)
from .demo import has_business_data, seed_demo_data
from .models import (
    DocumentStatus,
    InventoryDocument,
    InventoryLine,
    InventoryScope,
    Item,
    StockDocument,
    StockDocumentLine,
    StockDocumentType,
    Unit,
    Warehouse,
)
from .permissions import can_manage_references, require_demo_admin, require_reference_manager, require_stock_operator
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


def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


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
        form.save()
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
        form.save()
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
        form.save()
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
        form.save()
        messages.success(request, "Склад обновлен.")
        return redirect("warehouse_list")
    return render(
        request,
        "warehouse_app/simple_form.html",
        {"form": form, "title": "Редактирование склада", "back_url": reverse("warehouse_list")},
    )


def item_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    items = Item.objects.select_related("unit").order_by("name", "sku")
    if query:
        items = items.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    page_obj, page_size, pagination_query = _paginate_collection(items, request)

    form = ItemForm(request.POST or None)
    if request.method == "POST" and not can_manage_references(request.user):
        raise PermissionDenied("Недостаточно прав для изменения справочников.")
    if request.method == "POST" and form.is_valid():
        form.save()
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
        },
    )


@require_reference_manager
def item_update(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Item, pk=pk)
    form = ItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Позиция обновлена.")
        return redirect("item_list")
    return render(
        request,
        "warehouse_app/simple_form.html",
        {"form": form, "title": "Редактирование номенклатуры", "back_url": reverse("item_list")},
    )


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
                document = form.save()
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
                document = form.save()
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
        StockDocument.objects.select_related("warehouse", "destination_warehouse", "source_inventory").prefetch_related("lines__item__unit"),
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
        document.post()
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
                inventory = form.save()
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
                inventory = form.save()
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
        InventoryDocument.objects.select_related("warehouse").prefetch_related("lines__item__unit", "generated_documents"),
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
        inventory.post()
        messages.success(request, "Инвентаризация проведена, корректировка создана автоматически.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("inventory_detail", pk=inventory.pk)


def balance_report(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()
    warehouse_id = request.GET.get("warehouse")
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
        get_balance_rows(warehouse=warehouse, presentation=presentation, include_zero=include_zero),
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
        "selected_warehouse": warehouse_id or "",
        "selected_presentation": presentation,
        "selected_include_zero": include_zero,
        "selected_preset": preset if preset in BALANCE_PRESETS else "",
    }
    return render(request, "warehouse_app/balances.html", context)


def daily_ledger_report(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
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
        "selected_warehouse": warehouse_id or "",
        "selected_presentation": presentation,
        "selected_anchor_date": (anchor_date or resolved["start"]).isoformat(),
        "prev_period_query": _encode_query_params(
            anchor_date=prev_anchor_date.isoformat(),
            warehouse=warehouse_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
        "next_period_query": _encode_query_params(
            anchor_date=next_anchor_date.isoformat(),
            warehouse=warehouse_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
    }
    return render(request, "warehouse_app/daily_ledger.html", context)


def monthly_ledger_report(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
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
        "selected_warehouse": warehouse_id or "",
        "selected_presentation": presentation,
        "selected_date_from": period_start.isoformat(),
        "selected_date_to": period_end.isoformat(),
        "prev_period_query": _encode_query_params(
            date_from=prev_period_start.isoformat(),
            date_to=prev_period_end.isoformat(),
            warehouse=warehouse_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
        "next_period_query": _encode_query_params(
            date_from=next_period_start.isoformat(),
            date_to=next_period_end.isoformat(),
            warehouse=warehouse_id or "",
            presentation=presentation,
            page_size=page_size,
        ),
    }
    return render(request, "warehouse_app/monthly_ledger.html", context)


def analytics_report(request: HttpRequest) -> HttpResponse:
    mode = request.GET.get("mode", "day")
    warehouse_id = request.GET.get("warehouse")
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
    )

    context = {
        "report": report,
        "period": resolved,
        "warehouses": Warehouse.objects.order_by("name"),
        "selected_warehouse": warehouse_id or "",
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
        )
    )


def export_daily_ledger(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
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
        )
    )


def export_monthly_ledger(request: HttpRequest) -> HttpResponse:
    warehouse_id = request.GET.get("warehouse")
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
