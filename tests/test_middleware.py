from __future__ import annotations

from leadbot.formatting import PRIVATE_ONLY_TEXT
from leadbot.middlewares import PrivateChatMiddleware, chat_is_private
from tests.helpers import run
from tests.fakes import FakeCallback, FakeMessage


def test_private_chat_passes_and_group_is_rejected() -> None:
    assert chat_is_private(None) is True

    async def scenario() -> None:
        called = {"value": False}

        async def handler(event: object, data: dict[str, object]) -> str:
            called["value"] = True
            return "ok"

        private = FakeMessage("/new", 1, chat_type="private")
        assert await PrivateChatMiddleware()(handler, private, {}) == "ok"
        assert called["value"] is True

        called["value"] = False
        group = FakeMessage("/new", 1, chat_type="group")
        assert await PrivateChatMiddleware()(handler, group, {}) is None
        assert called["value"] is False
        assert group.answers[-1]["text"] == PRIVATE_ONLY_TEXT

        callback = FakeCallback("lead:save", 1)
        callback.message.chat.type = "supergroup"
        assert await PrivateChatMiddleware()(handler, callback, {}) is None
        assert callback.callback_answers[-1]["show_alert"] is True
        assert called["value"] is False

    run(scenario())
