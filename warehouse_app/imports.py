from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from django.db import transaction
from openpyxl import load_workbook

from .models import Item, Unit


@dataclass(frozen=True)
class ItemImportRow:
    row_number: int
    sku: str
    name: str
    unit_code: str
    is_active: bool
    comment: str


@dataclass(frozen=True)
class ImportErrorDetail:
    row_number: int
    message: str


@dataclass(frozen=True)
class ItemImportResult:
    rows: list[ItemImportRow]
    errors: list[ImportErrorDetail]


@dataclass(frozen=True)
class ItemImportCommitResult:
    created_count: int
    errors: list[ImportErrorDetail]


REQUIRED_COLUMNS = {
    "Артикул": "Артикул обязателен",
    "Наименование": "Наименование обязательно",
    "Единица": "Единица обязательна",
}


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _as_bool(value) -> bool:
    text = _as_text(value).lower()
    if text in {"нет", "no", "false", "0"}:
        return False
    return True


def _header_map(header_row) -> dict[str, int]:
    return {_as_text(value): index for index, value in enumerate(header_row)}


def _cell(row, headers: dict[str, int], column: str) -> str:
    index = headers.get(column)
    if index is None or index >= len(row):
        return ""
    return _as_text(row[index])


def parse_items_import_workbook(file_obj: BinaryIO) -> ItemImportResult:
    workbook = load_workbook(file_obj, data_only=True, read_only=True)
    try:
        sheet = workbook["Номенклатура"] if "Номенклатура" in workbook.sheetnames else workbook.active
        rows_iter = sheet.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        headers = _header_map(header_row or [])

        rows: list[ItemImportRow] = []
        errors: list[ImportErrorDetail] = []

        for row_number, raw_row in enumerate(rows_iter, start=2):
            values = [_as_text(value) for value in raw_row]
            if not any(values):
                continue

            sku = _cell(raw_row, headers, "Артикул")
            name = _cell(raw_row, headers, "Наименование")
            unit_code = _cell(raw_row, headers, "Единица")

            for column, message in REQUIRED_COLUMNS.items():
                if not _cell(raw_row, headers, column):
                    errors.append(ImportErrorDetail(row_number=row_number, message=message))

            rows.append(
                ItemImportRow(
                    row_number=row_number,
                    sku=sku,
                    name=name,
                    unit_code=unit_code,
                    is_active=_as_bool(_cell(raw_row, headers, "Активна")),
                    comment=_cell(raw_row, headers, "Комментарий"),
                )
            )

        return ItemImportResult(rows=rows, errors=errors)
    finally:
        workbook.close()


def validate_items_import_result(result: ItemImportResult) -> list[ImportErrorDetail]:
    errors = list(result.errors)
    seen_skus: set[str] = set()

    for row in result.rows:
        if row.sku:
            if row.sku in seen_skus:
                errors.append(ImportErrorDetail(row_number=row.row_number, message="Артикул повторяется в файле"))
            else:
                seen_skus.add(row.sku)
            if Item.objects.filter(sku=row.sku).exists():
                errors.append(ImportErrorDetail(row_number=row.row_number, message="Артикул уже существует"))

        if row.unit_code and not Unit.objects.filter(code=row.unit_code).exists():
            errors.append(ImportErrorDetail(row_number=row.row_number, message="Единица не найдена"))

    return errors


def commit_items_import(result: ItemImportResult) -> ItemImportCommitResult:
    errors = validate_items_import_result(result)
    if errors:
        return ItemImportCommitResult(created_count=0, errors=errors)

    units = Unit.objects.in_bulk([row.unit_code for row in result.rows], field_name="code")
    with transaction.atomic():
        for row in result.rows:
            Item.objects.create(
                sku=row.sku,
                name=row.name,
                unit=units[row.unit_code],
                is_active=row.is_active,
                notes=row.comment,
            )

    return ItemImportCommitResult(created_count=len(result.rows), errors=[])
