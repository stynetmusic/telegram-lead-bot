"""Общие фикстуры. Тесты не используют настоящий токен и Telegram API."""

from __future__ import annotations

from pathlib import Path

import pytest

from leadbot.config import Settings
from leadbot.repository import LeadRepository
from tests.helpers import make_token

ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = (
    "BOT_TOKEN",
    "ADMIN_IDS",
    "DATABASE_PATH",
    "EXPORT_DIR",
    "BUSINESS_NAME",
    "TIMEZONE",
    "LOG_LEVEL",
    "LOG_FILE",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_token=make_token(),
        admin_ids=frozenset({1}),
        database_path=tmp_path / "leads.db",
        export_dir=tmp_path / "exports",
        business_name="Сервис заявок",
        timezone="Europe/Moscow",
        log_level="INFO",
        log_file=None,
    )


@pytest.fixture
def repo(settings: Settings) -> LeadRepository:
    return LeadRepository(settings.database_path)
