"""Application-field rules: comparisons and which fields apply to which product type."""

import pytest

from app.matching import application_findings, compare_alcohol, compare_text, compare_volume, parse_abv, parse_volume_ml
from app.models import Application, ExtractedLabel


def status(result: tuple[str, str]) -> str:
    return result[0]


# ---------------------------------------------------------------- text fields

def test_exact_match_passes():
    assert compare_text("brand_name", "OLD TOM DISTILLERY", "OLD TOM DISTILLERY") == ("pass", "Exact match.")


def test_case_and_punctuation_difference_passes_with_note():
    result, note = compare_text("brand_name", "Stone's Throw", "STONE'S THROW")
    assert result == "pass" and "capitalization" in note


def test_curly_apostrophe_is_same_as_straight():
    assert status(compare_text("brand_name", "Stone's Throw", "STONE’S THROW")) == "pass"


def test_one_letter_typo_needs_review():
    assert status(compare_text("brand_name", "Old Tom Distillery", "Old Tom Distilery")) == "needs_review"


def test_different_brand_fails():
    assert status(compare_text("brand_name", "Harbor Light", "SALT HARBOR")) == "fail"


def test_known_label_phrasing_still_passes():
    assert status(compare_text("country_of_origin", "Scotland", "Product of Scotland")) == "pass"
    assert status(compare_text("country_of_origin", "France", "Made in France")) == "pass"
    for label in (
        "Distilled and bottled by Old Tom Distillery, Bardstown, KY",
        "Brewed and canned by Old Tom Distillery, Bardstown, KY",
    ):
        assert status(compare_text("producer_name_address", "Old Tom Distillery, Bardstown, KY", label)) == "pass"


def test_partial_word_is_not_a_containment_match():
    assert status(compare_text("country_of_origin", "Scot", "Product of Scotland")) != "pass"


def test_extra_or_missing_words_need_review():
    assert status(compare_text("class_type", "Rum", "Spiced Rum Liqueur")) == "needs_review"
    assert status(compare_text("brand_name", "Old Tom", "OLD TOM DISTILLERY")) == "needs_review"
    assert status(compare_text("country_of_origin", "Mexico", "Product of New Mexico")) == "needs_review"


# -------------------------------------------------------------------- alcohol

def test_parse_abv_and_proof():
    assert parse_abv("45% Alc./Vol. (90 Proof)") == (45.0, 90.0)
    assert parse_abv("ALC. 12.5% BY VOL.") == (12.5, None)
    assert parse_abv("12,5 % vol") == (12.5, None)


def test_abv_prefers_the_alcohol_statement_over_other_percentages():
    assert parse_abv("100% Blue Agave 40% Alc/Vol") == (40.0, None)
    assert parse_abv("100% Blue Agave · ALC. 40% BY VOL.") == (40.0, None)


def test_abv_formatting_differences_pass():
    assert status(compare_alcohol("45% Alc./Vol. (90 Proof)", "45 % ALC/VOL - 90 PROOF")) == "pass"


def test_proof_only_application_matches_abv_label():
    assert status(compare_alcohol("90 Proof", "45% Alc./Vol.")) == "pass"


def test_abv_mismatch_fails_and_names_both_values():
    result, note = compare_alcohol("45% Alc./Vol.", "40% Alc./Vol.")
    assert result == "fail" and "45" in note and "40" in note


def test_label_with_inconsistent_proof_fails():
    result, note = compare_alcohol("45%", "45% Alc./Vol. (80 Proof)")
    assert result == "fail" and "80" in note


# --------------------------------------------------------------- net contents

def test_parse_volume_units():
    assert parse_volume_ml("750 mL") == 750
    assert parse_volume_ml("75 cl") == 750
    assert parse_volume_ml("1 L") == 1000
    assert parse_volume_ml("0.75 L") == 750
    assert parse_volume_ml("1.75 Liters") == 1750
    assert parse_volume_ml("1,000 mL") == 1000
    assert round(parse_volume_ml("12 FL OZ")) == 355
    assert round(parse_volume_ml("12 FL. OZ")) == 355
    assert round(parse_volume_ml("1 PINT")) == 473


