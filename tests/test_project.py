from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"\d{6,15}:[A-Za-z0-9_-]{35}")
SKIP_DIRS = {".venv", "venv", ".pytest_cache", ".pip-cache", "__pycache__", ".git"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".txt", ".example"}
LOCAL_DATA_SUFFIXES = {
    ".db",
    ".db-journal",
    ".db-wal",
    ".db-shm",
    ".sqlite",
    ".sqlite3",
    ".xlsx",
    ".xls",
    ".log",
    ".pem",
    ".key",
}


def test_required_files_exist() -> None:
    required = [
        "README.md",
        "LICENSE",
        ".gitignore",
        ".env.example",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "src/leadbot/__init__.py",
        "src/leadbot/__main__.py",
        "src/leadbot/cli.py",
        "src/leadbot/config.py",
        "src/leadbot/repository.py",
        "src/leadbot/export.py",
        "src/leadbot/validation.py",
        "src/leadbot/permissions.py",
        "src/leadbot/handlers/client.py",
        "src/leadbot/handlers/admin.py",
        "tests/test_repository.py",
        "tests/test_handlers.py",
        "tests/test_export.py",
    ]
    missing = [item for item in required if not (ROOT / item).is_file()]
    assert missing == []


def test_license_is_mit_for_stynet() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text
    assert "Copyright (c) 2026 Stynet" in text


def test_gitignore_covers_secrets_database_logs_and_exports() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    rules = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for item in (".env", "*.db", "*.log", "data/", ".venv/", "*.xlsx", "*.sqlite"):
        assert item in rules
    assert ".env.example" not in rules


def test_env_example_has_no_real_token() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "BOT_TOKEN=" in text
    assert "ADMIN_IDS=" in text
    assert TOKEN_RE.search(text) is None
    assert "put-your-telegram-bot-token-here" in text


def test_readme_covers_required_topics() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8").casefold()
    for topic in (
        "назначение",
        "возможности",
        "структура",
        "установка",
        ".env",
        "botfather",
        "запуск",
        "/start",
        "/new",
        "/admin",
        "/leads",
        "/lead_",
        "/status_",
        "/export",
        "pytest",
        "безопасность",
        "ограничен",
    ):
        assert topic in text


def _is_local_secret(path: Path) -> bool:
    name = path.name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    return path.suffix.lower() in LOCAL_DATA_SUFFIXES


def _tracked_local_secrets() -> list[str]:
    if not (ROOT / ".git").is_dir():
        return []
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    tracked = [item.decode() for item in completed.stdout.split(b"\0") if item]
    unexpected: list[str] = []
    for relative in tracked:
        path = ROOT / relative
        if relative == "SESSION_NOTES.md" or relative.startswith("data/"):
            unexpected.append(relative)
        elif _is_local_secret(path):
            unexpected.append(relative)
    return unexpected


def test_repository_has_no_real_tokens_or_local_data() -> None:
    """Каталог .git допустим. Секреты и локальные рабочие данные — нет."""
    assert not (ROOT / ".env").exists()
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if _is_local_secret(path):
            offenders.append(relative)
            continue
        if path.name not in {".gitignore", ".env.example"} and path.suffix not in TEXT_SUFFIXES:
            if path.name != "LICENSE":
                continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if TOKEN_RE.search(text):
            offenders.append(relative)
    offenders.extend(_tracked_local_secrets())
    assert offenders == []
