"""Модель заявки и статусы."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LeadStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    DONE = "done"

    @property
    def label(self) -> str:
        labels = {
            LeadStatus.NEW: "Новая",
            LeadStatus.IN_PROGRESS: "В работе",
            LeadStatus.DONE: "Выполнена",
        }
        return labels[self]


@dataclass(frozen=True)
class Lead:
    id: int
    user_id: int
    username: str | None
    client_name: str
    phone: str
    description: str
    status: LeadStatus
    created_at: datetime
    updated_at: datetime

    @property
    def number(self) -> str:
        return str(self.id)
