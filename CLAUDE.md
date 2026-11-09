# Label Check

Prototype for TTB compliance agents. It reads an alcohol label image, compares each field to the COLA application, and checks the Government Health Warning word for word. The brief is at https://github.com/treasurytakehome-rgb/instructions, summarized in `REQUIREMENTS.md`. Keep Markdown docs plain and readable, with no numbered ID schemes. Users are nontechnical government workers, many over 50, so the UI must stay plain and must not mention AI, models or other internals.

## Working rules

- Bring design decisions to the user before building: model choice, thresholds, cutoffs, fallback rules, UX behavior, architecture, hosting. Give options and a recommendation, then wait. Mechanical work on an already-chosen design needs no approval.
- Never credit Claude in git. No `Co-Authored-By: Claude`, no `Claude-Session:` trailer, no "Generated with Claude Code" line in PR bodies. Commits are authored as the user.
- Use short descriptive branch names (`nextjs-frontend`), never generated ones like `claude/eager-carson-pk57m6`. Commit to `main` when the user asks.
- Record every design decision, with options considered and trade-offs, in `docs/DESIGN.md`.
- Secrets go in `.env` (gitignored): `ANTHROPIC_API_KEY`, `COLA_API_KEY`. Never commit or print them.
- COLA Cloud data: API only (their terms forbid scraping), and never commit their images or records (redistribution is forbidden). Commit only the scripts that fetch them.

## Commands

```bash
brew install tesseract                          # offline OCR fallback
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload                   # http://localhost:8000
pytest                                          # no key or network needed
python scripts/generate_samples.py              # regenerate samples/ and samples/batch.csv
python scripts/benchmark.py --runs 3            # real, billed API calls; writes docs/benchmark-results.md
```

## Architecture

- `app/extraction/` reads the label. `claude_reader.py` calls Claude with a schema-constrained response (`ExtractedLabel`). `__init__.py` runs the configured models in parallel under `READ_DEADLINE_SECONDS` and falls back to Tesseract (`ocr_reader.py`) when none answer.
- `app/matching.py` and `app/warning.py` decide pass/fail with plain, tested rules. The AI only transcribes and never judges.
- `app/consensus.py` merges two readings. A field can only PASS if every reader that answered passed it.
- `app/main.py` holds thin FastAPI routes. `app/static/` is the current plain HTML/JS UI.
- `app/config.py` reads all settings from environment variables.
- Tests fake the models. Real model quality is measured only by `scripts/benchmark.py`.

## Invariants

- The government warning must match 27 CFR 16.21 exactly, punctuation included, with `GOVERNMENT WARNING:` in capitals and bold. A silent correction of a label typo by a model is the main false-PASS risk; keep the prompt's no-correction instruction and the typo samples (10-12).
- OCR results are graded more cautiously than AI results. In OCR mode, "not found" and look-alike misreads become REVIEW, never FAIL.
- Status is always shown as an icon plus words, never color alone.
