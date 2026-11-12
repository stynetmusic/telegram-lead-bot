from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from leadbot.errors import InvalidStatus, LeadNotFound, StorageError, ValidationError
from leadbot.models import LeadStatus
from leadbot.repository import LeadRepository


def _create(repo: LeadRepository, **overrides: object):
    payload = {
        "user_id": 100,
        "username": "client_user",
        "client_name": "Анна",
        "phone": "+79990001122",
        "description": "Тестовая заявка на консультацию",
    }
    payload.update(overrides)
    return repo.create_lead(**payload)  # type: ignore[arg-type]


def test_create_lead_assigns_unique_numbers_and_new_status(repo: LeadRepository) -> None:
    first = _create(repo)
    second = _create(repo, client_name="Борис", phone="+79990001123")
    assert first.id == 1
    assert second.id == 2
    assert first.id != second.id
    assert first.status is LeadStatus.NEW
    assert first.number == "1"
    assert repo.count() == 2


def test_required_fields_are_rejected(repo: LeadRepository) -> None:
    with pytest.raises(ValidationError, match="Имя"):
        _create(repo, client_name=" ")
    with pytest.raises(ValidationError, match="Телефон"):
        _create(repo, phone="")
    with pytest.raises(ValidationError, match="Описание"):
        _create(repo, description="   ")
    with pytest.raises(ValidationError):
        _create(repo, user_id=0)
    assert repo.count() == 0


def test_leads_persist_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "leads.db"
    original = LeadRepository(path)
    created = _create(original, description="Заявка должна пережить перезапуск")
    reopened = LeadRepository(path)
    loaded = reopened.get_lead(created.id)
    assert loaded == created
    assert reopened.count() == 1


def test_recent_leads_come_newest_first(repo: LeadRepository) -> None:
    _create(repo, client_name="Анна")
    _create(repo, client_name="Борис", phone="+79990001123")
    _create(repo, client_name="Вера", phone="+79990001124")
    recent = repo.list_recent(2)
    assert [lead.client_name for lead in recent] == ["Вера", "Борис"]
    assert [lead.id for lead in repo.list_all()] == [1, 2, 3]


def test_recent_limit_is_validated(repo: LeadRepository) -> None:
    with pytest.raises(ValidationError):
        repo.list_recent(0)
    with pytest.raises(ValidationError):
        repo.list_recent(51)


def test_status_change_and_unknown_lead(tmp_path: Path) -> None:
    moments = [
        datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 11, 12, 12, 30, tzinfo=timezone.utc),
    ]

    class Clock:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> datetime:
            index = min(self.calls, len(moments) - 1)
            self.calls += 1
            return moments[index]

    repo = LeadRepository(tmp_path / "leads.db", clock=Clock())
    lead = _create(repo)
    same = repo.update_status(lead.id, LeadStatus.NEW)
    assert same.updated_at == lead.updated_at
    changed = repo.update_status(lead.id, LeadStatus.IN_PROGRESS)
    assert changed.status is LeadStatus.IN_PROGRESS
    assert changed.created_at == moments[0]
    assert changed.updated_at == moments[1]
    done = repo.update_status(lead.id, LeadStatus.DONE)
    assert done.status is LeadStatus.DONE
    assert done.status.label == "Выполнена"
    with pytest.raises(InvalidStatus):
        repo.update_status(lead.id, "done")  # type: ignore[arg-type]
    with pytest.raises(LeadNotFound):
        repo.update_status(999, LeadStatus.DONE)
    assert repo.get_lead(0) is None
    assert repo.get_lead(999) is None


def test_sql_injection_payload_is_stored_as_text(repo: LeadRepository) -> None:
    payload = "Robert'); DROP TABLE leads;--"
    lead = _create(repo, description=payload + " тестовая заявка")
    loaded = repo.get_lead(lead.id)
    assert loaded is not None
    assert loaded.description == payload + " тестовая заявка"
    second = _create(repo, client_name="Борис", phone="+79990001123")
    assert second.id == 2
    assert repo.count() == 2


def test_invalid_username_is_not_stored(repo: LeadRepository) -> None:
    lead = _create(repo, username="не имя")
    assert lead.username is None


def test_wal_error_is_logged_without_personal_data(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phone = "+79990001122"

    def broken(connection: object) -> str:
        raise sqlite3.OperationalError(f"disk I/O error {phone}")

    monkeypatch.setattr("leadbot.repository.enable_wal", broken)
    with caplog.at_level(logging.WARNING, logger="leadbot"):
        repo = LeadRepository(tmp_path / "leads.db")
        _create(repo, phone=phone, description="Скрытое описание заявки")
    text = caplog.text
    assert "Режим WAL не включён" in text
    assert "OperationalError" in text
    assert "disk I/O error" in text
    assert phone not in text
    assert "79990001122" not in text
    assert "Анна" not in text
    assert "Скрытое описание" not in text
    assert text.count("Режим WAL не включён") == 1


def test_wal_silent_fallback_names_the_real_mode(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stayed_on_delete(connection: object) -> str:
        return "delete"

    monkeypatch.setattr("leadbot.repository.enable_wal", stayed_on_delete)
    with caplog.at_level(logging.WARNING, logger="leadbot"):
        LeadRepository(tmp_path / "leads.db")
    assert "PRAGMA journal_mode = WAL вернул режим delete" in caplog.text
    assert "работает в режиме delete" in caplog.text


def test_unknown_journal_mode_stops_and_does_not_echo_raw_value(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def garbage(connection: object) -> str:
        return "weird mode"

    monkeypatch.setattr("leadbot.repository.enable_wal", garbage)
    with caplog.at_level(logging.WARNING, logger="leadbot"):
        with pytest.raises(StorageError, match="безопасном режиме"):
            LeadRepository(tmp_path / "leads.db")
    assert "weird mode" not in caplog.text
    assert "неизвестный" in caplog.text
    assert "Операция остановлена" in caplog.text


def test_unreadable_journal_mode_logs_both_reasons(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_enable(connection: object) -> str:
        raise sqlite3.OperationalError("disk I/O error")

    def broken_read(connection: object) -> str:
        raise sqlite3.OperationalError("unable to read journal")

    monkeypatch.setattr("leadbot.repository.enable_wal", broken_enable)
    monkeypatch.setattr("leadbot.repository.read_journal_mode", broken_read)
    with caplog.at_level(logging.WARNING, logger="leadbot"):
        with pytest.raises(StorageError, match="определить режим"):
            LeadRepository(tmp_path / "leads.db")
    assert "disk I/O error" in caplog.text
    assert "unable to read journal" in caplog.text
    assert "OperationalError" in caplog.text


def test_queries_are_parameterized() -> None:
    source = (Path(__file__).resolve().parents[1] / "src/leadbot/repository.py").read_text(
        encoding="utf-8"
    )
    assert 'execute(f"' not in source
    assert "execute(f'" not in source
    assert "executescript(f" not in source
