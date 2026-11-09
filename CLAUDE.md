# Label Check

Prototype that checks alcohol label photos against their TTB application. Requirements are in `REQUIREMENTS.md`, design in `docs/DESIGN.md`.

## Rules

- Ask the user before making design decisions. Give options and a recommendation.
- Never credit Claude in commits or PRs. No co-author or session lines.
- Use descriptive branch names, not generated ones.
- Keep Markdown docs short and plain. No numbered ID schemes.
- The UI must never mention AI, models, OCR or other internals. Users are nontechnical.
- Secrets go in `.env` (template in `.env.example`). Never commit them.
- COLA Cloud data comes from their API only and is never committed.

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
- `app/extraction/` reads the label with two models under a time limit.
- `app/matching.py` and `app/warning.py` decide each result. The AI never does.
- `app/consensus.py` combines the two readings and decides the overall result.
- `app/queue.py` serves the simulated review queue from `samples/queue/applications.json`.
- `scripts/generate_samples.py` draws the queue. Rerun it after changing it; a test catches drift.
- `app/main.py` holds the API routes.
- `web/` is the Next.js page.
