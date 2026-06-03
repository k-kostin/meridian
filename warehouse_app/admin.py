from django.contrib import admin

from .models import DocumentStatus, InventoryDocument, InventoryLine, Item, StockDocument, StockDocumentLine, Unit, Warehouse


class StockDocumentLineInline(admin.TabularInline):
    model = StockDocumentLine
    extra = 0


class InventoryLineInline(admin.TabularInline):
    model = InventoryLine
    extra = 0


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "display_precision")
    search_fields = ("code", "name")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "unit", "is_active")
    search_fields = ("sku", "name")
    list_filter = ("is_active", "unit")


@admin.register(StockDocument)
class StockDocumentAdmin(admin.ModelAdmin):
    list_display = ("number", "document_type", "warehouse", "operation_date", "status")
    list_filter = ("document_type", "status", "warehouse")
    search_fields = ("number", "comment")
    inlines = [StockDocumentLineInline]

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.status == DocumentStatus.POSTED:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status == DocumentStatus.POSTED:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(InventoryDocument)
class InventoryDocumentAdmin(admin.ModelAdmin):
    list_display = ("number", "warehouse", "inventory_date", "scope", "status")
    list_filter = ("scope", "status", "warehouse")
    search_fields = ("number", "comment")
    inlines = [InventoryLineInline]

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.status == DocumentStatus.POSTED:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status == DocumentStatus.POSTED:
            return False
        return super().has_delete_permission(request, obj)
