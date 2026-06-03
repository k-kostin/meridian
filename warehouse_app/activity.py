from __future__ import annotations

from .models import (
    ActivityEvent,
    ActivityEventType,
    InventoryDocument,
    StockDocument,
)


def record_stock_document_posted(document: StockDocument) -> None:
    ActivityEvent.objects.get_or_create(
        event_type=ActivityEventType.STOCK_DOCUMENT_POSTED,
        stock_document=document,
        defaults={
            "warehouse": document.warehouse,
            "inventory_document": document.source_inventory,
            "message": f"Документ {document.number} проведен: {document.get_document_type_display()}",
            "metadata": {
                "document_number": document.number,
                "document_type": document.document_type,
                "operation_date": document.operation_date.isoformat(),
            },
        },
    )


def record_inventory_posted(inventory: InventoryDocument) -> None:
    ActivityEvent.objects.get_or_create(
        event_type=ActivityEventType.INVENTORY_POSTED,
        inventory_document=inventory,
        defaults={
            "warehouse": inventory.warehouse,
            "message": f"Инвентаризация {inventory.number} проведена",
            "metadata": {
                "inventory_number": inventory.number,
                "inventory_date": inventory.inventory_date.isoformat(),
                "scope": inventory.scope,
            },
        },
    )


def record_inventory_adjustment_created(inventory: InventoryDocument, adjustment: StockDocument) -> None:
    ActivityEvent.objects.get_or_create(
        event_type=ActivityEventType.INVENTORY_ADJUSTMENT_CREATED,
        inventory_document=inventory,
        stock_document=adjustment,
        defaults={
            "warehouse": inventory.warehouse,
            "message": f"Создана автокорректировка {adjustment.number}",
            "metadata": {
                "inventory_number": inventory.number,
                "adjustment_number": adjustment.number,
            },
        },
    )


def get_document_timeline(document: StockDocument):
    return ActivityEvent.objects.select_related(
        "warehouse",
        "stock_document",
        "inventory_document",
    ).filter(stock_document=document)


def get_inventory_timeline(inventory: InventoryDocument):
    return ActivityEvent.objects.select_related(
        "warehouse",
        "stock_document",
        "inventory_document",
    ).filter(inventory_document=inventory)
