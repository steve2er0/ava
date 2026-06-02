# Rules

This folder contains deterministic, executable engineering rules.

## What belongs here

- YAML or other structured rule definitions with inputs, conditions, actions, and rationale
- Versioned thresholds and screening logic
- Rule metadata needed for validation and release control

## What should not go here

- Prose-only discussion with no machine-actionable logic
- Source extracts or concepts that have not been formalized
- One-off analyst conclusions tied to a single project only

## How it fits into the AVA pipeline

`rules/` is where engineering knowledge becomes operational. Rules consume structured inputs, make bounded decisions, and produce outputs that skills and tests can evaluate consistently.
