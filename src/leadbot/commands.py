"""Разбор команд вида /lead_ID и /status_ID."""

from __future__ import annotations

import re

from leadbot.models import LeadStatus

_MENTION = r"(?:@[A-Za-z0-9_]+)?"
_LEAD_ID = re.compile(rf"^/lead_(\d{{1,18}}){_MENTION}$", re.IGNORECASE)
_STATUS_ID = re.compile(rf"^/status_(\d{{1,18}}){_MENTION}$", re.IGNORECASE)
_STATUS_CALLBACK = re.compile(r"^setstatus:(\d{1,18}):(new|in_progress|done)$")


def _command_name(text: str) -> str:
    head = text.strip().split(maxsplit=1)[0]
    return head.split("@", 1)[0].lower()


def extract_lead_id(text: str | None) -> int | None:
    if not text:
        return None
    match = _LEAD_ID.match(text.strip())
    if match is None:
        return None
    value = int(match.group(1))
    if value < 1:
        return None
    return value


def extract_status_id(text: str | None) -> int | None:
    if not text:
        return None
    match = _STATUS_ID.match(text.strip())
    if match is None:
        return None
    value = int(match.group(1))
    if value < 1:
        return None
    return value


def is_lead_command(text: str | None) -> bool:
    if not text:
        return False
    name = _command_name(text)
    return name == "/lead" or name.startswith("/lead_")


def is_status_command(text: str | None) -> bool:
    if not text:
        return False
    name = _command_name(text)
    return name == "/status" or name.startswith("/status_")


def parse_status_callback(data: str | None) -> tuple[int, LeadStatus] | None:
    if not data:
        return None
    match = _STATUS_CALLBACK.fullmatch(data)
    if match is None:
        return None
    lead_id = int(match.group(1))
    if lead_id < 1:
        return None
    return lead_id, LeadStatus(match.group(2))
