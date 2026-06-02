# Skills

This folder contains versioned agent workflows that apply AVA knowledge to specific tasks.

## What belongs here

- Workflow definitions, explanation patterns, assumptions, and output contracts
- Versioned operational guidance that calls rules and interprets results
- Domain workflows for extraction, rule application, and review support

## What should not go here

- Raw source extracts or standalone rules with no workflow context
- Unversioned prompts that cannot be reviewed or reproduced
- General engineering notes that do not drive an agent action

## How it fits into the AVA pipeline

`skills/` is the execution layer. A skill turns concepts and rules into a repeatable procedure that an AVA agent can follow and that reviewers can audit.
