from app.matching import compare_alcohol, compare_text, compare_volume, parse_abv, parse_volume_ml, verify
from app.models import ApplicationData, ExtractedLabel, Status
from app.warning import BODY, FULL_TEXT, check_warning


# ---------------------------------------------------------------- text fields

def test_exact_match_passes():
    r = compare_text("brand_name", "OLD TOM DISTILLERY", "OLD TOM DISTILLERY")
    assert r.status == Status.PASS and r.note == "Exact match."


def test_case_and_punctuation_difference_passes_with_note():
    # Dave's example: obviously the same brand.
    r = compare_text("brand_name", "Stone's Throw", "STONE'S THROW")
    assert r.status == Status.PASS
    assert "capitalization" in r.note


def test_curly_apostrophe_is_same_as_straight():
    assert compare_text("brand_name", "Stone's Throw", "STONE’S THROW").status == Status.PASS


def test_one_letter_typo_needs_review():
    r = compare_text("brand_name", "Old Tom Distillery", "Old Tom Distilery")
    assert r.status == Status.REVIEW


def test_different_brand_fails():
    assert compare_text("brand_name", "Old Tom Distillery", "Riverbend").status == Status.FAIL


def test_value_inside_longer_label_text_passes():
    assert compare_text("country_of_origin", "Scotland", "Product of Scotland").status == Status.PASS


def test_partial_word_is_not_a_containment_match():
    # "Scot" must not match "Scotland" just because it's a substring.
    assert compare_text("country_of_origin", "Scot", "Product of Scotland").status != Status.PASS


def test_blank_application_field_is_skipped():
    assert compare_text("class_type", "", "Vodka").status == Status.SKIPPED


def test_field_absent_from_label_is_missing():
    assert compare_text("class_type", "Vodka", None).status == Status.MISSING


# -------------------------------------------------------------------- alcohol

def test_parse_abv_and_proof():
    assert parse_abv("45% Alc./Vol. (90 Proof)") == (45.0, 90.0)
    assert parse_abv("ALC. 12.5% BY VOL.") == (12.5, None)
    assert parse_abv("12,5 % vol") == (12.5, None)


def test_abv_formatting_differences_pass():
    assert compare_alcohol("45% Alc./Vol. (90 Proof)", "45 % ALC/VOL - 90 PROOF").status == Status.PASS


def test_abv_mismatch_fails():
    r = compare_alcohol("45% Alc./Vol.", "40% Alc./Vol.")
    assert r.status == Status.FAIL and "45" in r.note and "40" in r.note


def test_proof_only_application_matches_abv_label():
    assert compare_alcohol("90 Proof", "45% Alc./Vol.").status == Status.PASS


def test_label_with_inconsistent_proof_fails():
    r = compare_alcohol("45%", "45% Alc./Vol. (80 Proof)")
    assert r.status == Status.FAIL and "inconsistent" in r.note


# --------------------------------------------------------------- net contents

def test_parse_volume_units():
    assert parse_volume_ml("750 mL") == 750
    assert parse_volume_ml("75 cl") == 750
    assert parse_volume_ml("1 L") == 1000
    assert parse_volume_ml("1.75 Liters") == 1750
    assert round(parse_volume_ml("12 FL. OZ")) == 355


def test_same_volume_different_units_passes():
    r = compare_volume("700 mL", "70 cl")
    assert r.status == Status.PASS and "written differently" in r.note


def test_volume_mismatch_fails():
    assert compare_volume("750 mL", "700 mL").status == Status.FAIL


# -------------------------------------------------------------------- warning

def test_exact_bold_warning_passes():
    assert check_warning(FULL_TEXT, header_bold=True)[0] == "pass"


def test_warning_with_line_breaks_passes():
    wrapped = FULL_TEXT.replace(" women ", "\nwomen ").replace(" (2) ", "\n(2) ")
    assert check_warning(wrapped, header_bold=True)[0] == "pass"


def test_title_case_header_fails():
    # Jenny's example.
    status, note, _ = check_warning("Government Warning: " + BODY, header_bold=True)
    assert status == "fail" and "capital" in note


def test_missing_colon_fails():
    assert check_warning("GOVERNMENT WARNING " + BODY, header_bold=True)[0] == "fail"


def test_reworded_warning_fails_and_diff_shows_change():
    altered = FULL_TEXT.replace("may cause health problems", "can cause problems")
    status, _, diff = check_warning(altered, header_bold=True)
    assert status == "fail"
    assert {"op": "missing", "text": "may"} in diff
    assert {"op": "extra", "text": "can"} in diff


