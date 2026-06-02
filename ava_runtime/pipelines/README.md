# Pipelines

This folder contains end-to-end execution workflows that connect data loading, computation, rule evaluation hooks, and output generation.

## Purpose

Define the operational sequence that AVA follows for specific engineering tasks, such as shock-response screening or modal-adequacy review.

## What belongs here

- Workflow entry points that call parsers, analysis modules, and visualization utilities
- Runtime-side rule-evaluation hooks and result packaging
- Output-generation logic for review artifacts

## What should not go here

- Released rule definitions that belong in `ava_knowledge/`
- Low-level file parsers or standalone solver helpers
- Ad hoc analysis scripts with no stable workflow role

## How it interacts with `ava_knowledge`

Pipelines are the execution bridge into `ava_knowledge/`. They load case data, compute response, call rule hooks aligned with the knowledge base, and emit structured outcomes that remain traceable to the controlling knowledge artifact.
