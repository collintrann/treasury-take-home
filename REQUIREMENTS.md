# Requirements — TTB Alcohol Label Verification

Source: [Treasury take-home instructions](https://github.com/treasurytakehome-rgb/instructions)

## Functional requirements

- Let an agent upload a label image and enter its corresponding application information.
- Compare the label against application data for:
    - Brand name
    - Class/type
    - Alcohol content (ABV/proof)
    - Net contents
    - Bottler/producer name and address
    - Country of origin for imports, where applicable
- Identify which requirements apply to the beverage type and scenario; clearly disclose checks not implemented or not evaluated.
- Verify that the Government Health Warning is present and follows the [TTB health-warning requirements](https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/labeling-wine/wine-labeling-health-warning-statement), including:
    - Exact prescribed wording, punctuation, and capitalization
    - Uppercase and bold `GOVERNMENT WARNING:` heading
    - Non-bold warning body in a continuous paragraph
    - Required separation, contrast, and legibility
    - Applicable physical type-size requirements, **only when sufficient measurement evidence exists**
- Allow benign representational differences (e.g., `STONE'S THROW` versus `Stone's Throw`, 90 proof versus 45% ABV, or 750 mL versus 0.75 L) without false mismatches. Use contextual judgment for genuinely ambiguous names or descriptions.
- Return **Pass**, **Fail**, or **Needs Review** for each evaluated requirement. A failure must be supported by reliable evidence; missing, unreadable, or uncertain information must not silently pass or be treated as a confirmed violation.
- Show the observed value, expected value, a brief explanation, and supporting label evidence where available. Preserve original extracted text, including casing and punctuation.
- Present a simple, obvious workflow accessible to agents with limited technical experience; clearly communicate loading states, processing errors, and inconclusive findings.
- Handle imperfect label photos (angles, glare, low light) where possible, and flag cases that cannot be reliably assessed.
- Support the stakeholder's longer-term need for batch review of roughly 200–300 labels; for the prototype, prioritize a reliable single-label workflow and explicitly document whether batching is implemented.
- Minimize retention of submitted images and application data. Do not persist sensitive content by default; disclose any third-party processing and data-handling limitations.
- Document external dependencies and a path toward deployment on networks with restricted outbound access. The public prototype need not run inside a government network.
- Treat findings as **decision support for human agents**, not as autonomous regulatory approval.

## Performance

- Target approximately **5 seconds per label** for user-facing verification on representative inputs. Measure and report actual latency; don't sacrifice correctness to hit the target.
- Fail gracefully on unsupported files, unusable images, timeouts, and provider errors.

## Prototype scope and priorities

- **Required MVP:** Deployed, working single-label upload → extraction → hybrid validation → understandable per-field results; tests for core rules and error cases.
- **If time permits:** Precise evidence-region highlighting, targeted OCR, improved difficult-image handling, and broader beverage-specific checks.
- **Future / optional:** Batch-processing infrastructure, comprehensive regulatory coverage, persistence/audit history, and restricted-network deployment.
- Be transparent about unsupported fields, unmeasurable physical typography, incomplete coverage, and other prototype limitations.

## Deliverables

- Source code repository with a README explaining setup, configuration, running, and testing.
- A deployed application URL demonstrating the core workflow.
- Brief documentation of architecture, tools, assumptions, trade-offs, tested coverage, limitations, and observed performance.
