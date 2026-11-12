from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from leadbot.cli import main
from tests.conftest import ENV_KEYS
from tests.helpers import make_token


def _clean_environment(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in ENV_KEYS:
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["DATABASE_PATH"] = str(tmp_path / "leads.db")
    env["EXPORT_DIR"] = str(tmp_path / "exports")
    return env


def test_cli_without_token_exits_with_message(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert "BOT_TOKEN" not in os.environ
    code = main([])
    captured = capsys.readouterr()
    assert code == 2
    assert "BOT_TOKEN" in captured.err
    assert "Traceback" not in captured.err
    assert not (tmp_path / "data").exists()


def test_invalid_token_is_not_printed(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "this-value-must-stay-hidden"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", secret)
    code = main([])
    captured = capsys.readouterr()
    assert code == 2
    assert secret not in captured.out
    assert secret not in captured.err


def test_check_does_not_start_bot(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token = make_token()

    async def forbidden(settings: object) -> None:
        raise AssertionError("подключение к Telegram не должно запускаться")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", token)
    monkeypatch.setenv("ADMIN_IDS", "42")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "leads.db"))
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setattr("leadbot.runtime.run_bot", forbidden)
    code = main(["--check"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Конфигурация корректна." in captured.out
    assert "Подключение к Telegram не выполняется." in captured.out
    assert "42" in captured.out
    assert token not in captured.out
    assert token not in captured.err
    assert (tmp_path / "leads.db").is_file()


def test_start_delegates_to_runtime_without_network(
    clean_env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = make_token()
    seen: dict[str, object] = {}

    async def fake_run(settings: object) -> None:
        seen["token"] = getattr(settings, "bot_token", None)
        seen["called"] = True

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", token)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "leads.db"))
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setattr("leadbot.runtime.run_bot", fake_run)
    code = main([])
    assert code == 0
    assert seen["called"] is True
    assert seen["token"] == token


def test_module_entrypoint_reports_missing_token(tmp_path: Path) -> None:
    env = _clean_environment(tmp_path)
    assert "BOT_TOKEN" not in env
    result = subprocess.run(
        [sys.executable, "-m", "leadbot"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "BOT_TOKEN" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout


def test_module_check_does_not_print_token(tmp_path: Path) -> None:
    token = make_token()
    env = _clean_environment(tmp_path)
    env["BOT_TOKEN"] = token
    env["ADMIN_IDS"] = "15"
    result = subprocess.run(
        [sys.executable, "-m", "leadbot", "--check"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0
    assert "Конфигурация корректна." in result.stdout
    assert token not in result.stdout
    assert token not in result.stderr
    assert "Traceback" not in result.stderr
