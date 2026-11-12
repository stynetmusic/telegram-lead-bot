from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from leadbot.config import default_database_path, default_export_dir, default_work_dir, load_settings
from leadbot.errors import ConfigError
from leadbot.logging_setup import RedactingFormatter, setup_logging
from tests.helpers import make_token


def test_missing_token(clean_env: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError, match="BOT_TOKEN") as exc:
        load_settings()
    assert "AA" not in str(exc.value)


def test_invalid_token_is_not_echoed(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "super-secret-but-invalid"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", secret)
    with pytest.raises(ConfigError, match="неверный формат") as exc:
        load_settings()
    assert secret not in str(exc.value)


def test_settings_repr_hides_token(settings) -> None:
    rendered = f"{settings!r} {settings}"
    assert settings.bot_token not in rendered
    assert "bot_token" not in rendered


def test_env_file_and_existing_environment(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = make_token()
    other = "100000002:" + ("B" * 35)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# комментарий",
                f'export BOT_TOKEN="{token}"',
                "ADMIN_IDS=7, 7, 8",
                "BUSINESS_NAME=Мастерская",
                "TIMEZONE=Europe/Moscow",
                "LOG_LEVEL=warning",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    loaded = load_settings(env_file)
    assert loaded.bot_token == token
    assert loaded.admin_ids == frozenset({7, 8})
    assert loaded.business_name == "Мастерская"
    assert loaded.log_level == "WARNING"

    monkeypatch.setenv("BOT_TOKEN", other)
    overridden = load_settings(env_file)
    assert overridden.bot_token == other


def test_bad_admin_ids_timezone_and_log_level_do_not_echo_values(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", make_token())
    monkeypatch.setenv("ADMIN_IDS", "10,secret-value")
    with pytest.raises(ConfigError, match="ADMIN_IDS") as admin_error:
        load_settings(env_file=None)
    assert "secret-value" not in str(admin_error.value)

    monkeypatch.setenv("ADMIN_IDS", "10")
    monkeypatch.setenv("TIMEZONE", "Not/AZone")
    with pytest.raises(ConfigError, match="TIMEZONE") as zone_error:
        load_settings(env_file=None)
    assert "Not/AZone" not in str(zone_error.value)

    monkeypatch.setenv("TIMEZONE", "Europe/Moscow")
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        load_settings(env_file=None)


def test_default_paths_stay_outside_the_project_and_are_not_created(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = default_work_dir()
    database = default_database_path()
    export = default_export_dir()
    before = (work.exists(), database.exists(), export.exists())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", make_token())
    loaded = load_settings(env_file=None)
    project = Path(__file__).resolve().parents[1]
    assert loaded.database_path == database.resolve()
    assert loaded.export_dir == export.resolve()
    assert loaded.database_path.name == "leads.db"
    assert loaded.export_dir.name == "exports"
    assert "TelegramLeadBot" in loaded.database_path.parts
    assert project not in loaded.database_path.parents
    assert project not in loaded.export_dir.parents
    assert (work.exists(), database.exists(), export.exists()) == before
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "leads.db").exists()


def test_database_and_export_paths_follow_environment_without_creating_files(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", make_token())
    monkeypatch.setenv("DATABASE_PATH", "custom/leads.db")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "out"))
    loaded = load_settings(env_file=None)
    assert loaded.database_path == (tmp_path / "custom" / "leads.db").resolve()
    assert loaded.export_dir == (tmp_path / "out").resolve()
    assert not loaded.database_path.exists()
    assert not loaded.export_dir.exists()


def test_formatter_redacts_token_in_message_and_traceback() -> None:
    token = make_token()
    formatter = RedactingFormatter(secrets=[token], fmt="%(message)s")
    record = logging.LogRecord(
        name="leadbot",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="value=%s",
        args=(token,),
        exc_info=None,
    )
    assert token not in formatter.format(record)
    try:
        raise RuntimeError(token)
    except RuntimeError:
        broken = logging.LogRecord(
            name="leadbot",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="сбой",
            args=(),
            exc_info=sys.exc_info(),
        )
    rendered = formatter.format(broken)
    assert token not in rendered
    assert "***" in rendered


def test_log_file_does_not_contain_token(tmp_path: Path, settings) -> None:
    log_path = tmp_path / "logs" / "bot.log"
    logged = replace(settings, log_file=log_path)
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    try:
        setup_logging(logged)
        logging.getLogger("leadbot").error("проверка %s", logged.bot_token)
    finally:
        for handler in list(root.handlers):
            handler.close()
        root.handlers.clear()
        for handler in previous_handlers:
            root.addHandler(handler)
        root.setLevel(previous_level)
    text = log_path.read_text(encoding="utf-8")
    assert logged.bot_token not in text
    assert "***" in text
