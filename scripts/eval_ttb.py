"""Measure the checker on the 120 real, approved applications in samples/ttb/.

    python scripts/eval_ttb.py run              # check every record not yet in the results
    python scripts/eval_ttb.py run --only ID,ID  # check these records again
    python scripts/eval_ttb.py rejudge          # apply the current rules to the saved readings, no calls
    python scripts/eval_ttb.py report           # write docs/ttb-eval.md

Each check is the app's own pipeline (``extract`` then ``decide``) with the
production readers and deadline, on all of the record's label images. The
application holds what TTB's record gives: the brand and, for imports, the
country of origin.

Besides the originals, ALTERED_COUNT seeded copies swap in a different
record's brand name. Those should never pass.

Every approved label that gets a Fail is inspected by hand and classified in
samples/ttb/fail_review.json; the report lists them with that classification.

Results, including each reader's raw reading and token counts, go to
samples/ttb/eval_results.json. Rerunning ``run`` only checks what is missing,
so an interrupted run resumes. This makes real, billed API calls.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app import config  # noqa: E402
from app.consensus import decide  # noqa: E402
from app.extraction import ClaudeExtractionError, Reading, extract  # noqa: E402
from app.main import _warm_up  # noqa: E402
from app.matching import FIELD_LABELS, normalize  # noqa: E402
from app.models import MAX_LABEL_IMAGES, ExtractedLabel, QueueEntry  # noqa: E402
from app.warning import warning_findings  # noqa: E402
from benchmark import PRICES, pct  # noqa: E402
from generate_samples import REGISTRY_URL, TTB_DIR, real_entry, ttb_records  # noqa: E402

RESULTS = TTB_DIR / "eval_results.json"
FAIL_REVIEW = TTB_DIR / "fail_review.json"
REPORT = ROOT / "docs" / "ttb-eval.md"
CONCURRENCY = 4
ALTERED_COUNT = 30
ALTERED_SEED = 20261111
STATUSES = ["pass", "fail", "needs_review", "not_evaluated"]
CLASS_PLURALS = {"checker bug": "checker bugs", "reading error": "reading errors", "label issue": "genuine label issues"}
STATUS_WORDS = {"pass": "Pass", "fail": "Fail", "needs_review": "Needs review", "not_evaluated": "Not evaluated"}
TYPE_NAMES = {"distilled_spirits": "Spirits", "wine": "Wine", "malt_beverage": "Malt beverage"}


def cases() -> list[dict]:
    """Every check to run: each record as approved, then the altered-brand copies."""
    records = sorted(ttb_records(), key=lambda r: r["ttb_id"])
    out = [{"key": r["ttb_id"], "variant": "original", "record": r, "brand": r["brand_name"]} for r in records]
    rng = random.Random(ALTERED_SEED)
    for record in rng.sample(records, ALTERED_COUNT):
        donors = [
            r for r in records
            if normalize(r["brand_name"]) not in normalize(record["brand_name"])
            and normalize(record["brand_name"]) not in normalize(r["brand_name"])
        ]
        donor = rng.choice(donors)
        out.append({"key": f"{record['ttb_id']}-altered", "variant": "altered_brand", "record": record,
                    "brand": donor["brand_name"]})
    return out


def entry_for(case: dict) -> QueueEntry:
    entry = real_entry(case["record"])
    return entry.model_copy(update={"application": entry.application.model_copy(update={"brand_name": case["brand"]})})


def judged(entry: QueueEntry, readings: list[Reading]) -> dict:
    result = decide(entry.product_type, entry.application, readings)
    return {
        "overall": result.overall,
        "image_assessable": result.image_assessable,
        "image_note": result.image_note,
        "findings": [f.model_dump(include={"key", "status", "expected", "observed", "explanation"}) for f in result.findings],
    }


async def check(case: dict, slots: asyncio.Semaphore) -> dict:
    entry = entry_for(case)
    images = [TTB_DIR / "images" / name for name in entry.images][:MAX_LABEL_IMAGES]
    base = {
        "key": case["key"], "ttb_id": entry.id, "variant": case["variant"], "product_type": entry.product_type,
        "imported": bool(entry.application.country_of_origin), "image_count": len(images),
        "application": entry.application.model_dump(),
    }
    async with slots:
        started = time.perf_counter()
        try:
            readings = await extract([path.read_bytes() for path in images])
        except ClaudeExtractionError as exc:
            return {**base, "error": str(exc), "latency_ms": int((time.perf_counter() - started) * 1000)}
        outcome = judged(entry, readings)
        latency_ms = int((time.perf_counter() - started) * 1000)
    print(f"{case['key']}: {outcome['overall']} in {latency_ms / 1000:.1f} s ({len(images)} images)", flush=True)
    return {
        **base, **outcome, "latency_ms": latency_ms,
        "readings": [{"model": r.model, "role": r.role, "usage": r.usage, "label": r.label.model_dump()} for r in readings],
    }


def load_results() -> dict[str, dict]:
    return {r["key"]: r for r in json.loads(RESULTS.read_text())} if RESULTS.exists() else {}


def save_results(results: dict[str, dict]) -> None:
    order = {c["key"]: i for i, c in enumerate(cases())}
    rows = sorted(results.values(), key=lambda r: order.get(r["key"], len(order)))
    RESULTS.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


async def run(only: set[str], limit: int | None) -> None:
    if not config.claude_configured():
        raise SystemExit("Set ANTHROPIC_API_KEY in .env.")
    results = load_results()
    todo = [c for c in cases() if c["key"] in only] if only else [c for c in cases() if c["key"] not in results]
    todo = todo[:limit]
    print(f"{len(todo)} checks to run", flush=True)
    # As at service startup: the first call after a change to the reading
    # format waits while the format is prepared, which would hit the deadline.
    await _warm_up()
    slots = asyncio.Semaphore(CONCURRENCY)
    for done in asyncio.as_completed([check(c, slots) for c in todo]):
        row = await done
        if only:
            row["rerun"] = dt.date.today().isoformat()
        results[row["key"]] = row
        save_results(results)


def rejudge() -> None:
    """Re-apply the current rules to the saved readings. No calls; latency and usage stay as measured."""
    by_key = {c["key"]: c for c in cases()}
    results = load_results()
    changed = 0
    for key, row in results.items():
        if "readings" not in row:
            continue
        readings = [Reading(r["model"], r["role"], ExtractedLabel.model_validate(r["label"]), r["usage"]) for r in row["readings"]]
        outcome = judged(entry_for(by_key[key]), readings)
        changed += outcome["overall"] != row["overall"]
        row.update(outcome)
    save_results(results)
    print(f"Rejudged {len(results)} results; {changed} changed overall.")


# --------------------------------------------------------------------- report


def cost_usd(row: dict) -> float:
    total = 0.0
    for reading in row.get("readings", []):
        pin, pout = PRICES.get(reading["model"], (0, 0))
        usage = reading["usage"]
        total += (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1e6
    return total


def table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def finding_names() -> dict[str, str]:
    sample = ExtractedLabel(government_warning="GOVERNMENT WARNING: x", image_readable=True)
    return {**FIELD_LABELS, **{f.key: f.label for f in warning_findings(sample)}}


def report() -> None:
    results = list(load_results().values())
    review = json.loads(FAIL_REVIEW.read_text())
    first_fails = review["fails"]
    reviewed = {(r["ttb_id"], r["finding"]) for r in first_fails}
    names = finding_names()
    checked = [r for r in results if "overall" in r]
    errors = [r for r in results if "error" in r]
    originals = [r for r in checked if r["variant"] == "original"]
    altered = [r for r in checked if r["variant"] == "altered_brand"]
    now = {(r["ttb_id"], f["key"]): f["status"] for r in originals for f in r["findings"]}

    def overall_row(name: str, rows: list[dict], first: dict) -> list:
        return [name, *(sum(r["overall"] == o for r in rows) for o in ("pass", "needs_review", "fail")),
                first.get("fail", 0), len(rows)]

    first_all = Counter()
    for counts in review["first_run_overall"].values():
        first_all.update(counts)
    by_type = [overall_row(TYPE_NAMES[t], [r for r in originals if r["product_type"] == t], review["first_run_overall"][t])
               for t in TYPE_NAMES]
    by_type.append(overall_row("All", originals, first_all))

    counts = {key: Counter() for key in names}
    for r in originals:
        for f in r["findings"]:
            counts[f["key"]][f["status"]] += 1
    requirement_rows = [[names[k], *(c[s] for s in STATUSES)] for k, c in counts.items()]

    fail_rows = [
        [f"[{r['ttb_id']}]({REGISTRY_URL.format(r['ttb_id'])})", names[r["finding"]], r["class"], r["note"],
         STATUS_WORDS[now[(r["ttb_id"], r["finding"])]]]
        for r in first_fails
    ]
    classes = Counter(r["class"] for r in first_fails)
    current_fails = [(r["ttb_id"], f["key"]) for r in originals for f in r["findings"] if f["status"] == "fail"]
    unreviewed = [k for k in current_fails if k not in reviewed]
    current_classes = Counter(r["class"] for r in first_fails if (r["ttb_id"], r["finding"]) in set(current_fails))
    review_reasons = Counter(f["key"] for r in originals if r["overall"] == "needs_review"
                             for f in r["findings"] if f["status"] == "needs_review")
    multi_image = sum(r["image_count"] > 1 for r in originals)
    brand_review = [next(f for f in r["findings"] if f["key"] == "brand_name") for r in originals]
    brand_review = [f for f in brand_review if f["status"] == "needs_review"]
    elsewhere = sum(f["explanation"].startswith("The label leads with a different name") for f in brand_review)
    partial = sum("part of the application value" in f["explanation"] or "extra words" in f["explanation"] for f in brand_review)
    disagree = sum(f["explanation"].startswith("We couldn't confirm") for f in brand_review)
    brand_reasons = (
        f"Of the {len(brand_review)} brand names that need review, {elsewhere} are labels that lead with another name "
        f"and print the brand elsewhere, {partial} show only part of the name on record or add words to it "
        f"(\"perennial\" for PERENNIAL ARTISAN ALES), and {disagree} are names the two readings disagreed on."
    )

    caught = [r for r in altered if r["overall"] != "pass"]
    brand_failed = [r for r in altered if next(f for f in r["findings"] if f["key"] == "brand_name")["status"] == "fail"]
    latencies = [r["latency_ms"] / 1000 for r in checked]
    costs = [cost_usd(r) for r in checked]
    single = [r for r in checked if len(r.get("readings", [])) < 2]
    unassessable = [r for r in originals if not r["image_assessable"]]
    reruns = sorted(r["ttb_id"] for r in results if r.get("rerun"))
    models = sorted({m["model"] for r in checked for m in r.get("readings", [])})
    checks_run = len(results) + len(reruns)

    REPORT.write_text(f"""# Accuracy on real applications

