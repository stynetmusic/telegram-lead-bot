"""Журнал без токена и без текста заявок."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from leadbot.config import Settings


class RedactingFormatter(logging.Formatter):
    """Убирает известные секреты из уже собранной строки журнала, включая traceback."""

    def __init__(self, secrets: Iterable[str], *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._secrets = [secret for secret in secrets if secret]

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        for secret in self._secrets:
            rendered = rendered.replace(secret, "***")
        return rendered


def setup_logging(settings: Settings) -> None:
    formatter = RedactingFormatter(
        secrets=[settings.bot_token],
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)
    if settings.log_file is not None:
        settings.log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(settings.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("leadbot").info(
        "Журнал включён. Уровень: %s. Администраторов: %s",
        settings.log_level,
        len(settings.admin_ids),
    )
