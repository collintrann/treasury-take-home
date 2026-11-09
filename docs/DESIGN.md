# Design

How Label Check works and why, with the trade-offs of each choice.

## How a label is checked

1. The agent opens an application from the review queue. The service's upload route also accepts label images with the application fields typed in.
2. Two models read all of the application's label images into fixed fields: brand, other names on the label, class/type, alcohol content, net contents, producer, country of origin and the warning text. They also answer yes, no or can't tell on the warning's typography and on whether the images are clear enough to read.
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

Anything missing, unreadable or uncertain is needs review. A field not found in the images may be on a panel that wasn't submitted, so it is never a fail. Not evaluated says why, for example "Not an import." It never changes the overall result.

The overall result is fail if any finding fails, otherwise needs review if any needs review, otherwise pass.

## Several label images

Real labels are usually split across panels: a front label, a back label with the warning, sometimes a neck label. An application holds up to six images. Each reader gets all of them in one request, each downscaled as before, with a note that they are panels of one container and a field may be on any of them. One reading per model keeps the two-reader merge unchanged.

The review screen shows the chosen panel large and the others as thumbnails, each named "Label panel 2 of 3" for screen readers.

Trade-off: more images mean more tokens and a longer read. Real applications took a median of 7.8 seconds, against 3 to 4 seconds for one generated label.

## Brands on real labels

The brand on TTB's record is often not the biggest name on the label. Labels lead with a product name and print the brand smaller, or use the bottler's name as the brand. So each reading also lists the label's other names. When the application's brand matches one of them, or appears in the bottler statement, the brand finding is needs review with a note saying where it appears. It fails only when the brand is nowhere on the label.

Accents are ignored, because TTB's records are plain capitals ("MARTI" for "Martí"). The same words in another order, or run together in a logo, need review.

## What applies to which product

The agent picks distilled spirits, wine or malt beverage.

- Alcohol content is required for spirits. Wine over 14% must show it. Wine at 14% or less, and beer, may leave it off, which is not evaluated. If they do show it, it must match.
- Country of origin is only checked for imports, meaning the application gives a country.
- Any other blank application field is not evaluated.

Other beverage-specific rules are not implemented. Examples are beer net contents in US units, wine appellation and vintage, sulfite statements, and spirits age statements. Country of origin is a Customs rule rather than a TTB one, but the brief asks for it. Sources are 27 CFR parts 4, 5, 7 and 16 (https://www.ecfr.gov/current/title-27).

## The warning

The warning has nine findings, always in this order: present, wording, lead-in in capitals, lead-in bold, rest not bold, one continuous paragraph, separate from other text, legible, and type size.

- Wording must match the regulation word for word, punctuation included. Layout doesn't matter: line breaks, a hyphen that splits a word at a line break, and the spacing around "(1)" and "(2)". A mismatch shows which words differ.
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

If only one reader answers in time, its results stand, except that the faster second reader alone can't pass anything about the warning beyond its presence. So when only the first reader answers, its reading alone can pass the warning. That is the risk the second reading guards against. It was kept because the first reader is the more accurate model and, with a 15-second cutoff, a reading rarely misses it. If neither answers, the agent sees "We couldn't read this label right now. Please try again in a minute."

## Unclear photos

Each reader says whether the photo can be read with confidence. If either says no, every fail becomes needs review, the overall result is needs review, and the result says "This image can't be reliably assessed. Request a clearer image." with the reader's note on what got in the way.

Angled photos with some glare are still read. The queue has two of these, and one deliberately blurry, low-contrast photo.

## Speed

The brief asks for about 5 seconds per label.

- Both readers run at once. Low thinking effort and downscaled images keep calls short.
- Measured on four generated queue labels through the API: 3.3, 3.6, 4.4 and 6.4 seconds. The slowest was the blurry photo.
- On 120 real applications with all their images: median 7.8 seconds, 90th percentile 10.4 seconds. This misses the 5 second target. More images per label is the main cause.
- A 15 second cutoff drops a reader that hangs. It is a guard, not the target.
- The first request after the reading schema changes took 60 to 140 seconds, while the API prepared the schema. The next took 3 to 4 seconds. The service reads one sample label with each model when it starts, with a 5-minute limit, so that wait happens before any agent's first check.

## Review queue

The queue has 18 real applications and 25 generated ones.

The real ones are six per beverage type, drawn at random with a fixed seed (`REAL_SEED` in `scripts/generate_samples.py`) from the 120-record test set in `samples/ttb/`. They are not hand-picked. They hold what TTB's public record has: brand, applicant, approval date and, for imports, the country of origin. The other fields are blank, so they are not evaluated. Their right answer isn't known, so they have no expected result. Each links to its record in TTB's Public COLA Registry.

The generated ones are 10 spirits, 8 wines and 7 beers. Fourteen are clean. The rest have realistic problems: wrong alcohol content, wrong net contents, a different brand, changed warning wording, a title-case or colon-less lead-in, a lead-in not in bold, a missing warning, an unclear photo. Clean ones cover the allowed differences, like "STONE'S THROW" against "Stone's Throw", 750 mL against 0.75 L, 90 proof against 45%, 1 pint against 16 fl oz, and wine or beer with no alcohol statement.

`scripts/generate_samples.py` draws every generated label, copies the real labels' images, and writes `samples/queue/applications.json`. Each entry also records the expected result and the scenario, which the tests and the benchmark use and the API never serves.

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
- `scripts/benchmark.py` scores real models on the generated queue against each expected result. It hasn't been run yet.
- `scripts/eval_ttb.py` runs the real check on the 120 real applications and on 30 copies with a different brand. Results are in [ttb-eval.md](ttb-eval.md). Every Fail on an approved label was opened and classified by hand.

## Limitations

- Accuracy on real labels covers only the brand, the country of origin and the warning, since TTB's public record has no other application fields.
- The real labels are artwork files, not photos of bottles. Photo handling was tested on generated labels only.
- Checks on real applications take longer than the 5 second target.

## Open decisions

- Which two models to use. Best decided from benchmark results.
- What the input form asks for. The real application (TTB F 5100.31 and COLAs Online) has no alcohol content or net contents fields; those exist only on the label. The brief still treats them as values to match.
