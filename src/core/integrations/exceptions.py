"""Исключения механизма Module Bridge."""


class BridgeError(Exception):
    """Базовое исключение для всех ошибок ModuleBridge."""


class DuplicateProvider(BridgeError):
    """
    Попытка зарегистрировать второго провайдера для уже занятого имени операции.

    Чтобы заменить регистрацию — вызывайте provide(..., override=True)
    или предварительно bridge.unregister(name).
    """
