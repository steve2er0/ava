# Modal Rules

This folder contains executable logic for modal model adequacy and interpretation.

## What belongs here

- Effective mass checks, mode retention rules, and damping assignment logic
- Deterministic conditions for deciding whether a reduced modal basis is acceptable
- Reusable modal rules that can support shock, vibration, or acoustic workflows

## What should not go here

- Shock acceptance logic with no reusable modal content
- Narrative-only concept notes
- Project-specific exceptions that have not been generalized

## How it fits into the AVA pipeline

These rules provide baseline modal reasoning for multiple AVA workflows. They keep downstream decisions consistent when dynamic response fidelity depends on model content.