Generated by `scripts/eval_ttb.py report` from `samples/ttb/eval_results.json` and the hand review in `samples/ttb/fail_review.json`.

## What was tested

The test set is 120 approved applications drawn at random from TTB's Public COLA Registry: 40 spirits, 40 wines and 40 malt beverages, approved between November 2023 and October 2026. Each was checked with all of its label images and the production settings ({", ".join(models)}, {config.READ_DEADLINE_SECONDS:g} second limit), {CONCURRENCY} checks at a time.

TTB's application record gives only the brand name and, for imports, the country of origin. So those two fields and the government warning were checked. Class/type, alcohol content, net contents and the bottler were not evaluated.

Every one of these labels was approved. A Fail on one is either a checker mistake or a problem TTB let through, so each one was opened and classified by hand.

## Overall results

After the fixes described below. The first run's Fail count is shown for comparison.

{table(["Beverage type", "Pass", "Needs review", "Fail", "Fail in first run", "Checked"], by_type)}

Needs review is the most common result. Among labels that need review, the findings that most often need it are {"; ".join(f"{names[k]} ({n})" for k, n in review_reasons.most_common(4))}. {brand_reasons} The bold and paragraph findings need review whenever the two readings disagree or can't tell, which is common on small back-label print.

{len(unassessable)} of {len(originals)} were marked as images that can't be reliably assessed. {len(errors)} checks returned no result. In {len(single)} checks only one of the two readings came back in time.

