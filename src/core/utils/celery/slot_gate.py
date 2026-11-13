"""Счётчик слотов очереди и квитанция о взятом слоте."""

from __future__ import annotations

import threading
from dataclasses import dataclass


class SlotGate:
    """Считает занятые слоты при любом лимите. Лимит 0 значит «без ограничения».

    Счёт идёт и без лимита: когда план позже поставит потолок, уже идущие
    задачи в нём учтены, и узел не пускает лишние.
    """

    def __init__(self, limit: int):
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self.limit = max(0, int(limit))
        self.held = 0

    def _has_room(self) -> bool:
        return self.limit <= 0 or self.held < self.limit

    def acquire(self, blocking: bool = False) -> bool:
        with self._cv:
            if self._has_room():
                self.held += 1
                return True
            if not blocking:
                return False
            while not self._has_room():
                self._cv.wait()
            self.held += 1
            return True

    def release(self) -> None:
        with self._cv:
            if self.held > 0:
                self.held -= 1
            self._cv.notify_all()

    def set_limit(self, limit: int) -> None:
        with self._cv:
            self.limit = max(0, int(limit))
            self._cv.notify_all()


@dataclass(frozen=True)
class SlotLease:
    """Что именно взяла задача. Отпускается то же самое, даже если лимит успел смениться."""

    queue: str
    queue_slot: bool
    class_slot: bool
