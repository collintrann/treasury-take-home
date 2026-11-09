# Label Check

A prototype that checks an alcohol label photo against its TTB application. It reads the label, compares each field to the application for the product type, and checks the Government Health Warning. Results are decision support for an agent, not an approval.

**Deployed URL:** not deployed yet.

![Label Check screenshot](docs/screenshot.png)

## Run it

Needs Python 3.11 or newer, Node.js 20 or newer, and an Anthropic API key.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # then add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload --env-file .env
```

That starts the checking service on port 8000. Then start the web page:

```bash
cd web
npm install
cp .env.example .env.local        # CHECKER_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000 and pick an application from the review queue.

The page is Next.js with shadcn components. Its server forwards requests to the checking service and adds the shared secret, so the browser never calls the service directly. Photos are shrunk in the browser to stay under Vercel's 4.5 MB upload limit. The application fields are defined once, in `web/lib/fields.ts`.

Run the tests with `pytest`. They need no API key or network.

The checking service also runs with Docker:

```bash
docker build -t label-check .
docker run -p 8000:8000 --env-file .env label-check
```

## Using it

- **Review queue.** A simulated queue of 25 generated applications (spirits, wine and beer). Open one and run the check on its stored label image.
- **Check one label.** Upload a photo, choose the product type, and type what the application says. Blank fields are not evaluated. The warning is always checked.

Batch review of hundreds of labels is not implemented. The queue is a simulation, checked one application at a time.

Each requirement gets one of four results:

| Result | Meaning |
|---|---|
| Pass | Matches the application, or differs only in capitalization, punctuation or units |
| Fail | The label text clearly differs from the application or the required warning |
| Needs review | Missing from the photo, unclear, or the two readings disagree. The agent should look |
| Not evaluated | Doesn't apply to this product, wasn't in the application, or can't be measured from a photo. Each one says why |

The label's overall result is fail if anything fails, otherwise needs review if anything does, otherwise pass. When the photo can't be read with confidence, nothing fails and the result asks for a clearer image.

## How it works

- Claude reads the label into fixed fields and gives yes, no or can't-tell answers on the warning's typography and on whether the photo is readable. Plain, tested Python rules decide each result.
- Two different models read each label at once. A requirement only passes if both pass it. Any disagreement goes to needs review, which catches a model quietly fixing a typo in the warning.
- What applies depends on the product type. Alcohol content is required on spirits, on wine over 14%, and optional on beer. Country of origin is only checked for imports.
- Numbers are compared as numbers, so 90 proof matches 45% and 0.75 L matches 750 mL.
- The warning wording and the capitalized "GOVERNMENT WARNING:" lead-in are checked from the text and can fail. Bold, paragraph, separation and legibility are judged from the photo, so they can pass or need review but never fail. Type size is never evaluated.

## API

The checking service speaks JSON. The response models in `app/models.py` are the contract.

| Route | Purpose |
|---|---|
| `GET /api/health` | Status, no secret needed |
| `GET /api/queue` | Queue items, oldest first |
| `GET /api/queue/{id}` | One queued application |
| `POST /api/queue/{id}/check` | Check a queued application's stored image |
| `POST /api/check` | Check an upload: `image`, `product_type` and the application fields |
| `GET /samples/queue/{file}` | Queue label images |

Errors return `{"detail": "..."}` with 400, 404, 413 or 503.

The reasoning and trade-offs are in [docs/DESIGN.md](docs/DESIGN.md). The requirements are in [REQUIREMENTS.md](REQUIREMENTS.md).

## Benchmark

```bash
python scripts/benchmark.py --runs 3
```

Runs each model on the 25 queue labels and scores them against each application's expected result. It reports speed, accuracy, and how often a model silently fixes a typo. It makes real, billed API calls and writes `docs/benchmark-results.md`. It has not been run yet.

## Code

| Path | Contents |
|---|---|
| `app/main.py` | API routes |
| `app/models.py` | Request and response shapes |
| `app/extraction/` | Reads the label with two models under a time limit |
| `app/matching.py`, `app/warning.py` | The rules that decide each result |
| `app/consensus.py` | Combines the two readings into the final result |
| `app/queue.py` | Loads the simulated review queue |
| `web/` | The web page (Next.js) |
| `samples/queue/` | 25 generated label images and `applications.json` |
| `scripts/` | Queue generator (`generate_samples.py`) and benchmark |
| `tests/` | Unit and API tests, with stand-ins for the models |

## Settings

Set in `.env`. Only the API key is required.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required |
| `PRIMARY_MODEL` | `claude-opus-5-5` | First reader |
| `SECONDARY_MODEL` | `claude-haiku-5-5` | Second reader; empty for one reader only |
| `CLAUDE_EFFORT` | `low` | Thinking effort |
| `READ_DEADLINE_SECONDS` | `15` | Readers still running after this are dropped. Only a guard against hung calls |
| `MAX_CONCURRENCY` | `8` | Labels checked at once per server |
| `MAX_UPLOAD_MB` | `15` | Upload size limit |
| `CHECKER_SECRET` | none | When set, API calls must send it in the `X-Checker-Secret` header |

## Limitations

- Measured on a handful of generated labels only (3.3 to 6.4 s per label). The benchmark hasn't been run.
- The first check after the reading schema changes takes about a minute while the API prepares it. Later checks are fast.
- Test labels are generated, not real photos.
- Only alcohol content and country of origin vary by product type. Other beverage-specific rules are not implemented (see `docs/DESIGN.md`).
- Batch review is not implemented beyond the simulated queue.
- No COLA integration. Nothing is stored.
