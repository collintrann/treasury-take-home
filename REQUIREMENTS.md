# Requirements

Derived from the take-home brief at
https://github.com/treasurytakehome-rgb/instructions: the stakeholder
interviews, the technical requirements, the additional context, and the
deliverables. Each requirement cites its source so it can be traced back.

- **MUST**: stated directly as a need, a deliverable or a regulation. Missing it fails the brief.
- **SHOULD**: a clear stakeholder wish. Leaving it out needs a written reason.
- **OUT OF SCOPE**: explicitly excluded by a stakeholder.

Design choices that answer these requirements live in [docs/DESIGN.md](docs/DESIGN.md).

## Core function

| ID | Requirement | Level | Source |
|---|---|---|---|
| F1 | Compare a label image against the values in its application and report, field by field, whether they match. | MUST | Sarah: "checks that what's on the label matches what's in the application" |
| F2 | Check the brand name. | MUST | Sarah ("Brand name matches?"); sample label |
| F3 | Check the alcohol content (ABV). | MUST | Sarah ("ABV is correct?"); sample label |
| F4 | Check that the government health warning is present. | MUST | Sarah ("Government warning is there?"); additional context: mandatory on all alcohol beverages |
| F5 | Check the class/type designation. | MUST | Additional context (common elements); sample label |
| F6 | Check the net contents. | MUST | Additional context; sample label |
| F7 | Check the bottler/producer name and address. | MUST | Additional context |
| F8 | Check the country of origin when the product is imported. | MUST | Additional context ("for imports") |
| F9 | Handle distilled spirits labels at least as complete as the sample (OLD TOM DISTILLERY, Kentucky Straight Bourbon Whiskey, 45% Alc./Vol. (90 Proof), 750 mL, warning). | MUST | Sample label |
| F10 | Account for rules that differ by beverage type (beer, wine, spirits), e.g. ABV exemptions for some wine and beer. | SHOULD | Additional context ("vary by beverage type", "with some exceptions") |

## Matching rules

| ID | Requirement | Level | Source |
|---|---|---|---|
| M1 | The government warning must match the regulatory text word for word. | MUST | Jenny ("It has to be exact. Like, word-for-word") |
| M2 | "GOVERNMENT WARNING:" must be in all capital letters. Title case ("Government Warning") is a failure. | MUST | Jenny |
| M3 | "GOVERNMENT WARNING:" must be in bold. | MUST | Jenny |
| M4 | Catch warnings that are reworded, shrunk or buried. | SHOULD | Jenny ("Smaller font, different wording, burying it in tiny text") |
| M5 | Apply judgment to harmless differences: "STONE'S THROW" on the label and "Stone's Throw" in the application are the same brand and must not be a plain rejection. | MUST | Dave |
| M6 | Don't reduce review to rigid pattern matching. Cases that need judgment should go to the agent rather than be decided wrongly. | MUST | Dave ("there's nuance... You need judgment") |
| M7 | Matching a number on the form to the number on the label is the main routine work to automate. | MUST | Sarah ("literally just making sure the number on the form is the same as the number on the label") |

## Performance

| ID | Requirement | Level | Source |
|---|---|---|---|
| P1 | Return a result for one label in about 5 seconds. Slower than that and agents won't use it. | MUST | Sarah ("If we can't get results back in about 5 seconds, nobody's going to use it") |
| P2 | Be faster than checking by eye. The previous pilot failed at 30-40 s per label. | MUST | Sarah |

## Usability

| ID | Requirement | Level | Source |
|---|---|---|---|
| U1 | Usable by agents with low technical comfort. The benchmark is a 73-year-old who just learned video calls. | MUST | Sarah ("something my mother could figure out") |
| U2 | Clean and obvious, with no hunting for buttons. | MUST | Sarah |
| U3 | Don't make an agent's job harder than the current manual process. | MUST | Dave ("just don't make my life harder"); the 2008 phone-system failure |
| U4 | Work for agents across the range, from Dave (prints his emails) to Jenny (could build it herself). Half the team is over 50. | MUST | Sarah |

## Batch processing

| ID | Requirement | Level | Source |
|---|---|---|---|
| B1 | Accept many labels in one upload, not one at a time. | SHOULD | Sarah ("that would be huge"); Janet, Seattle office |
| B2 | Handle a batch of 200-300 label applications from one importer. | SHOULD | Sarah ("dump 200, 300 label applications on us at once") |

## Image quality

| ID | Requirement | Level | Source |
|---|---|---|---|
| I1 | Read labels photographed at an angle, in bad lighting, or with glare on the bottle. | SHOULD | Jenny (flagged by her as "maybe out of scope") |
| I2 | When a label can't be read, say so clearly so the agent can request a better image. | MUST | Jenny (today's practice: unreadable labels are rejected and a better image requested) |

## Environment and security

| ID | Requirement | Level | Source |
|---|---|---|---|
| E1 | Work despite a network that blocks outbound traffic to many domains, including cloud ML endpoints. | MUST | Marcus ("half their features didn't work because our firewall blocked connections") |
| E2 | Fit an Azure environment if it moves past prototype. | SHOULD | Marcus (migrated to Azure in 2019; FedRAMP) |
| E3 | Store no sensitive data. Don't do "anything crazy" with security. | MUST | Marcus |
| E4 | Keep PII and document-retention policy in mind for any production path. | SHOULD | Marcus |

## Out of scope

| ID | Item | Source |
|---|---|---|
| X1 | Integration with COLA. This is a standalone proof of concept. | Marcus ("we're not looking to integrate with COLA directly") |
| X2 | Production deployment and its compliance work (FedRAMP, authorization). | Marcus |

## Deliverables

| ID | Requirement | Level | Source |
|---|---|---|---|
| D1 | Source code repository with all source code. | MUST | Deliverables |
| D2 | README with setup and run instructions. | MUST | Deliverables |
| D3 | Brief documentation of approach, tools used, and assumptions made. | MUST | Deliverables |
| D4 | A deployed application URL that evaluators can access and test. | MUST | Deliverables |
| D5 | Document trade-offs and limitations. | MUST | Evaluation criteria |
| D6 | Test labels beyond the single sample (generated or sourced). | SHOULD | Sample label section ("We encourage you to create or source additional test labels") |

## How the work is judged

The brief evaluates correctness and completeness of core requirements, code
quality and organization, appropriate technical choices for the scope, user
experience and error handling, attention to requirements, and creative
problem-solving. It states that "a working core application with clean code is
preferred over ambitious but incomplete features."
