"""Общие помощники тестов."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable


def make_token() -> str:
    return "100000001:" + ("A" * 35)


def run(awaitable: Awaitable[object]) -> object:
    return asyncio.run(awaitable)
