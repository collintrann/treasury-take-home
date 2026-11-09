# Label Check

A web application that helps TTB agents verify alcohol labels against their application and the Government Health Warning requirements.

**Live demo:** https://treasury-take-home-flame.vercel.app

Pick a label from "Try an example" and click "Check label".

![Label Check showing a misspelled warning flagged as a problem](docs/screenshot.png)

## Setup

Requires Python 3.11+, Node.js 20+, and an Anthropic API key.

### Backend (checking service)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Add your `ANTHROPIC_API_KEY` to `.env`, then start the service on port 8000:

```bash
uvicorn app.main:app --reload --env-file .env
```

### Frontend

In a separate terminal:

```bash
cd web
npm install
cp .env.example .env.local
npm run dev
```

`.env.local` already points `CHECKER_URL` at `http://localhost:8000`. Open http://localhost:3000.

### Tests

```bash
pytest                              # backend: matching rules, warning check, API; no key or network needed
cd web && npm run lint && npm run build
```

## How it works

1. The agent uploads a label image and enters what the application says.
2. Two Claude vision models (Opus 5.5 and Haiku 5.5) read the label at the same time and transcribe its fields into a fixed format. They only transcribe; they never decide whether anything passes.
3. Plain Python rules compare each reading to the application and give every field a result.
4. The two sets of results are compared field by field. A field passes only if both readings pass it. If they disagree, it goes to the agent for review.
5. The page shows, for each field, what the application says, what was found on the label, and a short explanation.

The rules:

- **Government Health Warning:** must match the regulation word for word, punctuation included, with "GOVERNMENT WARNING:" in capital letters and bold. Differences are shown word by word.
- **Brand, class/type, producer, country:** pass when identical or differing only in capitalization or punctuation ("STONE'S THROW" matches "Stone's Throw"). Near-misses go to review.
- **Alcohol content and net contents:** compared as numbers, so 90 proof matches 45%, and 70 cl matches 700 mL.

## Design decisions

- **The AI reads, code decides.** Every result comes from a rule with a test, so results are explainable and consistent, and a prompt change can't quietly change what passes.
- **Two independent readings.** The most dangerous error is approving a bad label. The likeliest cause is a model quietly correcting a typo in the warning while reading it, which makes the result look perfect. A second, different model rarely makes the same correction, so a disagreement catches it.
- **Human review over guessing.** Unclear or conflicting results are marked for review rather than passed or failed automatically. The tool supports the agent's decision; it doesn't make it.
- **Plain language.** Agents never see technical terms. Notes say what to do, such as "Please check the label".
- **Standalone.** No connection to TTB's internal systems or COLA.

More detail, including the trade-offs, is in [docs/DESIGN.md](docs/DESIGN.md). Requirements are in [REQUIREMENTS.md](REQUIREMENTS.md).

## Performance

Measured on the live demo: 3.0 to 3.7 seconds per label (server time), within the brief's target of about 5 seconds. The two readings run in parallel, so a check takes about as long as the slower one.

The first request with a new output format takes about 10 seconds longer, because the API prepares that format once and then caches it.

## Tools

- **Frontend:** Next.js, React, Tailwind CSS, shadcn/ui, Lucide icons
- **Backend:** Python, FastAPI, Pillow
- **AI:** Anthropic Claude (Opus 5.5 and Haiku 5.5)
- **Testing:** pytest, Playwright (manual end-to-end runs)
- **Deployment:** Vercel (frontend), DigitalOcean App Platform with Docker (backend)

## Configuration

Backend (`.env`):

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required |
| `CHECKER_SECRET` | none | When set, every API call must send it in the `X-Checker-Secret` header |
| `PRIMARY_MODEL` | `claude-opus-5-5` | First reader |
| `SECONDARY_MODEL` | `claude-haiku-5-5` | Second reader; empty for one reader only |
| `READ_DEADLINE_SECONDS` | `4.5` | Readings still running after this are dropped |

Frontend (`web/.env.local`): `CHECKER_URL` (where the backend runs) and `CHECKER_SECRET` (the same value as the backend). The browser only talks to the Next.js server, which adds the secret, so the backend can't be called directly.

## Assumptions and limitations

- The tool assists reviewers. It does not make approval decisions.
- Some requirements can't be verified from an image, such as the warning's minimum type size, because a photo has no known scale.
- Test labels are generated (`samples/`), covering one case each from the stakeholder interviews. Accuracy on real label submissions hasn't been measured yet.
- Batch checking works from a CSV plus images in the browser. There is no server-side job queue, so closing the tab stops a batch.
- Label images are sent to Anthropic to be read and are not stored. Running on a network that blocks outside services needs only one allowed address, because the browser talks only to this site. In a government environment, the model would need to come from an approved provider, such as Claude through the agency's own cloud, or be hosted locally.
