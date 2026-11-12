from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from leadbot.export import create_export_file, excel_text, export_leads
from leadbot.models import Lead, LeadStatus
from leadbot.repository import LeadRepository


def _lead(**overrides: object) -> Lead:
    payload: dict[str, object] = {
        "id": 1,
        "user_id": 100,
        "username": "client_user",
        "client_name": "Анна",
        "phone": "+79990001122",
        "description": "Тестовая заявка на консультацию",
        "status": LeadStatus.IN_PROGRESS,
        "created_at": datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 11, 12, 12, 30, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return Lead(**payload)  # type: ignore[arg-type]


def test_excel_text_neutralizes_formulas() -> None:
    assert excel_text("=1+1").startswith("'")
    assert excel_text("+79990001122").startswith("'")
    assert excel_text("-cmd").startswith("'")
    assert excel_text("@SUM(A1)").startswith("'")
    assert excel_text("Обычный текст") == "Обычный текст"
    assert "\x00" not in excel_text("а\x00б")


def test_export_contains_leads_and_russian_status(tmp_path: Path) -> None:
    zone = ZoneInfo("Europe/Moscow")
    dangerous = "=CMD()|тестовая заявка"
    path = tmp_path / "leads.xlsx"
    export_leads(
        [
            _lead(description=dangerous),
            _lead(id=2, client_name="Борис", phone="+79990001123", status=LeadStatus.DONE),
        ],
        path,
        zone,
    )
    workbook = load_workbook(path)
    sheet = workbook.active
    assert sheet.title == "Заявки"
    assert [cell.value for cell in sheet[1]] == [
        "Номер",
        "Создана",
        "Обновлена",
        "Статус",
        "Имя",
        "Телефон",
        "Описание",
        "Telegram ID",
        "Username",
    ]
    assert sheet.max_row == 3
    assert str(sheet["A2"].value) == "1"
    assert sheet["D2"].value == "В работе"
    assert sheet["D3"].value == "Выполнена"
    assert sheet["B2"].value == "12.11.2026 13:00"
    assert "79990001122" in str(sheet["F2"].value)
    assert sheet["F2"].data_type != "f"
    assert sheet["G2"].data_type != "f"
    assert "CMD()" in str(sheet["G2"].value)
    assert not str(sheet["G2"].value).startswith("=")
    assert sheet.freeze_panes == "A2"
    assert workbook.properties.creator == "telegram-lead-bot"
    workbook.close()


def test_export_from_repository_roundtrip(tmp_path: Path, repo: LeadRepository) -> None:
    repo.create_lead(
        user_id=100,
        username=None,
        client_name="Анна",
        phone="+7 999 000 11 22",
        description="Нужна консультация по услуге",
    )
    path = create_export_file(repo.list_all(), tmp_path, ZoneInfo("UTC"))
    workbook = load_workbook(path)
    sheet = workbook.active
    assert sheet.max_row == 2
    assert sheet["E2"].value == "Анна"
    assert sheet["D2"].value == "Новая"
    workbook.close()


def test_empty_export_has_header_only(tmp_path: Path) -> None:
    path = export_leads([], tmp_path / "empty.xlsx", ZoneInfo("UTC"))
    workbook = load_workbook(path)
    sheet = workbook.active
    assert sheet.max_row == 1
    assert sheet["A1"].value == "Номер"
    workbook.close()


def test_export_names_do_not_overwrite(tmp_path: Path) -> None:
    moment = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    zone = ZoneInfo("UTC")
    first = create_export_file([], tmp_path, zone, moment)
    second = create_export_file([], tmp_path, zone, moment)
    assert first != second
    assert first.exists() and second.exists()
