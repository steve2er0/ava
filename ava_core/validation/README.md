# AVA Validation

Shared validation procedures belong here: required checks, evidence standards,
test expectations, and release criteria.

Validation guidance in this scope is intended to keep AVA's engineering output
auditable and repeatable.

## Approval Gate

An engineering skill is not approved until it has a validation package in this
directory. The package must include:

- `golden_cases/<skill>.json`: deterministic input cases that exercise normal,
  edge, and failure behavior.
- `expected_outputs/<skill>.json`: expected summaries, findings, statuses, and
  tolerances for each golden case.
- `regression_tests/<skill>.md`: the regression procedure or test entrypoint
  that replays the cases.
- `approval_records/<skill>.json`: the release decision, approver, date, linked
  cases, and evidence.

Approved records are machine-checked by `tests/ava_core/test_validation_approval_records.py`.
If a record says `status: approved`, every referenced golden case and expected
output must exist, and every validated case must be represented in the approval
record.

## Directory Layout

```text
validation/
├── golden_cases/
├── expected_outputs/
├── regression_tests/
└── approval_records/
```

## Required Case Coverage

Each approved skill should include:

- One synthetic case with a known answer.
- One representative real or project-derived case, sanitized as needed.
- One missing-input or malformed-input case.
- One boundary or mismatch case that protects a known failure mode.

For data-sensitive workflows, golden cases should use synthetic, sanitized, or
hash-referenced artifacts. The approval record should describe what was
validated without requiring raw proprietary data to be ingested by an LLM.
