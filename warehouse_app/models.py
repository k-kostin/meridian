from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Unit(TimeStampedModel):
    code = models.CharField("Код", max_length=20, unique=True)
    name = models.CharField("Наименование", max_length=80)
    display_precision = models.PositiveSmallIntegerField(
        "Знаков после запятой",
        default=3,
        validators=[MaxValueValidator(6)],
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Единица измерения"
        verbose_name_plural = "Единицы измерения"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Warehouse(TimeStampedModel):
    code = models.CharField("Код", max_length=20, unique=True)
    name = models.CharField("Наименование", max_length=120)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Склад"
        verbose_name_plural = "Склады"

    def __str__(self) -> str:
        return self.name


class Item(TimeStampedModel):
    sku = models.CharField("Артикул", max_length=40, unique=True)
    name = models.CharField("Наименование", max_length=180)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="items", verbose_name="Ед. изм.")
    is_active = models.BooleanField("Активен", default=True)
    notes = models.TextField("Комментарий", blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Номенклатура"
        verbose_name_plural = "Номенклатура"

    def __str__(self) -> str:
        return f"{self.name} [{self.sku}]"


class DocumentStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    POSTED = "posted", "Проведен"


class StockDocumentType(models.TextChoices):
    RECEIPT = "receipt", "Приход"
    ISSUE = "issue", "Расход"
    ADJUSTMENT = "adjustment", "Корректировка"
    TRANSFER = "transfer", "Перемещение"


class InventoryScope(models.TextChoices):
    PARTIAL = "partial", "Частичная"
    FULL = "full", "Полная"


class ActivityEventType(models.TextChoices):
    STOCK_DOCUMENT_POSTED = "stock_document_posted", "Документ проведен"
    INVENTORY_POSTED = "inventory_posted", "Инвентаризация проведена"
    INVENTORY_ADJUSTMENT_CREATED = "inventory_adjustment_created", "Автокорректировка создана"


NUMBER_GENERATION_ATTEMPTS = 8


def _generate_number(prefix: str, model_cls: type[models.Model], date_value):
    date_part = date_value.strftime("%Y%m%d")
    prefix_stub = f"{prefix}-{date_part}-"
    existing_numbers = set(
        model_cls.objects.select_for_update()
        .filter(number__startswith=prefix_stub)
        .values_list("number", flat=True)
    )
    counter = 1
    while True:
        candidate = f"{prefix_stub}{counter:03d}"
        if candidate not in existing_numbers:
            return candidate
        counter += 1


class StockDocument(TimeStampedModel):
    number = models.CharField("Номер", max_length=32, unique=True, blank=True)
    document_type = models.CharField(
        "Тип документа",
        max_length=20,
        choices=StockDocumentType.choices,
        default=StockDocumentType.RECEIPT,
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="documents", verbose_name="Склад")
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="incoming_documents",
        verbose_name="Склад-получатель",
        null=True,
        blank=True,
    )
    operation_date = models.DateField("Дата документа", default=timezone.localdate)
    status = models.CharField(
        "Статус",
        max_length=10,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT,
    )
    comment = models.TextField("Комментарий", blank=True)
    posted_at = models.DateTimeField("Дата проведения", null=True, blank=True)
    source_inventory = models.ForeignKey(
        "InventoryDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_documents",
        verbose_name="Источник инвентаризации",
    )

    class Meta:
        ordering = ["-operation_date", "-created_at"]
        verbose_name = "Документ движения"
        verbose_name_plural = "Документы движения"

    def __str__(self) -> str:
        return self.number or "Новый документ"

    @property
    def type_label(self) -> str:
        return self.get_document_type_display()

    def _number_prefix(self) -> str:
        return {
            StockDocumentType.RECEIPT: "RCV",
            StockDocumentType.ISSUE: "ISS",
            StockDocumentType.ADJUSTMENT: "ADJ",
            StockDocumentType.TRANSFER: "TRF",
        }[self.document_type]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.number:
            last_error = None
            for _ in range(NUMBER_GENERATION_ATTEMPTS):
                try:
                    with transaction.atomic():
                        self.number = _generate_number(self._number_prefix(), StockDocument, self.operation_date)
                        return super().save(*args, **kwargs)
                except IntegrityError as exc:
                    self.number = ""
                    last_error = exc
            raise last_error or IntegrityError("Не удалось сгенерировать уникальный номер документа.")
        super().save(*args, **kwargs)

    def clean(self):
        if self.source_inventory and self.document_type != StockDocumentType.ADJUSTMENT:
            raise ValidationError("Инвентаризация может порождать только документ корректировки.")
        if self.document_type == StockDocumentType.TRANSFER:
            if not self.destination_warehouse:
                raise ValidationError("Для перемещения нужно указать склад-получатель.")
            if self.warehouse_id and self.destination_warehouse_id == self.warehouse_id:
                raise ValidationError("Склад-источник и склад-получатель должны отличаться.")
        elif self.destination_warehouse_id:
            raise ValidationError("Склад-получатель можно указывать только для перемещения.")

    def total_quantity(self) -> Decimal:
        total = self.lines.aggregate(total=models.Sum("quantity"))["total"]
        return total or Decimal("0")

    @transaction.atomic
    def post(self):
        locked_document = StockDocument.objects.select_for_update().get(pk=self.pk)
        if locked_document.status == DocumentStatus.POSTED:
            self.status = locked_document.status
            self.posted_at = locked_document.posted_at
            return

        Warehouse.objects.select_for_update().get(pk=locked_document.warehouse_id)

        lines = list(locked_document.lines.select_related("item"))
        if not lines:
            raise ValidationError("Документ нельзя провести без строк.")

        from .services import get_balance_map

        if locked_document.document_type in {StockDocumentType.ISSUE, StockDocumentType.TRANSFER}:
            balances = get_balance_map(locked_document.warehouse, as_of_date=locked_document.operation_date)
            for line in lines:
                quantity_delta = line.quantity if locked_document.document_type == StockDocumentType.ISSUE else -abs(line.quantity)
                balances[line.item_id] = balances.get(line.item_id, Decimal("0")) + quantity_delta
                if balances[line.item_id] < 0:
                    action_label = "расхода" if locked_document.document_type == StockDocumentType.ISSUE else "перемещения"
                    raise ValidationError(f"Недостаточно остатка по позиции «{line.item.name}» для проведения {action_label}.")

        locked_document.status = DocumentStatus.POSTED
        locked_document.posted_at = timezone.now()
        locked_document.save(update_fields=["status", "posted_at", "updated_at"])
        self.status = locked_document.status
        self.posted_at = locked_document.posted_at

        from .activity import record_stock_document_posted

        record_stock_document_posted(locked_document)


