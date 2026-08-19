"""Приёмка шага 3: 100% совпадение с эталоном на tests/fixtures/screen_01.png."""
import shutil
from pathlib import Path
import numpy as np
import pytest

from qt.core.config import load_config
from qt.core.io import imread_u
from qt.capture.auto_rois import assign_rois
from qt.ocr.preprocess import prepare, hud_present
from qt.ocr.digits import TemplateEngine, segment, window_for
from qt.ocr.fields import FIELD_SPECS, parse_value, clean_pilot
from qt.ocr.filters import MedianFilter, RepeatFilter

FIXTURE = Path(__file__).parent / "fixtures" / "screen_01.png"

FIXTURE_ROIS = {
    "pilot":     [0, 0, 471, 33],
    "datetime":  [40, 39, 152, 21],
    "battery":   [126, 66, 104, 32],
    "mode":      [40, 107, 92, 30],
    "limit":     [1816, 70, 38, 11],
    "speed":     [107, 528, 81, 75],
    "alt":       [1597, 556, 16, 23],
    "laps":      [99, 1026, 36, 24],
    "cur_time":  [263, 1027, 95, 21],
    "best_time": [1786, 1027, 95, 21],
}

RAW = {
    "pilot": "", "speed": "00", "alt": "0",
    "cur_time": "00:00:02.059", "best_time": "00:01:47.067",
    "laps": "1/3", "battery": "25,1V2,4A", "limit": "02:58",
    "datetime": "17.08.2623:58:57", "mode": "ACRO",
}
EXPECTED = {
    "pilot": "ЧЕЛЯБИНСКАЯ ОБЛАСТЬ: БОЙКО АРСЕНИЙ СТБ",
    "dt_wall": "17.08.26 23:58:57",
    "bat_v": 25.1, "bat_a": 2.4,
    "mode": "ACRO", "limit_s": 178.0,
    "speed": 0.0, "alt": 0.0,
    "lap_cur": 1, "lap_tot": 3,
    "cur_t": 2.059, "best_t": 107.067,
}

def _ascii(bw, w=96, h=28):
    H, W = bw.shape
    ys = np.linspace(0, H, h + 1).astype(int)
    xs = np.linspace(0, W, w + 1).astype(int)
    out = []
    for i in range(h):
        out.append("".join(
            "#" if bw[ys[i]:ys[i + 1], xs[j]:xs[j + 1]].max() > 0 else "."
            for j in range(w)))
    return "\n" + "\n".join(out)

@pytest.fixture(scope="module")
def crops():
    assert FIXTURE.exists(), "положите эталонный скриншот в tests/fixtures/screen_01.png"
    img = imread_u(FIXTURE)
    assert img is not None, "fixture не читается"
    H, W = img.shape[:2]
    rois = FIXTURE_ROIS if (W, H) == (1920, 1080) else assign_rois(img)
    if (W, H) != (1920, 1080):
        missing = [n for n in RAW if n not in rois]
        assert not missing, "auto_rois не нашёл поля: %s" % missing
    return {n: np.ascontiguousarray(img[rois[n][1]:rois[n][1] + rois[n][3],
                                      rois[n][0]:rois[n][0] + rois[n][2]]) for n in RAW}

@pytest.fixture(scope="module")
def trained(crops):
    eng = TemplateEngine()
    for n, raw in RAW.items():
        spec = FIELD_SPECS[n]
        # Поле pilot обрабатывается только через Tesseract, не через шаблонный движок
        if spec["kind"] == "pilot":
            continue
        bw = prepare(crops[n], spec)
        segs = segment(bw)
        wsegs = window_for(segs, spec["kind"])
        ok = eng.train(bw, raw, kind=spec["kind"])
        if not ok:
            pytest.fail("%s: окно=%d нужно=%d | segs(x,w,h)=%s%s" % (
                n, len(wsegs), len(raw),
                ",".join("%d:%dx%d" % (s[0], s[1] - s[0], s[3] - s[2]) for s in segs),
                _ascii(bw)))
    return eng

def test_template_100_percent(trained, crops):
    for n, raw in RAW.items():
        # Поле pilot обрабатывается только через Tesseract
        if FIELD_SPECS[n]["kind"] == "pilot":
            continue
        text, conf = trained.recognize(prepare(crops[n], FIELD_SPECS[n]),
                                       kind=FIELD_SPECS[n]["kind"])
        assert text == raw, "%s: %r != %r" % (n, text, raw)
        assert conf >= 0.5, "%s: conf=%.2f" % (n, conf)

def test_parsed_values(trained, crops):
    for n, raw in RAW.items():
        # Поле pilot обрабатывается только через Tesseract
        if FIELD_SPECS[n]["kind"] == "pilot":
            continue
        v = parse_value(FIELD_SPECS[n]["kind"], raw)
        assert v is not None, n
        if n == "speed": assert v == EXPECTED["speed"]
        if n == "alt": assert v == EXPECTED["alt"]
        if n == "cur_time": assert abs(v - EXPECTED["cur_t"]) < 1e-9
        if n == "best_time": assert abs(v - EXPECTED["best_t"]) < 1e-9
        if n == "limit": assert v == EXPECTED["limit_s"]
        if n == "laps": assert v == (EXPECTED["lap_cur"], EXPECTED["lap_tot"])
        if n == "battery": assert v == (EXPECTED["bat_v"], EXPECTED["bat_a"])
        if n == "datetime": assert v == EXPECTED["dt_wall"]
        if n == "mode": assert v == EXPECTED["mode"]

def test_parse_units():
    assert parse_value("hms", "01:02:03.500") == 3723.5
    assert parse_value("mmss", "02:49") == 169
    assert parse_value("battery", "25,2V1,1A") == (25.2, 1.1)
    assert parse_value("hms", "12:34.5") is None
    assert parse_value("int", "12a") is None

def test_hud_present(crops):
    bw = prepare(crops["cur_time"], FIELD_SPECS["cur_time"])
    assert hud_present(bw)

def test_filters():
    f = MedianFilter(window=5)
    for i, v in enumerate([10, 10, 99, 10, 11]):
        out = f.push(v, float(i))
    assert out == 10.0
    r = RepeatFilter()
    assert r.push("ACRO", 0.0) == "ACRO"
    assert r.push("XCR0", 0.1) == "ACRO"
    assert r.push("XCR0", 0.2) == "XCR0"

def test_pilot_easyocr(crops):
    """Тест распознавания имени пилота через EasyOCR."""
    pytest.importorskip("easyocr", reason="EasyOCR не установлен (опциональная зависимость)")
    
    from qt.ocr.engine import EasyOCREngine
    cfg = load_config()
    eng = EasyOCREngine(cfg)
    if not eng.available():
        pytest.skip("EasyOCR недоступен")
    txt, conf = eng.run(crops["pilot"], FIELD_SPECS["pilot"])
    # EasyOCR может вернуть текст с небольшими отличиями в форматировании
    # Проверяем ключевые слова
    assert "БОЙКО" in txt.upper() or "АРСЕНИЙ" in txt.upper(), f"EasyOCR не распознал имя: {txt}"
    assert conf > 0.5, f"Слишком низкая уверенность: {conf}"
