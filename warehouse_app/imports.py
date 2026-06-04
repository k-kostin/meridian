from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from openpyxl import load_workbook


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
