"""Очереди без блокировки производителя: игра/захват не ждут обработку."""
from __future__ import annotations
import threading
from collections import deque

class LatestSlot:
    """Хранит 1 элемент; новый вытесняет старый (для OCR — достаточно свежего)."""
    def __init__(self):
        self._cond = threading.Condition()
        self._item = None

    def put(self, item):
        with self._cond:
            self._item = item
            self._cond.notify()

    def get(self, timeout=None):
        with self._cond:
            if self._item is None:
                self._cond.wait(timeout)
            item, self._item = self._item, None
            return item

class DropOldestQueue:
    """FIFO с вытеснением старого при переполнении (для стиков — каждый кадр)."""
    def __init__(self, maxsize=4):
        self._q = deque(maxlen=maxsize)   # maxlen сам дропает старейший
        self._cond = threading.Condition()

    def put(self, item):
        with self._cond:
            self._q.append(item)
            self._cond.notify()

    def get(self, timeout=None):
        with self._cond:
            while not self._q:
                if not self._cond.wait(timeout):
                    return None
            return self._q.popleft()