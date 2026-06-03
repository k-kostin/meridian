from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
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

DEMO_LABEL_ALPHABET = list("АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭЮЯ")


def _demo_sku(index):
    return f"{100000 + index:06d}"


def _demo_label(index):
    base = len(DEMO_LABEL_ALPHABET)
    value = index + 1
    label = ""
    while value > 0:
        value, remainder = divmod(value - 1, base)
        label = DEMO_LABEL_ALPHABET[remainder] + label
    return label


def _demo_unit_code(index):
    if index < 10:
        return "кг"
    if index < 20:
        return "шт"
    return "м"


DEMO_ITEMS = [
    (
        _demo_sku(index + 1),
        f"Позиция {_demo_label(index)}",
        _demo_unit_code(index),
        f"[demo] Демонстрационная позиция {_demo_label(index)}",
    )
    for index in range(30)
]

DEMO_MOVEMENTS = [
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "main",
        "days_ago": 58,
        "comment": "Стартовый приход на основной склад",
        "lines": [
            (_demo_sku(1), "48"),
            (_demo_sku(2), "36"),
            (_demo_sku(3), "52"),
            (_demo_sku(4), "44"),
            (_demo_sku(5), "38"),
            (_demo_sku(6), "41"),
        ],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "reserve",
        "days_ago": 55,
        "comment": "Стартовый приход на резервный склад",
        "lines": [
            (_demo_sku(7), "27"),
            (_demo_sku(8), "31"),
            (_demo_sku(9), "29"),
            (_demo_sku(10), "35"),
            (_demo_sku(11), "120"),
            (_demo_sku(12), "95"),
        ],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "kit",
        "days_ago": 52,
        "comment": "Стартовый приход на склад комплектации",
        "lines": [
            (_demo_sku(13), "80"),
            (_demo_sku(14), "65"),
            (_demo_sku(15), "72"),
            (_demo_sku(16), "90"),
            (_demo_sku(17), "60"),
            (_demo_sku(18), "75"),
        ],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "main",
        "days_ago": 50,
        "comment": "Стартовый приход линейных и штучных позиций",
        "lines": [
            (_demo_sku(19), "55"),
            (_demo_sku(20), "48"),
            (_demo_sku(21), "180"),
            (_demo_sku(22), "220"),
            (_demo_sku(23), "195"),
            (_demo_sku(24), "170"),
        ],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "reserve",
        "days_ago": 48,
        "comment": "Стартовый приход длинномерных позиций",
        "lines": [
            (_demo_sku(25), "150"),
            (_demo_sku(26), "165"),
            (_demo_sku(27), "140"),
            (_demo_sku(28), "175"),
            (_demo_sku(29), "155"),
            (_demo_sku(30), "160"),
        ],
    },
    {
        "type": StockDocumentType.ISSUE,
        "warehouse": "main",
        "days_ago": 45,
        "comment": "Расход по основному складу",
        "lines": [(_demo_sku(1), "-7"), (_demo_sku(2), "-5"), (_demo_sku(19), "-15"), (_demo_sku(21), "-20")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "reserve",
        "days_ago": 42,
        "comment": "Пополнение резерва",
        "lines": [(_demo_sku(3), "10"), (_demo_sku(12), "18"), (_demo_sku(22), "30"), (_demo_sku(25), "25")],
    },
    {
        "type": StockDocumentType.ISSUE,
        "warehouse": "kit",
        "days_ago": 39,
        "comment": "Выдача со склада комплектации",
        "lines": [(_demo_sku(13), "-12"), (_demo_sku(14), "-9"), (_demo_sku(15), "-18")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "reserve",
        "days_ago": 36,
        "comment": "Точечное пополнение резервного склада",
        "lines": [(_demo_sku(15), "20"), (_demo_sku(16), "18"), (_demo_sku(24), "35")],
    },
    {
        "type": StockDocumentType.ISSUE,
        "warehouse": "main",
        "days_ago": 32,
        "comment": "Внутренний расход основного склада",
        "lines": [(_demo_sku(4), "-8"), (_demo_sku(5), "-6"), (_demo_sku(19), "-9")],
    },
    {
        "type": StockDocumentType.ADJUSTMENT,
        "warehouse": "reserve",
        "days_ago": 29,
        "comment": "Ручная корректировка по резерву",
        "lines": [(_demo_sku(8), "2"), (_demo_sku(26), "-6")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "kit",
        "days_ago": 26,
        "comment": "Пополнение склада комплектации",
        "lines": [(_demo_sku(17), "15"), (_demo_sku(18), "14"), (_demo_sku(27), "24"), (_demo_sku(28), "22")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "main",
        "days_ago": 23,
        "comment": "Точечное пополнение основного склада",
        "lines": [(_demo_sku(29), "28"), (_demo_sku(30), "18"), (_demo_sku(6), "9")],
    },
    {
        "type": StockDocumentType.ISSUE,
        "warehouse": "reserve",
        "days_ago": 19,
        "comment": "Отпуск с резервного склада",
        "lines": [(_demo_sku(7), "-4"), (_demo_sku(12), "-10"), (_demo_sku(25), "-15")],
    },
    {
        "type": StockDocumentType.ISSUE,
        "warehouse": "kit",
        "days_ago": 16,
        "comment": "Комплектация заказа",
        "lines": [(_demo_sku(16), "-7"), (_demo_sku(18), "-5"), (_demo_sku(27), "-9")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "reserve",
        "days_ago": 13,
        "comment": "Поступление на резервный склад",
        "lines": [(_demo_sku(9), "12"), (_demo_sku(10), "11"), (_demo_sku(20), "16")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "main",
        "days_ago": 9,
        "comment": "Докомплектация перед выдачей",
        "lines": [(_demo_sku(1), "6"), (_demo_sku(14), "12"), (_demo_sku(22), "20")],
    },
    {
        "type": StockDocumentType.ISSUE,
        "warehouse": "main",
        "days_ago": 6,
        "comment": "Расход по основному складу",
        "lines": [(_demo_sku(2), "-3"), (_demo_sku(24), "-11"), (_demo_sku(29), "-8")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "reserve",
        "days_ago": 3,
        "comment": "Финальное пополнение резервного склада",
        "lines": [(_demo_sku(11), "14"), (_demo_sku(26), "19"), (_demo_sku(30), "17")],
    },
    {
        "type": StockDocumentType.RECEIPT,
        "warehouse": "kit",
        "days_ago": 1,
        "comment": "Последнее пополнение склада комплектации",
        "lines": [(_demo_sku(13), "9"), (_demo_sku(15), "10"), (_demo_sku(28), "13")],
    },
]

DEMO_INVENTORIES = [
    {
        "warehouse": "main",
        "days_ago": 20,
        "scope": InventoryScope.PARTIAL,
        "comment": "Контрольный пересчет основного склада",
        "lines": [(_demo_sku(1), "45"), (_demo_sku(11), "107"), (_demo_sku(21), "174"), (_demo_sku(29), "24")],
    },
    {
        "warehouse": "reserve",
        "days_ago": 5,
        "scope": InventoryScope.PARTIAL,
        "comment": "Контрольный пересчет резервного склада",
        "lines": [(_demo_sku(10), "39"), (_demo_sku(12), "103"), (_demo_sku(25), "143"), (_demo_sku(26), "177")],
    },
]


def has_business_data():
    return (
        Unit.objects.exists()
        or Warehouse.objects.exists()
        or Item.objects.exists()
        or StockDocument.objects.exists()
        or InventoryDocument.objects.exists()
    )


def reset_demo_data():
    InventoryDocument.objects.all().delete()
    StockDocument.objects.all().delete()
    Item.objects.all().delete()
    Warehouse.objects.all().delete()
    Unit.objects.all().delete()


def seed_demo_data(force_reset=False):
    if has_business_data() and not force_reset:
        raise ValidationError("Демо-данные можно загружать только в пустую базу.")

    today = timezone.localdate()

    with transaction.atomic():
        if force_reset:
            reset_demo_data()

        units = {
            "кг": Unit.objects.create(code="кг", name="Килограмм", display_precision=3),
            "шт": Unit.objects.create(code="шт", name="Штука", display_precision=0),
            "м": Unit.objects.create(code="м", name="Метр", display_precision=3),
        }
        warehouses = {
            "main": Warehouse.objects.create(code="main", name="Основной склад"),
            "reserve": Warehouse.objects.create(code="reserve", name="Резервный склад"),
            "kit": Warehouse.objects.create(code="kit", name="Склад комплектации"),
        }
        items = {
            sku: Item.objects.create(sku=sku, name=name, unit=units[unit_code], notes=notes)
            for sku, name, unit_code, notes in DEMO_ITEMS
        }

        _load_demo_movements(today=today, warehouses=warehouses, items=items)
        _load_demo_inventories(today=today, warehouses=warehouses, items=items)

        earliest_doc = StockDocument.objects.order_by("operation_date").first()
        latest_doc = StockDocument.objects.order_by("-operation_date").first()
        span_days = 0
        if earliest_doc and latest_doc:
            span_days = (latest_doc.operation_date - earliest_doc.operation_date).days

        return {
            "units": Unit.objects.count(),
            "warehouses": Warehouse.objects.count(),
            "items": Item.objects.count(),
            "documents": StockDocument.objects.count(),
            "inventories": InventoryDocument.objects.count(),
            "span_days": span_days,
        }


def _load_demo_movements(*, today, warehouses, items):
    for payload in DEMO_MOVEMENTS:
        document = StockDocument.objects.create(
            document_type=payload["type"],
            warehouse=warehouses[payload["warehouse"]],
            operation_date=today - timedelta(days=payload["days_ago"]),
            comment=f"[demo] {payload['comment']}",
        )
        for sku, quantity in payload["lines"]:
            StockDocumentLine.objects.create(
                document=document,
                item=items[sku],
                quantity=Decimal(quantity),
                comment="[demo]",
            )
        document.post()


def _load_demo_inventories(*, today, warehouses, items):
    for payload in DEMO_INVENTORIES:
        inventory = InventoryDocument.objects.create(
            warehouse=warehouses[payload["warehouse"]],
            inventory_date=today - timedelta(days=payload["days_ago"]),
            scope=payload["scope"],
            comment=f"[demo] {payload['comment']}",
        )
        for sku, actual_quantity in payload["lines"]:
            InventoryLine.objects.create(
                inventory=inventory,
                item=items[sku],
                actual_quantity=Decimal(actual_quantity),
                comment="[demo]",
            )
        inventory.post()