def test_truncated_warning_fails():
    assert check_warning(FULL_TEXT.split("(2)")[0], header_bold=True)[0] == "fail"


def test_not_bold_fails():
    assert check_warning(FULL_TEXT, header_bold=False)[0] == "fail"


def test_unknown_boldness_needs_review():
    assert check_warning(FULL_TEXT, header_bold=None)[0] == "review"


def test_absent_warning_is_missing():
    assert check_warning(None, header_bold=None)[0] == "missing"


def test_ocr_misread_is_review_not_fail():
    misread = FULL_TEXT.replace("alcoholic beverages during", "alcahalic beverages during")
    assert check_warning(misread, None, lenient=True)[0] == "review"
    assert check_warning(misread, True, lenient=False)[0] == "fail"


def test_ocr_mode_still_fails_real_rewording():
    altered = FULL_TEXT.replace("may cause health problems", "can cause problems")
    assert check_warning(altered, None, lenient=True)[0] == "fail"


def test_ocr_mode_still_fails_title_case_header():
    assert check_warning("Government Warning: " + BODY, None, lenient=True)[0] == "fail"


# -------------------------------------------------------------------- rollup

APP = ApplicationData(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
)
GOOD_LABEL = ExtractedLabel(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    government_warning=FULL_TEXT,
    warning_header_bold=True,
)


def test_all_good_is_pass():
    overall, fields = verify(APP, GOOD_LABEL)
    assert overall == Status.PASS
    assert len(fields) == 7


def test_any_fail_makes_overall_fail():
    overall, _ = verify(APP, GOOD_LABEL.model_copy(update={"net_contents": "1 L"}))
    assert overall == Status.FAIL


def test_review_without_fail_is_review():
    overall, _ = verify(APP, GOOD_LABEL.model_copy(update={"warning_header_bold": None}))
    assert overall == Status.REVIEW


def test_ocr_missing_becomes_review():
    overall, fields = verify(APP, GOOD_LABEL.model_copy(update={"class_type": None}), from_ocr=True)
    assert next(f for f in fields if f.field == "class_type").status == Status.REVIEW
    assert overall == Status.REVIEW


def test_low_confidence_fail_becomes_review():
    label = GOOD_LABEL.model_copy(update={"alcohol_content": "40%"})
    overall, fields = verify(APP, label, from_ocr=True, low_confidence=True)
    abv = next(f for f in fields if f.field == "alcohol_content")
    assert abv.status == Status.REVIEW and "hard to read" in abv.note


# ------------------------------------------------- audit regressions (M1, M6)

def test_warning_header_wrapped_across_lines_passes():
    assert check_warning("GOVERNMENT\nWARNING: " + BODY, header_bold=True)[0] == "pass"
    assert check_warning("GOVERNMENT  WARNING: " + BODY, header_bold=True)[0] == "pass"


def test_extra_words_around_class_type_are_not_a_pass():
    assert compare_text("class_type", "Rum", "Spiced Rum Liqueur").status == Status.REVIEW


def test_brand_that_is_only_part_of_the_label_brand_is_not_a_pass():
    assert compare_text("brand_name", "Old Tom", "OLD TOM DISTILLERY").status == Status.REVIEW


def test_country_inside_a_different_place_name_is_not_a_pass():
    assert compare_text("country_of_origin", "Mexico", "Product of New Mexico").status == Status.REVIEW


def test_known_label_phrasing_still_passes():
    assert compare_text("country_of_origin", "Scotland", "Product of Scotland").status == Status.PASS
    assert compare_text("country_of_origin", "France", "Made in France").status == Status.PASS
    assert compare_text(
        "producer_name_address", "Old Tom Distillery, Bardstown, KY", "Distilled and bottled by Old Tom Distillery, Bardstown, KY"
    ).status == Status.PASS


def test_punctuation_only_application_value_is_skipped():
    assert compare_text("brand_name", "-", "Anything").status == Status.SKIPPED


def test_thousands_separator_in_volume():
    assert parse_volume_ml("1,000 mL") == 1000
    assert compare_volume("1 L", "1,000 mL").status == Status.PASS


def test_us_customary_volume_units():
    assert round(parse_volume_ml("1 PINT")) == 473
    assert round(parse_volume_ml("1 Quart")) == 946
    assert round(parse_volume_ml("1 gallon")) == 3785


def test_abv_prefers_the_alcohol_statement_over_other_percentages():
    assert parse_abv("100% Blue Agave 40% Alc/Vol") == (40.0, None)
    assert parse_abv("100% Blue Agave · ALC. 40% BY VOL.") == (40.0, None)
