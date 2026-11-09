"""The real test set and the cases the accuracy run checks. No API calls."""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_ttb  # noqa: E402
from generate_samples import TTB_DIR, real_entry, ttb_records  # noqa: E402

from app.matching import normalize  # noqa: E402


def test_test_set_is_balanced_and_complete():
    records = ttb_records()
    assert Counter(r["product_type"] for r in records) == {"distilled spirits": 40, "wine": 40, "malt beverage": 40}
    for record in records:
        entry = real_entry(record)
        assert entry.images and all((TTB_DIR / "images" / name).is_file() for name in entry.images)
        assert entry.application.brand_name
        assert bool(entry.application.country_of_origin) == (record["source_of_product"] == "Imported")


def test_altered_copies_carry_a_different_brand():
    cases = eval_ttb.cases()
    assert len({c["key"] for c in cases}) == len(cases) == 120 + eval_ttb.ALTERED_COUNT
    for case in cases:
        original, used = normalize(case["record"]["brand_name"]), normalize(case["brand"])
        if case["variant"] == "altered_brand":
            assert used not in original and original not in used
        else:
            assert used == original
