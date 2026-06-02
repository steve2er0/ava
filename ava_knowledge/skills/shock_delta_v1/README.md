# shock_delta_v1

This folder contains the first version of the shock delta workflow.

## What belongs here

- The step-by-step workflow for ingesting or applying shock knowledge deltas
- Standard explanation language for rule outcomes
- Assumptions, scope limits, and version-specific behavior

## What should not go here

- Experimental prompt fragments with no release intent
- Rules that belong in `rules/shock/`
- Test cases that belong in `tests/shock_delta/`

## How it fits into the AVA pipeline

This skill operationalizes the shock rule set. It is the interface between structured knowledge and agent behavior, and it should remain tightly coupled to its validation tests.
