"""Turn one or two readings of a label into the final result ("double-keying").

Each reading is judged on its own by the same rules, then the findings are
merged. Comparing verdicts rather than raw text means "45% Alc./Vol." and
"45% ALC/VOL" don't count as a disagreement.

The safety property: a finding passes only if every reader that answered
passed it. Any disagreement goes to needs_review, since a fail needs evidence
both readers saw. The likeliest cause of a false pass is a reader quietly
fixing a typo while transcribing, and two different models rarely make the
same fix. See docs/DESIGN.md.
"""

from __future__ import annotations

from .extraction import Reading
from .matching import application_findings
from .models import Application, CheckResult, Finding, Overall, ProductType
from .warning import warning_findings

DISAGREE = "We couldn't confirm this item. Please check the label."
UNCONFIRMED = "This looks right, but we couldn't fully confirm it. Please check the label."
UNCLEAR_IMAGE = "This image can't be reliably assessed. Request a clearer image."
UNCLEAR_FAIL = " The photo isn't clear enough to be sure."


def judge_reading(product_type: ProductType, app: Application, reading: Reading) -> list[Finding]:
    return application_findings(product_type, app, reading.label) + warning_findings(reading.label)


def merge(findings: list[Finding]) -> Finding:
    """Combine one finding (same key) across readers."""
    if len({f.status for f in findings}) == 1:
        return findings[0]
    # Show what the objecting reader saw, so the agent knows where to look.
    objector = next(f for f in findings if f.status != "pass")
    observed = objector.observed or next((f.observed for f in findings if f.observed), None)
    return objector.model_copy(update={"status": "needs_review", "explanation": DISAGREE, "observed": observed})


def _secondary_alone(finding: Finding) -> Finding:
    # A fast secondary reader's typical failure is silently correcting the
    # warning, so on its own it can't pass anything about the warning's text
    # or look. Whether a warning is there at all it can still confirm.
    if finding.group == "warning" and finding.status == "pass" and finding.key != "warning_present":
        return finding.model_copy(update={"status": "needs_review", "explanation": UNCONFIRMED})
    return finding


def overall(findings: list[Finding]) -> Overall:
    statuses = {f.status for f in findings}
    if "fail" in statuses:
        return "fail"
    if "needs_review" in statuses:
        return "needs_review"
    return "pass"


def decide(product_type: ProductType, app: Application, readings: list[Reading]) -> CheckResult:
    """The final result for one label. ``readings`` is non-empty, primary first. elapsed_ms is left at 0."""
    per_reader = [judge_reading(product_type, app, r) for r in readings]
    findings = [merge(list(same_key)) for same_key in zip(*per_reader, strict=True)]
    if len(readings) == 1 and readings[0].role == "secondary":
        findings = [_secondary_alone(f) for f in findings]

    assessable = all(r.label.image_readable for r in readings)
    issues = next((r.label.image_issues.strip() for r in readings if (r.label.image_issues or "").strip()), "")
    if assessable:
        return CheckResult(
            overall=overall(findings), image_assessable=True, image_note=issues, findings=findings, elapsed_ms=0
        )

    # A fail needs reliable evidence, which an unclear photo can't give. And
    # nothing passes overall on a photo that couldn't be read with confidence.
    findings = [
        f.model_copy(update={"status": "needs_review", "explanation": f.explanation + UNCLEAR_FAIL})
        if f.status == "fail"
        else f
        for f in findings
    ]
    note = f"{UNCLEAR_IMAGE} {issues}".strip()
    return CheckResult(overall="needs_review", image_assessable=False, image_note=note, findings=findings, elapsed_ms=0)
