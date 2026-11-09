"""The simulated review queue: generated applications in samples/queue/applications.json."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter

from .models import QueueDetail, QueueEntry, QueueItem

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
QUEUE_DIR = SAMPLES_DIR / "queue"
MANIFEST = QUEUE_DIR / "applications.json"


@lru_cache
def load_queue() -> dict[str, QueueEntry]:
    """Queue entries by id, oldest first. Empty when no manifest is present."""
    if not MANIFEST.exists():
        return {}
    entries = TypeAdapter(list[QueueEntry]).validate_json(MANIFEST.read_bytes())
    return {e.id: e for e in sorted(entries, key=lambda e: (e.submitted_at, e.id))}


def image_urls(entry: QueueEntry) -> list[str]:
    return [f"/samples/queue/{name}" for name in entry.images]


def as_item(entry: QueueEntry) -> QueueItem:
    return QueueItem(
        id=entry.id,
        submitted_at=entry.submitted_at,
        applicant=entry.applicant,
        product_type=entry.product_type,
        brand_name=entry.application.brand_name,
        images=image_urls(entry),
    )


def as_detail(entry: QueueEntry) -> QueueDetail:
    return QueueDetail(
        id=entry.id,
        submitted_at=entry.submitted_at,
        applicant=entry.applicant,
        product_type=entry.product_type,
        images=image_urls(entry),
        application=entry.application,
    )
