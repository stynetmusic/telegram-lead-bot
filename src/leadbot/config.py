"""Загрузка настроек из окружения и файла .env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from leadbot.errors import ConfigError

# Секрет BotFather не фиксирован на 35 символах. ID остаётся числом, алфавит — прежним.
_TOKEN_RE = re.compile(r"\d{6,15}:[A-Za-z0-9_-]{35,64}")
_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_DEFAULT_BUSINESS_NAME = "Сервис заявок"


def default_work_dir() -> Path:
    """Каталог рабочих данных на внутреннем диске macOS, не рядом с исходниками."""

    return Path.home() / "Library" / "Application Support" / "Stynet" / "TelegramLeadBot"


def default_database_path() -> Path:
    return default_work_dir() / "leads.db"


def default_export_dir() -> Path:
    return default_work_dir() / "exports"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_path: Path
    export_dir: Path
    business_name: str
    timezone: str
    log_level: str
    log_file: Path | None = None

    def __repr__(self) -> str:
        return self._safe_text()

    def __str__(self) -> str:
        return self._safe_text()

    def _safe_text(self) -> str:
        # Токен намеренно не попадает в repr: объект могут записать в журнал.
        admins = ",".join(str(item) for item in sorted(self.admin_ids))
        return (
            "Settings("
            f"admin_ids={{{admins}}}, "
            f"database_path={self.database_path}, "
            f"export_dir={self.export_dir}, "
            f"business_name={self.business_name!r}, "
            f"timezone={self.timezone!r}, "
            f"log_level={self.log_level!r}, "
            f"log_file={self.log_file})"
        )


def load_env_file(path: Path) -> None:
    """Прочитать .env. Уже заданные переменные окружения не перезаписываются."""

    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Не удалось прочитать {path.name}: {exc.strerror or 'ошибка чтения'}"
        ) from exc
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            raise ConfigError(f"Некорректная строка в {path.name}:{line_number}")
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _ENV_KEY_RE.fullmatch(key):
            raise ConfigError(f"Некорректное имя переменной в {path.name}:{line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def parse_admin_ids(raw: str | None) -> frozenset[int]:
    if raw is None or not raw.strip():
        return frozenset()
    admin_ids: list[int] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if not item.isdigit():
            raise ConfigError("ADMIN_IDS должен содержать числовые Telegram ID через запятую.")
        value = int(item)
        if value <= 0:
            raise ConfigError("ADMIN_IDS содержит некорректный идентификатор.")
        admin_ids.append(value)
    return frozenset(admin_ids)


def parse_business_name(raw: str | None) -> str:
    if raw is None or not raw.strip():
        return _DEFAULT_BUSINESS_NAME
    name = re.sub(r"\s+", " ", raw).strip()
    if any(ord(char) < 32 for char in name):
        raise ConfigError("BUSINESS_NAME содержит недопустимые символы.")
    if not 2 <= len(name) <= 80:
        raise ConfigError("BUSINESS_NAME должен содержать от 2 до 80 символов.")
    return name


def parse_timezone(raw: str | None) -> str:
    name = (raw or "").strip() or "Europe/Moscow"
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError("TIMEZONE задан неверно. Пример: Europe/Moscow.") from exc
    return name


def parse_log_level(raw: str | None) -> str:
    level = (raw or "INFO").strip().upper()
    if level not in _LOG_LEVELS:
        raise ConfigError("LOG_LEVEL должен быть DEBUG, INFO, WARNING, ERROR или CRITICAL.")
    return level


def parse_path(raw: str | None, default: str) -> Path:
    value = (raw or "").strip() or default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def parse_optional_path(raw: str | None) -> Path | None:
    if raw is None or not raw.strip():
        return None
    return parse_path(raw, raw)


def load_settings(env_file: Path | None = Path(".env")) -> Settings:
    if env_file is not None:
        load_env_file(env_file)
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env и укажите токен бота. "
            "Токен в журнал не записывается."
        )
    if not _TOKEN_RE.fullmatch(token):
        raise ConfigError(
            "BOT_TOKEN имеет неверный формат. Ожидается токен вида 123456789:AA.... "
            "Значение не показано из соображений безопасности."
        )
    return Settings(
        bot_token=token,
        admin_ids=parse_admin_ids(os.environ.get("ADMIN_IDS")),
        database_path=parse_path(
            os.environ.get("DATABASE_PATH"),
            str(default_database_path()),
        ),
        export_dir=parse_path(os.environ.get("EXPORT_DIR"), str(default_export_dir())),
        business_name=parse_business_name(os.environ.get("BUSINESS_NAME")),
        timezone=parse_timezone(os.environ.get("TIMEZONE")),
        log_level=parse_log_level(os.environ.get("LOG_LEVEL")),
        log_file=parse_optional_path(os.environ.get("LOG_FILE")),
    )


def render_check_report(settings: Settings) -> str:
    admins = ", ".join(str(item) for item in sorted(settings.admin_ids)) or "не заданы"
    lines = [
        "Конфигурация корректна.",
        f"Сервис: {settings.business_name}",
        f"База данных: {settings.database_path}",
        f"Каталог экспорта: {settings.export_dir}",
        f"Администраторы: {admins}",
        f"Часовой пояс: {settings.timezone}",
        f"Уровень журнала: {settings.log_level}",
        "Подключение к Telegram не выполняется.",
    ]
    if settings.log_file is not None:
        lines.append(f"Файл журнала: {settings.log_file}")
    return "\n".join(lines)