class StockDocumentLine(models.Model):
    document = models.ForeignKey(StockDocument, on_delete=models.CASCADE, related_name="lines", verbose_name="Документ")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_lines", verbose_name="Номенклатура")
    quantity = models.DecimalField("Количество", max_digits=14, decimal_places=3)
    comment = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["document", "item"], name="uniq_stock_document_item"),
        ]
        verbose_name = "Строка документа"
        verbose_name_plural = "Строки документов"

    def __str__(self) -> str:
        return f"{self.document} / {self.item}"

    def clean(self):
        if self.quantity == 0:
            raise ValidationError("Количество не может быть нулевым.")
        if not self.document_id and not self.document:
            return
        document = self.document
        if document.document_type == StockDocumentType.RECEIPT and self.quantity < 0:
            raise ValidationError("Для прихода количество должно быть положительным.")
        if document.document_type == StockDocumentType.ISSUE and self.quantity > 0:
            raise ValidationError("Для расхода количество должно быть отрицательным.")
        if document.document_type == StockDocumentType.TRANSFER and self.quantity < 0:
            raise ValidationError("Для перемещения количество должно быть положительным.")


class InventoryDocument(TimeStampedModel):
    number = models.CharField("Номер", max_length=32, unique=True, blank=True)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="inventory_documents",
        verbose_name="Склад",
    )
    inventory_date = models.DateField("Дата инвентаризации", default=timezone.localdate)
    scope = models.CharField(
        "Охват",
        max_length=10,
        choices=InventoryScope.choices,
        default=InventoryScope.PARTIAL,
    )
    status = models.CharField(
        "Статус",
        max_length=10,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT,
    )
    comment = models.TextField("Комментарий", blank=True)
    posted_at = models.DateTimeField("Дата проведения", null=True, blank=True)

    class Meta:
        ordering = ["-inventory_date", "-created_at"]
        verbose_name = "Инвентаризация"
        verbose_name_plural = "Инвентаризации"

    def __str__(self) -> str:
        return self.number or "Новая инвентаризация"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.number:
            last_error = None
            for _ in range(NUMBER_GENERATION_ATTEMPTS):
                try:
                    with transaction.atomic():
                        self.number = _generate_number("INV", InventoryDocument, self.inventory_date)
                        return super().save(*args, **kwargs)
                except IntegrityError as exc:
                    self.number = ""
                    last_error = exc
            raise last_error or IntegrityError("Не удалось сгенерировать уникальный номер инвентаризации.")
        super().save(*args, **kwargs)

    @transaction.atomic
    def post(self):
        locked_inventory = InventoryDocument.objects.select_for_update().get(pk=self.pk)
        if locked_inventory.status == DocumentStatus.POSTED:
            self.status = locked_inventory.status
            self.posted_at = locked_inventory.posted_at
            return

        from .services import get_balance_map

        Warehouse.objects.select_for_update().get(pk=locked_inventory.warehouse_id)

        balances = get_balance_map(locked_inventory.warehouse, as_of_date=locked_inventory.inventory_date)
        line_map = {
            line.item_id: line
            for line in locked_inventory.lines.select_related("item")
        }

        if locked_inventory.scope == InventoryScope.FULL:
            for item_id, quantity in balances.items():
                if item_id not in line_map:
                    line = InventoryLine.objects.create(
                        inventory=locked_inventory,
                        item_id=item_id,
                        actual_quantity=Decimal("0"),
                        expected_quantity=quantity,
                    )
                    line_map[item_id] = line

        if not line_map:
            raise ValidationError("Инвентаризация не содержит строк.")

        adjustment_lines = []
        for item_id, line in line_map.items():
            expected = balances.get(item_id, Decimal("0"))
            actual = line.actual_quantity
            delta = actual - expected

            if line.expected_quantity != expected:
                line.expected_quantity = expected
                line.save(update_fields=["expected_quantity"])

            if delta != 0:
                adjustment_lines.append(
                    StockDocumentLine(
                        item_id=item_id,
                        quantity=delta,
                        comment=f"Разница по инвентаризации {locked_inventory.number}",
                    )
                )

        adjustment = None
        if adjustment_lines:
            adjustment = StockDocument.objects.create(
                document_type=StockDocumentType.ADJUSTMENT,
                warehouse=locked_inventory.warehouse,
                operation_date=locked_inventory.inventory_date,
                comment=f"Автокорректировка по инвентаризации {locked_inventory.number}",
                source_inventory=locked_inventory,
            )
            for line in adjustment_lines:
                line.document = adjustment
                line.full_clean()
            StockDocumentLine.objects.bulk_create(adjustment_lines)
            adjustment.post()

        locked_inventory.status = DocumentStatus.POSTED
        locked_inventory.posted_at = timezone.now()
        locked_inventory.save(update_fields=["status", "posted_at", "updated_at"])
        self.status = locked_inventory.status
        self.posted_at = locked_inventory.posted_at

        from .activity import record_inventory_adjustment_created, record_inventory_posted

        record_inventory_posted(locked_inventory)
        if adjustment:
            record_inventory_adjustment_created(locked_inventory, adjustment)


