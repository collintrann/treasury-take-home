# Design

How Label Check works and why, with the trade-offs of each choice.

## How a label is checked

1. The agent opens an application from the review queue, or uploads a photo, picks the product type and types what the application says.
2. Two models read the photo into fixed fields: brand, class/type, alcohol content, net contents, producer, country of origin and the warning text. They also answer yes, no or can't tell on the warning's typography and on whether the photo is clear enough to read.
3. Plain Python rules turn each reading into findings, one per application field and nine for the warning.
4. The two sets of findings are merged, and the page shows an overall result with a short explanation per finding.

## The AI reads, code decides

Claude only transcribes the label and answers fixed questions about it. It never decides pass or fail. The rules in `app/matching.py`, `app/warning.py` and `app/consensus.py` do that.

- Every result traces back to a rule with a test.
- Changing the prompt can't quietly change what passes.
- Grey areas go to needs review instead of being guessed.

The trade-off is that fuzzy judgment has to be written down as rules.

## Four results

Each requirement is pass, fail, needs review or not evaluated. A fail needs reliable evidence, so only facts checked from the text can fail:

- a value that clearly differs from the application, like a wrong alcohol content, brand or net contents
- warning wording that differs from the regulation
- a lead-in that isn't "GOVERNMENT WARNING:" in capitals with the colon

Anything missing, unreadable or uncertain is needs review. A field not found in the photo may be on another panel of the label, so it is never a fail. Not evaluated says why, for example "Not an import." It never changes the overall result.

The overall result is fail if any finding fails, otherwise needs review if any needs review, otherwise pass.

## What applies to which product

The agent picks distilled spirits, wine or malt beverage.

- Alcohol content is required for spirits. Wine over 14% must show it. Wine at 14% or less, and beer, may leave it off, which is not evaluated. If they do show it, it must match.
- Country of origin is only checked for imports, meaning the application gives a country.
- Any other blank application field is not evaluated.

Other beverage-specific rules are not implemented. Examples are beer net contents in US units, wine appellation and vintage, sulfite statements, and spirits age statements. Country of origin is a Customs rule rather than a TTB one, but the brief asks for it. Sources are 27 CFR parts 4, 5, 7 and 16 (https://www.ecfr.gov/current/title-27).

## The warning

The warning has nine findings, always in this order: present, wording, lead-in in capitals, lead-in bold, rest not bold, one continuous paragraph, separate from other text, legible, and type size.

- Wording must match the regulation word for word, punctuation included. Line breaks don't matter. A mismatch shows which words differ.
- Bold, paragraph, separation and legibility are visual judgments from the photo. They pass only when both readers say the label looks right. Otherwise they need review. They never fail, because a photo isn't reliable enough evidence.
- Type size and characters per inch can't be measured reliably from a photo, so they are always not evaluated.
- If no warning is found, that is needs review. It may be on the back label.

## Two readers

Each label is read by two different models at the same time (Opus 5.5 and Haiku 5.5 by default). A finding only passes if every reader that answered passes it. Any disagreement becomes needs review with "We couldn't confirm this item. Please check the label."

Why: the most dangerous error is approving a bad label. The likeliest cause is a model quietly fixing a typo in the warning while reading it, which makes the result look perfect. A second, different model rarely makes the same fix, so the disagreement catches it. A fail that only one reader saw also goes to needs review.

Trade-offs:

- Two API calls per label. At about 2 cents a label, cost isn't the concern.
- More labels go to needs review, since every disagreement does.
- The wait is set by the slower of the two readers.

If only one reader answers in time, its results stand, except that the faster second reader alone can't pass anything about the warning beyond its presence. If neither answers, the agent sees "We couldn't read this label right now. Please try again in a minute."

## Unclear photos

Each reader says whether the photo can be read with confidence. If either says no, every fail becomes needs review, the overall result is needs review, and the result says "This image can't be reliably assessed. Request a clearer image." with the reader's note on what got in the way.

Angled photos with some glare are still read. The queue has two of these, and one deliberately blurry, low-contrast photo.

## Speed

The brief asks for about 5 seconds per label.

- Both readers run at once. Low thinking effort and downscaled images keep calls short.
- Measured on four queue labels through the API: 3.3, 3.6, 4.4 and 6.4 seconds. The slowest was the blurry photo.
- A 15 second cutoff drops a reader that hangs. It is a guard, not the target.
- The first request after the reading schema changes took about 60 seconds for both models, while the API prepared the schema. The next took 3 to 4 seconds. A deployment should send one check after each release so agents never see that wait.

## Review queue

The queue is 25 generated applications: 10 spirits, 8 wines and 7 beers. Fourteen are clean. The rest have realistic problems: wrong alcohol content, wrong net contents, a different brand, changed warning wording, a title-case or colon-less lead-in, a lead-in not in bold, a missing warning, an unclear photo. Clean ones cover the allowed differences, like "STONE'S THROW" against "Stone's Throw", 750 mL against 0.75 L, 90 proof against 45%, 1 pint against 16 fl oz, and wine or beer with no alcohol statement.

`scripts/generate_samples.py` draws every label and writes `samples/queue/applications.json`. Each entry also records the expected result and the scenario, which the tests and the benchmark use and the API never serves.

Batch review of hundreds of labels is not implemented. The queue is checked one application at a time. A real batch would need a job queue and stored results.

## Restricted networks

Agents' browsers only talk to our site, and our server calls the model API, so IT only has to allow one address. Inside the agency, the same service could run in its own cloud and call Claude through Microsoft Azure or another approved provider, with no outside calls from agents' machines.

## No offline backup

An earlier version fell back to Tesseract, a local text-recognition program, when the AI couldn't be reached. It was removed. It could never pass a compliant label, since it can't see bold type, and it was weak on real photos.

## Interface

Built for agents with little technical comfort. Every result is shown as an icon and a word, never color alone. Nothing on screen mentions AI, models or how the app works. Tests check both the service's messages and the web page's text.

## Privacy

Uploaded images are processed in memory and never stored. Labels are sent to the Anthropic API to be read, which a real deployment would need to clear with TTB's data policies.

## Testing

- Unit tests cover every comparison, applicability and warning rule, and how two readings combine.
- API tests cover every route and error with scripted stand-ins for the models: agreement, disagreement, a slow reader, failures and unclear photos.
- A test fails if the committed queue drifts from its generator.
- `scripts/benchmark.py` scores real models on the queue against each expected result. It hasn't been run yet.

## Limitations

- Speed and accuracy were measured on four generated labels only.
- The labels are generated, not real photos.
- Not deployed yet.

## Open decisions

- Which two models to use. Best decided from benchmark results.
- What the input form asks for. The real application (TTB F 5100.31 and COLAs Online) has no alcohol content or net contents fields; those exist only on the label. The brief still treats them as values to match.
