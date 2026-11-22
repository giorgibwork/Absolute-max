# LEDGER — Auditable Agent Memory Under Change

**Source:** LEDGER: Auditable Agent Memory Under Change (arXiv:2611.20927, 16 Nov 2026).

**Status:** Protocol for Absolute Max OS memory under changing facts, multi-source trust, and user deletion. Free-only. Complements HEAMS, DISCERN, CoReMem, AGENT-MEMORY-GUARD, origin-bound memory.

## Core Claim
Most memory systems are scored on fixed histories and final answers. Real use has changing facts, differing source reliability, and deletion requests. LEDGER makes a language model *propose* facts while *explicit rules* decide: which value is current, which source to trust, and what to delete. Each fact keeps source and validity period. LEDGER+EP adds fallback search over raw turns (with scrub on delete).

## Protocol Sketch
1. **Propose + rule.** Model proposes candidate facts; deterministic rules (not the model alone) select current value, resolve conflicts by source priority / recency policy, and apply deletes.
2. **Provenance.** Every fact carries source ID and interval of validity. Never silently overwrite without retaining supersession link (aligns with DISCERN preserve-at-write).
3. **Deletion fidelity.** On user forget/correct: remove from ledger evidence and scrub fallback raw turns so deleted content does not reappear in later evidence packs.
4. **Budgeted retrieval.** Evidence sent to the answering model is bounded; history growth does not imply unbounded context.
5. **Modes.** Fallback (LEDGER primary, EP when uncovered) vs augment (both) — choose by ticket risk and HEAMS privacy/sovereignty needs.

## Integration
- Use for multi-session coding agents and long-horizon personal memory.
- Pair with HEAMS evaluation (security/privacy/sovereignty dimensions).
- Write path still passes AGENT-MEMORY-GUARD / SMSR before origin-bind.
- Resolve-at-read (DISCERN) can consult ledger current value + period.

## Effect Size Notes
Coding multi-session workload: LEDGER+EP ~91–94% correct vs ~82–83% full-history replay (strongest baseline). Deletion probes: no deleted value reached system evidence. LongMemEval: same accuracy as full replay at ~1% of context.

## Fail-closed
No explicit current-value / source / delete rules → treat as ungoverned memory; do not promote for high-sensitivity use. Deletion request without scrub path → do not claim forget complete.
