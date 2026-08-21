"""OCR модуль: шаблонный движок."""
from .digits import TemplateEngine
from .engine import TemplateOCREngine
from .fields import parse_fields, FieldSpec
from .preprocess import prepare
from .filters import MedianFilter, RepeatFilter

__all__ = [
    "TemplateEngine",
    "TemplateOCREngine",
    "parse_fields",
    "parse_value",
    "FieldSpec",
    "FIELD_SPECS",
    "prepare",
    "MedianFilter",
    "RepeatFilter",
    "HudParser",
]