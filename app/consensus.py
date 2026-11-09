"""Reconcile two independent AI readings into one verdict ("double-keying").

Why compare *verdicts* instead of raw text?
    The readers may format the same thing differently ("45% Alc./Vol." vs
    "45% ALC/VOL"). The matching rules already know those are equivalent, so
    we run the rules on each reading and compare the outcomes. Text-level
    disagreement only matters if it changes the verdict.

The safety property this module guarantees:
    A field can only PASS if every reader that answered passed it.

The dangerous error in label review is a false PASS (a bad label approved).
The likeliest cause is a model silently "fixing" a typo while transcribing.
Two different models rarely make the same silent fix, so any pass/not-pass
split goes to a human. See docs/DESIGN.md.
"""

from __future__ import annotations

from .extraction import Extraction
from .matching import overall_status, verify
from .models import ApplicationData, FieldResult, Status

# Higher = worse. MISSING and FAIL both mean "not compliant as read".
_SEVERITY = {Status.SKIPPED: 0, Status.PASS: 1, Status.REVIEW: 2, Status.FAIL: 3, Status.MISSING: 3}


def merge_field(primary: FieldResult, secondary: FieldResult) -> FieldResult:
    """Combine one field's results from the two readers."""
    if primary.status == secondary.status:
        return primary.model_copy(update={"agreement": "agreed"})

    passed = {primary.status, secondary.status} & {Status.PASS}
    if passed:
        # The case this whole design exists for: one says fine, one says not.
        # Show the objecting reader's word diff, so the agent sees *where* to look.
        objector = primary if primary.status != Status.PASS else secondary
        return primary.model_copy(
            update={
                "status": Status.REVIEW,
                "agreement": "disputed",
                "diff": objector.diff,
                "note": "We couldn't confirm this item. Please check the label.",
            }
        )

    # Neither passed (e.g. REVIEW vs FAIL): both already route it to a human,
    # so keep the more severe finding rather than water it down.
    worse = primary if _SEVERITY[primary.status] >= _SEVERITY[secondary.status] else secondary
    return worse.model_copy(update={"agreement": "agreed"})


def verify_extraction(app: ApplicationData, extraction: Extraction) -> tuple[Status, list[FieldResult]]:
    """Turn an Extraction (one or two readings) into the final verdict."""
    per_reader = [verify(app, r.label)[1] for r in extraction.readings]

    if len(per_reader) >= 2:
        fields = [merge_field(a, b) for a, b in zip(per_reader[0], per_reader[1], strict=True)]
        return overall_status(fields), fields

    # Only one reader answered.
    (only,), (reading,) = per_reader, extraction.readings
    fields = []
    for f in only:
        f = f.model_copy(update={"agreement": "single"})
        # Silent auto-correction is the weaker model's characteristic failure,
        # and the warning is the field where it matters. If only the fast
        # secondary answered, its clean warning read isn't trusted on its own.
        if reading.role == "secondary" and f.field == "government_warning" and f.status == Status.PASS:
            f = f.model_copy(
                update={
                    "status": Status.REVIEW,
                    "note": "The wording looks correct, but we couldn't fully confirm it. "
                    "Please check the exact text on the label.",
                }
            )
        fields.append(f)
    return overall_status(fields), fields
