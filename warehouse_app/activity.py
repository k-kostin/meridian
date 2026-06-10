from __future__ import annotations

from .models import (
    ActivityEvent,
    ActivityEventType,
    InventoryDocument,
    StockDocument,
)


def actor_defaults(actor) -> dict:
    if getattr(actor, "is_authenticated", False):
        return {"actor": actor, "actor_label": actor.get_username()}
    return {"actor": None, "actor_label": ""}


def record_stock_document_posted(document: StockDocument, *, actor=None) -> None:
    ActivityEvent.objects.get_or_create(
        event_type=ActivityEventType.STOCK_DOCUMENT_POSTED,
        stock_document=document,
        defaults={
            "warehouse": document.warehouse,
            "inventory_document": document.source_inventory,
            "message": f"Документ {document.number} проведен: {document.get_document_type_display()}",
            **actor_defaults(actor),
            "metadata": {
                "document_number": document.number,
                "document_type": document.document_type,
                "operation_date": document.operation_date.isoformat(),
            },
        },
    )


def record_inventory_posted(inventory: InventoryDocument, *, actor=None) -> None:
    ActivityEvent.objects.get_or_create(
        event_type=ActivityEventType.INVENTORY_POSTED,
        inventory_document=inventory,
        defaults={
            "warehouse": inventory.warehouse,
            "message": f"Инвентаризация {inventory.number} проведена",
            **actor_defaults(actor),
            "metadata": {
                "inventory_number": inventory.number,
                "inventory_date": inventory.inventory_date.isoformat(),
                "scope": inventory.scope,
            },
        },
    )


def record_inventory_adjustment_created(inventory: InventoryDocument, adjustment: StockDocument, *, actor=None) -> None:
    ActivityEvent.objects.get_or_create(
        event_type=ActivityEventType.INVENTORY_ADJUSTMENT_CREATED,
        inventory_document=inventory,
        stock_document=adjustment,
        defaults={
            "warehouse": inventory.warehouse,
            "message": f"Создана автокорректировка {adjustment.number}",
            **actor_defaults(actor),
            "metadata": {
                "inventory_number": inventory.number,
                "adjustment_number": adjustment.number,
            },
        },
    )


def record_item_import_committed(
    *,
    created_count: int,
    updated_count: int,
    import_mode: str,
    auto_create_units: bool,
    actor=None,
) -> None:
    ActivityEvent.objects.create(
        event_type=ActivityEventType.ITEM_IMPORT_COMMITTED,
        message=f"Импорт номенклатуры выполнен: создано {created_count}, обновлено {updated_count}",
        **actor_defaults(actor),
        metadata={
            "created_count": created_count,
            "updated_count": updated_count,
            "import_mode": import_mode,
            "auto_create_units": auto_create_units,
        },
    )


def record_opening_inventory_import_committed(
    *,
    inventory: InventoryDocument,
    created_lines_count: int,
    actor=None,
) -> None:
    ActivityEvent.objects.create(
        event_type=ActivityEventType.OPENING_INVENTORY_IMPORT_COMMITTED,
        warehouse=inventory.warehouse,
        inventory_document=inventory,
        message=f"Импорт стартовых остатков создал инвентаризацию {inventory.number}",
        **actor_defaults(actor),
        metadata={
            "inventory_number": inventory.number,
            "created_lines_count": created_lines_count,
        },
    )


def record_manual_backup_created(*, backup_record, actor=None) -> None:
    ActivityEvent.objects.create(
        event_type=ActivityEventType.MANUAL_BACKUP_CREATED,
        message=f"Создана резервная копия #{backup_record.pk}",
        **actor_defaults(actor),
        metadata={
            "backup_id": backup_record.pk,
            "backup_kind": backup_record.kind,
            "backup_status": backup_record.status,
            "size_bytes": backup_record.size_bytes,
        },
    )


def record_demo_data_reset(*, summary: dict, reset_performed: bool, actor=None) -> None:
    ActivityEvent.objects.create(
        event_type=ActivityEventType.DEMO_DATA_RESET,
        message="Демо-данные перезагружены" if reset_performed else "Демо-данные загружены",
        **actor_defaults(actor),
        metadata={
            "reset_performed": reset_performed,
            "warehouses": summary.get("warehouses", 0),
            "items": summary.get("items", 0),
            "documents": summary.get("documents", 0),
            "inventories": summary.get("inventories", 0),
        },
    )


def record_reference_record_changed(*, instance, action: str, actor=None) -> None:
    ActivityEvent.objects.create(
        event_type=ActivityEventType.REFERENCE_RECORD_CHANGED,
        message=f"Справочник изменен: {instance._meta.verbose_name} #{instance.pk}",
        **actor_defaults(actor),
        metadata={
            "action": action,
            "model": instance.__class__.__name__,
            "object_id": instance.pk,
            "label": str(instance),
        },
    )


def get_document_timeline(document: StockDocument):
    return ActivityEvent.objects.select_related(
        "warehouse",
        "actor",
    ).filter(stock_document=document)


def get_inventory_timeline(inventory: InventoryDocument):
    return ActivityEvent.objects.select_related(
        "warehouse",
        "actor",
    ).filter(inventory_document=inventory)