@pytest.mark.parametrize(
    "application, label",
    [("750 mL", "0.75 L"), ("0.75 L", "750 mL"), ("700 mL", "70 cl"), ("1 L", "1,000 mL"), ("16 fl oz", "1 PINT")],
)
def test_same_volume_in_different_units_passes(application, label):
    assert status(compare_volume(application, label)) == "pass"


def test_volume_mismatch_fails():
    assert status(compare_volume("750 mL", "375 mL")) == "fail"


# -------------------------------------------------------------- applicability

FULL_APP = Application(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    producer_name_address="Old Tom Distillery, Bardstown, KY",
)
FULL_LABEL = ExtractedLabel(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    producer_name_address="Bottled by Old Tom Distillery, Bardstown, KY",
    image_readable=True,
)


def findings(product_type, app=FULL_APP, label=FULL_LABEL) -> dict:
    return {f.key: f for f in application_findings(product_type, app, label)}


def test_one_finding_per_application_field_in_order():
    keys = [f.key for f in application_findings("distilled_spirits", FULL_APP, FULL_LABEL)]
    assert keys == list(Application.model_fields)


def test_matching_spirits_label_passes_every_field_but_country():
    by = findings("distilled_spirits")
    assert {k: f.status for k, f in by.items()} == {
        "brand_name": "pass",
        "class_type": "pass",
        "alcohol_content": "pass",
        "net_contents": "pass",
        "producer_name_address": "pass",
        "country_of_origin": "not_evaluated",
    }
    assert by["country_of_origin"].explanation == "No country of origin in the application. It is needed only for imports."


def test_observed_keeps_the_label_text_as_printed():
    by = findings("distilled_spirits", app=FULL_APP.model_copy(update={"brand_name": "Old Tom Distillery"}))
    assert by["brand_name"].observed == "OLD TOM DISTILLERY"
    assert by["brand_name"].expected == "Old Tom Distillery"


def test_blank_application_field_is_not_evaluated():
    by = findings("distilled_spirits", app=FULL_APP.model_copy(update={"class_type": ""}))
    assert by["class_type"].status == "not_evaluated"
    assert by["class_type"].explanation == "Not provided in the application."


def test_field_missing_from_the_photo_needs_review_not_fail():
    by = findings("distilled_spirits", label=FULL_LABEL.model_copy(update={"brand_name": None, "net_contents": " "}))
    assert by["brand_name"].status == "needs_review"
    assert by["net_contents"].status == "needs_review"


def test_spirits_without_alcohol_statement_needs_review():
    by = findings("distilled_spirits", label=FULL_LABEL.model_copy(update={"alcohol_content": None}))
    assert by["alcohol_content"].status == "needs_review"


@pytest.mark.parametrize("app_abv", ["12.5% Alc./Vol.", "14%", "28 Proof"])
def test_wine_at_or_under_14_may_omit_alcohol(app_abv):
    by = findings(
        "wine",
        app=FULL_APP.model_copy(update={"alcohol_content": app_abv}),
        label=FULL_LABEL.model_copy(update={"alcohol_content": None}),
    )
    assert by["alcohol_content"].status == "not_evaluated"
    assert by["alcohol_content"].explanation == "Not required for wine at 14% or less."


def test_wine_at_or_under_14_must_still_match_when_shown():
    by = findings(
        "wine",
        app=FULL_APP.model_copy(update={"alcohol_content": "12.5% Alc./Vol."}),
        label=FULL_LABEL.model_copy(update={"alcohol_content": "13% Alc./Vol."}),
    )
    assert by["alcohol_content"].status == "fail"


