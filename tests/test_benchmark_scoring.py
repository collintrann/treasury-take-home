"""Benchmark scoring, checked with simulated readers (no API calls).

Also pins down the core claim of the two-reader design: a reader that silently
"fixes" typos produces false PASSes alone, and none when paired with a
faithful reader.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark as bm  # noqa: E402
from app.models import ExtractedLabel  # noqa: E402
from app.warning import FULL_TEXT  # noqa: E402


def simulated_calls():
    calls = []
    for lab in bm.LABELS:
        printed = bm.printed_warning(lab)
        faithful = ExtractedLabel(
            brand_name=lab.brand, class_type=lab.class_type, alcohol_content=lab.abv, net_contents=lab.net,
            producer_name_address=lab.producer, country_of_origin=lab.country or None,
            government_warning=printed, warning_header_bold=lab.header_bold if printed else None,
        )
        fixer = faithful.model_copy(update={"government_warning": FULL_TEXT if printed else None})
        calls.append(bm.Call("faithful", lab, 0, 2.0, faithful, None, {}))
        calls.append(bm.Call("fixer", lab, 0, 1.0, fixer, None, {}))
    return calls


def cols(row, names):
    return dict(zip(names, row))


def test_perfect_reader_scores_perfectly():
    row = cols(bm.model_row("faithful", [c for c in simulated_calls() if c.model == "faithful"]),
               ["m", "ok", "lat", "budget", "exact", "silent", "bold", "verdict", "fp", "ff", "review", "cost"])
    assert row["verdict"] == f"{len(bm.LABELS)}/{len(bm.LABELS)}"
    assert row["fp"] == "**0**" and row["silent"].startswith("**0**")


def test_silent_corrector_alone_causes_false_passes():
    row = cols(bm.model_row("fixer", [c for c in simulated_calls() if c.model == "fixer"]),
               ["m", "ok", "lat", "budget", "exact", "silent", "bold", "verdict", "fp", "ff", "review", "cost"])
    assert row["fp"] != "**0**"


def test_pairing_turns_false_passes_into_reviews():
    calls = simulated_calls()
    by_key = {}
    for c in calls:
        by_key.setdefault((c.run, c.label.filename), {})[c.model] = c
    row = cols(bm.pair_row("faithful", "fixer", by_key), ["pair", "lat", "budget", "verdict", "fp", "ff", "review", "cost"])
    assert row["fp"] == "**0**"
    assert int(row["review"]) > 0
    assert row["lat"].startswith("2.0")  # pair latency = the slower reader
