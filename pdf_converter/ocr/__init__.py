"""OCR模块"""

from .ocr_extractor import ocr_extract_text_from_image
from .ocr_parser import parse_noise_detection_record_from_ocr

__all__ = [
    "ocr_extract_text_from_image",
    "parse_noise_detection_record_from_ocr",
]
