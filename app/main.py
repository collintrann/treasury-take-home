"""HTTP layer: thin routes that validate input and delegate to extraction and the rules."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import get_args

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from . import config
from .consensus import decide
from .extraction import ClaudeExtractionError, InvalidImageError, extract
from .extraction.claude_reader import extract_with_claude
from .extraction.image import load_image, to_upload_jpeg
from .models import MAX_LABEL_IMAGES, Application, CheckResult, ProductType, QueueDetail, QueueEntry, QueueItem
from .queue import QUEUE_DIR, SAMPLES_DIR, as_detail, as_item, load_queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("label-check")

PRODUCT_TYPES: tuple[str, ...] = get_args(ProductType)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
UNAVAILABLE = "We couldn't read this label right now. Please try again in a minute."

# The API prepares each new response format the first time it sees it, which
# took about a minute when measured. Reading one sample label at startup pays
# that cost before an agent's first check would hit the deadline.
WARM_UP_TIMEOUT_SECONDS = 180


async def _warm_up() -> None:
    entry = next(iter(load_queue().values()), None)
    if entry is None:
        return
    jpegs = [to_upload_jpeg(load_image((QUEUE_DIR / name).read_bytes())) for name in entry.images]
    for model, _ in config.reader_models():
        started = time.perf_counter()
        try:
            await extract_with_claude(jpegs, model, timeout=WARM_UP_TIMEOUT_SECONDS)
            log.info("warm-up read with %s took %.1f s", model, time.perf_counter() - started)
        except ClaudeExtractionError as exc:
            log.warning("warm-up read with %s failed: %s", model, exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_warm_up()) if config.claude_configured() else None
    if task:
        task.add_done_callback(
            lambda t: t.cancelled() or t.exception() is None or log.error("warm-up crashed: %r", t.exception())
        )
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="Label Check", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None, lifespan=lifespan
)

# Caps simultaneous checks so a burst of requests can't exhaust API rate
# limits or the box's CPU. Extra requests wait their turn.
_slots = asyncio.Semaphore(config.MAX_CONCURRENCY)


@app.middleware("http")
async def require_checker_secret(request: Request, call_next):
    path = request.url.path
    if config.CHECKER_SECRET and path.startswith("/api/") and path != "/api/health":
        given = request.headers.get("X-Checker-Secret", "")
        if not secrets.compare_digest(given.encode(), config.CHECKER_SECRET.encode()):
            return JSONResponse({"detail": "Not allowed."}, status_code=401)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"detail": "Some of the information sent is missing or not valid."}, status_code=400)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "configured": config.claude_configured(),
        "models": [m for m, _ in config.reader_models()],
    }


async def run_check(
    images: list[bytes], product_type: ProductType, application: Application, name: str
) -> CheckResult:
    started = time.perf_counter()
    try:
        async with _slots:
            readings = await extract(images)
    except InvalidImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ClaudeExtractionError as exc:
        log.error("could not read %s: %s", name, exc)
        raise HTTPException(503, UNAVAILABLE) from exc

    result = decide(product_type, application, readings)
    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "checked %s (%d images) via %s in %d ms -> %s%s",
        name,
        len(images),
        ",".join(r.model for r in readings),
        result.elapsed_ms,
        result.overall,
        "" if result.image_assessable else " (image not assessable)",
    )
    return result


@app.post("/api/check", response_model=CheckResult)
async def check_upload(
    images: list[UploadFile] | None = File(None),
    product_type: str = Form(""),
    brand_name: str = Form(""),
    class_type: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    producer_name_address: str = Form(""),
    country_of_origin: str = Form(""),
) -> CheckResult:
    if not images:
        raise HTTPException(400, "Choose a label image to check.")
    if len(images) > MAX_LABEL_IMAGES:
        raise HTTPException(400, f"Choose at most {MAX_LABEL_IMAGES} label images.")
    data = [await image.read(config.MAX_UPLOAD_BYTES + 1) for image in images]
    if any(len(d) > config.MAX_UPLOAD_BYTES for d in data):
        raise HTTPException(413, f"An image is too large (limit {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    if product_type not in PRODUCT_TYPES:
        raise HTTPException(400, "Choose whether this is distilled spirits, wine or a malt beverage.")

    application = Application(
        brand_name=brand_name,
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
        producer_name_address=producer_name_address,
        country_of_origin=country_of_origin,
    )
    if not any(v.strip() for v in application.model_dump().values()):
        raise HTTPException(400, "Enter at least one application field to compare against.")
    return await run_check(data, product_type, application, images[0].filename or "upload")


def _queued(application_id: str) -> QueueEntry:
    entry = load_queue().get(application_id)
    if entry is None:
        raise HTTPException(404, "We couldn't find that application.")
    return entry


@app.get("/api/queue", response_model=list[QueueItem])
def queue() -> list[QueueItem]:
    return [as_item(e) for e in load_queue().values()]


@app.get("/api/queue/{application_id}", response_model=QueueDetail)
def queue_detail(application_id: str) -> QueueDetail:
    return as_detail(_queued(application_id))


@app.post("/api/queue/{application_id}/check", response_model=CheckResult)
async def check_queued(application_id: str) -> CheckResult:
    entry = _queued(application_id)
    try:
        data = [(QUEUE_DIR / name).read_bytes() for name in entry.images]
    except OSError as exc:
        log.error("queue image missing for %s: %s", entry.id, exc)
        raise HTTPException(404, "We couldn't find the label for that application.") from exc
    return await run_check(data, entry.product_type, entry.application, entry.id)


@app.get("/samples/{path:path}")
def sample_image(path: str) -> FileResponse:
    """Sample label images only. The queue manifest next to them holds test answers and stays private."""
    file = (SAMPLES_DIR / path).resolve()
    if file.suffix.lower() not in IMAGE_SUFFIXES or not file.is_file() or not file.is_relative_to(SAMPLES_DIR.resolve()):
        raise HTTPException(404, "Not found.")
    return FileResponse(file)
