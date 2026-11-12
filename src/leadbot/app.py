"""Сборка диспетчера aiogram."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from leadbot.config import Settings
from leadbot.handlers.admin import router as admin_router
from leadbot.handlers.client import router as client_router
from leadbot.handlers.fallback import router as fallback_router
from leadbot.middlewares import PrivateChatMiddleware, on_unexpected_error
from leadbot.repository import LeadRepository


def build_dispatcher(settings: Settings, repo: LeadRepository) -> Dispatcher:
    # SimpleEventIsolation есть в aiogram 3.31: события одного пользователя
    # не обрабатываются параллельно. Вместе с замком в on_save это не даёт
    # двум нажатиям «Сохранить» создать две заявки.
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
    )
    dispatcher["settings"] = settings
    dispatcher["repo"] = repo
    dispatcher.message.outer_middleware(PrivateChatMiddleware())
    dispatcher.callback_query.outer_middleware(PrivateChatMiddleware())
    dispatcher.include_router(client_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(fallback_router)
    dispatcher.errors.register(on_unexpected_error)
    return dispatcher
