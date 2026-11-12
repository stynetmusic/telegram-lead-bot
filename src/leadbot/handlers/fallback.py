"""Ответы на сообщения вне сценария заявки."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from leadbot.handlers.client import NewLead

router = Router(name="fallback")


@router.message(StateFilter(NewLead), F.text.startswith("/"))
async def unknown_command_during_flow(message: Message) -> None:
    await message.answer(
        "Такой команды нет. Продолжите заполнение заявки или отправьте /cancel."
    )


@router.message(F.contact)
async def contact_outside_flow(message: Message) -> None:
    await message.answer("Контакт получен вне заявки. Начните с команды /new.")


@router.message(F.text)
async def plain_text(message: Message) -> None:
    text = message.text or ""
    if text.startswith("/"):
        await message.answer("Неизвестная команда. Отправьте /start, чтобы увидеть подсказку.")
        return
    await message.answer("Я принимаю заявки. Отправьте /new, чтобы начать, или /start для подсказки.")
