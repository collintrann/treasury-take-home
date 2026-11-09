"""Pick a reader: two AI models in parallel first, local OCR as the fallback.

Routing in one picture (details and trade-offs in docs/DESIGN.md):

    image ─┬─► primary model   (most accurate) ─┐
           │                                    ├─► consensus.py ─► verdict
           └─► secondary model (fast, different)┘
                    both run at once, hard deadline READ_DEADLINE_SECONDS
                    nobody answered in time / errors ─► Tesseract OCR
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

from .. import config
from ..models import ApplicationData, ExtractedLabel
from .claude_reader import ClaudeExtractionError, extract_with_claude
from .image import InvalidImageError, load_image, to_upload_jpeg
from .ocr_reader import LOW_CONFIDENCE, extract_with_ocr

log = logging.getLogger(__name__)

__all__ = ["extract", "Extraction", "Reading", "InvalidImageError"]

# OCR is CPU-bound, so more parallel jobs than cores only adds contention.
# (AI calls are network-bound and are limited separately in main.py.)
_ocr_slots = asyncio.Semaphore(max(1, os.cpu_count() or 1))


@dataclass
class Reading:
    model: str  # model id, or "ocr"
    role: str  # "primary" | "secondary" | "ocr"
    label: ExtractedLabel


@dataclass
class Extraction:
    method: str  # "claude" | "ocr"
    readings: list[Reading] = field(default_factory=list)  # primary first
    note: str = ""  # shown to the agent: fallback reason, image quality, ...
    low_confidence: bool = False


async def read_with_models(jpeg: bytes) -> tuple[list[Reading], list[str]]:
    """Run every configured AI reader concurrently under one shared deadline.

    Returns (readings that succeeded in time, human-readable failure notes).
    Concurrency means the wait is roughly the *slower* reader's latency, not
    the sum. The deadline means a hung call can't hold the agent hostage.
    """
    tasks = {
        asyncio.create_task(extract_with_claude(jpeg, model)): (model, role)
        for model, role in config.reader_models()
    }
    done, pending = await asyncio.wait(tasks, timeout=config.READ_DEADLINE_SECONDS)
    for task in pending:
        task.cancel()

    readings, failures = [], []
    for task, (model, role) in tasks.items():
        if task in pending:
            failures.append(f"{model} didn't answer within {config.READ_DEADLINE_SECONDS:g} s")
        elif task.exception() is not None:
            failures.append(f"{model}: {task.exception()}")
        else:
            readings.append(Reading(model, role, task.result()))
    readings.sort(key=lambda r: r.role != "primary")  # primary first
    return readings, failures


async def extract(data: bytes, app: ApplicationData) -> Extraction:
    """Read a label image. Raises InvalidImageError for bad uploads."""
    img = load_image(data)
    mode = config.EXTRACTION_MODE

    if mode != "ocr":
        if config.claude_configured():
            readings, failures = await read_with_models(to_upload_jpeg(img))
            for f in failures:
                log.warning("AI reader failed: %s", f)
            if readings:
                return Extraction("claude", readings, readings[0].label.image_issues or "")
            if mode == "claude":
                raise ClaudeExtractionError("; ".join(failures))
            log.warning("All AI readers failed; using offline OCR")
        elif mode == "claude":
            raise ClaudeExtractionError("EXTRACTION_MODE=claude but no ANTHROPIC_API_KEY is set")

    # Tesseract is a blocking subprocess call; run it off the event loop.
    async with _ocr_slots:
        label, confidence = await asyncio.to_thread(extract_with_ocr, img, app)
    return Extraction("ocr", [Reading("ocr", "ocr", label)], label.image_issues or "", low_confidence=confidence < LOW_CONFIDENCE)
