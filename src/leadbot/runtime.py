"""Запуск long polling. Модуль импортируется только когда бота действительно запускают."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from leadbot.app import build_dispatcher
from leadbot.config import Settings
from leadbot.errors import BotStartupError
from leadbot.logging_setup import setup_logging
from leadbot.repository import LeadRepository

logger = logging.getLogger("leadbot")

_CLIENT_COMMANDS = (
    BotCommand(command="start", description="Приветствие и инструкция"),
    BotCommand(command="new", description="Создать заявку"),
    BotCommand(command="cancel", description="Отменить заполнение"),
    BotCommand(command="id", description="Показать мой Telegram ID"),
)
_ADMIN_COMMANDS = _CLIENT_COMMANDS + (
    BotCommand(command="admin", description="Меню администратора"),
    BotCommand(command="leads", description="Последние заявки"),
    BotCommand(command="export", description="Выгрузить заявки в Excel"),
)


async def setup_commands(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands(list(_CLIENT_COMMANDS), scope=BotCommandScopeDefault())
    for admin_id in sorted(settings.admin_ids):
        try:
            await bot.set_my_commands(
                list(_ADMIN_COMMANDS),
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except TelegramAPIError:
            logger.warning("Не удалось обновить команды администратора %s", admin_id)


async def run_bot(settings: Settings) -> None:
    setup_logging(settings)
    repo = LeadRepository(settings.database_path)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = build_dispatcher(settings, repo)
    logger.info("Бот запускается. Администраторов: %s", len(settings.admin_ids))
    try:
        try:
            await setup_commands(bot, settings)
            await dispatcher.start_polling(bot)
        except TelegramUnauthorizedError:
            logger.error("Telegram отклонил токен авторизации")
            raise BotStartupError(
                "Telegram отклонил токен. Проверьте BOT_TOKEN в .env. "
                "Значение токена не записывается."
            ) from None
    finally:
        await bot.session.close()
