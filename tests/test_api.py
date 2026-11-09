"""End-to-end tests through the HTTP API.

The readers are scripted stand-ins, so the suite needs no API key and no network.
"""

import asyncio
import io
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, extraction
from app.extraction.claude_reader import ClaudeExtractionError
from app.main import app
from app.models import Application, CheckResult, ExtractedLabel, QueueDetail, QueueItem
from app.queue import QUEUE_DIR, load_queue
from app.warning import FULL_TEXT

client = TestClient(app)
FIRST = next(iter(load_queue().values()))  # COLA-26-0001, a clean bourbon label
IMAGE = QUEUE_DIR / FIRST.image
UNAVAILABLE = "We couldn't read this label right now. Please try again in a minute."


@pytest.fixture
def fake_readers(monkeypatch):
    """Pretend a key is configured and script each reader's answer.

    Set ``state[model]`` to an ExtractedLabel, an Exception to raise, or a
    ("sleep", seconds, label) tuple to simulate a slow reader.
    """
    monkeypatch.setattr(config, "claude_configured", lambda: True)
    monkeypatch.setattr(config, "PRIMARY_MODEL", "primary-model")
    monkeypatch.setattr(config, "SECONDARY_MODEL", "secondary-model")
    state = {}

    async def fake(jpeg: bytes, model: str, usage=None):
        assert jpeg[:2] == b"\xff\xd8", "should upload a JPEG"
        result = state[model]
        if isinstance(result, tuple):
            _, seconds, result = result
            await asyncio.sleep(seconds)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(extraction, "extract_with_claude", fake)
    return state


GOOD = ExtractedLabel(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    producer_name_address="Bottled by Old Tom Distillery, Bardstown, KY",
    government_warning=FULL_TEXT,
    warning_header_bold=True,
    warning_body_bold=False,
    warning_continuous_paragraph=True,
    warning_separate_from_other_text=True,
    warning_legible=True,
    image_readable=True,
)
TYPO = GOOD.model_copy(update={"government_warning": FULL_TEXT.replace("Surgeon General", "Surgeon Generel")})


def post_check(product_type="distilled_spirits", image_path=IMAGE, **fields):
    data = {"product_type": product_type, **(FIRST.application.model_dump() | fields)}
    with open(image_path, "rb") as img:
        return client.post("/api/check", files={"image": (image_path.name, img, "image/png")}, data=data)


def findings(body: dict) -> dict:
    return {f["key"]: f for f in body["findings"]}


# ----------------------------------------------------------------- queue

def test_queue_lists_every_application_oldest_first():
    items = [QueueItem.model_validate(i) for i in client.get("/api/queue").json()]
    assert len(items) == len(load_queue()) >= 20
    dates = [i.submitted_at for i in items]
    assert dates == sorted(dates)
    assert {i.product_type for i in items} == {"distilled_spirits", "wine", "malt_beverage"}


def test_queue_never_reveals_test_answers():
    raw = client.get("/api/queue").text + client.get(f"/api/queue/{FIRST.id}").text
    assert "expected_overall" not in raw and "scenario" not in raw
    assert client.get("/samples/queue/applications.json").status_code == 404


def test_queue_images_are_served():
    item = client.get("/api/queue").json()[0]
    res = client.get(item["image"])
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert client.get("/samples/../app/config.py").status_code == 404


def test_queue_detail_has_the_application():
    detail = QueueDetail.model_validate(client.get(f"/api/queue/{FIRST.id}").json())
    assert detail.application == FIRST.application
    assert detail.product_type == FIRST.product_type


def test_unknown_queue_id_is_404():
    assert client.get("/api/queue/COLA-00-0000").status_code == 404
    res = client.post("/api/queue/COLA-00-0000/check")
    assert res.status_code == 404 and res.json()["detail"]


def test_check_queued_application(fake_readers):
    fake_readers["primary-model"] = GOOD
    fake_readers["secondary-model"] = GOOD
    res = client.post(f"/api/queue/{FIRST.id}/check")
    assert res.status_code == 200, res.text
    body = CheckResult.model_validate(res.json())
    assert body.overall == "pass" and body.image_assessable


# ----------------------------------------------------------- uploaded check

