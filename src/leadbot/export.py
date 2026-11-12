"""Выгрузка заявок в Excel."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from leadbot.errors import StorageError
from leadbot.models import Lead

_HEADERS = (
    "Номер",
    "Создана",
    "Обновлена",
    "Статус",
    "Имя",
    "Телефон",
    "Описание",
    "Telegram ID",
    "Username",
)
_WIDTHS = (12, 20, 20, 16, 28, 22, 60, 18, 24)
# Excel воспринимает эти символы в начале ячейки как формулу.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def excel_text(value: object) -> str:
    """Превратить значение в текст и нейтрализовать формульную инъекцию."""

    if value is None:
        return ""
    text = str(value).replace("\x00", "")
    if len(text) > 32767:
        text = text[:32764] + "..."
    if text.startswith(_FORMULA_PREFIXES):
        text = "'" + text
    return text


def assign_text(cell: object, value: object) -> None:
    safe = excel_text(value)
    setter = getattr(cell, "set_explicit_value", None)
    if callable(setter):
        setter(safe, data_type="s")
    else:
        cell.value = safe  # type: ignore[attr-defined]
        if getattr(cell, "data_type", None) == "f":
            cell.data_type = "s"  # type: ignore[attr-defined]
    cell.number_format = "@"  # type: ignore[attr-defined]


def format_export_datetime(value: datetime, zone: ZoneInfo) -> str:
    moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def unique_export_path(export_dir: Path, moment: datetime | None = None) -> Path:
    stamp = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc)
    base = f"leads_{stamp.strftime('%Y%m%d_%H%M%S')}"
    candidate = export_dir / f"{base}.xlsx"
    counter = 1
    while candidate.exists():
        candidate = export_dir / f"{base}_{counter}.xlsx"
        counter += 1
    return candidate


def export_leads(leads: list[Lead], destination: Path, zone: ZoneInfo) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Заявки"
    _write_header(sheet)
    for row_index, lead in enumerate(leads, start=2):
        values = (
            str(lead.id),
            format_export_datetime(lead.created_at, zone),
            format_export_datetime(lead.updated_at, zone),
            lead.status.label,
            lead.client_name,
            lead.phone,
            lead.description,
            str(lead.user_id),
            lead.username or "",
        )
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row_index, column)
            assign_text(cell, value)
            cell.alignment = Alignment(vertical="top", wrap_text=column == 7)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:I{max(sheet.max_row, 1)}"
    workbook.properties.creator = "telegram-lead-bot"
    workbook.properties.title = "Заявки"
    workbook.properties.subject = ""
    workbook.properties.description = "Экспорт заявок telegram-lead-bot"
    try:
        workbook.save(destination)
    except OSError as exc:
        raise StorageError("Не удалось записать файл Excel.") from exc
    finally:
        workbook.close()
    return destination


def create_export_file(
    leads: list[Lead],
    export_dir: Path,
    zone: ZoneInfo,
    moment: datetime | None = None,
) -> Path:
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageError("Не удалось создать каталог экспорта.") from exc
    destination = unique_export_path(export_dir, moment)
    return export_leads(leads, destination, zone)


def _write_header(sheet: Worksheet) -> None:
    header_font = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    thin = Border(
        left=Side(style="thin", color="D9E2F3"),
        right=Side(style="thin", color="D9E2F3"),
        top=Side(style="thin", color="D9E2F3"),
        bottom=Side(style="thin", color="D9E2F3"),
    )
    for column, title in enumerate(_HEADERS, start=1):
        cell = sheet.cell(1, column, title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin
        sheet.column_dimensions[get_column_letter(column)].width = _WIDTHS[column - 1]
    sheet.row_dimensions[1].height = 22
    sheet.sheet_view.showGridLines = False
