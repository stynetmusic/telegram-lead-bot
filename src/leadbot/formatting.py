"""Тексты сообщений с экранированием пользовательских данных."""

from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from leadbot.models import Lead


def format_dt(value: datetime, zone: ZoneInfo) -> str:
    moment = value if value.tzinfo is not None else value.replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def preview(text: str, limit: int = 60) -> str:
    single = " ".join(text.split())
    if len(single) <= limit:
        return single
    return single[: limit - 1] + "…"


def start_text(business_name: str, *, is_admin: bool) -> str:
    safe_name = html.escape(business_name)
    lines = [
        f"Здравствуйте. Это бот заявок сервиса <b>{safe_name}</b>.",
        "",
        "Как оставить заявку:",
        "1. Отправьте /new",
        "2. Напишите своё имя",
        "3. Поделитесь телефоном кнопкой Telegram",
        "4. Опишите задачу",
        "5. Проверьте итог и нажмите «Сохранить»",
        "",
        "Команда /cancel прерывает заполнение.",
        "Команда /id показывает ваш числовой Telegram ID.",
    ]
    if is_admin:
        lines.extend(
            [
                "",
                "Вы администратор. Команда /admin открывает меню управления заявками.",
            ]
        )
    return "\n".join(lines)


def format_summary(name: str, phone: str, description: str) -> str:
    return (
        "<b>Проверьте заявку</b>\n\n"
        f"<b>Имя:</b> {html.escape(name)}\n"
        f"<b>Телефон:</b> {html.escape(phone)}\n"
        f"<b>Описание:</b>\n{html.escape(description)}\n\n"
        "Если всё верно, нажмите «Сохранить». Заявка ещё не записана."
    )


def saved_text(lead: Lead) -> str:
    return (
        f"Заявка <b>№{lead.id}</b> сохранена.\n"
        f"Статус: {html.escape(lead.status.label)}.\n"
        "Сохраните этот номер, чтобы назвать его при обращении."
    )


def format_lead_detail(lead: Lead, zone: ZoneInfo) -> str:
    username = f"@{html.escape(lead.username)}" if lead.username else "не указан"
    return (
        f"<b>Заявка №{lead.id}</b>\n"
        f"Статус: {html.escape(lead.status.label)}\n"
        f"Создана: {format_dt(lead.created_at, zone)}\n"
        f"Обновлена: {format_dt(lead.updated_at, zone)}\n"
        f"Имя: {html.escape(lead.client_name)}\n"
        f"Телефон: {html.escape(lead.phone)}\n"
        f"Telegram: {username} (id {lead.user_id})\n"
        f"Описание:\n{html.escape(lead.description)}"
    )


def format_leads_list(leads: list[Lead], total: int, zone: ZoneInfo) -> str:
    if total == 0 or not leads:
        return "Заявок пока нет."
    lines = [f"<b>Последние заявки</b> ({len(leads)} из {total})", ""]
    for lead in leads:
        lines.append(
            f"№{lead.id} · {html.escape(lead.status.label)} · "
            f"{html.escape(lead.client_name)} · {format_dt(lead.created_at, zone)} · "
            f"{html.escape(preview(lead.description))}"
        )
    lines.extend(
        [
            "",
            "Карточка: /lead_ID",
            "Смена статуса: /status_ID",
            "Полный список: /export",
        ]
    )
    return "\n".join(lines)


ADMIN_MENU = (
    "<b>Меню администратора</b>\n\n"
    "/leads — последние заявки\n"
    "/lead_12 — карточка заявки №12\n"
    "/status_12 — изменить статус заявки №12\n"
    "/export — выгрузить все заявки в Excel\n\n"
    "Статусы: Новая, В работе, Выполнена."
)

ERROR_TEXT = "Не получилось обработать запрос. Попробуйте ещё раз позже."
PRIVATE_ONLY_TEXT = "Этот бот работает только в личных сообщениях."
