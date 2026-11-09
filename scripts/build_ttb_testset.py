"""Build a test set of real, approved label applications from TTB's Public COLA Registry.

    python scripts/build_ttb_testset.py --per-type 40

1. Pick records: a stratified random sample of TTB IDs, drawn with COLA Cloud's
   search API (needs COLA_API_KEY in .env). Equal counts of distilled spirits,
   wine and malt beverages; for each pick, a random approval date in the window,
   then one random approved record from that day; at most one per permit holder.
   Only search results are used (no detail views, nothing from COLA Cloud is saved
   except the public TTB ID).
2. Fetch each record from TTB's Public COLA Registry (ttbonline.gov): the
   application fields and the label images. These are public government records.

Output: samples/ttb/manifest.json and samples/ttb/images/. Images are re-encoded
as JPEG at most 1568 px on the long edge, the size the checker uses anyway.
The fixed seed makes the draw reproducible.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import http.cookiejar
import io
import json
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
from dotenv import dotenv_values
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
COLA_CLOUD = "https://app.colacloud.us/api/v1"
TTB = "https://ttbonline.gov/colasonline"
TYPES = ["distilled spirits", "wine", "malt beverage"]
PER_PAGE = 50
COLA_CLOUD_PAUSE = 6.5  # free tier: 10 requests per minute
TTB_PAUSE = 1.5  # be polite to a government site
MAX_EDGE = 1568

# ttbonline.gov omits its intermediate certificate. Trust the official one
# (published by the issuer at the URL in the site certificate) on top of the
# normal roots, so TLS stays verified.
ENTRUST_INTERMEDIATE = "http://crt.sectigo.com/EntrustOVTLSIssuingRSACA2.crt"


def ttb_ssl_context(cache: Path) -> ssl.SSLContext:
    if not cache.exists():
        der = urllib.request.urlopen(ENTRUST_INTERMEDIATE, timeout=30).read()
        cache.write_text(ssl.DER_cert_to_PEM_cert(der))
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=str(cache))
    return context


# ------------------------------------------------------------------ sampling


def cola_cloud_search(key: str, **query) -> list[dict]:
    url = f"{COLA_CLOUD}/colas?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"X-API-Key": key, "User-Agent": "label-check-testset"})
    for attempt in range(5):
        time.sleep(COLA_CLOUD_PAUSE * (2 ** attempt))
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)["data"]
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
        except urllib.error.URLError:
            if attempt == 4:
                raise
    raise RuntimeError("unreachable")


def draw_sample(key: str, per_type: int, seed: int, start: dt.date, end: dt.date) -> list[dict]:
    rng = random.Random(seed)
    span = (end - start).days + 1
    picks, permits = [], set()
    for product_type in TYPES:
        count, misses = 0, 0
        while count < per_type and misses < 40:
            day = (start + dt.timedelta(days=rng.randrange(span))).isoformat()
            rows = cola_cloud_search(key, product_type=product_type, status="approved",
                                     approval_date_from=day, approval_date_to=day, per_page=PER_PAGE)
            rows = [r for r in rows if r.get("image_count") and r["permit_number"] not in permits]
            if not rows:
                misses += 1
                continue
            pick = rng.choice(rows)
            permits.add(pick["permit_number"])
            picks.append({"ttb_id": pick["ttb_id"], "product_type": product_type})
            count += 1
            print(f"picked {product_type} {count}/{per_type}: {pick['ttb_id']} ({day})", flush=True)
    return picks


# ------------------------------------------------------------- TTB registry


class Registry:
    def __init__(self, context: ssl.SSLContext):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def get(self, path: str, referer: str | None = None) -> tuple[bytes, str]:
        time.sleep(TTB_PAUSE)
        headers = {"User-Agent": "Mozilla/5.0 (label-check test set)"}
        if referer:
            headers["Referer"] = referer
        with self.opener.open(urllib.request.Request(f"{TTB}/{path}", headers=headers), timeout=60) as response:
            return response.read(), response.headers.get_content_type()


def _text_lines(page: str) -> list[str]:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _after(lines: list[str], label: str) -> str:
    """Value on the line after `label`, or '' when the next line is another label."""
    if label not in lines:
        return ""
    value = lines[lines.index(label) + 1]
    return "" if value.endswith(":") else value


def parse_detail(page: str) -> dict:
    lines = _text_lines(page)
    address: list[str] = []
    marker = "Plant Registry/Basic Permit/Brewers No (Principal Place of Business):"
    if marker in lines:
        for line in lines[lines.index(marker) + 2:]:
            if line.endswith(":"):
                break
            address.append(line)
    return {
        "status": _after(lines, "Status:"),
        "class_type_code": _after(lines, "Class/Type Code:"),
        "origin_code": _after(lines, "Origin Code:"),
        "brand_name": _after(lines, "Brand Name:"),
        "fanciful_name": _after(lines, "Fanciful Name:"),
        "approval_date": _after(lines, "Approval Date:"),
        "applicant_name_address": ", ".join(address),
    }


def parse_form(page: str) -> dict:
    def checked(group: str) -> str:
        match = re.search(rf'<input[^>]*checked[^>]*alt="{group}: ([^"]+)"', page)
        return match.group(1) if match else ""

    images = re.findall(r'publicViewAttachment\.do\?filename=([^"&]+)&(?:amp;)?filetype=l', page)
    return {
        "source_of_product": checked("Source of Product"),
        "type_of_product": checked("Type of Product"),
        "image_files": list(dict.fromkeys(html.unescape(f) for f in images)),
    }


def save_image(data: bytes, path: Path) -> dict:
    image = Image.open(io.BytesIO(data))
    image.load()
    image = image.convert("RGB")
    image.thumbnail((MAX_EDGE, MAX_EDGE))
    image.save(path, format="JPEG", quality=85)
    return {"file": path.name, "width_px": image.width, "height_px": image.height}


def fetch_record(registry: Registry, ttb_id: str, image_dir: Path) -> dict:
    detail_page, _ = registry.get(f"viewColaDetails.do?action=publicDisplaySearchBasic&ttbid={ttb_id}")
    form_url = f"viewColaDetails.do?action=publicFormDisplay&ttbid={ttb_id}"
    form_page, _ = registry.get(form_url)
    record = {"ttb_id": ttb_id, **parse_detail(detail_page.decode("latin-1")), **parse_form(form_page.decode("latin-1"))}
    images = []
    for index, filename in enumerate(record.pop("image_files")):
        data, content_type = registry.get(
            f"publicViewAttachment.do?filename={urllib.parse.quote(filename)}&filetype=l", referer=f"{TTB}/{form_url}"
        )
        if not content_type.startswith("image/"):
            continue
        images.append({**save_image(data, image_dir / f"{ttb_id}_{index}.jpg"), "original_name": filename})
    record["images"] = images
    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-type", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--start", default="2023-11-01")
    ap.add_argument("--end", default="2026-10-31")
    ap.add_argument("--out", type=Path, default=ROOT / "samples" / "ttb")
    ap.add_argument("--env", type=Path, default=ROOT / ".env")
    args = ap.parse_args()

    out, image_dir = args.out, args.out / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    ids_path, manifest_path = out / "sample_ids.json", out / "manifest.json"

    if ids_path.exists():
        picks = json.loads(ids_path.read_text())
    else:
        key = (dotenv_values(args.env).get("COLA_API_KEY") or "").strip()
        if not key:
            raise SystemExit("Set COLA_API_KEY in .env to draw the sample.")
        picks = draw_sample(key, args.per_type, args.seed, dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end))
        ids_path.write_text(json.dumps(picks, indent=1))

    records = {r["ttb_id"]: r for r in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
    registry = Registry(ttb_ssl_context(out / ".ttb-intermediate.pem"))
    for n, pick in enumerate(picks, 1):
        if pick["ttb_id"] in records:
            continue
        try:
            record = fetch_record(registry, pick["ttb_id"], image_dir)
        except Exception as exc:  # one bad record shouldn't stop the run; it's retried next time
            print(f"[{n}/{len(picks)}] {pick['ttb_id']}: failed ({exc})", flush=True)
            continue
        records[pick["ttb_id"]] = {**record, "product_type": pick["product_type"]}
        manifest_path.write_text(json.dumps(list(records.values()), indent=1))
        print(f"[{n}/{len(picks)}] {pick['ttb_id']}: {record['brand_name']} ({len(record['images'])} images)", flush=True)
    print(f"Done: {len(records)} records in {manifest_path}")


if __name__ == "__main__":
    main()
