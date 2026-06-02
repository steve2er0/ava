# Shock Rules

This folder contains executable logic for shock-specific decisions.

## What belongs here

- Screening rules for retained modal content, convergence, damping caution, and response metric coverage
- Deterministic logic tied to transient or shock environments
- Rule metadata that identifies scope, assumptions, and fail-safe behavior

## What should not go here

- General modal adequacy logic that is not shock-specific
- Workflow prompts or analyst-facing narrative without structured logic
- Rules with invented thresholds that are not documented as internal defaults

## How it fits into the AVA pipeline

These rules are consumed by shock workflows and validated by shock-focused test cases. They are the operational layer between extracted shock knowledge and agent action.
