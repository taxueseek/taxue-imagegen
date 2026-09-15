# Image Generation Quality and Performance Baseline

## Problem redefinition

The engineering target is not to make prompts longer or to maximize visual complexity. It is to maximize instruction fidelity and reproducibility per unit of generation cost and iteration.

## MECE dimensions

1. **Instruction fidelity**: subject, composition, style, typography, aspect ratio, and explicit constraints.
2. **Reference fidelity**: preservation of the requested reference attributes without inventing unsupported details.
3. **Visual quality**: composition coherence, artifact rate, legibility, and stylistic consistency.
4. **Iteration efficiency**: first-pass success rate, retry count, prompt size, and unnecessary instruction overhead.
5. **Robustness**: ambiguous inputs, multiple constraints, negative constraints, and reference-heavy prompts.

## Evaluation corpus

Version a fixed set of representative prompts covering simple generation, reference-guided generation, typography, multi-constraint composition, style transfer, and adversarial omissions/additions.

## Quantitative gates

Track hard-constraint pass rate, semantic fidelity, artifact/unintended-element rate, text accuracy where relevant, first-pass acceptance rate, retry count, and prompt/token footprint.

## P1 optimization gate

Any prompt or pipeline optimization must identify a measured failure concentration, state one falsifiable hypothesis, run a controlled ablation, and prove that hard constraints do not regress. More instructions are not evidence of better quality.

## Experiment loop

`fixed corpus -> baseline -> failure classification -> hypothesis -> single-variable change -> ablation -> regression gate -> retain/revert`
