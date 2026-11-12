"""Хранение заявок в SQLite. Все значения передаются параметрами, не через склейку SQL."""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from leadbot.errors import InvalidStatus, LeadNotFound, StorageError, ValidationError
from leadbot.models import Lead, LeadStatus
from leadbot.validation import (
    clean_username,
    require_user_id,
    validate_description,
    validate_name,
    validate_phone,
)

Clock = Callable[[], datetime]
logger = logging.getLogger("leadbot")

# Режимы с журналом отката. memory и off не сохраняют транзакцию при сбое.
_DURABLE_FALLBACK_MODES = frozenset({"delete", "truncate", "persist"})
_MODE_WORD = re.compile(r"[a-z]{1,16}")
_SECRET_IN_DB_ERROR = re.compile(r"\d{6,}:[A-Za-z0-9_-]{10,}")
_LONG_NUMBER = re.compile(r"\+?\d{10,15}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL CHECK (user_id > 0),
    username TEXT,
    client_name TEXT NOT NULL CHECK (length(trim(client_name)) > 0),
    phone TEXT NOT NULL CHECK (length(trim(phone)) > 0),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    status TEXT NOT NULL CHECK (status IN ('new', 'in_progress', 'done')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_user_id ON leads(user_id);
"""


def _mode_name(row: object) -> str:
    if row is None:
        return ""
    try:
        value = row[0]  # type: ignore[index]
    except (TypeError, IndexError, KeyError):
        return ""
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def enable_wal(connection: sqlite3.Connection) -> str:
    """Включить WAL и вернуть режим, который SQLite реально оставил.

    При неудаче SQLite часто не бросает исключение, а возвращает прежний режим.
    """

    row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
    return _mode_name(row)


def read_journal_mode(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA journal_mode").fetchone()
    return _mode_name(row)


def _safe_sqlite_text(exc: BaseException) -> str:
    raw = "".join(char for char in str(exc) if 32 <= ord(char) < 127)
    raw = _SECRET_IN_DB_ERROR.sub("***", raw)
    raw = _LONG_NUMBER.sub("***", raw)
    raw = " ".join(raw.split())
    if len(raw) > 160:
        raw = raw[:160]
    return raw or type(exc).__name__


def _shown_mode(mode: str) -> str:
    if _MODE_WORD.fullmatch(mode):
        return mode
    return "неизвестный"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise StorageError("Внутренняя дата без часового пояса.")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def from_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StorageError("В базе повреждена дата заявки.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class LeadRepository:
    def __init__(self, db_path: Path, clock: Clock | None = None) -> None:
        self.db_path = db_path
        self._clock = clock or utc_now
        self._journal_notice: str | None = None
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError("Не удалось создать каталог базы данных.") from exc
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = sqlite3.connect(self.db_path, timeout=5.0)
        except sqlite3.Error as exc:
            raise StorageError("Не удалось открыть базу данных.") from exc
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            self._configure_journal(connection)
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise StorageError("Не удалось выполнить операцию с базой данных.") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _configure_journal(self, connection: sqlite3.Connection) -> None:
        reason = ""
        try:
            mode = enable_wal(connection)
        except sqlite3.Error as exc:
            reason = f"{type(exc).__name__}: {_safe_sqlite_text(exc)}"
            try:
                mode = read_journal_mode(connection)
            except sqlite3.Error as check_exc:
                check_reason = f"{type(check_exc).__name__}: {_safe_sqlite_text(check_exc)}"
                logger.warning(
                    "Не удалось включить WAL (%s) и прочитать режим журнала (%s).",
                    reason,
                    check_reason,
                )
                raise StorageError(
                    "Не удалось определить режим журнала SQLite. Проверьте диск базы данных."
                ) from check_exc
        if mode == "wal":
            return
        if not reason:
            reason = f"PRAGMA journal_mode = WAL вернул режим {_shown_mode(mode)}"
        self._report_journal_mode(mode, reason)

    def _report_journal_mode(self, mode: str, reason: str) -> None:
        notice = f"{mode}|{reason}"
        if notice == self._journal_notice:
            return
        self._journal_notice = notice
        shown = _shown_mode(mode)
        if mode in _DURABLE_FALLBACK_MODES:
            logger.warning(
                "Режим WAL не включён. Причина: %s. SQLite работает в режиме %s.",
                reason,
                shown,
            )
            return
        logger.warning(
            "Режим WAL не включён. Причина: %s. Режим журнала: %s. "
            "Операция остановлена, чтобы не работать в неизвестном режиме.",
            reason,
            shown,
        )
        raise StorageError(
            "Не удалось включить журнал SQLite в безопасном режиме. Проверьте диск базы данных."
        )

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def create_lead(
        self,
        *,
        user_id: int,
        username: str | None,
        client_name: str,
        phone: str,
        description: str,
    ) -> Lead:
        safe_user_id = require_user_id(user_id)
        safe_name = validate_name(client_name)
        safe_phone = validate_phone(phone)
        safe_description = validate_description(description)
        safe_username = clean_username(username)
        moment = self._clock()
        created = to_iso(moment)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO leads (
                    user_id, username, client_name, phone, description, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_user_id,
                    safe_username,
                    safe_name,
                    safe_phone,
                    safe_description,
                    LeadStatus.NEW.value,
                    created,
                    created,
                ),
            )
            lead_id = cursor.lastrowid
        if not isinstance(lead_id, int):
            raise StorageError("Не удалось получить номер новой заявки.")
        lead = self.get_lead(lead_id)
        if lead is None:
            raise StorageError("Заявка не найдена сразу после сохранения.")
        return lead

    def get_lead(self, lead_id: int) -> Lead | None:
        if isinstance(lead_id, bool) or not isinstance(lead_id, int) or lead_id < 1:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, user_id, username, client_name, phone, description,
                       status, created_at, updated_at
                FROM leads
                WHERE id = ?
                """,
                (lead_id,),
            ).fetchone()
        if row is None:
            return None
        return self._map(row)

    def list_recent(self, limit: int = 10) -> list[Lead]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValidationError("Можно запросить от 1 до 50 последних заявок.")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, username, client_name, phone, description,
                       status, created_at, updated_at
                FROM leads
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._map(row) for row in rows]

    def list_all(self) -> list[Lead]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, username, client_name, phone, description,
                       status, created_at, updated_at
                FROM leads
                ORDER BY id ASC
                """
            ).fetchall()
        return [self._map(row) for row in rows]

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM leads").fetchone()
        if row is None:
            return 0
        return int(row["total"])

    def update_status(self, lead_id: int, status: LeadStatus) -> Lead:
        if not isinstance(status, LeadStatus):
            raise InvalidStatus("Неизвестный статус заявки.")
        current = self.get_lead(lead_id)
        if current is None:
            raise LeadNotFound(f"Заявка №{lead_id} не найдена.")
        if current.status is status:
            return current
        updated_at = to_iso(self._clock())
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, updated_at, lead_id),
            )
            if cursor.rowcount != 1:
                raise LeadNotFound(f"Заявка №{lead_id} не найдена.")
        lead = self.get_lead(lead_id)
        if lead is None:
            raise LeadNotFound(f"Заявка №{lead_id} не найдена.")
        return lead

    def _map(self, row: sqlite3.Row) -> Lead:
        try:
            status = LeadStatus(row["status"])
        except ValueError as exc:
            raise StorageError("В базе найдена заявка с неизвестным статусом.") from exc
        return Lead(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            username=row["username"],
            client_name=row["client_name"],
            phone=row["phone"],
            description=row["description"],
            status=status,
            created_at=from_iso(row["created_at"]),
            updated_at=from_iso(row["updated_at"]),
        )
