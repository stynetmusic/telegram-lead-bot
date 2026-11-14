"""Регистрация команд не ходит в Telegram: бот в тесте подменён."""

from __future__ import annotations

import logging

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SetMyCommands
from aiogram.types import BotCommandScopeChat, BotCommandScopeDefault

from leadbot.config import Settings
from leadbot.runtime import setup_commands
from tests.helpers import run


def test_admin_command_registration_error_is_logged(
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = settings.bot_token
    calls: list[object] = []

    class FakeBot:
        async def set_my_commands(self, commands: list[object], scope: object = None) -> bool:
            calls.append(scope)
            if isinstance(scope, BotCommandScopeChat):
                raise TelegramBadRequest(
                    method=SetMyCommands(commands=[]),
                    message=f"Bad Request: chat not found {token}",
                )
            return True

    with caplog.at_level(logging.WARNING, logger="leadbot"):
        run(setup_commands(FakeBot(), settings))  # type: ignore[arg-type]

    text = caplog.text
    assert len(calls) == 2
    assert isinstance(calls[0], BotCommandScopeDefault)
    assert isinstance(calls[1], BotCommandScopeChat)
    assert calls[1].chat_id == 1
    assert "Не удалось обновить команды администратора 1: TelegramBadRequest:" in text
    assert "Bad Request: chat not found" in text
    assert token not in text
    assert "***" in text
