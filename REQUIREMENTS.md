# Requirements

From the take-home brief: https://github.com/treasurytakehome-rgb/instructions

## Functional requirements

- Compare a label image against the application and show whether each field matches.
- Check the brand name, class/type, alcohol content, net contents, bottler/producer name and address, and country of origin for imports.
- Check that the Government Health Warning is present and matches the required text word for word.
- "GOVERNMENT WARNING:" must be in all capital letters and bold.
- Treat harmless differences, like capitalization in a brand name, with judgment rather than as a plain mismatch.
- Accept batch uploads of many labels at once.
- Handle imperfect photos where possible: odd angles, bad lighting, glare.
- Simple enough for agents with little technical comfort. Clean and obvious, with no hunting for buttons.
- Work on a network that blocks outbound traffic to many domains.
- Store nothing sensitive.

## Performance

- Return a result in about 5 seconds per label.

## Deliverables

- Source code repository with a README covering setup and run instructions.
- Brief documentation of the approach, tools used, assumptions, trade-offs and limitations.
- A deployed application URL.