## Results per requirement

Counts over the {len(originals)} approved labels.

{table(["Requirement", "Pass", "Fail", "Needs review", "Not evaluated"], requirement_rows)}

## Fails on approved labels

In the first run, {len({r["ttb_id"] for r in first_fails})} of {len(originals)} approved labels got at least one Fail, with {len(first_fails)} Fail findings in all. Every label was opened. {classes["checker bug"]} were checker bugs, {classes["reading error"]} were reading errors (the label says something else), and {classes["label issue"]} were genuine label issues.

The checker bugs had four causes, all fixed with tests:

- Labels often set the warning tight, as in "(1)According" or "defects.(2)". Spacing is now ignored, like line breaks. A hyphen that splits a word at a line break is ignored too.
- Labels print accents that TTB's records leave out, as in Martí and MARTI. Accents are now ignored.
- Many labels lead with a product or brewery name and print the brand smaller, or use the bottler's name as the brand. The reading kept only one name, so the brand was never compared. The reading now also lists the label's other names. When the brand appears in one of them or in the bottler statement, the result is needs review instead of fail.
- The same words in another order, or run together in a logo, now need review instead of failing.

After the fixes, {len(set(current_fails))} Fail findings remain on {len({k[0] for k in current_fails})} labels: {", ".join(f"{n} {CLASS_PLURALS[c]}" for c, n in current_classes.items())}.{f" {len(unreviewed)} current Fail findings are not in the hand review yet." if unreviewed else ""}

