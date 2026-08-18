"""Спецификации полей HUD, парсеры значений, оркестратор HudParser."""
from __future__ import annotations
import re

from .digits import TemplateEngine
from .engine import EasyOCREngine
from .preprocess import prepare

FIELD_SPECS = {
    "speed":     dict(kind="int", scale=4),
    "alt":       dict(kind="int", scale=4),
    "cur_time":  dict(kind="hms", scale=4),
    "best_time": dict(kind="hms", scale=4),
    "laps":      dict(kind="laps", scale=4),
    "battery":   dict(kind="battery", scale=4),
    "limit":     dict(kind="mmss", scale=4, color=dict(lo=[80, 40, 40], hi=[115, 255, 255])),
    "datetime":  dict(kind="dt", scale=4),
    "mode":      dict(kind="mode", scale=4),
    "pilot":     dict(kind="pilot"),
}
TEMPLATABLE = sorted(k for k, s in FIELD_SPECS.items() if s["kind"] != "pilot")

def parse_value(kind, joined):
    if joined is None:
        return None
    if kind == "int":
        return float(joined) if re.fullmatch(r"\d{1,4}", joined) else None
    if kind == "hms":
        m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})", joined)
        if not m:
            return None
        h, mi, s, ms = map(int, m.groups())
        return h * 3600 + mi * 60 + s + ms / 1000.0
    if kind == "mmss":
        m = re.fullmatch(r"(\d{2}):(\d{2})", joined)
        return int(m.group(1)) * 60 + int(m.group(2)) if m else None
    if kind == "laps":
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", joined)
        return (int(m.group(1)), int(m.group(2))) if m else None
    if kind == "battery":
        m = re.fullmatch(r"(\d{1,3}[.,]\d)V(\d{1,3}[.,]\d)A", joined)
        if not m:
            return None
        return (float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))
    if kind == "dt":
        m = re.fullmatch(r"(\d{2}\.\d{2}\.\d{2})(\d{2}:\d{2}:\d{2})", joined)
        return ("%s %s" % (m.group(1), m.group(2))) if m else None
    if kind == "mode":
        u = joined.upper()
        return u if u in {"ACRO", "ANGLE", "HORIZON", "STAB", "FAIL"} else None
    return None

def clean_pilot(s):
    # Удаляем ведущие/замыкающие пробелы, символы подчёркивания и другие артефакты
    s = re.sub(r"[\s_]+", " ", s).strip()
    # Удаляем одиночные символы в начале (артефакты распознавания)
    s = re.sub(r"^[A-ZА-ЯЁ]\s+", "", s)
    return s.upper()

class HudParser:
    def __init__(self, cfg: dict, atlas_path=None):
        self.tpl = TemplateEngine(atlas_path)
        self.ocr = EasyOCREngine(cfg)

    def parse_field(self, name, crop):
        spec = FIELD_SPECS[name]
        if name == "pilot":
            txt, conf = self.ocr.run(crop, spec)
            return clean_pilot(txt), txt, conf
        bw = prepare(crop, spec)
        text, conf = ("", 0.0)
        if self.tpl.trained:
            text, conf = self.tpl.recognize(bw, spec["kind"])
        if parse_value(spec["kind"], text) is None:
            t2, c2 = self.ocr.run(bw, spec, binary=True)
            j2 = re.sub(r"\s+", "", t2)
            if parse_value(spec["kind"], j2) is not None:
                text, conf = j2, min(c2, 0.9)
        return parse_value(spec["kind"], text), text, conf

# Алиас для обратной совместимости
parse_fields = HudParser
FieldSpec = dict
