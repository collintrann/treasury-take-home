"""The consensus rules, tested directly (no HTTP, no models)."""

from app.consensus import merge_field, verify_extraction
from app.extraction import Extraction, Reading
from app.models import ApplicationData, ExtractedLabel, FieldResult, Status
from app.warning import FULL_TEXT

def fr(status: Status, found: str = "x") -> FieldResult:
    return FieldResult(field="brand_name", label="Brand name", expected="x", found=found, status=status, note=status.value)


def test_same_verdict_is_agreed():
    out = merge_field(fr(Status.PASS), fr(Status.PASS, found="X"))
    assert out.status == Status.PASS and out.agreement == "agreed"


def test_pass_vs_fail_goes_to_review():
    out = merge_field(fr(Status.FAIL, "Riverbend"), fr(Status.PASS, "Old Tom"))
    assert out.status == Status.REVIEW and out.agreement == "disputed"


def test_pass_vs_review_is_also_disputed():
    assert merge_field(fr(Status.PASS), fr(Status.REVIEW)).agreement == "disputed"


def test_neither_passes_keeps_the_more_severe():
    out = merge_field(fr(Status.REVIEW), fr(Status.FAIL))
    assert out.status == Status.FAIL
    out = merge_field(fr(Status.MISSING), fr(Status.REVIEW))
    assert out.status == Status.MISSING


APP = ApplicationData(brand_name="OLD TOM DISTILLERY", net_contents="750 mL")
GOOD = ExtractedLabel(brand_name="OLD TOM DISTILLERY", net_contents="750 mL", government_warning=FULL_TEXT, warning_header_bold=True)


def test_different_formatting_same_verdict_agrees():
    # "75 cl" and "750 mL" are different text but the same verdict.
    other = GOOD.model_copy(update={"net_contents": "75 cl"})
    overall, fields = verify_extraction(
        APP, Extraction("claude", [Reading("a", "primary", GOOD), Reading("b", "secondary", other)])
    )
    assert overall == Status.PASS
    assert all(f.agreement == "agreed" for f in fields)


def test_disagreement_on_bold_goes_to_review():
    other = GOOD.model_copy(update={"warning_header_bold": False})
    overall, fields = verify_extraction(
        APP, Extraction("claude", [Reading("a", "primary", GOOD), Reading("b", "secondary", other)])
    )
    warning = next(f for f in fields if f.field == "government_warning")
    assert warning.status == Status.REVIEW and warning.agreement == "disputed"
    assert overall == Status.REVIEW


def test_primary_alone_is_trusted():
    overall, fields = verify_extraction(APP, Extraction("claude", [Reading("a", "primary", GOOD)]))
    assert overall == Status.PASS and all(f.agreement == "single" for f in fields)


def test_secondary_alone_cannot_pass_warning_but_other_fields_stand():
    overall, fields = verify_extraction(APP, Extraction("claude", [Reading("b", "secondary", GOOD)]))
    by = {f.field: f for f in fields}
    assert by["government_warning"].status == Status.REVIEW
    assert by["brand_name"].status == Status.PASS
    assert overall == Status.REVIEW
