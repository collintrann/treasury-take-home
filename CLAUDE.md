# Label Check

Prototype that checks alcohol label photos against their TTB application. Requirements are in `REQUIREMENTS.md`, design in `docs/DESIGN.md`.

## Rules

- Ask the user before making design decisions. Give options and a recommendation.
- Never credit Claude in commits or PRs. No co-author or session lines.
- Use descriptive branch names, not generated ones.
- Keep Markdown docs short and plain. No numbered ID schemes.
- The UI must never mention AI, models, OCR or other internals. Users are nontechnical.
- Secrets go in `.env` (template in `.env.example`). Never commit them.
- COLA Cloud data comes from their API only and is never committed. Only public TTB IDs from it are kept.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --env-file .env   # checking service, port 8000
cd web && npm run dev                            # web page, http://localhost:3000
pytest
```

## Code

- `app/models.py` holds the API's request and response shapes. The web page mirrors them.
- `app/extraction/` reads all of an application's label images with two models under a time limit.
- `app/matching.py` and `app/warning.py` decide each result. The AI never does.
- `app/consensus.py` combines the two readings and decides the overall result.
- `app/queue.py` serves the review queue from `samples/queue/applications.json`.
- `scripts/generate_samples.py` builds the queue: generated labels plus a seeded draw of real ones from `samples/ttb/`. Rerun it after changing it; a test catches drift.
- `samples/ttb/` is 120 approved applications from TTB's Public COLA Registry, built by `scripts/build_ttb_testset.py`.
- `scripts/eval_ttb.py` measures accuracy on them and writes `docs/ttb-eval.md`. It makes billed calls. Use `rejudge` to re-apply rule changes to saved readings for free.
- `app/main.py` holds the API routes.
- `web/` is the Next.js page.
