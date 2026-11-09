"""The committed queue matches its generator, and its mix covers the cases the brief asks for."""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_samples  # noqa: E402
from app.queue import QUEUE_DIR, load_queue  # noqa: E402


def test_committed_manifest_matches_the_generator():
    # Fails when generate_samples.py changed but wasn't rerun.
    assert list(load_queue().values()) == sorted(generate_samples.queue_entries(), key=lambda e: (e.submitted_at, e.id))


def test_every_queue_image_exists():
    for entry in load_queue().values():
        assert (QUEUE_DIR / entry.image).is_file(), entry.image


def test_queue_mix():
    entries = list(load_queue().values())
    assert Counter(e.product_type for e in entries) == {"distilled_spirits": 10, "wine": 8, "malt_beverage": 7}
    outcomes = Counter(e.expected_overall for e in entries)
    assert 0.5 <= outcomes["pass"] / len(entries) <= 0.6
    assert outcomes["fail"] and outcomes["needs_review"]
    assert len({e.id for e in entries}) == len(entries)
