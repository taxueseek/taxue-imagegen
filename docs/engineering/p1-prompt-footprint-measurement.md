# P1 measurement: image-generation prompt footprint

## Problem redefinition

The practical optimization target is the total instruction surface required to obtain an accepted first result. Prompt length alone is insufficient because removing a useful constraint can increase retries and total generation cost.

## Hypothesis

The large instruction/reference corpus may contain reusable rules whose marginal contribution is low for some task families. Selective loading or consolidation could reduce context cost without lowering first-pass acceptance.

## Measurement matrix

Use a fixed corpus covering poster, illustration, typography, reference-image, and constraint-heavy tasks.

Record:

- prompt/instruction token estimate
- reference count and estimated reference footprint
- hard-constraint pass rate
- semantic/reference fidelity
- text accuracy where applicable
- first-pass acceptance
- retry count
- total iteration footprint

Separate mandatory constraints from optional stylistic guidance.

## Ablation

Compare current behavior with one change at a time: remove duplicate guidance, narrow family-specific references, or load optional guidance conditionally. Keep model, image size, reference inputs, and generation settings fixed.

## P1 gate

Accept a production change only when total iteration cost decreases while quality metrics remain within the established baseline. Shorter prompts with worse first-pass acceptance are regressions.

This PR is measurement-only.
