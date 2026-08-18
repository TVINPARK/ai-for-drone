"""Контракты данных между модулями (фиксированы с шага 1)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional
import numpy as np

# Поля HUD, для которых калибруются ROI (порядок = порядок обхода в калибровке)
HUD_ROI_FIELDS = ["pilot", "datetime", "battery", "mode", "limit",
                  "speed", "alt", "laps", "cur_time", "best_time"]

@dataclass(eq=False)
class Frame:
    t: float            # time.perf_counter() в момент получения
    img: np.ndarray     # BGR uint8, полный кадр

@dataclass
class Sticks:
    # левый крест: ly=газ, lx=руль; правый: ry=тангаж, rx=крен; нормировано [-1, 1]
    lx: float = 0.0; ly: float = 0.0
    rx: float = 0.0; ry: float = 0.0
    conf_l: float = 0.0; conf_r: float = 0.0

@dataclass
class Hud:
    pilot: Optional[str] = None
    region: Optional[str] = None
    dt_wall: Optional[str] = None
    bat_v: Optional[float] = None
    bat_a: Optional[float] = None
    mode: Optional[str] = None
    limit_s: Optional[float] = None
    speed: Optional[float] = None
    alt: Optional[float] = None
    lap_cur: Optional[int] = None
    lap_tot: Optional[int] = None
    cur_t: Optional[float] = None
    best_t: Optional[float] = None
    hud_present: bool = False

    def as_dict(self) -> dict:
        return asdict(self)

@dataclass
class TelemetryRow:
    t: float
    hud: Hud
    sticks: Sticks
    delta_live: Optional[float] = None

@dataclass
class Event:
    type: str
    t: float
    payload: dict = field(default_factory=dict)