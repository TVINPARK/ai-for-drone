"""Самообучение атласа: сегментация выравнивается с чтением EasyOCR."""
from __future__ import annotations
import argparse
import re

from ..core.config import load_config
from ..core.io import imread_u
from ..capture.roi import RoiRegistry
from .digits import TemplateEngine
from .engine import EasyOCREngine
from .fields import FIELD_SPECS, TEMPLATABLE
from .preprocess import prepare

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default="qt/ocr/atlas.npz")
    args = ap.parse_args()
    cfg = load_config(args.config)
    img = imread_u(args.image)
    if img is None:
        raise SystemExit("не читается image")
    reg = RoiRegistry(cfg)
    eng_easy = EasyOCREngine(cfg)
    eng = TemplateEngine()
    for name in TEMPLATABLE:
        bw = prepare(reg.crop(img, name), FIELD_SPECS[name])
        txt, _ = eng_easy.run(bw, FIELD_SPECS[name], binary=True)
        joined = re.sub(r"\s+", "", txt)
        ok = eng.train(bw, joined, kind=FIELD_SPECS[name]["kind"])
        print("%-10s easyocr=%-22r train=%s" % (name, joined, "ok" if ok else "SKIP"))
    if eng.trained:
        eng.save(args.out)
        print("atlas saved ->", args.out)

if __name__ == "__main__":
    main()