def test_wine_over_14_requires_alcohol():
    by = findings(
        "wine",
        app=FULL_APP.model_copy(update={"alcohol_content": "14.5% Alc./Vol."}),
        label=FULL_LABEL.model_copy(update={"alcohol_content": None}),
    )
    assert by["alcohol_content"].status == "needs_review"


def test_malt_beverage_may_omit_alcohol():
    by = findings(
        "malt_beverage",
        app=FULL_APP.model_copy(update={"alcohol_content": "5% Alc./Vol."}),
        label=FULL_LABEL.model_copy(update={"alcohol_content": None}),
    )
    assert by["alcohol_content"].status == "not_evaluated"
    assert by["alcohol_content"].explanation == "Not required for malt beverages."


def test_malt_beverage_alcohol_is_compared_when_shown():
    app = FULL_APP.model_copy(update={"alcohol_content": "5% Alc./Vol."})
    shown = FULL_LABEL.model_copy(update={"alcohol_content": "6.8% ALC/VOL"})
    assert findings("malt_beverage", app=app, label=shown)["alcohol_content"].status == "fail"
    shown = FULL_LABEL.model_copy(update={"alcohol_content": "5% ALC/VOL"})
    assert findings("malt_beverage", app=app, label=shown)["alcohol_content"].status == "pass"


def test_import_country_is_compared():
    app = FULL_APP.model_copy(update={"country_of_origin": "Scotland"})
    assert findings("distilled_spirits", app=app, label=FULL_LABEL)["country_of_origin"].status == "needs_review"
    label = FULL_LABEL.model_copy(update={"country_of_origin": "Product of Scotland"})
    assert findings("distilled_spirits", app=app, label=label)["country_of_origin"].status == "pass"
    label = FULL_LABEL.model_copy(update={"country_of_origin": "Product of Ireland"})
    assert findings("distilled_spirits", app=app, label=label)["country_of_origin"].status == "fail"


# ------------------------------------------- cases found on real approved labels

def test_accents_are_a_benign_difference():
    # TTB's records are plain capitals; labels print the accents.
    assert status(compare_text("brand_name", "MARTI", "Martí")) == "pass"
    assert status(compare_text("brand_name", "CUVAR", "ČUVAR")) == "pass"


def test_same_words_in_another_order_need_review():
    assert status(compare_text("brand_name", "JEAN PAUL PICARD", "PICARD Jean-Paul")) == "needs_review"


def test_run_together_words_are_compared_without_spaces():
    assert status(compare_text("brand_name", "EVIL TWIN BREWING NEW YORK CITY", "EVILTWIN BREWING")) == "needs_review"


def test_brand_printed_elsewhere_on_the_label_needs_review_not_fail():
    # Real labels often lead with a product name and print the brand smaller,
    # or use the bottler's name as the brand.
    app = Application(brand_name="BULLY ROOK CO")
    label = ExtractedLabel(brand_name="SOMEL", other_names=["BullyRookCo.", "BEEHIVE DISTILLING"], image_readable=True)
    brand = findings("distilled_spirits", app=app, label=label)["brand_name"]
    assert brand.status == "needs_review" and "BullyRookCo." in brand.explanation

    app = Application(brand_name="NEWPORT VINEYARDS")
    label = ExtractedLabel(
        brand_name="RHODY COYOTE",
        producer_name_address="PRODUCED & BOTTLED BY NEWPORT VINEYARDS, MIDDLETOWN, RI",
        image_readable=True,
    )
    assert findings("wine", app=app, label=label)["brand_name"].status == "needs_review"


def test_brand_found_nowhere_on_the_label_still_fails():
    app = Application(brand_name="HARBOR LIGHT")
    label = ExtractedLabel(
        brand_name="SALT HARBOR", other_names=["Lighthouse Reserve"],
        producer_name_address="Bottled by Salt Harbor Rum Co., Charleston, SC", image_readable=True,
    )
    assert findings("distilled_spirits", app=app, label=label)["brand_name"].status == "fail"
