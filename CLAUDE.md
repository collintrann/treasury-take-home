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
uvicorn app.main:app --reload --env-file .env   # http://localhost:8000
pytest
```

## Code

- `app/extraction/` reads the label with two models under a time limit.
- `app/matching.py` and `app/warning.py` decide each result. The AI never does.
- `app/consensus.py` combines the two readings.
- `app/main.py` holds the API routes. `app/static/` is the UI.
