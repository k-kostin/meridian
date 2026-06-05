from django import forms
from django.forms import BaseFormSet, formset_factory

from .imports import ITEM_IMPORT_MODE_CREATE_ONLY, ITEM_IMPORT_MODE_UPDATE_EXISTING
from .models import (
    InventoryDocument,
    InventoryScope,
    Item,
    StockDocument,
    StockDocumentType,
    Unit,
    Warehouse,
)


class NativeDateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None, format=None):
        super().__init__(attrs=attrs, format=format or "%Y-%m-%d")


class StyledFieldsMixin:
    def _apply_field_styles(self):
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "").split()
            if "app-control" not in existing_classes:
                existing_classes.append("app-control")
            input_type = getattr(field.widget, "input_type", "")
            if input_type == "date":
                if "date-input" not in existing_classes:
                    existing_classes.append("date-input")
                field.widget.attrs.setdefault("data-autoblur-date", "1")
            field.widget.attrs["class"] = " ".join(existing_classes).strip()


class UnitForm(StyledFieldsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()

    class Meta:
        model = Unit
        fields = ["code", "name", "display_precision"]


class WarehouseForm(StyledFieldsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()

    class Meta:
        model = Warehouse
        fields = ["code", "name", "is_active"]


class ItemForm(StyledFieldsMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()

    class Meta:
        model = Item
        fields = ["sku", "name", "unit", "is_active", "notes"]


class ItemImportPreviewForm(StyledFieldsMixin, forms.Form):
    workbook = forms.FileField(label="Excel-файл .xlsx")
    import_mode = forms.ChoiceField(
        label="Режим импорта",
        choices=[
            (ITEM_IMPORT_MODE_CREATE_ONLY, "Создать только новые позиции"),
            (ITEM_IMPORT_MODE_UPDATE_EXISTING, "Обновить существующие позиции"),
        ],
        initial=ITEM_IMPORT_MODE_CREATE_ONLY,
        required=False,
    )
    auto_create_units = forms.BooleanField(label="Создать отсутствующие единицы измерения", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workbook_field = self.fields["workbook"]
        workbook_field.help_text = (
            "Ожидается лист «Номенклатура» или активный лист. Поддерживаются колонки: "
            "Артикул/SKU, Наименование/Название, Единица/Ед.изм., Активна, Комментарий."
        )
        workbook_field.widget.attrs["accept"] = ".xlsx"
        self._apply_field_styles()

    def clean_workbook(self):
        workbook = self.cleaned_data.get("workbook")
        if workbook and not workbook.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Загрузите файл в формате .xlsx.")
        return workbook

    def clean_import_mode(self):
        return self.cleaned_data.get("import_mode") or ITEM_IMPORT_MODE_CREATE_ONLY


class OpeningInventoryImportForm(StyledFieldsMixin, forms.Form):
    workbook = forms.FileField(label="Excel-файл .xlsx")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workbook_field = self.fields["workbook"]
        workbook_field.help_text = (
            "Ожидается лист «Стартовые остатки» или активный лист. Поддерживаются колонки: "
            "Склад/Код склада, Артикул/SKU, Фактическое количество/Остаток, Комментарий."
        )
        workbook_field.widget.attrs["accept"] = ".xlsx"
        self._apply_field_styles()

    def clean_workbook(self):
        workbook = self.cleaned_data.get("workbook")
        if workbook and not workbook.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Загрузите файл в формате .xlsx.")
        return workbook


class StockDocumentForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = StockDocument
        fields = ["document_type", "warehouse", "destination_warehouse", "operation_date", "comment"]
        widgets = {"operation_date": NativeDateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()
        self.fields["document_type"].choices = [
            (StockDocumentType.RECEIPT, "Приход"),
            (StockDocumentType.ISSUE, "Расход"),
            (StockDocumentType.ADJUSTMENT, "Корректировка"),
            (StockDocumentType.TRANSFER, "Перемещение"),
        ]
        self.fields["destination_warehouse"].required = False
        self.fields["destination_warehouse"].help_text = "Используется только для документа перемещения."


class InventoryDocumentForm(StyledFieldsMixin, forms.ModelForm):
    class Meta:
        model = InventoryDocument
        fields = ["warehouse", "inventory_date", "scope", "comment"]
        widgets = {"inventory_date": NativeDateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()
        self.fields["scope"].choices = [
            (InventoryScope.PARTIAL, "Частичная"),
            (InventoryScope.FULL, "Полная"),
        ]


class StockLineForm(StyledFieldsMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=Item.objects.filter(is_active=True), label="Номенклатура")
    quantity = forms.DecimalField(max_digits=14, decimal_places=3, label="Количество")
    comment = forms.CharField(max_length=255, required=False, label="Комментарий")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()


class InventoryLineForm(StyledFieldsMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=Item.objects.filter(is_active=True), label="Номенклатура")
    actual_quantity = forms.DecimalField(max_digits=14, decimal_places=3, label="Фактическое количество")
    comment = forms.CharField(max_length=255, required=False, label="Комментарий")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_field_styles()


class BaseRequiredLinesFormSet(BaseFormSet):
    empty_row_error = "Добавьте хотя бы одну строку."

    def clean(self):
        super().clean()
        has_line = False
        seen_items = set()
        for form in self.forms:
            if not getattr(form, "cleaned_data", None):
                continue
            if form.cleaned_data.get("DELETE"):
                continue
            item = form.cleaned_data.get("item")
            if item is None:
                continue
            has_line = True
            if item.pk in seen_items:
                raise forms.ValidationError("Одна и та же позиция указана несколько раз.")
            seen_items.add(item.pk)

        if not has_line:
            raise forms.ValidationError(self.empty_row_error)


class BaseInventoryLinesFormSet(BaseRequiredLinesFormSet):
    empty_row_error = "Для инвентаризации нужна хотя бы одна строка."


StockLineFormSet = formset_factory(
    StockLineForm,
    formset=BaseRequiredLinesFormSet,
    extra=6,
    can_delete=True,
)

InventoryLineFormSet = formset_factory(
    InventoryLineForm,
    formset=BaseInventoryLinesFormSet,
    extra=8,
    can_delete=True,
)
