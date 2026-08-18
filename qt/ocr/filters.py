"""Фильтры выбросов: медиана (числа), повтор (строки), hold-last-valid."""
from __future__ import annotations
from collections import deque
import numpy as np

class MedianFilter:
    def __init__(self, window=5, hold_s=1.0):
        self._d = deque(maxlen=window)
        self.value = None
        self._last_t = -1e9
        self.hold_s = hold_s

    def push(self, raw, t):
        if raw is not None:
            self._d.append(float(raw))
            self.value = float(np.median(list(self._d)))
            self._last_t = t
        elif t - self._last_t > self.hold_s:
            self.value = None
        return self.value

class RepeatFilter:
    def __init__(self, k=2, hold_s=2.0):
        self.k = k
        self._prev = None
        self._count = 0
        self.value = None
        self._last_t = -1e9
        self.hold_s = hold_s

    def push(self, raw, t):
        if raw is not None:
            if raw == self._prev:
                self._count += 1
            else:
                self._prev, self._count = raw, 1
            if self._count >= self.k or self.value is None:
                self.value, self._last_t = raw, t
        elif t - self._last_t > self.hold_s:
            self.value = None
        return self.value
