"""Сценарий клиента: приветствие и новая заявка."""

from __future__ import annotations

import asyncio
import html
import logging

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from leadbot.config import Settings
from leadbot.errors import PermissionDenied, StorageError, ValidationError
from leadbot.formatting import format_summary, saved_text, start_text
from leadbot.keyboards import (
    CALLBACK_CANCEL,
    CALLBACK_SAVE,
    CANCEL_BUTTON,
    confirm_keyboard,
    phone_keyboard,
    remove_keyboard,
)
from leadbot.permissions import authorize
from leadbot.repository import LeadRepository
from leadbot.validation import accept_contact, validate_description, validate_name, validate_phone

logger = logging.getLogger("leadbot")
router = Router(name="client")
# Замок на пользователя держится на всё подтверждение, включая запись в базу.
# Пока первое нажатие не закончилось, второе не проходит проверку состояния.
# Ключ включает цикл событий: новый запуск не должен брать замок закрытого цикла.
_confirmation_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _confirmation_lock(user_id: int) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), user_id)
    lock = _confirmation_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _confirmation_locks[key] = lock
    return lock


class NewLead(StatesGroup):
    name = State()
    phone = State()
    description = State()
    confirm = State()


def _skip_commands(message: Message) -> None:
    text = message.text or ""
    if text.startswith("/"):
        raise SkipHandler()


async def _cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Заполнение заявки отменено. Новую можно начать командой /new.",
        reply_markup=remove_keyboard(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    user = message.from_user
    is_admin = False
    if user is not None:
        try:
            authorize(user.id, settings.admin_ids)
        except PermissionDenied:
            is_admin = False
        else:
            is_admin = True
    await message.answer(start_text(settings.business_name, is_admin=is_admin))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await _cancel(message, state)


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось определить ваш Telegram ID.")
        return
    await message.answer(
        f"Ваш Telegram ID: <code>{user.id}</code>\n"
        "Чтобы выдать права администратора, добавьте этот номер в ADMIN_IDS и перезапустите бота."
    )


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewLead.name)
    await message.answer(
        "Новая заявка. Напишите имя клиента: от 2 до 80 символов.\n"
        "Чтобы прервать заполнение, отправьте /cancel.",
        reply_markup=remove_keyboard(),
    )


@router.message(NewLead.name, F.text)
async def on_name(message: Message, state: FSMContext) -> None:
    _skip_commands(message)
    try:
        name = validate_name(message.text or "")
    except ValidationError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await state.update_data(name=name)
    await state.set_state(NewLead.phone)
    await message.answer(
        "Нажмите «Поделиться контактом». Номер, набранный вручную, не принимается.",
        reply_markup=phone_keyboard(),
    )


@router.message(NewLead.name)
async def on_name_invalid(message: Message) -> None:
    await message.answer("Отправьте имя обычным текстом.")


@router.message(NewLead.phone, F.contact)
async def on_phone_contact(message: Message, state: FSMContext) -> None:
    contact = message.contact
    user = message.from_user
    if contact is None or user is None:
        await message.answer("Не удалось прочитать контакт.", reply_markup=phone_keyboard())
        return
    try:
        phone = accept_contact(contact.phone_number, contact.user_id, user.id)
    except ValidationError as exc:
        await message.answer(html.escape(str(exc)), reply_markup=phone_keyboard())
        return
    await state.update_data(phone=phone)
    await state.set_state(NewLead.description)
    await message.answer(
        "Опишите задачу: что нужно сделать. От 5 до 2000 символов.",
        reply_markup=remove_keyboard(),
    )


@router.message(NewLead.phone, F.text)
async def on_phone_text(message: Message, state: FSMContext) -> None:
    _skip_commands(message)
    if (message.text or "").strip() == CANCEL_BUTTON:
        await _cancel(message, state)
        return
    await message.answer(
        "Вводить номер вручную не нужно. Нажмите «Поделиться контактом».",
        reply_markup=phone_keyboard(),
    )


@router.message(NewLead.phone)
async def on_phone_invalid(message: Message) -> None:
    await message.answer(
        "На этом шаге нужна кнопка «Поделиться контактом».",
        reply_markup=phone_keyboard(),
    )


@router.message(NewLead.description, F.text)
async def on_description(message: Message, state: FSMContext) -> None:
    _skip_commands(message)
    try:
        description = validate_description(message.text or "")
    except ValidationError as exc:
        await message.answer(html.escape(str(exc)))
        return
    data = await state.update_data(description=description)
    name = str(data.get("name", ""))
    phone = str(data.get("phone", ""))
    await state.set_state(NewLead.confirm)
    await message.answer(
        format_summary(name, phone, description),
        reply_markup=confirm_keyboard(),
    )


@router.message(NewLead.description)
async def on_description_invalid(message: Message) -> None:
    await message.answer("Отправьте описание задачи текстом.")


@router.message(NewLead.confirm, F.text)
async def on_confirm_text(message: Message) -> None:
    _skip_commands(message)
    await message.answer("Нажмите «Сохранить» или «Отменить» под итогом заявки.")


@router.callback_query(F.data == CALLBACK_SAVE)
async def on_save(callback: CallbackQuery, state: FSMContext, repo: LeadRepository) -> None:
    user = callback.from_user
    # Нет числового ID — сериализуем отдельно, чтобы и этот редкий случай не шёл параллельно.
    lock_id = user.id if user is not None else 0
    async with _confirmation_lock(lock_id):
        if await state.get_state() != NewLead.confirm.state:
            await callback.answer("Сначала заполните заявку командой /new", show_alert=True)
            return
        data = await state.get_data()
        try:
            name = validate_name(str(data.get("name", "")))
            phone = validate_phone(str(data.get("phone", "")))
            description = validate_description(str(data.get("description", "")))
            if user is None:
                raise ValidationError("Не удалось определить отправителя.")
            lead = await asyncio.to_thread(
                repo.create_lead,
                user_id=user.id,
                username=user.username,
                client_name=name,
                phone=phone,
                description=description,
            )
        except ValidationError as exc:
            await callback.answer("Проверьте данные заявки", show_alert=True)
            if callback.message is not None:
                await callback.message.answer(html.escape(str(exc)))
            return
        except StorageError:
            # Черновик остаётся в состоянии подтверждения: клиент может нажать «Сохранить» снова.
            await callback.answer("Не удалось сохранить заявку", show_alert=True)
            if callback.message is not None:
                await callback.message.answer("Не удалось сохранить заявку. Попробуйте ещё раз.")
            return
        await state.clear()
        logger.info("Сохранена заявка id=%s user_id=%s", lead.id, user.id)
        if callback.message is not None:
            await callback.message.answer(saved_text(lead), reply_markup=remove_keyboard())
        await callback.answer("Сохранено")


@router.callback_query(F.data == CALLBACK_CANCEL)
async def on_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.answer(
            "Заявка не сохранена.",
            reply_markup=remove_keyboard(),
        )
    await callback.answer("Отменено")
