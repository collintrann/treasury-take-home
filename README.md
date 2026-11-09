# Label Check

Label Check helps TTB agents check an alcohol label against its application and the Government Health Warning rules.

**Live demo:** https://treasury-take-home-flame.vercel.app

Pick a label from "Try an example" and click "Check label".

![Label Check flagging a misspelled government warning](docs/screenshot.png)

## Setup

You need Python 3.11 or newer, Node.js 20 or newer, and an Anthropic API key.

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Add your `ANTHROPIC_API_KEY` to `.env`, then start the checking service on port 8000.

```bash
uvicorn app.main:app --reload --env-file .env
```

### Frontend

In a second terminal:

```bash
cd web
npm install
cp .env.example .env.local
npm run dev
```

The example settings already point the web page at `http://localhost:8000`. Open http://localhost:3000.

### Tests

```bash
pytest
cd web && npm run lint && npm run build
```

The backend tests cover the matching rules, the warning check and the API. They use stand-ins for the models, so they need no API key or network.

## How it works

1. The agent uploads a label image and types in what the application says.
2. Two Claude models, Opus 5.5 and Haiku 5.5, read the label at the same time. Each one copies the label's text into the same set of fields. Neither decides whether anything passes.
3. Python rules compare each reading with the application and give each field a result.
4. The service compares the two sets of results. A field passes only when both readings pass it. When they disagree, the field goes to the agent for review.
5. The page shows each field's application value, the value found on the label, and a short note.

The government warning has to match the regulation word for word, including punctuation. "GOVERNMENT WARNING:" has to be in capital letters and bold. When the wording differs, the page marks the missing and extra words.

Brand name, class/type, producer and country pass when they are identical or differ only in capitalization or punctuation, so "STONE'S THROW" matches "Stone's Throw". A near miss, such as a one-letter difference, goes to review.

Alcohol content and net contents are compared as numbers. 90 proof matches 45%, and 70 cl matches 700 mL.

## Design decisions

- **The AI reads and the code decides.** Every result comes from a rule that has a test. Changing the prompt can't change what passes.
- **Two readings of every label.** Approving a bad label is the worst mistake this tool can make. The most likely cause is a model fixing a typo in the warning as it reads, which produces a clean-looking result. A second, different model rarely makes the same fix, so the two readings disagree and the agent sees the field.
- **Unclear results go to the agent.** A conflict or an unreadable field is marked for review. The agent makes the decision.
- **Plain language.** The page never shows technical terms. Notes tell the agent what to do, such as "Please check the label."
- **No connection to TTB systems.** The tool doesn't use COLA or any internal TTB data.

[docs/DESIGN.md](docs/DESIGN.md) explains the trade-offs. [REQUIREMENTS.md](REQUIREMENTS.md) lists the requirements.

## Performance

On the live demo, a check took 3.0 to 3.7 seconds on the server. The brief's target is about 5 seconds. The two readings run in parallel, so a check takes as long as the slower reading.

The first request after the output format changes takes about 10 seconds longer. The API prepares each new format once and then caches it.

## Tools

- Frontend: Next.js, React, Tailwind CSS, shadcn/ui, Lucide icons
- Backend: Python, FastAPI, Pillow
- Models: Anthropic Claude Opus 5.5 and Haiku 5.5
- Testing: pytest, plus Playwright for end-to-end runs
- Hosting: Vercel for the frontend, DigitalOcean App Platform with Docker for the backend

## Configuration

Backend settings go in `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required |
| `CHECKER_SECRET` | none | When set, every API call must send this value in the `X-Checker-Secret` header |
| `PRIMARY_MODEL` | `claude-opus-5-5` | First reading |
| `SECONDARY_MODEL` | `claude-haiku-5-5` | Second reading. Leave empty to use one reading. |
| `READ_DEADLINE_SECONDS` | `4.5` | The service drops any reading that takes longer |

Frontend settings go in `web/.env.local`. `CHECKER_URL` is the backend's address, and `CHECKER_SECRET` must match the backend's value. The browser only talks to the Next.js server, which adds the secret, so nobody can call the backend directly.

## Assumptions and limitations

- The tool helps agents review labels. It doesn't approve or reject them.
- A photo has no known scale, so the tool can't check the warning's minimum type size.
- The test labels in `samples/` are generated. Each one covers a case from the stakeholder interviews. Accuracy on real submissions hasn't been measured yet.
- Batch checking runs in the browser from a CSV file and a set of images. There is no server-side job queue, so closing the tab stops the batch.
- The service sends label images to Anthropic to be read and doesn't store them. On a network that blocks outside services, IT only needs to allow this site's address, because the browser never contacts anything else. A government deployment would need the model from an approved provider, such as Claude in the agency's own cloud, or a model hosted on site.
