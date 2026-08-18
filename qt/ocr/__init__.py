"""OCR модуль: шаблонный движок + EasyOCR бэкенд."""
from .digits import TemplateEngine
from .engine import EasyOCREngine
from .fields import parse_fields, FieldSpec
from .preprocess import prepare
from .filters import MedianFilter, RepeatFilter

__all__ = [
    "TemplateEngine",
    "EasyOCREngine",
    "parse_fields",
    "parse_value",
    "FieldSpec",
    "FIELD_SPECS",
    "prepare",
    "MedianFilter",
    "RepeatFilter",
    "HudParser",
]