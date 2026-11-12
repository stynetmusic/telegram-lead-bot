"""Точка входа. Без BOT_TOKEN процесс завершается и не подключается к Telegram."""

from __future__ import annotations

import argparse
import asyncio
import sys

from leadbot.config import Settings, load_settings, render_check_report
from leadbot.errors import BotStartupError, ConfigError, StorageError
from leadbot.repository import LeadRepository


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="leadbot",
        description="Telegram-бот для учёта клиентских заявок",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить конфигурацию и базу, не подключаясь к Telegram",
    )
    return parser.parse_args(argv)


def prepare_storage(settings: Settings) -> None:
    try:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        settings.export_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(
            f"Не удалось создать каталоги данных: {exc.strerror or 'ошибка файловой системы'}"
        ) from exc
    if settings.database_path.exists() and not settings.database_path.is_file():
        raise ConfigError("DATABASE_PATH указывает не на файл.")
    probe = settings.export_dir / ".write_probe"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise ConfigError(
            f"Каталог экспорта недоступен для записи: {exc.strerror or 'ошибка'}"
        ) from exc
    try:
        LeadRepository(settings.database_path)
    except StorageError as exc:
        raise ConfigError("Не удалось подготовить базу данных. Проверьте DATABASE_PATH.") from exc


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = load_settings()
        prepare_storage(settings)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2
    if args.check:
        print(render_check_report(settings))
        return 0
    from leadbot.runtime import run_bot

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        print("\nОстановка бота.")
        return 0
    except BotStartupError as exc:
        print(f"Ошибка запуска: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print(
            "Бот остановился из-за непредвиденной ошибки. "
            "Токен в это сообщение не входит.",
            file=sys.stderr,
        )
        return 1
    return 0


def console_main() -> None:
    raise SystemExit(main())
