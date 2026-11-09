"""Benchmark AI readers (alone and in pairs) on the review queue labels.

    ANTHROPIC_API_KEY=... python scripts/benchmark.py --runs 3

What it measures, per model and per primary+secondary pairing:
  * latency p50 / p90 and share of labels inside the 5 s budget
  * warning transcribed exactly as printed
  * silent corrections: the label has a typo but the reader returned the
    correct regulatory text - the failure that causes false PASSes
  * bold detection accuracy
  * verdict accuracy against each item's expected_overall, false PASS (worst),
    false FAIL, and how often a label is routed to needs review
  * approximate cost per label

Applications and expected results come from samples/queue/applications.json.
What was printed on each label (for the warning and bold scores) comes from
scripts/generate_samples.py, which made the images. Results are written to
docs/benchmark-results.md.

Note: this makes real, billed API calls (25 labels x models x runs).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import itertools
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app import config  # noqa: E402

# Measure true model latency, not our deadline: give calls plenty of time.
config.READ_DEADLINE_SECONDS = 120

from app.consensus import decide  # noqa: E402
from app.extraction import Reading  # noqa: E402
from app.extraction.claude_reader import extract_with_claude  # noqa: E402
from app.extraction.image import load_image, to_upload_jpeg  # noqa: E402
from app.models import ExtractedLabel, QueueEntry  # noqa: E402
from app.queue import QUEUE_DIR, load_queue  # noqa: E402
from app.warning import FULL_TEXT  # noqa: E402
from generate_samples import CASES, Printed  # noqa: E402

PRINTED = {c.id: c.printed for c in CASES}

# USD per million tokens (input, output). Update if pricing changes.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
BUDGET_SECONDS = 5.0


@dataclass
class Call:
    model: str
    entry: QueueEntry
    run: int
    seconds: float
    result: ExtractedLabel | None
    error: str | None
    usage: dict


def squash(text: str | None) -> str:
    return " ".join((text or "").split())


def printed_warning(p: Printed) -> str | None:
    if not p.has_warning:
        return None
    return squash(f"{p.warning_header or ''} {p.warning_body}")


def overall_for(entry: QueueEntry, readings: list[Reading]) -> str:
    return decide(entry.product_type, entry.application, readings).overall


async def timed_call(model: str, entry: QueueEntry, run: int, jpeg: bytes) -> Call:
    usage: dict = {}
    start = time.perf_counter()
    try:
        result = await extract_with_claude(jpeg, model, usage=usage)
        return Call(model, entry, run, time.perf_counter() - start, result, None, usage)
    except Exception as exc:  # benchmark records every failure rather than stopping
        return Call(model, entry, run, time.perf_counter() - start, None, str(exc), usage)


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * len(ordered) + 0.5) - 1))]


def verdict_stats(pairs: list[tuple[str, str]]) -> dict:
    """pairs: (expected, actual) verdicts."""
    n = len(pairs)
    return {
        "correct": sum(e == a for e, a in pairs),
        "false_pass": sum(e != "pass" and a == "pass" for e, a in pairs),
        "false_fail": sum(e == "pass" and a == "fail" for e, a in pairs),
        "review": sum(a == "needs_review" for _, a in pairs),
        "n": n,
    }


def cost(call: Call) -> float:
    pin, pout = PRICES.get(call.model, (0, 0))
    return (call.usage.get("input_tokens", 0) * pin + call.usage.get("output_tokens", 0) * pout) / 1e6


def model_stats(calls: list[Call]) -> dict:
    """Score one model's calls. Every value is a number, for the report and the tests."""
    ok = [c for c in calls if c.result]
    printed = {c.entry.id: PRINTED[c.entry.id] for c in calls}
    warn = [c for c in ok if printed_warning(printed[c.entry.id])]
    typo = [c for c in warn if printed_warning(printed[c.entry.id]) != FULL_TEXT]
    bold = [c for c in warn if printed[c.entry.id].warning_header]
    verdicts = [
        (c.entry.expected_overall, overall_for(c.entry, [Reading(c.model, "primary", c.result)])) for c in ok
    ]
    return {
        "ok": len(ok),
        "calls": len(calls),
        "latencies": [c.seconds for c in ok],
        "warnings": len(warn),
        "warning_exact": sum(
            squash(c.result.government_warning) == printed_warning(printed[c.entry.id]) for c in warn
        ),
        "typo_labels": len(typo),
        "silent_corrections": sum(squash(c.result.government_warning) == FULL_TEXT for c in typo),
        "bold_labels": len(bold),
        "bold_right": sum(c.result.warning_header_bold == printed[c.entry.id].header_bold for c in bold),
        "cents": [cost(c) * 100 for c in ok],
        **verdict_stats(verdicts),
    }


