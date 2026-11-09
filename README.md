# Label Check

A prototype that checks an alcohol label photo against its TTB application. It reads the label, compares each field to the application, and checks the Government Health Warning word for word.

**Deployed URL:** not deployed yet.

![Label Check screenshot](docs/screenshot.png)

## Run it

Needs Python 3.11 or newer and an Anthropic API key.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # then add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload --env-file .env
```

Open http://localhost:8000 and pick a label from "Try an example".

Run the tests with `pytest`. They need no API key or network.

With Docker:

```bash
docker build -t label-check .
docker run -p 8000:8000 --env-file .env label-check
```

## Using it

- **Check one label.** Upload a photo, type what the application says, and click "Check label". Blank fields are skipped. The warning is always checked.
- **Check many labels.** Upload a CSV with one row per label (a `filename` column plus any application fields) and select the images. Results appear as each label finishes.

Each field gets one of three results:

| Result | Meaning |
|---|---|
| ✔ Match | Same as the application, or differs only in capitalization or punctuation |
| ⚠ Check | Probably fine, but the agent should look |
| ✖ Mismatch | Different from the application, or missing from the label |

## How it works

- Claude reads the label into fixed fields. Plain, tested Python rules decide each result, so the AI never decides pass or fail.
- Two different models read each label at once. A field only passes if both agree, which catches a model quietly fixing a typo in the warning.
- Capitalization differences pass. Numbers are compared as numbers, so 70 cl matches 700 mL. The warning must match word for word, with "GOVERNMENT WARNING:" in capitals and bold.

The reasoning and trade-offs are in [docs/DESIGN.md](docs/DESIGN.md). The requirements are in [REQUIREMENTS.md](REQUIREMENTS.md).

## Benchmark

```bash
python scripts/benchmark.py --runs 3
```

Runs each model on the 12 sample labels and reports speed, accuracy, and how often a model silently fixes a typo. It makes real, billed API calls and writes `docs/benchmark-results.md`.

## Code

| Path | Contents |
|---|---|
| `app/main.py` | API routes |
| `app/extraction/` | Reads the label with two models under a time limit |
| `app/matching.py`, `app/warning.py` | The rules that decide each result |
| `app/consensus.py` | Combines the two readings |
| `app/static/` | The web page |
| `samples/` | 12 generated test labels and `batch.csv` |
| `scripts/` | Sample generator and benchmark |
| `tests/` | Unit and API tests, with stand-ins for the models |

## Settings

Set in `.env`. Only the API key is required.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required |
| `PRIMARY_MODEL` | `claude-opus-5-5` | First reader |
| `SECONDARY_MODEL` | `claude-haiku-5-5` | Second reader; empty for one reader only |
| `CLAUDE_EFFORT` | `low` | Thinking effort |
| `READ_DEADLINE_SECONDS` | `4.5` | Readers still running after this are dropped |
| `MAX_CONCURRENCY` | `8` | Labels checked at once per server |
| `MAX_UPLOAD_MB` | `15` | Upload size limit |

## Limitations

- Not yet run against the real API, so speed and accuracy are unmeasured.
- Test labels are generated, not real photos.
- No COLA integration. Nothing is stored.