class InventoryLine(models.Model):
    inventory = models.ForeignKey(
        InventoryDocument,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Инвентаризация",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="inventory_lines", verbose_name="Номенклатура")
    expected_quantity = models.DecimalField(
        "Учетное количество",
        max_digits=14,
        decimal_places=3,
        default=Decimal("0"),
    )
    actual_quantity = models.DecimalField("Фактическое количество", max_digits=14, decimal_places=3)
    comment = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["inventory", "item"], name="uniq_inventory_item"),
        ]
        verbose_name = "Строка инвентаризации"
        verbose_name_plural = "Строки инвентаризации"

    def __str__(self) -> str:
        return f"{self.inventory} / {self.item}"

    @property
    def variance(self) -> Decimal:
        return self.actual_quantity - self.expected_quantity

    def clean(self):
        if self.actual_quantity < 0:
            raise ValidationError("Фактическое количество не может быть отрицательным.")


class ActivityEvent(TimeStampedModel):
    event_type = models.CharField("Тип события", max_length=40, choices=ActivityEventType.choices)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="activity_events",
        verbose_name="Склад",
    )
    stock_document = models.ForeignKey(
        StockDocument,
        on_delete=models.CASCADE,
        related_name="activity_events",
        verbose_name="Документ движения",
        null=True,
        blank=True,
    )
    inventory_document = models.ForeignKey(
        InventoryDocument,
        on_delete=models.CASCADE,
        related_name="activity_events",
        verbose_name="Инвентаризация",
        null=True,
        blank=True,
    )
    message = models.CharField("Событие", max_length=255)
    metadata = models.JSONField("Метаданные", default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Событие активности"
        verbose_name_plural = "События активности"

    def __str__(self) -> str:
        return self.message
