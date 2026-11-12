"""Ограничение бота личными чатами и общий ответ на сбой."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.bases import CancelHandler, SkipHandler
from aiogram.types import ErrorEvent, Message

from leadbot.formatting import ERROR_TEXT, PRIVATE_ONLY_TEXT

logger = logging.getLogger("leadbot")


def event_chat(event: object) -> object | None:
    chat = getattr(event, "chat", None)
    if chat is not None:
        return chat
    message = getattr(event, "message", None)
    return getattr(message, "chat", None)


def chat_is_private(chat: object | None) -> bool:
    if chat is None:
        return True
    return getattr(chat, "type", "private") == "private"


class PrivateChatMiddleware(BaseMiddleware):
    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        if chat_is_private(event_chat(event)):
            return await handler(event, data)
        # У callback нет собственного chat: ответ уходит через всплывающее окно.
        if getattr(event, "chat", None) is None and getattr(event, "message", None) is not None:
            answer = getattr(event, "answer", None)
            if callable(answer):
                await answer(PRIVATE_ONLY_TEXT, show_alert=True)
            return None
        answer = getattr(event, "answer", None)
        if callable(answer):
            await answer(PRIVATE_ONLY_TEXT)
        return None


def extract_answer_target(event: ErrorEvent) -> Message | None:
    update = event.update
    if update.message is not None:
        return update.message
    if update.edited_message is not None:
        return update.edited_message
    callback = update.callback_query
    if callback is not None and isinstance(callback.message, Message):
        return callback.message
    return None


async def on_unexpected_error(event: ErrorEvent) -> None:
    # В журнал пишется только тип ошибки: текст исключения может содержать данные заявки.
    logger.error("Необработанная ошибка: %s", type(event.exception).__name__)
    if isinstance(event.exception, (SkipHandler, CancelHandler)):
        return
    target = extract_answer_target(event)
    if target is None:
        return
    try:
        await target.answer(ERROR_TEXT)
    except Exception:
        logger.error("Не удалось отправить сообщение об ошибке")
