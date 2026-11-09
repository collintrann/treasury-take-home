"""Read a label's images with two models in parallel under one deadline."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

from .. import config
from ..models import ExtractedLabel
from .claude_reader import ClaudeExtractionError, extract_with_claude
from .image import InvalidImageError, load_image, to_upload_jpeg

log = logging.getLogger(__name__)

__all__ = ["extract", "Reading", "InvalidImageError", "ClaudeExtractionError"]


@dataclass
class Reading:
    model: str
    role: Literal["primary", "secondary"]
    label: ExtractedLabel
    usage: dict = field(default_factory=dict)  # token counts, when the reader reported them


async def read_with_models(jpegs: list[bytes]) -> tuple[list[Reading], list[str]]:
    """Run every configured AI reader concurrently under one shared deadline.

    Returns (readings that succeeded in time, human-readable failure notes).
    Concurrency means the wait is roughly the *slower* reader's latency, not
    the sum. The deadline means a hung call can't hold the agent hostage.
    """
    usage = {model: {} for model, _ in config.reader_models()}
    tasks = {
        asyncio.create_task(extract_with_claude(jpegs, model, usage=usage[model])): (model, role)
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
            readings.append(Reading(model, role, task.result(), usage[model]))
    readings.sort(key=lambda r: r.role != "primary")  # primary first
    return readings, failures


async def extract(images: list[bytes]) -> list[Reading]:
    """Read every image of one application's label together; returns at least one reading, primary first.

    Raises InvalidImageError or ClaudeExtractionError.
    """
    jpegs = [to_upload_jpeg(load_image(data)) for data in images]
    if not config.claude_configured():
        raise ClaudeExtractionError("no ANTHROPIC_API_KEY is set")
    readings, failures = await read_with_models(jpegs)
    for f in failures:
        log.warning("reader failed: %s", f)
    if not readings:
        raise ClaudeExtractionError("; ".join(failures))
    return readings
