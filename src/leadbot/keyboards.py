"""Клавиатуры клиента и администратора."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from leadbot.models import LeadStatus

PHONE_BUTTON = "Поделиться контактом"
CANCEL_BUTTON = "Отмена"
CALLBACK_SAVE = "lead:save"
CALLBACK_CANCEL = "lead:cancel"
CALLBACK_ADMIN_LEADS = "admin:leads"
CALLBACK_ADMIN_EXPORT = "admin:export"


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=PHONE_BUTTON, request_contact=True)],
            [KeyboardButton(text=CANCEL_BUTTON)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Нажмите кнопку ниже",
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сохранить", callback_data=CALLBACK_SAVE),
                InlineKeyboardButton(text="Отменить", callback_data=CALLBACK_CANCEL),
            ]
        ]
    )


def status_keyboard(lead_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=status.label,
                    callback_data=f"setstatus:{lead_id}:{status.value}",
                )
            ]
            for status in LeadStatus
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Последние заявки", callback_data=CALLBACK_ADMIN_LEADS)],
            [InlineKeyboardButton(text="Выгрузить Excel", callback_data=CALLBACK_ADMIN_EXPORT)],
        ]
    )
