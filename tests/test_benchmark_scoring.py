"""Benchmark scoring, checked with simulated readers (no API calls).

Also pins down the core claim of the two-reader design: a reader that silently
"fixes" typos produces false passes alone, and none when paired with a
faithful reader.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark as bm  # noqa: E402
from app.models import ExtractedLabel  # noqa: E402
from app.warning import FULL_TEXT  # noqa: E402


def faithful_reading(entry) -> ExtractedLabel:
    """What a perfect reader would return for this queue image."""
    p = bm.PRINTED[entry.id]
    printed = bm.printed_warning(p)
    clear = p.photo != "blurry"
    return ExtractedLabel(
        brand_name=p.brand, class_type=p.class_type, alcohol_content=p.abv or None, net_contents=p.net,
        producer_name_address=p.producer, country_of_origin=p.country or None,
        government_warning=printed, warning_header_bold=p.header_bold if printed else None,
        warning_body_bold=False if printed else None, warning_continuous_paragraph=True if printed else None,
        warning_separate_from_other_text=True if printed else None, warning_legible=clear if printed else None,
        image_readable=clear,
    )


def simulated_calls():
    calls = []
    for entry in bm.scored_entries():
        faithful = faithful_reading(entry)
        fixer = faithful.model_copy(update={"government_warning": FULL_TEXT if faithful.government_warning else None})
        calls.append(bm.Call("faithful", entry, 0, 2.0, faithful, None, {}))
        calls.append(bm.Call("fixer", entry, 0, 1.0, fixer, None, {}))
    return calls


def by_key(calls):
    grouped = {}
    for c in calls:
        grouped.setdefault((c.run, c.entry.id), {})[c.model] = c
    return grouped


def test_perfect_reader_gets_every_expected_result():
    st = bm.model_stats([c for c in simulated_calls() if c.model == "faithful"])
    assert st["correct"] == st["n"] == len(bm.scored_entries())
    assert st["false_pass"] == 0 and st["silent_corrections"] == 0


def test_silent_corrector_alone_causes_false_passes():
    st = bm.model_stats([c for c in simulated_calls() if c.model == "fixer"])
    assert st["silent_corrections"] == st["typo_labels"] > 0
    assert st["false_pass"] > 0


def test_pairing_turns_false_passes_into_reviews():
    st = bm.pair_stats("faithful", "fixer", by_key(simulated_calls()))
    assert st["false_pass"] == 0
    assert st["review"] > 0
    assert set(st["latencies"]) == {2.0}  # pair latency is the slower reader


def test_report_rows_render():
    calls = simulated_calls()
    assert bm.model_row("fixer", [c for c in calls if c.model == "fixer"])[0] == "`fixer`"
    assert bm.pair_row("faithful", "fixer", by_key(calls))[0] == "`faithful` + `fixer`"
