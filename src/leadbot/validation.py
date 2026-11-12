"""Проверка имени, телефона и описания заявки."""

from __future__ import annotations

import re

from leadbot.errors import ValidationError

_INVISIBLE = {
    0x200B,
    0x200C,
    0x200D,
    0x2060,
    0xFEFF,
    0x202A,
    0x202B,
    0x202C,
    0x202D,
    0x202E,
    0x2066,
    0x2067,
    0x2068,
    0x2069,
}
_NAME_EXTRA = set(" -'.’")
_PHONE_SEPARATORS = re.compile(r"[\s()\-]")
_USERNAME = re.compile(r"[A-Za-z0-9_]{5,32}")
_MAX_RAW_LENGTH = 4000


def sanitize_text(raw: str, *, keep_newlines: bool) -> str:
    if not isinstance(raw, str):
        raise ValidationError("Ожидается текстовое сообщение.")
    if len(raw) > _MAX_RAW_LENGTH:
        raise ValidationError("Сообщение слишком длинное.")
    pieces: list[str] = []
    for char in raw:
        if char == "\x00":
            continue
        if char in "\n\r":
            pieces.append("\n" if keep_newlines else " ")
            continue
        if char == "\t":
            pieces.append(" ")
            continue
        code = ord(char)
        if code < 32 or code == 127 or code in _INVISIBLE:
            continue
        pieces.append(char)
    return "".join(pieces)


def validate_name(raw: str) -> str:
    cleaned = sanitize_text(raw, keep_newlines=False)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not 2 <= len(cleaned) <= 80:
        raise ValidationError("Имя должно содержать от 2 до 80 символов.")
    if not any(char.isalpha() for char in cleaned):
        raise ValidationError("Имя должно содержать буквы.")
    if not all(char.isalpha() or char in _NAME_EXTRA for char in cleaned):
        raise ValidationError("Имя может содержать только буквы, пробел, дефис и апостроф.")
    return cleaned


def validate_phone(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValidationError("Телефон нужно отправить контактом Telegram.")
    if len(raw) > 64:
        raise ValidationError("Телефон слишком длинный.")
    compact = _PHONE_SEPARATORS.sub("", raw.strip())
    digits = compact[1:] if compact.startswith("+") else compact
    if not digits.isdigit():
        raise ValidationError("Телефон содержит недопустимые символы.")
    if not 10 <= len(digits) <= 15:
        raise ValidationError("Телефон должен содержать от 10 до 15 цифр.")
    return f"+{digits}"


_SHARE_OWN_NUMBER = (
    "Нажмите кнопку «Поделиться контактом» и отправьте свой номер телефона."
)


def accept_contact(phone_number: str, contact_user_id: int | None, sender_id: int) -> str:
    """Принять номер только из собственного контакта Telegram.

    Контакт годится, когда Telegram передал владельца и этот владелец
    совпадает с отправителем. Контакт без user_id и чужой контакт отклоняются.
    Номер обычным текстом сюда не попадает: его отсекает шаг анкеты.
    """

    if not isinstance(sender_id, int) or isinstance(sender_id, bool) or sender_id <= 0:
        raise ValidationError("Не удалось определить отправителя.")
    # bool является подклассом int, поэтому его нужно отсечь отдельно.
    if (
        isinstance(contact_user_id, bool)
        or not isinstance(contact_user_id, int)
        or contact_user_id <= 0
    ):
        raise ValidationError(
            "Контакт без владельца не принимается. " + _SHARE_OWN_NUMBER
        )
    if contact_user_id != sender_id:
        raise ValidationError("Чужой контакт не принимается. " + _SHARE_OWN_NUMBER)
    if not isinstance(phone_number, str) or not phone_number.strip():
        raise ValidationError("В контакте нет номера телефона.")
    return validate_phone(phone_number)


def validate_description(raw: str) -> str:
    cleaned = sanitize_text(raw, keep_newlines=True).strip()
    cleaned = re.sub(r"[ ]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    if not 5 <= len(cleaned) <= 2000:
        raise ValidationError("Описание должно содержать от 5 до 2000 символов.")
    if not any(char.isalnum() for char in cleaned):
        raise ValidationError("Описание должно содержать текст заявки.")
    return cleaned


def clean_username(username: str | None) -> str | None:
    if username is None:
        return None
    if not isinstance(username, str):
        return None
    normalized = username.strip().lstrip("@")
    if _USERNAME.fullmatch(normalized):
        return normalized
    return None


def require_user_id(user_id: object) -> int:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValidationError("Некорректный идентификатор пользователя.")
    return user_id