{table(["Application", "Requirement", "Classification", "Note", "Now"], fail_rows)}

## Changed brand names

{len(altered)} copies had their brand name replaced with another record's brand. None of these should pass.

- {len(caught)} of {len(altered)} did not pass overall after the fixes, and {review["first_run_altered_not_passed"]} of {len(altered)} before them.
- {len(brand_failed)} of {len(altered)} failed the brand name finding. The rest went to needs review.

## Speed and cost

- Median {statistics.median(latencies):.1f} seconds per check, 90th percentile {pct(latencies, 0.9):.1f} seconds, slowest {max(latencies):.1f} seconds. {multi_image} of {len(originals)} applications have two or more label images, and every image goes to both readings, so checks take longer than on the one-image generated labels.
- About {100 * statistics.mean(costs):.1f} cents per check from the token counts at list prices. The {checks_run} checks cost about {statistics.mean(costs) * checks_run:.0f} dollars.

## How the fixes were applied

The rule fixes were applied to the saved readings with `scripts/eval_ttb.py rejudge`, which makes no new calls. Only the {len(reruns)} labels whose brand was printed somewhere the old reading didn't capture were checked again, after the reading started listing other names: {", ".join(reruns)}. The other labels keep their first readings, which don't have the list of other names.
""", encoding="utf-8")
    print(f"Wrote {REPORT.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "rejudge", "report"])
    ap.add_argument("--only", default="", help="comma-separated result keys to check again")
    ap.add_argument("--limit", type=int, default=None, help="check at most this many")
    args = ap.parse_args()
    if args.command == "run":
        asyncio.run(run({k.strip() for k in args.only.split(",") if k.strip()}, args.limit))
    elif args.command == "rejudge":
        rejudge()
    else:
        report()


if __name__ == "__main__":
    main()
