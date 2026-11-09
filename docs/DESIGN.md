# Design

How Label Check works and why, with the trade-offs of each choice.

## How a label is checked

1. The agent uploads a label photo and types what the application says.
2. The photo is read into fixed fields: brand, class/type, alcohol content, net contents, producer, country of origin, the warning text, and whether the warning header is bold.
3. Plain Python rules compare each field to the application and give it a result: Match, Check, or Mismatch.
4. The page shows one overall result and a short note per field.

## The AI reads, code decides

Claude only transcribes the label. It never decides pass or fail. The rules in `app/matching.py` and `app/warning.py` do that.

- Every result traces back to a rule with a test.
- Changing the prompt can't quietly change what passes.
- Grey areas go to "Check" for the agent instead of being guessed.

The trade-off is that fuzzy judgment has to be written down as rules.

## Two readers

Each label is read by two different models at the same time (Opus 5.5 and Haiku 5.5 by default). A field only passes if both readers pass it. If they disagree, the agent sees "We couldn't confirm this item. Please check the label." with the questionable words highlighted.

Why: the most dangerous error is approving a bad label. The likeliest cause is a model quietly fixing a typo in the warning while reading it, which makes the result look perfect. A second, different model rarely makes the same fix, so the disagreement catches it.

Trade-offs:

- Two API calls per label. At about 2 cents a label, cost isn't the concern.
- More labels go to "Check", since every disagreement does.
- The wait is set by the slower of the two readers.

If only one reader answers in time, its results stand, except that the second reader alone can't pass the warning. If neither answers, the offline backup runs.

These choices were made before any real measurement and are still open (see the end of this doc).

## Speed

The brief asks for about 5 seconds per label.

- Both readers run at once under a 4.5 second cutoff. Anything still running is dropped.
- Low thinking effort and downscaled images keep calls short.
- Real API timing has not been measured yet. `scripts/benchmark.py` measures it once there's an API key.

If both readers miss the cutoff, the offline backup runs after it, so that path can take about 5.5 seconds.

## Offline backup

When the AI can't be reached, Tesseract reads the label on the server. This answers the brief's note that the network blocks many outside services.

Its results are graded more cautiously. A field it can't find becomes "Check", not "Mismatch". It can't see bold type, so the warning is always "Check".

The trade-off is a second code path that can never pass a compliant label. Removing it is an open question.

## Matching rules

- Text fields pass when they're identical, or the same apart from capitalization and punctuation. "STONE'S THROW" matches "Stone's Throw".
- "Product of", "Made in", "Bottled by" and similar label wording is ignored for country and producer.
- Other extra or missing words, and near-misses like a one-letter typo, go to "Check".
- Alcohol content and net contents are compared as numbers. "90 Proof" equals 45%, and 70 cl equals 700 mL.
- The warning must match the regulation word for word, punctuation included. Line breaks don't matter. "GOVERNMENT WARNING:" must be in capitals, with the colon, and bold. A mismatch shows which words differ.

## Interface

Built for agents with little technical comfort.

- Two tabs: check one label, or check many.
- Numbered steps, large text, one main button.
- Every result is shown as an icon and a word, never color alone.
- Nothing on screen mentions AI, models or how the app works. Notes say what to do, and failures say "We couldn't read this label right now." Tests enforce this.

## Batch

The agent uploads a CSV with one row per label, plus the image files. The browser sends four labels at a time and fills in results as they finish. Results can be filtered and downloaded as a CSV.

This needs no database or job queue. The trade-off is that closing the tab stops the batch.

## Privacy

Images are processed in memory and never stored. Labels are sent to the Anthropic API to be read, which a real deployment would need to clear with TTB's data policies.

## Testing

- Unit tests cover every matching and warning rule.
- API tests run real Tesseract on the sample labels, with scripted stand-ins for the models.
- Twelve generated sample labels each test one case from the brief, including three subtle warning typos.
- `scripts/benchmark.py` measures real models: speed, accuracy, and how often a reader silently fixes a typo. It hasn't been run yet.

## Limitations

- The AI path has never run against the real API, so speed and accuracy are unmeasured.
- The sample labels are generated, not real photos.
- No rules specific to beer, wine or spirits yet.
- Not deployed yet.

## Open decisions

- Which two models to use, and the cutoff time. Best decided from benchmark results.
- What happens when only one reader answers.
- Whether to keep the offline backup.
- Whether to keep the CSV download.
