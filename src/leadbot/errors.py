"""Ошибки приложения. Сообщения безопасны для показа пользователю и в журнале."""


class LeadBotError(Exception):
    """Базовая ошибка приложения."""


class ConfigError(LeadBotError):
    """Конфигурация отсутствует или заполнена неверно."""


class ValidationError(LeadBotError):
    """Пользовательские данные не прошли проверку."""


class PermissionDenied(LeadBotError):
    """Команда доступна только администратору."""


class LeadNotFound(LeadBotError):
    """Заявка с указанным номером не найдена."""


class InvalidStatus(LeadBotError):
    """Передан статус, которого нет в модели."""


class StorageError(LeadBotError):
    """База данных недоступна или отклонила операцию."""


class BotStartupError(LeadBotError):
    """Бота не удалось запустить. Текст не содержит секрет."""
