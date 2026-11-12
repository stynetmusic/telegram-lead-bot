"""Проверка сценариев без обращения к Telegram."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.storage.memory import SimpleEventIsolation

from leadbot.app import build_dispatcher
from leadbot.config import Settings
from leadbot.errors import StorageError
from leadbot.handlers.admin import cmd_export, cmd_lead, cmd_leads, cmd_status, on_set_status
from leadbot.handlers.client import (
    NewLead,
    cmd_id,
    cmd_new,
    cmd_start,
    on_cancel_callback,
    on_description,
    on_name,
    on_phone_contact,
    on_phone_text,
    on_save,
)
from leadbot.handlers.fallback import plain_text
from leadbot.models import LeadStatus
from leadbot.repository import LeadRepository
from tests.fakes import FakeCallback, FakeContact, FakeMessage, make_state
from tests.helpers import run


def test_dispatcher_registers_routers_in_order(settings: Settings, repo: LeadRepository) -> None:
    dispatcher = build_dispatcher(settings, repo)
    assert [router.name for router in dispatcher.sub_routers] == ["client", "admin", "fallback"]
    assert isinstance(dispatcher.fsm.events_isolation, SimpleEventIsolation)


def test_start_and_id_do_not_need_admin(settings: Settings) -> None:
    async def scenario() -> None:
        client = FakeMessage("/start", 100)
        await cmd_start(client, settings)
        assert "/new" in str(client.answers[-1]["text"])
        assert "администратор" not in str(client.answers[-1]["text"]).lower()

        admin = FakeMessage("/start", 1)
        await cmd_start(admin, settings)
        assert "/admin" in str(admin.answers[-1]["text"])

        identity = FakeMessage("/id", 100)
        await cmd_id(identity)
        assert "100" in str(identity.answers[-1]["text"])

    run(scenario())


def test_lead_is_saved_only_after_confirmation(repo: LeadRepository) -> None:
    async def scenario() -> None:
        state = make_state(100)
        await cmd_new(FakeMessage("/new", 100), state)
        assert await state.get_state() == NewLead.name.state

        short = FakeMessage("А", 100)
        await on_name(short, state)
        assert "Имя" in str(short.answers[-1]["text"])
        assert await state.get_state() == NewLead.name.state
        assert repo.count() == 0

        named = FakeMessage("Анна", 100)
        await on_name(named, state)
        assert await state.get_state() == NewLead.phone.state
        button = named.answers[-1]["reply_markup"].keyboard[0][0]
        assert button.request_contact is True

        typed = FakeMessage("+79990001122", 100)
        await on_phone_text(typed, state)
        assert "кнопк" in str(typed.answers[-1]["text"]).lower() or "Поделиться" in str(
            typed.answers[-1]["text"]
        )
        assert await state.get_state() == NewLead.phone.state

        foreign = FakeMessage(None, 100, contact=FakeContact("+79990001122", 999))
        await on_phone_contact(foreign, state)
        assert "Чужой контакт" in str(foreign.answers[-1]["text"])
        assert "Поделиться контактом" in str(foreign.answers[-1]["text"])
        assert await state.get_state() == NewLead.phone.state

        missing_owner = FakeMessage(None, 100, contact=FakeContact("+79990001122", None))
        await on_phone_contact(missing_owner, state)
        assert "без владельца" in str(missing_owner.answers[-1]["text"])
        assert "Поделиться контактом" in str(missing_owner.answers[-1]["text"])
        assert await state.get_state() == NewLead.phone.state

        own = FakeMessage(None, 100, contact=FakeContact("+7 (999) 000-11-22", 100))
        await on_phone_contact(own, state)
        assert await state.get_state() == NewLead.description.state

        too_short = FakeMessage("ок", 100)
        await on_description(too_short, state)
        assert "Описание" in str(too_short.answers[-1]["text"])

        described = FakeMessage("Нужна консультация <b>по услуге</b>", 100)
        await on_description(described, state)
        summary = str(described.answers[-1]["text"])
        assert "Проверьте заявку" in summary
        assert "Анна" in summary
        assert "+79990001122" in summary
        assert "&lt;b&gt;" in summary
        assert "<b>по услуге</b>" not in summary
        buttons = [
            button.callback_data
            for row in described.answers[-1]["reply_markup"].inline_keyboard
            for button in row
        ]
        assert buttons == ["lead:save", "lead:cancel"]
        assert repo.count() == 0
        assert await state.get_state() == NewLead.confirm.state

        await on_cancel_callback(FakeCallback("lead:cancel", 100), state)
        assert repo.count() == 0
        assert await state.get_state() is None

        await cmd_new(FakeMessage("/new", 100), state)
        await on_name(FakeMessage("Анна", 100), state)
        await on_phone_contact(
            FakeMessage(None, 100, contact=FakeContact("79990001122", 100)),
            state,
        )
        await on_description(FakeMessage("Нужна консультация по услуге", 100), state)
        saved = FakeCallback("lead:save", 100, username="anna_test")
        await on_save(saved, state, repo)

        lead = repo.get_lead(1)
        assert lead is not None
        assert lead.client_name == "Анна"
        assert lead.phone == "+79990001122"
        assert lead.username == "anna_test"
        assert lead.user_id == 100
        assert lead.status is LeadStatus.NEW
        assert "№1" in str(saved.message.answers[-1]["text"])
        assert await state.get_state() is None

        await cmd_new(FakeMessage("/new", 100), state)
        await on_name(FakeMessage("Борис", 100), state)
        await on_phone_contact(
            FakeMessage(None, 100, contact=FakeContact("+79990001123", 100)),
            state,
        )
        await on_description(FakeMessage("Вторая тестовая заявка", 100), state)
        await on_save(FakeCallback("lead:save", 100), state, repo)
        assert repo.get_lead(2) is not None
        assert repo.get_lead(1).id != repo.get_lead(2).id

    run(scenario())


def test_commands_during_name_are_not_saved_as_name() -> None:
    async def scenario() -> None:
        state = make_state(100)
        await cmd_new(FakeMessage("/new", 100), state)
        with pytest.raises(SkipHandler):
            await on_name(FakeMessage("/leads", 100), state)
        assert await state.get_state() == NewLead.name.state

    run(scenario())


def test_cancel_button_stops_phone_step() -> None:
    async def scenario() -> None:
        state = make_state(100)
        await cmd_new(FakeMessage("/new", 100), state)
        await on_name(FakeMessage("Анна", 100), state)
        await on_phone_text(FakeMessage("Отмена", 100), state)
        assert await state.get_state() is None

    run(scenario())


def _confirmed_state():
    async def prepare():
        state = make_state(100)
        await state.set_state(NewLead.confirm)
        await state.update_data(
            name="Анна",
            phone="+79990001122",
            description="Нужна консультация по услуге",
        )
        return state

    return prepare()


def test_parallel_confirmation_creates_one_lead(
    repo: LeadRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = repo.create_lead
    presence = {"inside": 0, "max": 0}
    gate = threading.Lock()

    def slow_create(**kwargs: object):
        with gate:
            presence["inside"] += 1
            presence["max"] = max(presence["max"], presence["inside"])
        try:
            time.sleep(0.1)
            return original(**kwargs)
        finally:
            with gate:
                presence["inside"] -= 1

    monkeypatch.setattr(repo, "create_lead", slow_create)

    async def scenario() -> None:
        state = await _confirmed_state()
        first = FakeCallback("lead:save", 100)
        second = FakeCallback("lead:save", 100)
        await asyncio.gather(on_save(first, state, repo), on_save(second, state, repo))
        assert repo.count() == 1
        assert repo.get_lead(1) is not None
        assert await state.get_state() is None
        answers = first.callback_answers + second.callback_answers
        assert sum(item.get("text") == "Сохранено" for item in answers) == 1
        assert presence["max"] == 1

    run(scenario())


def test_parallel_save_keeps_draft_when_first_write_fails(
    repo: LeadRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = repo.create_lead
    calls = {"n": 0}

    def flaky_create(**kwargs: object):
        calls["n"] += 1
        if calls["n"] == 1:
            raise StorageError("Не удалось сохранить данные.")
        return original(**kwargs)

    monkeypatch.setattr(repo, "create_lead", flaky_create)

    async def scenario() -> None:
        state = await _confirmed_state()
        first = FakeCallback("lead:save", 100)
        second = FakeCallback("lead:save", 100)
        await asyncio.gather(on_save(first, state, repo), on_save(second, state, repo))
        assert calls["n"] == 2
        assert repo.count() == 1
        assert await state.get_state() is None
        assert "Не удалось сохранить" in str(first.callback_answers[0]["text"]) or (
            "Не удалось сохранить" in str(second.callback_answers[0]["text"])
        )

    run(scenario())


def test_phone_step_accepts_only_own_contact() -> None:
    async def scenario() -> None:
        own_state = make_state(100)
        await own_state.set_state(NewLead.phone)
        own = FakeMessage(None, 100, contact=FakeContact("+79990001122", 100))
        await on_phone_contact(own, own_state)
        assert await own_state.get_state() == NewLead.description.state

        foreign_state = make_state(100)
        await foreign_state.set_state(NewLead.phone)
        foreign = FakeMessage(None, 100, contact=FakeContact("+79990001122", 50))
        await on_phone_contact(foreign, foreign_state)
        foreign_text = str(foreign.answers[-1]["text"])
        assert "Чужой контакт" in foreign_text
        assert "Поделиться контактом" in foreign_text
        assert "+79990001122" not in foreign_text
        assert await foreign_state.get_state() == NewLead.phone.state

        missing_state = make_state(100)
        await missing_state.set_state(NewLead.phone)
        missing = FakeMessage(None, 100, contact=FakeContact("+79990001122", None))
        await on_phone_contact(missing, missing_state)
        missing_text = str(missing.answers[-1]["text"])
        assert "без владельца" in missing_text
        assert "Поделиться контактом" in missing_text
        assert await missing_state.get_state() == NewLead.phone.state

        typed_state = make_state(100)
        await typed_state.set_state(NewLead.phone)
        typed = FakeMessage("+79990001122", 100)
        await on_phone_text(typed, typed_state)
        assert await typed_state.get_state() == NewLead.phone.state
        assert "вручную" in str(typed.answers[-1]["text"])

    run(scenario())


def test_save_without_confirmation_does_not_create_lead(repo: LeadRepository) -> None:
    async def scenario() -> None:
        state = make_state(100)
        callback = FakeCallback("lead:save", 100)
        await on_save(callback, state, repo)
        assert repo.count() == 0
        assert callback.callback_answers

    run(scenario())


def test_storage_error_keeps_draft(repo: LeadRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = make_state(100)
        await state.set_state(NewLead.confirm)
        await state.update_data(
            name="Анна",
            phone="+79990001122",
            description="Нужна консультация по услуге",
        )

        def broken(*args: object, **kwargs: object) -> None:
            raise StorageError("Не удалось сохранить данные.")

        monkeypatch.setattr(repo, "create_lead", broken)
        callback = FakeCallback("lead:save", 100)
        await on_save(callback, state, repo)
        assert await state.get_state() == NewLead.confirm.state
        assert "Не удалось сохранить" in str(callback.message.answers[-1]["text"])

    run(scenario())


def test_client_cannot_use_admin_commands(settings: Settings, repo: LeadRepository) -> None:
    repo.create_lead(
        user_id=100,
        username=None,
        client_name="Анна",
        phone="+79990001122",
        description="Скрытое описание заявки",
    )

    async def scenario() -> None:
        exports_before = list(settings.export_dir.glob("*.xlsx")) if settings.export_dir.exists() else []
        leads = FakeMessage("/leads", 5)
        await cmd_leads(leads, settings, repo)
        export = FakeMessage("/export", 5)
        await cmd_export(export, settings, repo)
        card = FakeMessage("/lead_1", 5)
        await cmd_lead(card, settings, repo)
        status = FakeMessage("/status_1", 5)
        await cmd_status(status, settings, repo)
        callback = FakeCallback("setstatus:1:done", 5)
        await on_set_status(callback, settings, repo)

        for message in (leads, export, card, status):
            text = str(message.answers[-1]["text"])
            assert "только администратору" in text
            assert "+79990001122" not in text
            assert "Скрытое описание" not in text
        assert export.documents == []
        exports_after = list(settings.export_dir.glob("*.xlsx")) if settings.export_dir.exists() else []
        assert exports_after == exports_before
        assert callback.message.edits == []
        assert "только администратору" in str(callback.callback_answers[-1]["text"])
        assert repo.get_lead(1) is not None
        assert repo.get_lead(1).status is LeadStatus.NEW

    run(scenario())


def test_admin_views_changes_status_and_exports(settings: Settings, repo: LeadRepository) -> None:
    repo.create_lead(
        user_id=100,
        username="client_user",
        client_name="Анна",
        phone="+79990001122",
        description="Скрытое описание заявки",
    )

    async def scenario() -> None:
        leads = FakeMessage("/leads", 1)
        await cmd_leads(leads, settings, repo)
        listed = str(leads.answers[-1]["text"])
        assert "Анна" in listed
        assert "+79990001122" not in listed

        card = FakeMessage("/lead_1", 1)
        await cmd_lead(card, settings, repo)
        assert "+79990001122" in str(card.answers[-1]["text"])
        labels = [
            button.text
            for row in card.answers[-1]["reply_markup"].inline_keyboard
            for button in row
        ]
        assert labels == ["Новая", "В работе", "Выполнена"]

        missing = FakeMessage("/lead_999", 1)
        await cmd_lead(missing, settings, repo)
        assert "не найдена" in str(missing.answers[-1]["text"])

        hint = FakeMessage("/lead", 1)
        await cmd_lead(hint, settings, repo)
        assert "/lead_12" in str(hint.answers[-1]["text"])

        status = FakeMessage("/status_1", 1)
        await cmd_status(status, settings, repo)
        assert "новый статус" in str(status.answers[-1]["text"]).lower()

        change = FakeCallback("setstatus:1:in_progress", 1)
        await on_set_status(change, settings, repo)
        assert repo.get_lead(1).status is LeadStatus.IN_PROGRESS
        assert "В работе" in str(change.message.edits[-1]["text"])

        same = FakeCallback("setstatus:1:in_progress", 1)
        await on_set_status(same, settings, repo)
        assert "уже" in str(same.callback_answers[-1]["text"])

        done = FakeCallback("setstatus:1:done", 1)
        await on_set_status(done, settings, repo)
        assert repo.get_lead(1).status is LeadStatus.DONE
        assert repo.get_lead(1).status.label == "Выполнена"

        broken = FakeCallback("setstatus:1:archived", 1)
        await on_set_status(broken, settings, repo)
        assert "Некорректные" in str(broken.callback_answers[-1]["text"])

        export = FakeMessage("/export", 1)
        await cmd_export(export, settings, repo)
        files = list(settings.export_dir.glob("*.xlsx"))
        assert len(files) == 1
        assert export.documents
        assert "Строк: 1" in str(export.documents[0]["caption"])

        unknown = FakeMessage("/unknown", 100)
        await plain_text(unknown)
        assert "/start" in str(unknown.answers[-1]["text"])

    run(scenario())
