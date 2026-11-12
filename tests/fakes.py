"""Подставки вместо объектов Telegram. Сеть не используется."""

from __future__ import annotations

from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage


class FakeUser:
    def __init__(self, user_id: int, username: str | None = "tester") -> None:
        self.id = user_id
        self.username = username
        self.first_name = "Тест"
        self.is_bot = False


class FakeContact:
    def __init__(self, phone_number: str, user_id: int | None, first_name: str = "Тест") -> None:
        self.phone_number = phone_number
        self.user_id = user_id
        self.first_name = first_name


class FakeMessage:
    def __init__(
        self,
        text: str | None,
        user_id: int,
        contact: FakeContact | None = None,
        username: str | None = "tester",
        chat_type: str = "private",
    ) -> None:
        self.text = text
        self.contact = contact
        self.from_user = FakeUser(user_id, username=username)
        self.chat = SimpleNamespace(id=user_id, type=chat_type)
        self.answers: list[dict[str, object]] = []
        self.documents: list[dict[str, object]] = []
        self.edits: list[dict[str, object]] = []

    async def answer(self, text: str = "", **kwargs: object) -> FakeMessage:
        self.answers.append({"text": text, **kwargs})
        return self

    async def answer_document(self, document: object, **kwargs: object) -> FakeMessage:
        self.documents.append({"document": document, **kwargs})
        return self

    async def edit_text(self, text: str, **kwargs: object) -> FakeMessage:
        self.edits.append({"text": text, **kwargs})
        return self


class FakeCallback:
    def __init__(self, data: str, user_id: int, username: str | None = "tester") -> None:
        self.data = data
        self.from_user = FakeUser(user_id, username=username)
        self.message = FakeMessage(text=None, user_id=user_id, username=username)
        self.callback_answers: list[dict[str, object]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False, **kwargs: object) -> None:
        self.callback_answers.append({"text": text, "show_alert": show_alert, **kwargs})


def make_state(user_id: int = 100) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)
