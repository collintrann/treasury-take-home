# Label Check

Label Check helps TTB agents review alcohol label applications. It checks each label against the application and the Government Health Warning rules.

**Live demo:** https://treasury-take-home-flame.vercel.app

The demo opens on a review queue of 43 applications. 18 are real approved applications from TTB's Public COLA Registry, and 25 are generated. Open one and the label check runs. Agents don't upload or type anything.

![An application in the review queue with a misspelled government warning flagged](docs/screenshot.png)

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

The backend tests cover every checking rule, the two-reading merge, the queue and the API errors. They use stand-ins for the models, so they need no API key or network.

`scripts/eval_ttb.py` measures accuracy on real applications with the real models. It needs the API key and costs about 6 dollars for a full run. See [Accuracy on real applications](#accuracy-on-real-applications).

## How it works

1. Each application arrives with its label images and the information the company entered. Real labels are often split across a front, back and neck panel, so an application can have up to six images. It waits in the review queue.
2. When the agent opens an application, two Claude models, Opus 5.5 and Haiku 5.5, read all of its label images at the same time. Each one copies the label's text into the same set of fields. Neither decides whether anything passes.
3. Python rules compare each reading with the application and give each requirement a result: Pass, Fail, Needs review, or Not evaluated.
4. The service compares the two sets of results. A requirement passes only when both readings pass it. When they disagree, it goes to the agent for review.
5. The page shows the label beside the results, problems first. The first panel is shown large and the others as thumbnails. Each result has the application value, the value found on the label, and a short explanation.
6. The agent records a decision: Approve, Needs correction, or Reject. The decision stays in the browser tab. Nothing is saved on the server.

### The rules

A result is Fail only when the label clearly contradicts the application or the regulation, such as a different alcohol content or changed warning wording. Anything missing, unreadable or uncertain is Needs review, because the information may be on a label panel that wasn't submitted.

The government warning has to match the regulation word for word, including punctuation, with "GOVERNMENT WARNING:" in capital letters. When the wording differs, the page marks the missing and extra words. Whether the header is bold, the rest isn't bold, and the text is one legible paragraph set apart from other text are judged from the image, so a problem there is Needs review rather than Fail. The minimum type size is always Not evaluated, because a photo has no known scale.

Brand name, class/type, producer and country pass when they are identical or differ only in capitalization, punctuation or accents, so "STONE'S THROW" matches "Stone's Throw" and "Martí" matches "MARTI". A near miss, such as a one-letter difference, goes to review. So does a brand that isn't the label's main name but is printed elsewhere on it, which is common on real labels.

Alcohol content and net contents are compared as numbers. 90 proof matches 45%, and 750 mL matches 0.75 L.

Which rules apply depends on the beverage type. Alcohol content is required on spirits, on wine only above 14%, and not on malt beverages. Country of origin applies only to imports. A rule that doesn't apply shows as Not evaluated, with the reason.

If the image is too unclear to assess, the result is Needs review and the page asks the agent to request a clearer image.

## Design decisions

- **The AI reads and the code decides.** Every result comes from a rule that has a test. Changing the prompt can't change what passes.
- **Two readings of every label.** Approving a bad label is the worst mistake this tool can make. The most likely cause is a model fixing a typo in the warning as it reads, which produces a clean-looking result. A second, different model rarely makes the same fix, so the two readings disagree and the agent sees the requirement.
- **Unclear results go to the agent.** The tool supports the agent's review. The agent makes the decision.
- **A review queue, not an upload form.** In practice, applications arrive with their labels and wait for review, so the demo works the same way.
- **Plain language.** The page never shows technical terms. Notes tell the agent what to do, such as "Please check the label."

[docs/DESIGN.md](docs/DESIGN.md) explains the trade-offs. [REQUIREMENTS.md](REQUIREMENTS.md) lists the requirements.

## Accuracy on real applications

The checker was run on 120 approved applications drawn at random from TTB's Public COLA Registry: 40 spirits, 40 wines and 40 malt beverages. TTB's record gives the brand and, for imports, the country, so those and the government warning were checked.

- In the first run, 34 approved labels got a Fail. Every one was opened by hand. 26 Fail findings were checker mistakes, such as treating "(1)According" as a wording change or missing a brand printed below a product name. They are fixed, with tests.
- After the fixes, 9 approved labels fail. All 9 are real problems with the printed warning, such as "ACOHOLIC" or a missing comma. TTB approved them anyway.
- 33 pass and 78 need review. Most reviews are a brand worded differently from TTB's record, or a typography question the two readings didn't agree on.
- 30 copies with another record's brand name swapped in were all kept from passing.

[docs/ttb-eval.md](docs/ttb-eval.md) has the full results and every Fail with its classification.

## Performance

On the generated labels, live checks took 2.8 to 6.4 seconds per label, and most took 3 to 4 seconds. The brief's target is about 5 seconds. Real applications are slower because most have two or more images: a median of 7.8 seconds and 10.4 seconds at the 90th percentile. The two readings run in parallel, so a check takes as long as the slower reading. A reading that takes more than 15 seconds is dropped.

The API prepares each new output format the first time it sees it, which took one to two and a half minutes. The service reads one sample label with each model when it starts, so agents don't wait for that.

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
| `READ_DEADLINE_SECONDS` | `15` | The service drops any reading that takes longer |

Frontend settings go in `web/.env.local`. `CHECKER_URL` is the backend's address, and `CHECKER_SECRET` must match the backend's value. The browser only talks to the Next.js server, which adds the secret, so nobody can call the backend directly.

## Sample applications

The queue in `samples/queue/` has two kinds of application. `scripts/generate_samples.py` builds both.

**Real applications.** 18 approved applications, six per beverage type, drawn at random with a fixed seed from the test set in `samples/ttb/`. They carry the brand, applicant, approval date and, for imports, the country of origin from TTB's record. TTB's record has no class/type, alcohol content, net contents or bottler, so those show as Not evaluated. Their right answer isn't known in advance. Each one links to its record in the registry and is marked "Real application" in the queue.

**Generated applications.** 25 labels drawn with exact text, so each has a known correct result. They cover spirits, wine and malt beverages, clean labels, and the problems from the stakeholder interviews: a wrong alcohol content, changed warning wording, a title-case warning header, a missing warning, a brand mismatch, imports, angled photos with glare, and an unreadable photo.

**The test set.** `samples/ttb/` holds 120 approved applications from TTB's Public COLA Registry, 40 per beverage type, approved between November 2023 and October 2026. `scripts/build_ttb_testset.py` drew them as a stratified random sample and downloaded each record and its label images straight from the registry. These are public government records. The label artwork belongs to the brand owners and is included as public record for testing. The sample was drawn with COLA Cloud's search, and only the public TTB IDs from it are kept.

## Assumptions and limitations

- The tool helps agents review labels. It doesn't approve or reject them.
- Accuracy was measured on 120 real applications, but only on the brand, the country of origin and the warning, because TTB's public record has no other application fields.
- The real labels are the artwork files submitted to TTB, not photos of bottles. Photo handling was tested only on generated labels.
- Batch processing isn't implemented beyond the simulated queue. Results and decisions last only for the browser tab.
- The service sends label images to Anthropic to be read and doesn't store them. On a network that blocks outside services, IT only needs to allow this site's address, because the browser never contacts anything else. A government deployment would need the model from an approved provider, such as Claude in the agency's own cloud, or a model hosted on site.
