# High-Frequency Effects in Shock Response

Status: draft_reference_pending
Reference posture: Internal starter guidance only; do not cite as external authority until the placeholder reference is replaced with governing source records.

This concept note explains why high-frequency structural content can remain important even after lower modes capture most effective mass.

## Core Idea

High-frequency modes frequently contribute little to global base-motion participation, yet they can still control local acceleration, local stress, and attachment detail loads during short-duration shock events. The key issue is not whether those modes move the whole structure very far; it is whether they shape the local dynamic field at the point being qualified.

## When the effect becomes important

- The excitation duration is short compared with dominant structural periods.
- The quantity of interest is local acceleration, stress, or component interface load.
- The structural path between the input point and the response point contains local flexibility.
- The retained modal basis has achieved global mass targets but has not shown response convergence.

## Engineering implications

- A cumulative effective mass check can support screening, but it should not close the case by itself.
- Response convergence should be demonstrated for the specific quantity being used for acceptance.
- Damping assumptions deserve review because a small change in damping can suppress short-lived peaks.
- Qualification language should distinguish between global response adequacy and local response adequacy.

## Typical failure mode if ignored

The analyst stops after the low-order modes satisfy a mass-based criterion, reports acceptable global motion, and unintentionally underpredicts local hardware acceleration or stress. The model then appears well behaved while the actual hardware remains sensitive to higher-frequency response that was truncated out of the solution basis.

## Use in AVA

This concept supports shock rules that decide whether high-frequency modes must be retained, whether convergence evidence is mandatory, and how the agent should explain the limitation of mass-based adequacy checks.

## References

- `REF-AVA-STARTER-SHOCK-MODAL-001`: placeholder for starter shock and modal screening guidance. Replace before approving this concept for external theory citation.
