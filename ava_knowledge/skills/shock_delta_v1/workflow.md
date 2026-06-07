# shock_delta_v1 Workflow

This workflow applies AVA shock knowledge in a controlled, reviewable sequence. It is intended for extracting new shock guidance or evaluating an analysis package against the current shock rule base.

## Objective

Convert shock-relevant source content or analysis inputs into:

- Structured shock extracts
- Deterministic rule outcomes
- Review-ready explanations
- Regression tests when new logic is introduced

## Inputs

- A processed source package or structured analysis case
- Declared response metric
- Modal basis summary, including frequency coverage and effective mass by direction
- Shock characterization, including pulse duration or equivalent event descriptor
- Damping basis and any convergence evidence

## Workflow Steps

### 1. Frame the decision

Identify the engineering question before extracting or evaluating anything else. Typical questions are:

- Is the retained modal basis adequate for local shock response?
- Is a mass-based truncation argument sufficient for the stated response metric?
- Is the damping basis documented well enough for release review?

### 2. Extract only rule-bearing content

Capture statements that change a decision:

- Applicability conditions
- Quantitative limits or thresholds
- Required evidence, such as convergence or damping justification
- Exceptions that narrow the rule scope

Do not convert general background text into a rule candidate unless it changes a deterministic outcome.

### 3. Map the content to AVA concepts

Link each extracted statement to an existing concept where possible. For the current starter set, high-frequency shock adequacy should map to `concepts/high_frequency_effects.md`.

### 4. Evaluate current rules

Run the relevant shock rule set against the case inputs. For the current starter set:

- Apply `rules/shock/high_freq_modes.yaml`
- Record which rule fired
- Record which required inputs were actually present

### 5. Decide the delta

Classify the outcome as one of the following:

- `no_change`: the current rule base already covers the case
- `rule_update`: existing rule needs tighter scope or stronger evidence requirements
- `new_rule_candidate`: observed behavior is not represented in the current rule base
- `insufficient_evidence`: source or case data is not strong enough for a knowledge update

### 6. Generate the explanation

Produce a short engineering explanation that states:

- The response metric being judged
- The shock feature that controls the decision
- Why low-order mass participation is or is not sufficient
- What evidence is still required before closure
- The rule IDs and reference IDs supporting any theory or threshold statement

If a rule or concept only has placeholder references, describe it as internal starter guidance. Do not present placeholder-backed theory as external authority.

### 7. Add or update tests

If a rule changes, add at least one deterministic test case showing the triggering inputs and expected decision. The test should be strong enough that a reviewer can tell whether the rule logic drifted.

## Release Criteria

- No unstated response metric
- No unstated damping basis
- No uncited threshold promoted as released knowledge
- No theory citation without a reference ID from `../../references/reference_index.json`
- At least one validating test for each new or changed decision branch
- Output remains traceable to a source package or defined analysis case