def test_result_lists_application_then_warning_findings_in_order(fake_readers):
    fake_readers["primary-model"] = GOOD
    fake_readers["secondary-model"] = GOOD
    body = post_check().json()
    assert [f["key"] for f in body["findings"]] == [*Application.model_fields] + [
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
    assert body["overall"] == "pass"
    assert findings(body)["country_of_origin"]["status"] == "not_evaluated"
    assert isinstance(body["elapsed_ms"], int)


def test_product_type_changes_what_applies(fake_readers):
    no_abv = GOOD.model_copy(update={"alcohol_content": None})
    fake_readers["primary-model"] = no_abv
    fake_readers["secondary-model"] = no_abv
    assert findings(post_check("malt_beverage").json())["alcohol_content"]["status"] == "not_evaluated"
    assert findings(post_check("distilled_spirits").json())["alcohol_content"]["status"] == "needs_review"


def test_silent_correction_is_caught_by_disagreement(fake_readers):
    fake_readers["primary-model"] = TYPO
    fake_readers["secondary-model"] = GOOD
    body = post_check().json()
    wording = findings(body)["warning_wording"]
    assert wording["status"] == "needs_review"
    assert {"op": "missing", "text": "General,"} in wording["diff"]
    assert body["overall"] == "needs_review"


def test_unreadable_image_is_flagged(fake_readers):
    blurry = GOOD.model_copy(update={"alcohol_content": "40% Alc./Vol.", "image_readable": False})
    fake_readers["primary-model"] = blurry
    fake_readers["secondary-model"] = blurry
    body = post_check().json()
    assert body["image_assessable"] is False
    assert "Request a clearer image." in body["image_note"]
    assert body["overall"] == "needs_review"
    assert "fail" not in {f["status"] for f in body["findings"]}


def test_slow_secondary_is_dropped_at_deadline(fake_readers, monkeypatch):
    monkeypatch.setattr(config, "READ_DEADLINE_SECONDS", 0.3)
    fake_readers["primary-model"] = GOOD
    fake_readers["secondary-model"] = ("sleep", 5, GOOD)
    body = post_check().json()
    assert body["overall"] == "pass"  # the primary alone is trusted
    assert body["elapsed_ms"] < 2000  # didn't wait for the slow one


def test_secondary_alone_cannot_pass_the_warning(fake_readers):
    fake_readers["primary-model"] = ClaudeExtractionError("service error 529")
    fake_readers["secondary-model"] = GOOD
    body = post_check().json()
    assert findings(body)["warning_wording"]["status"] == "needs_review"
    assert body["overall"] == "needs_review"


def test_single_reader_mode(fake_readers, monkeypatch):
    monkeypatch.setattr(config, "SECONDARY_MODEL", "")
    fake_readers["primary-model"] = GOOD
    assert post_check().json()["overall"] == "pass"


def test_deadline_default_only_guards_hung_calls():
    # A documented default: 15 s, well past a typical read, so it only catches a hung call.
    import importlib
    import os

    saved = os.environ.pop("READ_DEADLINE_SECONDS", None)
    try:
        assert importlib.reload(config).READ_DEADLINE_SECONDS == 15
    finally:
        if saved is not None:
            os.environ["READ_DEADLINE_SECONDS"] = saved
        importlib.reload(config)


# ------------------------------------------------------------------- errors

def test_503_when_all_readers_fail(fake_readers):
    fake_readers["primary-model"] = ClaudeExtractionError("could not reach the service")
    fake_readers["secondary-model"] = ClaudeExtractionError("could not reach the service")
    for res in (post_check(), client.post(f"/api/queue/{FIRST.id}/check")):
        assert res.status_code == 503
        assert res.json() == {"detail": UNAVAILABLE}


def test_503_without_api_key(fake_readers, monkeypatch):
    monkeypatch.setattr(config, "claude_configured", lambda: False)
    assert post_check().status_code == 503


def test_rejects_non_image(fake_readers):
    res = client.post(
        "/api/check",
        files={"image": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"product_type": "wine", "brand_name": "X"},
    )
    assert res.status_code == 400
    assert "image" in res.json()["detail"].lower()


def test_requires_an_image(fake_readers):
    res = client.post("/api/check", data={"product_type": "wine", "brand_name": "X"})
    assert res.status_code == 400 and isinstance(res.json()["detail"], str)


@pytest.mark.parametrize("product_type", ["", "cider"])
def test_requires_a_known_product_type(fake_readers, product_type):
    res = post_check(product_type)
    assert res.status_code == 400 and res.json()["detail"]


def test_requires_some_application_data(fake_readers):
    blank = dict.fromkeys(Application.model_fields, "")
    assert post_check(**blank).status_code == 400


def test_rejects_oversized_upload(fake_readers, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    assert post_check().status_code == 413


# ------------------------------------------------------- access and wording

def test_health_needs_no_secret(monkeypatch):
    monkeypatch.setattr(config, "CHECKER_SECRET", "s3cret")
    assert client.get("/api/health").json()["status"] == "ok"


def test_checker_secret_is_required_when_configured(monkeypatch):
    monkeypatch.setattr(config, "CHECKER_SECRET", "s3cret")
    assert client.get("/api/queue").status_code == 401
    assert client.get("/api/queue", headers={"X-Checker-Secret": "wrong"}).status_code == 401
    assert client.get("/api/queue", headers={"X-Checker-Secret": "s3cret"}).status_code == 200
    assert client.post("/api/check").status_code == 401
    assert client.post(f"/api/queue/{FIRST.id}/check").status_code == 401


# Agents are nontechnical: nothing they see may mention how the app works.
INTERNAL_WORDS = re.compile(r"\b(AI|model|models|OCR|Claude|Opus|Haiku|Sonnet|reader|readers|API|Tesseract)\b", re.I)


def user_visible_text(body: dict) -> list[str]:
    if "detail" in body:
        return [body["detail"]]
    return [body["image_note"]] + [t for f in body["findings"] for t in (f["label"], f["explanation"])]


@pytest.mark.parametrize(
    "scenario", ["agree", "dispute", "secondary_only", "all_fail", "unreadable", "no_warning", "unsure"]
)
def test_user_facing_text_never_mentions_internals(fake_readers, scenario):
    down = ClaudeExtractionError("could not reach the AI service (network blocked?)")
    blurry = GOOD.model_copy(update={"image_readable": False, "alcohol_content": "40%"})
    no_warning = GOOD.model_copy(update={"government_warning": None, "brand_name": None})
    unsure = GOOD.model_copy(update={k: None for k in ("warning_header_bold", "warning_body_bold", "warning_legible")})
    fake_readers["primary-model"], fake_readers["secondary-model"] = {
        "agree": (GOOD, GOOD),
        "dispute": (TYPO, GOOD),
        "secondary_only": (down, GOOD),
        "all_fail": (down, down),
        "unreadable": (blurry, blurry),
        "no_warning": (no_warning, no_warning),
        "unsure": (unsure, GOOD),
    }[scenario]
    for product_type in ("distilled_spirits", "wine", "malt_beverage"):
        for text in user_visible_text(post_check(product_type, country_of_origin="").json()):
            assert not INTERNAL_WORDS.search(text), text


def test_error_text_never_mentions_internals(fake_readers, monkeypatch):
    responses = [
        client.get("/api/queue/nope"),
        client.post("/api/check", data={}),
        post_check("cider"),
        post_check(**dict.fromkeys(Application.model_fields, "")),
    ]
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    responses.append(post_check())
    for res in responses:
        assert not INTERNAL_WORDS.search(res.json()["detail"]), res.json()


def test_ui_source_never_mentions_internals():
    web = Path(__file__).parent.parent / "web"
    sources = [*web.glob("app/**/*.tsx"), *web.glob("components/**/*.tsx"), *web.glob("lib/*.ts")]
    sources = [s for s in sources if "/ui/" not in str(s)]
    assert sources
    for source in sources:
        code = source.read_text()
        jsx_text = re.findall(r">([^<>{}]+)<", code)
        strings = re.findall(r"`[^`]*`|\"[^\"]*\"|'[^']*'", code)
        for text in [*jsx_text, *strings]:
            assert not re.search(r"\b(AI|OCR|Claude|Opus|Haiku|Sonnet|model|models)\b", text), f"{source.name}: {text}"


def test_startup_reads_one_label_with_each_model(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(config, "claude_configured", lambda: True)
    calls = []

    async def fake(jpeg, model, usage=None, timeout=None):
        calls.append((model, timeout))
        return ExtractedLabel(image_readable=True)

    monkeypatch.setattr(main_module, "extract_with_claude", fake)
    with TestClient(app):
        deadline = time.monotonic() + 2
        while len(calls) < len(config.reader_models()) and time.monotonic() < deadline:
            time.sleep(0.05)  # the warm-up runs in the background on the server's event loop
    assert [m for m, _ in calls] == [m for m, _ in config.reader_models()]
    assert all(t == main_module.WARM_UP_TIMEOUT_SECONDS for _, t in calls)
