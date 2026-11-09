"""How readings combine into the final result: consensus, unclear photos and the overall verdict."""

from app.consensus import decide
from app.extraction import Reading
from app.models import Application, ExtractedLabel
from app.warning import FULL_TEXT

APP = Application(
    brand_name="OLD TOM DISTILLERY",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
)
GOOD = ExtractedLabel(
    brand_name="OLD TOM DISTILLERY",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    government_warning=FULL_TEXT,
    warning_header_bold=True,
    warning_body_bold=False,
    warning_continuous_paragraph=True,
    warning_separate_from_other_text=True,
    warning_legible=True,
    image_readable=True,
)
TYPO = GOOD.model_copy(update={"government_warning": FULL_TEXT.replace("Surgeon General", "Surgeon Generel")})


def run(*labels: ExtractedLabel, product_type="distilled_spirits", app=APP, roles=("primary", "secondary")):
    readings = [Reading(f"m{i}", role, label) for i, (role, label) in enumerate(zip(roles[: len(labels)], labels, strict=True))]
    result = decide(product_type, app, readings)
    return result, {f.key: f for f in result.findings}


def test_agreeing_readers_pass():
    result, _ = run(GOOD, GOOD)
    assert result.overall == "pass" and result.image_assessable and result.image_note == ""


def test_different_formatting_with_the_same_verdict_still_passes():
    result, _ = run(GOOD, GOOD.model_copy(update={"net_contents": "75 cl", "brand_name": "Old Tom Distillery"}))
    assert result.overall == "pass"


def test_silent_correction_is_caught_by_disagreement():
    # The primary reads the typo faithfully; the secondary "fixes" it.
    result, by = run(TYPO, GOOD)
    assert by["warning_wording"].status == "needs_review"
    assert {"op": "missing", "text": "General,"} in [d.model_dump() for d in by["warning_wording"].diff]
    assert result.overall == "needs_review"


def test_a_fail_seen_by_only_one_reader_needs_review():
    wrong = GOOD.model_copy(update={"alcohol_content": "40% Alc./Vol."})
    _, by = run(wrong, GOOD.model_copy(update={"alcohol_content": None}))
    assert by["alcohol_content"].status == "needs_review"
    assert by["alcohol_content"].observed == "40% Alc./Vol."


def test_a_fail_both_readers_see_stands():
    wrong = GOOD.model_copy(update={"alcohol_content": "40% Alc./Vol."})
    result, by = run(wrong, wrong)
    assert by["alcohol_content"].status == "fail" and result.overall == "fail"


def test_visual_judgment_passes_only_when_both_readers_say_fine():
    result, by = run(GOOD, GOOD.model_copy(update={"warning_header_bold": None}))
    assert by["warning_header_bold"].status == "needs_review"
    assert result.overall == "needs_review"


def test_visual_problem_alone_never_fails_the_label():
    not_bold = GOOD.model_copy(update={"warning_header_bold": False})
    result, _ = run(not_bold, not_bold)
    assert result.overall == "needs_review"


def test_not_evaluated_never_affects_overall():
    result, by = run(GOOD, GOOD)  # class type and country are blank in APP; type size is never measured
    assert by["class_type"].status == by["country_of_origin"].status == by["warning_type_size"].status == "not_evaluated"
    assert result.overall == "pass"


def test_missing_warning_needs_review_not_fail():
    gone = GOOD.model_copy(update={"government_warning": None})
    result, _ = run(gone, gone)
    assert result.overall == "needs_review"


def test_primary_alone_is_trusted():
    result, _ = run(GOOD, roles=("primary",))
    assert result.overall == "pass"


def test_secondary_alone_cannot_pass_the_warning_but_other_fields_stand():
    result, by = run(GOOD, roles=("secondary",))
    assert by["warning_wording"].status == "needs_review"
    assert by["warning_present"].status == "pass"
    assert by["brand_name"].status == "pass"
    assert result.overall == "needs_review"


def test_unreadable_image_turns_fails_into_needs_review_and_flags_it():
    blurry = GOOD.model_copy(
        update={"alcohol_content": "40% Alc./Vol.", "image_readable": False, "image_issues": "Heavy blur."}
    )
    result, by = run(blurry, blurry)
    assert by["alcohol_content"].status == "needs_review"
    assert result.overall == "needs_review"
    assert result.image_assessable is False
    assert result.image_note.startswith("This image can't be reliably assessed. Request a clearer image.")


def test_unreadable_image_never_passes_overall():
    blurry = GOOD.model_copy(update={"image_readable": False})
    result, _ = run(GOOD, blurry)
    assert result.overall == "needs_review" and result.image_assessable is False


def test_photo_issues_are_passed_on_when_still_readable():
    glare = GOOD.model_copy(update={"image_issues": "Some glare on the right."})
    result, _ = run(glare, GOOD)
    assert result.image_assessable and result.image_note == "Some glare on the right."
