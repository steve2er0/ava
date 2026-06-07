# Concepts

This folder contains stable engineering concepts derived from one or more extracts.

## What belongs here

- Explanatory notes that synthesize related extracted statements
- Definitions of mechanisms, boundary conditions, and failure modes
- Engineering interpretations that support multiple rules or skills

## What should not go here

- Untraceable opinions or design folklore
- Raw source text copied without structure
- Executable rule syntax that belongs in `rules/`

## How it fits into the AVA pipeline

`concepts/` turns extracted statements into durable engineering understanding. These files help AVA explain its decisions and keep rules grounded in real physical behavior.

## Reference Requirement

Every concept file must include a `## References` section. Approved concepts must cite real source records from `../references/reference_index.json`; concepts that still rely on placeholders must be marked `draft_reference_pending` and treated as internal starter guidance.
