# Label Check: AI-assisted alcohol label verification

A prototype that does the "matching" half of a TTB label review. It reads the
label image, compares each field to the application, and checks the
Government Health Warning word-for-word. The agent gets a plain-English
verdict for every field.

**Deployed URL:** _add after deploying (see [Deploy](#deploy))_

![Label Check screenshot](docs/screenshot.png)

---

## Quick start

```bash
# 1. System dependency for the offline OCR fallback
sudo apt-get install tesseract-ocr        # macOS: brew install tesseract

# 2. Python deps (Python 3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Optional: enable the AI reader. Without a key, the app runs in offline-OCR mode.
export ANTHROPIC_API_KEY=sk-ant-...

# 4. Run
uvicorn app.main:app --reload
# open http://localhost:8000 and pick a label from the "Try an example" menu
```

Run the tests with `pytest`. There are 50 tests, and they need no API key or network.

Or with Docker: `docker build -t label-check . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... label-check`

## Using it

* **Check one label:** upload a photo, type what the application says, and click **Check label**.
  Blank fields are skipped. The government warning is always checked.
* **Check many labels:** upload a CSV (one row per label, with a `filename` column) and select
  all the images. Results stream in as they finish, and you can filter to just the problems and
  download a results CSV. **Load the 9 example labels** runs a demo batch.

Every result is one of:

| Result | Meaning |
|---|---|
| ✔ **Match** | Identical, or the same apart from capitalization or punctuation (noted) |
| ⚠ **Check** | Probably fine, but a human should look: a near-miss, unconfirmed bold type, or a hard-to-read photo |
| ✖ **Mismatch / Not found** | Clearly different, or absent from the label |

---

## Approach

```
 image ─► extraction ─────────────────────────► matching (pure Python) ─► verdict
          ├─ Claude vision, JSON-schema output   ├─ text: exact / normalized / fuzzy
          └─ fallback: Tesseract OCR (local)     ├─ ABV & volume: compared as numbers
                                                 └─ warning: exact words, CAPS, bold
```

### Key decisions and trade-offs

**1. The AI reads, code judges.** Claude only *transcribes* the label into a fixed
JSON schema (`ExtractedLabel`). Pass/fail is decided by deterministic, unit-tested
rules in `app/matching.py` and `app/warning.py`.
*Why:* compliance verdicts must be explainable and consistent. A prompt tweak
can't silently change policy, and every rule has a test.
*Trade-off:* the model's judgment goes unused for fuzzy cases. I handle those
with an explicit **REVIEW** state instead.

**2. Hybrid extraction: Claude first, offline OCR fallback.** Two interview
notes conflict here. Marcus says the firewall blocks many ML endpoints. Jenny
wants bad photos handled and bold type checked, which only a vision model does
well. So:
* With a key and network access, **Claude** reads the label. It handles angled,
  curved or glary photos, and it can judge bold type.
* If the call fails, times out (`CLAUDE_TIMEOUT_SECONDS`, default 8 s) or no key
  is set, **Tesseract** runs locally. No network is needed, so it works behind
  any firewall. The UI always says which reader was used and why.
* `EXTRACTION_MODE=ocr` forces offline mode, and `=claude` disables the fallback.

**3. OCR results are graded more cautiously.** OCR can't tell a typo on the label
from its own misread, and it can't prove something is absent. So in OCR mode:
"not found" becomes REVIEW, a warning that differs only by look-alike words
("alcahalic") becomes REVIEW, and a low-confidence read can't hard-fail.
Genuine violations (title-case header, reworded warning, wrong ABV) still FAIL.
OCR can't see font weight, so the bold check is always REVIEW in OCR mode.

**4. Dave's "judgment" problem.** `STONE'S THROW` vs `Stone's Throw` passes,
with a note that only the case differs. A one-letter difference is REVIEW,
and anything else FAILs. Numbers are compared as numbers: `45% Alc./Vol.` =
`45 % ALC/VOL`, `90 Proof` = 45%, and `70 cl` = `700 mL`. The label's own proof
is also checked against its ABV.

**5. The government warning (Jenny's point).** It is checked against the 27 CFR
16.21 text word-for-word, with punctuation included and line breaks ignored.
The `GOVERNMENT WARNING:` lead-in must be in capitals with a colon, and bold.
On a mismatch, the UI shows a word-level diff of what's missing and what was added.

**6. The 5-second budget.**
* Claude is called with `effort: low` (less thinking, lower latency) and a
  single retry. Images are downscaled to 1568 px and sent as JPEG.
* The OCR path takes about 0.5–1 s per label.
* The timeout guarantees the agent never waits on a hung API call.

The default model is `claude-opus-5-5` for transcription accuracy. If measured
latency is too high, set `LABEL_MODEL=claude-haiku-5-5`. It's the speed/cost
lever, at some accuracy risk on hard photos. **I couldn't measure Claude
latency in my build environment (no API key), so treat the 5 s claim for the
AI path as unverified until it's measured.**

**7. Batch = many single checks, run from the browser.** The browser keeps 4
requests in flight and fills in the table as each finishes. The server caps
concurrency separately.
*Why:* no job queue, no database and no stored images, and the progress
display comes for free.
*Trade-off:* closing the tab stops the batch. A production version would use
a server-side job queue. The 9-label demo batch finishes in about 2 s on 4
cores in OCR mode.

**8. Simple UI for every comfort level.** Plain HTML/CSS/JS with no build step.
It uses 18 px base text, numbered steps, one big primary button, and status
shown as text plus an icon, not color alone. It supports dark mode and works
at phone width.

### Things I fixed along the way

* **Rotated photos defeated OCR.** I added a projection-profile deskew (Pillow
  only): rotate a thumbnail through ±15° and keep the angle where the text rows
  are sharpest. The angled, glary sample went from garbage to a correct read.
* **Batch OCR hung.** Tesseract uses one OpenMP thread per core, so 4 parallel
  jobs thrashed the CPU and were more than 60x slower. Setting
  `OMP_THREAD_LIMIT=1` and capping OCR concurrency at the core count fixed it.

## Project layout

```
app/
  main.py               HTTP routes (verify, parse-manifest, examples, health)
  models.py             ApplicationData / ExtractedLabel / VerificationResult
  matching.py           field comparison rules + overall verdict
  warning.py            canonical warning text, exact-match check, word diff
  config.py             env-var settings
  extraction/
    __init__.py         reader selection + fallback
    claude_reader.py    Claude vision, schema-constrained output
    ocr_reader.py       Tesseract + deskew + application-guided field finding
    image.py            decode, EXIF-rotate, downscale
  static/               index.html, app.js, styles.css
samples/                9 generated test labels + batch.csv (see "what_this_tests" column)
scripts/generate_samples.py   regenerates the samples
tests/                  matching/warning unit tests, API tests (real OCR, mocked Claude)
```

## Configuration

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | – | Enables the AI reader |
| `EXTRACTION_MODE` | `auto` | `auto` / `claude` / `ocr` |
| `LABEL_MODEL` | `claude-opus-5-5` | Model for the AI reader |
| `CLAUDE_EFFORT` | `low` | Thinking effort (latency vs. thoroughness) |
| `CLAUDE_TIMEOUT_SECONDS` | `8` | After this, fall back to OCR |
| `MAX_CONCURRENCY` | `8` | Simultaneous extractions per server |
| `MAX_UPLOAD_MB` | `15` | Upload size limit |

## Deploy

The app is one container with no database, so any container host works.
* **Render:** New → Blueprint → select this repo (it uses `render.yaml`), then
  set `ANTHROPIC_API_KEY`.
* **Azure App Service** (TTB's cloud): deploy the Dockerfile as a Web App for Containers.

## Assumptions and limitations

* **Prototype scope:** no COLA integration, no auth, no persistence. Images are
  processed in memory and never stored.
* **Application data is typed in or uploaded as CSV.** In production it would come from COLA.
* **Field checks are presence + match only.** No beverage-specific rules yet
  (e.g. wine ABV tolerances, ±0.3% for spirits, or type-size minimums).
  ABV must match exactly.
* **A model could "auto-correct" a typo while transcribing.** The prompt
  explicitly forbids this, but the risk isn't zero. A production version should
  measure it on an eval set of deliberately misspelled warnings.
* **The sample labels are synthetic.** Real bottle photos need a proper
  evaluation set before anyone relies on the accuracy numbers.
* The OCR fallback assumes dark text on a light background, which the deskew relies on.
