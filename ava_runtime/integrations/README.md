# Integrations

This folder contains boundary adapters for external systems that supply or consume AVA runtime data.

## Purpose

Provide stable seams for connecting AVA to PLM systems, job schedulers, document stores, or solver farms without contaminating the core runtime modules.

## What belongs here

- Connectors for external data sources or execution services
- Request and response translators for upstream and downstream systems
- Authentication-free local adapters used by pipelines in controlled environments

## What should not go here

- Core parser, solver, or numerical-analysis logic
- Released knowledge content
- Project-specific experimental code that is not intended to become a maintained interface

## How it interacts with `ava_knowledge`

Integrations move information into and out of the runtime layer, but they do not interpret engineering meaning. They enable AVA workflows to fetch model data and publish results while leaving rule intent and knowledge traceability in `ava_knowledge/`.
