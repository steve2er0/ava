# Tests

This folder contains deterministic validation cases for AVA knowledge artifacts.

## What belongs here

- Test cases with defined inputs, expected outcomes, and acceptance criteria
- Edge cases that protect against known failure modes in rules or skills
- Regression cases that preserve behavior across revisions

## What should not go here

- Raw analysis output with no expected result
- Project reports or certification evidence packages
- Open-ended examples that cannot be scored

## How it fits into the AVA pipeline

`tests/` closes the loop between knowledge authoring and reliable execution. Every important rule or skill should have at least one deterministic case that proves intended behavior.
