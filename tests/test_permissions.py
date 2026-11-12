from __future__ import annotations

import pytest

from leadbot.commands import (
    extract_lead_id,
    extract_status_id,
    is_lead_command,
    is_status_command,
    parse_status_callback,
)
from leadbot.errors import PermissionDenied
from leadbot.models import LeadStatus
from leadbot.permissions import authorize


def test_admin_is_allowed_and_client_is_denied() -> None:
    admins = frozenset({10, 20})
    authorize(10, admins)
    with pytest.raises(PermissionDenied, match="только администратору"):
        authorize(11, admins)
    with pytest.raises(PermissionDenied):
        authorize(None, admins)
    with pytest.raises(PermissionDenied):
        authorize(10, frozenset())


def test_lead_command_parser() -> None:
    assert extract_lead_id("/lead_15") == 15
    assert extract_lead_id("/lead_15@MyBot") == 15
    assert extract_lead_id("/LEAD_0007") == 7
    assert extract_lead_id("/leads") is None
    assert extract_lead_id("/lead") is None
    assert extract_lead_id("/lead_0") is None
    assert extract_lead_id("/lead_abc") is None
    assert extract_lead_id("lead_12") is None
    assert is_lead_command("/lead_1")
    assert is_lead_command("/lead")
    assert not is_lead_command("/leads")


def test_status_command_and_callback_parser() -> None:
    assert extract_status_id("/status_3") == 3
    assert extract_status_id("/status_0") is None
    assert is_status_command("/status_3@Bot")
    assert not is_status_command("/statusquo")
    parsed = parse_status_callback("setstatus:4:in_progress")
    assert parsed == (4, LeadStatus.IN_PROGRESS)
    assert parse_status_callback("setstatus:0:done") is None
    assert parse_status_callback("setstatus:4:archived") is None
    assert parse_status_callback("lead:save") is None
