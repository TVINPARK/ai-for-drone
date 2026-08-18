"""Tesseract-бэкенд: кириллица (ФИО), fallback и тренер шаблонного движка."""
from __future__ import annotations
import shutil
from pathlib import Path
import cv2

from .preprocess import prepare

WHITELISTS = {
    "int": "0123456789",
    "hms": "0123456789:.",
    "mmss": "0123456789:",
    "laps": "0123456789/",
    "battery": "0123456789,.VA",
    "dt": "0123456789.:",
    "mode": "ACROHZNILEGSTMB",
}

class TesseractEngine:
    def __init__(self, cfg: dict):
        import pytesseract
        self._pyt = pytesseract
        cmd = cfg.get("ocr", {}).get("tess_cmd", "tesseract")
        if cmd and (shutil.which(cmd) or Path(cmd).exists()):
            pytesseract.pytesseract.tesseract_cmd = cmd

    def available(self):
        try:
            self._pyt.get_tesseract_version()
            return True
        except Exception:
            return False

    def run(self, crop, spec: dict, binary: bool = False):
        bw = crop if binary else prepare(crop, spec)
        img = 255 - bw
        img = cv2.copyMakeBorder(img, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
        wl = WHITELISTS.get(spec.get("kind"))
        config = "--psm 7" + ((" -c tessedit_char_whitelist=%s" % wl) if wl else "")
        lang = "rus" if spec.get("kind") == "pilot" else "eng"
        try:
            txt = self._pyt.image_to_string(img, lang=lang, config=config)
        except Exception:
            return "", 0.0
        return txt.strip(), 0.7
