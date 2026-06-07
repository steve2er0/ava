# Extracts

This folder holds structured engineering statements distilled from processed sources.

## What belongs here

- Atomic observations, conditions, limitations, and decision cues organized by discipline
- Rule candidates that preserve technical nuance from the source
- Notes on applicability, assumptions, and exception cases

## What should not go here

- High-level tutorials with no extraction structure
- Executable YAML logic that belongs in `rules/`
- Test cases or workflow instructions

## How it fits into the AVA pipeline

`extracts/` is the bridge between source text and formalized knowledge. It captures engineering meaning in a form that can be reviewed by humans and converted into concepts or executable rules.

## Reference Requirement

Every non-README extract that carries engineering theory, thresholds, limitations, or rule authoring cues must include a `## References` section with IDs from `../references/reference_index.json`. Draft extracts may use placeholder IDs only when the file is marked `draft_reference_pending`.
