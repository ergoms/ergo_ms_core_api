from typing import Protocol


class NotificationChannel(Protocol):
    """Интерфейс канала доставки уведомлений.

    Реализации: in_app (запись в БД + WebSocket), позже email/push/sms.
    Канал должен быть идемпотентен по отношению к уже доставленному
    объекту notification (например, не дублировать запись/письмо).
    """

    name: str

    def deliver(self, notification, *, created: bool) -> None:  # pragma: no cover - интерфейс
        ...
