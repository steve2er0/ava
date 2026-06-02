# AVA Runtime

This directory contains the execution layer for the AVA Knowledge System. It turns structured engineering knowledge into runnable workflows by handling model parsing, solver orchestration, numerical response calculations, and output generation.

## What belongs here

- Parsers for structural model and result files
- Solver-facing utilities for deck generation and job execution
- Numerical analysis routines such as FRF and SRS calculations
- Visualization utilities for review-ready plots and geometry views
- Pipelines that connect runtime data to rule-evaluation hooks

## What should not go here

- Source-derived knowledge statements, concepts, or released rules
- Raw standards, handbooks, or engineering source material
- Project-specific scratch notebooks or one-off scripts with no runtime role

## How it interacts with `ava_knowledge`

`ava_runtime/` consumes released knowledge from `ava_knowledge/` and executes it. The knowledge layer defines what AVA should reason about; the runtime layer defines how AVA loads data, computes dynamic response, evaluates rule hooks, and emits engineering outputs.
