from __future__ import annotations

import pytest

from leadbot.errors import ValidationError
from leadbot.validation import (
    accept_contact,
    clean_username,
    validate_description,
    validate_name,
    validate_phone,
)


def test_name_accepts_russian_and_hyphen() -> None:
    assert validate_name("  Анна-Мария  ") == "Анна-Мария"


def test_name_rejects_blank_short_and_symbols() -> None:
    with pytest.raises(ValidationError, match="Имя"):
        validate_name("   ")
    with pytest.raises(ValidationError, match="Имя"):
        validate_name("А")
    with pytest.raises(ValidationError, match="Имя"):
        validate_name("Анна123")
    with pytest.raises(ValidationError, match="Имя"):
        validate_name("Robert'); DROP TABLE leads;--")


def test_name_length_bounds() -> None:
    assert validate_name("Ан" + "а" * 78) == "Ан" + "а" * 78
    with pytest.raises(ValidationError):
        validate_name("А" * 81)


def test_name_strips_control_and_invisible_characters() -> None:
    assert validate_name("Ан\x00на\u200b") == "Анна"


def test_phone_is_normalized() -> None:
    assert validate_phone("+7 (999) 000-11-22") == "+79990001122"
    assert validate_phone("79990001122") == "+79990001122"


def test_phone_rejects_invalid_values() -> None:
    for value in ("", "123", "телефон", "+7999", "++79990001122"):
        with pytest.raises(ValidationError, match="Телефон"):
            validate_phone(value)


def test_own_contact_is_accepted() -> None:
    assert accept_contact("79990001122", 10, 10) == "+79990001122"
    assert accept_contact("+7 (999) 000-11-22", 10, 10) == "+79990001122"


def test_foreign_contact_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Чужой контакт") as exc:
        accept_contact("+79990001122", 50, 10)
    assert "Поделиться контактом" in str(exc.value)


def test_contact_without_user_id_is_rejected() -> None:
    for owner in (None, True, 0, -5):
        with pytest.raises(ValidationError, match="без владельца") as exc:
            accept_contact("+79990001122", owner, 10)
        assert "Поделиться контактом" in str(exc.value)
        assert "79990001122" not in str(exc.value)


def test_description_requires_text_and_limits_length() -> None:
    assert validate_description("  Нужна\nпомощь  ") == "Нужна\nпомощь"
    with pytest.raises(ValidationError, match="Описание"):
        validate_description("ок")
    with pytest.raises(ValidationError, match="Описание"):
        validate_description("!!!!!")
    assert len(validate_description("А" * 2000)) == 2000
    with pytest.raises(ValidationError):
        validate_description("А" * 2001)


def test_description_removes_nulls_and_collapses_blank_lines() -> None:
    cleaned = validate_description("Нужна\x00 помощь\n\n\n\nсегодня")
    assert "\x00" not in cleaned
    assert "\n\n\n" not in cleaned
    assert "Нужна помощь" in cleaned


def test_username_is_cleaned() -> None:
    assert clean_username("@Valid_name") == "Valid_name"
    assert clean_username("bad name") is None
    assert clean_username("ab") is None
    assert clean_username(None) is None
