"""Pick a reader: Claude first, local OCR as the fallback."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from .. import config
from ..models import ApplicationData, ExtractedLabel
from .claude_reader import ClaudeExtractionError, extract_with_claude
from .image import InvalidImageError, load_image, to_upload_jpeg
from .ocr_reader import LOW_CONFIDENCE, extract_with_ocr

log = logging.getLogger(__name__)

# OCR is CPU-bound, so more parallel jobs than cores only adds contention.
# (Claude calls are network-bound and are limited separately in main.py.)
_ocr_slots = asyncio.Semaphore(max(1, os.cpu_count() or 1))

__all__ = ["extract", "Extraction", "InvalidImageError"]


@dataclass
class Extraction:
    label: ExtractedLabel
    method: str  # "claude" | "ocr"
    note: str = ""  # shown to the agent: fallback reason, image quality, ...
    low_confidence: bool = False


async def extract(data: bytes, app: ApplicationData) -> Extraction:
    """Read a label image. Raises InvalidImageError for bad uploads."""
    img = load_image(data)
    mode = config.EXTRACTION_MODE

    if mode != "ocr":
        if config.claude_configured():
            try:
                label = await extract_with_claude(to_upload_jpeg(img))
                return Extraction(label, "claude", label.image_issues or "")
            except ClaudeExtractionError as exc:
                if mode == "claude":
                    raise
                log.warning("Claude extraction failed, falling back to OCR: %s", exc)
                note = f"The AI reader was unavailable ({exc}), so offline OCR was used instead."
        elif mode == "claude":
            raise ClaudeExtractionError("EXTRACTION_MODE=claude but no ANTHROPIC_API_KEY is set")
        else:
            note = "Offline OCR mode (no AI key configured)."
    else:
        note = "Offline OCR mode."

    # Tesseract is a blocking subprocess call; run it off the event loop.
    async with _ocr_slots:
        label, confidence = await asyncio.to_thread(extract_with_ocr, img, app)
    low = confidence < LOW_CONFIDENCE
    if label.image_issues:
        note = f"{note} {label.image_issues}"
    return Extraction(label, "ocr", note, low_confidence=low)
