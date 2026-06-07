# shock_delta_v1 Explanation Patterns

This file defines how the shock delta skill should explain its decisions. The goal is to produce language that is technically clear, bounded in scope, and suitable for engineering review.

## Explanation Principles

- State the response metric first.
- State the controlling shock or modal feature second.
- Separate screening evidence from closure evidence.
- Avoid absolute claims when the decision is limited to one response quantity.
- Call out missing damping or convergence evidence explicitly.
- Cite rule IDs and reference IDs for theory, thresholds, and rule rationale.
- Treat placeholder-backed knowledge as internal starter guidance, not external authority.

## Standard Explanation Template

1. Identify the target response quantity.
2. Describe the event feature that matters to the decision.
3. State which rule fired.
4. Explain why that rule is appropriate.
5. State what action is required next.
6. List supporting reference IDs, or state that the available reference is a draft placeholder.

## Example: High-frequency modes must be retained

The target quantity is local acceleration at the equipment attachment. The shock duration is short relative to the first elastic period, so higher-frequency structural content can affect the local peak even though the low-order modes capture most translational effective mass. Rule `SHOCK-HF-001` therefore applies, and the modal basis should be extended until the local acceleration response converges. Reference `REF-AVA-STARTER-SHOCK-MODAL-001` is currently a draft placeholder, so this should be treated as internal starter guidance until replaced with governing source records.

## Example: Low-order screening is acceptable, but only narrowly

The target quantity is global displacement, the cumulative effective mass in the governing direction exceeds the internal screening threshold, and the displacement result is already converged. Rule `SHOCK-HF-002` therefore allows the current modal basis for global displacement screening only. This does not establish adequacy for local acceleration or local stress. Reference `REF-AVA-STARTER-SHOCK-MODAL-001` is currently a draft placeholder, so this should be treated as internal starter guidance until replaced with governing source records.

## Example: Engineering review is still required

The case does not provide a documented damping basis or convergence evidence for the stated response quantity. Rule `SHOCK-HF-003` therefore blocks release of the adequacy decision until the missing evidence is supplied. Reference `REF-AVA-STARTER-SHOCK-MODAL-001` is currently a draft placeholder, so this should be treated as internal starter guidance until replaced with governing source records.

## Review Triggers

Escalate the explanation for human review when:

- The response metric changes mid-analysis
- The case relies on a damping assumption with no documented origin
- A mass-based argument is used to justify local stress or local acceleration
- Source content suggests a threshold but the threshold has not been formally adopted into the rule base
