# Solvers

This folder contains utilities that prepare and execute external analysis solvers.

## Purpose

Encapsulate deck construction, solver command generation, run control, and output discovery so analysis workflows remain clean and testable.

## What belongs here

- Deck builders for modal, FRF, and transient analysis setups
- Solver runner wrappers with logging and return-code checks
- Output-file discovery and run metadata capture

## What should not go here

- Knowledge-layer rules or concept explanations
- File-format parsing that belongs in `parsers/`
- Final engineering plots or pipeline orchestration

## How it interacts with `ava_knowledge`

Solvers produce the raw numerical evidence that AVA workflows compare against the released knowledge base. They are execution infrastructure only; rule thresholds, workflow intent, and explanations remain owned by `ava_knowledge/`.
