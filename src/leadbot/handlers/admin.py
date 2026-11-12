"""Команды администратора: список, карточка, статус и экспорт."""

from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from leadbot.commands import (
    extract_lead_id,
    extract_status_id,
    is_lead_command,
    is_status_command,
    parse_status_callback,
)
from leadbot.config import Settings
from leadbot.errors import InvalidStatus, LeadNotFound, PermissionDenied, StorageError
from leadbot.export import create_export_file
from leadbot.formatting import ADMIN_MENU, format_lead_detail, format_leads_list
from leadbot.keyboards import (
    CALLBACK_ADMIN_EXPORT,
    CALLBACK_ADMIN_LEADS,
    admin_menu_keyboard,
    status_keyboard,
)
from leadbot.models import LeadStatus
from leadbot.permissions import authorize
from leadbot.repository import LeadRepository

logger = logging.getLogger("leadbot")
router = Router(name="admin")


class LeadCommand(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return is_lead_command(message.text)


class StatusCommand(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return is_status_command(message.text)


async def guard_admin_message(message: Message, settings: Settings) -> bool:
    user = message.from_user
    try:
        authorize(None if user is None else user.id, settings.admin_ids)
    except PermissionDenied as exc:
        await message.answer(str(exc))
        return False
    return True


async def guard_admin_callback(callback: CallbackQuery, settings: Settings) -> bool:
    user = callback.from_user
    try:
        authorize(None if user is None else user.id, settings.admin_ids)
    except PermissionDenied as exc:
        await callback.answer(str(exc), show_alert=True)
        return False
    return True


def _zone(settings: Settings) -> ZoneInfo:
    return ZoneInfo(settings.timezone)


async def show_leads(message: Message, settings: Settings, repo: LeadRepository) -> None:
    leads = await asyncio.to_thread(repo.list_recent, 10)
    total = await asyncio.to_thread(repo.count)
    await message.answer(format_leads_list(leads, total, _zone(settings)))


async def show_lead(message: Message, settings: Settings, repo: LeadRepository, lead_id: int) -> None:
    lead = await asyncio.to_thread(repo.get_lead, lead_id)
    if lead is None:
        await message.answer(f"Заявка №{lead_id} не найдена.")
        return
    await message.answer(
        format_lead_detail(lead, _zone(settings)),
        reply_markup=status_keyboard(lead.id),
    )


def build_export(repo: LeadRepository, settings: Settings) -> tuple[object, int]:
    leads = repo.list_all()
    path = create_export_file(leads, settings.export_dir, _zone(settings))
    return path, len(leads)


async def send_export(message: Message, settings: Settings, repo: LeadRepository) -> None:
    try:
        path, count = await asyncio.to_thread(build_export, repo, settings)
    except StorageError:
        await message.answer("Не удалось создать файл Excel.")
        return
    logger.info("Экспорт заявок: %s строк", count)
    await message.answer_document(
        FSInputFile(path),
        caption=f"Файл с заявками. Строк: {count}.",
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message, settings: Settings) -> None:
    if not await guard_admin_message(message, settings):
        return
    await message.answer(ADMIN_MENU, reply_markup=admin_menu_keyboard())


@router.message(Command("leads"))
async def cmd_leads(message: Message, settings: Settings, repo: LeadRepository) -> None:
    if not await guard_admin_message(message, settings):
        return
    await show_leads(message, settings, repo)


@router.message(Command("export"))
async def cmd_export(message: Message, settings: Settings, repo: LeadRepository) -> None:
    if not await guard_admin_message(message, settings):
        return
    await send_export(message, settings, repo)


@router.message(LeadCommand())
async def cmd_lead(message: Message, settings: Settings, repo: LeadRepository) -> None:
    if not await guard_admin_message(message, settings):
        return
    lead_id = extract_lead_id(message.text)
    if lead_id is None:
        await message.answer("Укажите номер заявки. Пример: /lead_12")
        return
    await show_lead(message, settings, repo, lead_id)


@router.message(StatusCommand())
async def cmd_status(message: Message, settings: Settings, repo: LeadRepository) -> None:
    if not await guard_admin_message(message, settings):
        return
    lead_id = extract_status_id(message.text)
    if lead_id is None:
        await message.answer("Укажите номер заявки. Пример: /status_12")
        return
    lead = await asyncio.to_thread(repo.get_lead, lead_id)
    if lead is None:
        await message.answer(f"Заявка №{lead_id} не найдена.")
        return
    await message.answer(
        format_lead_detail(lead, _zone(settings)) + "\n\nВыберите новый статус:",
        reply_markup=status_keyboard(lead.id),
    )


@router.callback_query(F.data == CALLBACK_ADMIN_LEADS)
async def on_admin_leads(
    callback: CallbackQuery,
    settings: Settings,
    repo: LeadRepository,
) -> None:
    if not await guard_admin_callback(callback, settings):
        return
    if callback.message is not None:
        await show_leads(callback.message, settings, repo)
    await callback.answer()


@router.callback_query(F.data == CALLBACK_ADMIN_EXPORT)
async def on_admin_export(
    callback: CallbackQuery,
    settings: Settings,
    repo: LeadRepository,
) -> None:
    if not await guard_admin_callback(callback, settings):
        return
    if callback.message is not None:
        await send_export(callback.message, settings, repo)
    await callback.answer()


@router.callback_query(F.data.startswith("setstatus:"))
async def on_set_status(
    callback: CallbackQuery,
    settings: Settings,
    repo: LeadRepository,
) -> None:
    if not await guard_admin_callback(callback, settings):
        return
    parsed = parse_status_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректные данные статуса", show_alert=True)
        return
    lead_id, status = parsed
    try:
        updated = await asyncio.to_thread(_apply_status, repo, lead_id, status)
    except LeadNotFound:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    except InvalidStatus:
        await callback.answer("Неизвестный статус", show_alert=True)
        return
    except StorageError:
        await callback.answer("Не удалось обновить статус", show_alert=True)
        return
    if updated is None:
        await callback.answer(f"Статус уже «{status.label}»")
        return
    logger.info("Статус заявки id=%s изменён на %s", updated.id, updated.status.value)
    text = format_lead_detail(updated, _zone(settings))
    message = callback.message
    if message is not None and callable(getattr(message, "edit_text", None)):
        try:
            await message.edit_text(text, reply_markup=status_keyboard(updated.id))
        except TelegramBadRequest:
            if callable(getattr(message, "answer", None)):
                await message.answer(text, reply_markup=status_keyboard(updated.id))
    await callback.answer("Статус обновлён")


def _apply_status(repo: LeadRepository, lead_id: int, status: LeadStatus):
    current = repo.get_lead(lead_id)
    if current is None:
        raise LeadNotFound(f"Заявка №{lead_id} не найдена.")
    if current.status is status:
        return None
    return repo.update_status(lead_id, status)
