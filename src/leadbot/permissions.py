"""Разграничение прав администратора и клиента."""

from __future__ import annotations

from leadbot.errors import PermissionDenied


def authorize(user_id: int | None, admin_ids: frozenset[int] | set[int]) -> None:
    if user_id is None or user_id not in admin_ids:
        raise PermissionDenied("Эта команда доступна только администратору.")
