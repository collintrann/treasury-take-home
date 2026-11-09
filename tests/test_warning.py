"""Government warning findings: wording and capitals can fail, typography can only pass or need review."""

import pytest

from app.models import ExtractedLabel
from app.warning import BODY, FULL_TEXT, warning_findings

WARNING_KEYS = [
    "warning_present",
    "warning_wording",
    "warning_header_caps",
    "warning_header_bold",
    "warning_body_not_bold",
    "warning_paragraph",
    "warning_separate",
    "warning_legible",
    "warning_type_size",
]

GOOD = ExtractedLabel(
    government_warning=FULL_TEXT,
    warning_header_bold=True,
    warning_body_bold=False,
    warning_continuous_paragraph=True,
    warning_separate_from_other_text=True,
    warning_legible=True,
    image_readable=True,
)


def check(**changes) -> dict:
    found = warning_findings(GOOD.model_copy(update=changes))
    assert [f.key for f in found] == WARNING_KEYS
    assert {f.group for f in found} == {"warning"}
    return {f.key: f for f in found}


def test_compliant_warning_passes_everything_but_type_size():
    by = check()
    assert {k: f.status for k, f in by.items() if k != "warning_type_size"} == dict.fromkeys(WARNING_KEYS[:-1], "pass")


def test_type_size_is_never_evaluated():
    for by in (check(), check(government_warning=None)):
        assert by["warning_type_size"].status == "not_evaluated"
        assert by["warning_type_size"].explanation == "Can't be measured reliably from a photo."


def test_line_breaks_and_wrapped_header_pass():
    wrapped = "GOVERNMENT\nWARNING: " + BODY.replace(" (2) ", "\n(2) ")
    by = check(government_warning=wrapped)
    assert by["warning_wording"].status == "pass" and by["warning_header_caps"].status == "pass"


def test_title_case_header_fails_and_keeps_label_casing():
    by = check(government_warning="Government Warning: " + BODY)
    assert by["warning_header_caps"].status == "fail"
    assert by["warning_header_caps"].observed == "Government Warning:"
    assert by["warning_wording"].status == "pass"


def test_missing_colon_fails():
    assert check(government_warning="GOVERNMENT WARNING " + BODY)["warning_header_caps"].status == "fail"


def test_missing_lead_in_fails():
    assert check(government_warning=BODY)["warning_header_caps"].status == "fail"


@pytest.mark.parametrize(
    "change",
    [
        ("may cause health problems", "can cause problems"),
        ("Surgeon General", "Surgeon Generel"),
        ("machinery, and", "machinery and"),
        ("drink alcoholic beverages", "drink alcohol beverages"),
    ],
)
def test_changed_wording_fails(change):
    assert check(government_warning=FULL_TEXT.replace(*change))["warning_wording"].status == "fail"


def test_wording_diff_points_at_the_change():
    by = check(government_warning=FULL_TEXT.replace("may cause health problems", "can cause problems"))
    diff = [d.model_dump() for d in by["warning_wording"].diff]
    assert {"op": "missing", "text": "may"} in diff
    assert {"op": "extra", "text": "can"} in diff


def test_truncated_warning_fails():
    assert check(government_warning=FULL_TEXT.split("(2)")[0])["warning_wording"].status == "fail"


def test_missing_warning_needs_review_and_nothing_else_is_judged():
    by = check(government_warning=None)
    assert by["warning_present"].status == "needs_review"
    assert all(by[k].status == "not_evaluated" and by[k].explanation for k in WARNING_KEYS[1:])


@pytest.mark.parametrize(
    "attribute, key, problem",
    [
        ("warning_header_bold", "warning_header_bold", False),
        ("warning_body_bold", "warning_body_not_bold", True),
        ("warning_continuous_paragraph", "warning_paragraph", False),
        ("warning_separate_from_other_text", "warning_separate", False),
        ("warning_legible", "warning_legible", False),
    ],
)
def test_visual_problems_and_uncertainty_need_review_never_fail(attribute, key, problem):
    assert check(**{attribute: problem})[key].status == "needs_review"
    assert check(**{attribute: None})[key].status == "needs_review"