def pair_stats(primary: str, secondary: str, by_key: dict) -> dict:
    """Score a primary+secondary pairing using the app's own consensus rules."""
    latencies, verdicts, cents = [], [], []
    for calls in by_key.values():
        a, b = calls.get(primary), calls.get(secondary)
        readings = []
        if a and a.result:
            readings.append(Reading(primary, "primary", a.result))
        if b and b.result:
            readings.append(Reading(secondary, "secondary", b.result))
        if not readings:
            continue
        entry = (a or b).entry
        verdicts.append((entry.expected_overall, overall_for(entry, readings)))
        latencies.append(max(c.seconds for c in (a, b) if c))
        cents.append(sum(cost(c) for c in (a, b) if c) * 100)
    return {"latencies": latencies, "cents": cents, **verdict_stats(verdicts)}


def _latency_cells(latencies: list[float]) -> list[str]:
    within = sum(x <= BUDGET_SECONDS for x in latencies) / max(1, len(latencies))
    return [f"{pct(latencies, .5):.1f} / {pct(latencies, .9):.1f}", f"{within:.0%}"]


def _verdict_cells(st: dict) -> list[str]:
    cost_cell = f"{statistics.mean(st['cents']):.2f}¢" if st["cents"] else "-"
    return [f"{st['correct']}/{st['n']}", f"**{st['false_pass']}**", str(st["false_fail"]), str(st["review"]), cost_cell]


def model_row(model: str, calls: list[Call]) -> list[str]:
    st = model_stats(calls)
    return [
        f"`{model}`",
        f"{st['ok']}/{st['calls']}",
        *_latency_cells(st["latencies"]),
        f"{st['warning_exact']}/{st['warnings']}",
        f"**{st['silent_corrections']}**/{st['typo_labels']}",
        f"{st['bold_right']}/{st['bold_labels']}",
        *_verdict_cells(st),
    ]


def pair_row(primary: str, secondary: str, by_key: dict) -> list[str]:
    st = pair_stats(primary, secondary, by_key)
    return [f"`{primary}` + `{secondary}`", *_latency_cells(st["latencies"]), *_verdict_cells(st)]


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default="claude-opus-5-5,claude-sonnet-5-5,claude-haiku-5-5")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--effort", default=config.EFFORT)
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmark-results.md"))
    args = ap.parse_args()

    config.EFFORT = args.effort
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    entries = list(load_queue().values())
    jpegs = {e.id: to_upload_jpeg(load_image((QUEUE_DIR / e.image).read_bytes())) for e in entries}

    calls: list[Call] = []
    total = args.runs * len(entries)
    for run in range(args.runs):
        for i, entry in enumerate(entries):
            # All models at once, as in production, so latency reflects real contention.
            batch = await asyncio.gather(*(timed_call(m, entry, run, jpegs[entry.id]) for m in models))
            calls.extend(batch)
            done = run * len(entries) + i + 1
            summary = ", ".join(f"{c.model.split('-')[1]} {c.seconds:.1f}s{' ERR' if c.error else ''}" for c in batch)
            print(f"[{done}/{total}] {entry.id}: {summary}", flush=True)

    errors = [c for c in calls if c.error]
    by_key: dict = {}
    for c in calls:
        by_key.setdefault((c.run, c.entry.id), {})[c.model] = c

    single = table(
        ["Model", "OK", "Latency p50 / p90 (s)", "≤ 5 s", "Warning exact", "Silent corrections",
         "Bold right", "Verdict right", "False PASS", "False FAIL", "→ Review", "Cost/label"],
        [model_row(m, [c for c in calls if c.model == m]) for m in models],
    )
    pairs = [(a, b) for a, b in itertools.permutations(models, 2) if models.index(a) < models.index(b)]
    paired = table(
        ["Primary + secondary", "Latency p50 / p90 (s)", "≤ 5 s", "Verdict right", "False PASS", "False FAIL",
         "→ Review", "Cost/label"],
        [pair_row(a, b, by_key) for a, b in pairs],
    )

    report = f"""# Benchmark results

Generated by `scripts/benchmark.py` on {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC}:
{len(entries)} queue labels × {args.runs} runs, effort `{args.effort}`, all models called concurrently per label.

**Caveats:** synthetic labels (see `samples/queue/`), small sample, and latency measured from the
build environment, not TTB's network. Treat it as a comparison between options, not a forecast.

## Single models

{single}

## Two-reader pairings (consensus rules from `app/consensus.py`)

Pair latency is the slower of the two readers (they run in parallel).

{paired}

## How to read this

* **False PASS** is the number that matters most: a non-compliant label marked as passing.
* **Silent corrections** counts typo'd warnings that a reader returned as the *correct*
  regulatory text. A single reader doing this produces a false PASS; a pairing only does if
  both readers make the same correction.
* **→ Review** (needs review) is the cost of caution: labels sent to a human. Too high, and agents stop
  trusting the tool.
* Errors: {len(errors)}{''.join(f'{chr(10)}  * `{c.model}` on {c.entry.id}: {c.error}' for c in errors[:10])}
"""
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(report)
    print("\n" + report)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
