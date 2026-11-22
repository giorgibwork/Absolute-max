# DISCERN — Preserve at Write, Resolve at Read

**Source:** Ahuja et al., arXiv:2611.15729 (2026-11-11). DISCERN: Preserve at Write, Resolve at Read for Persistent LLM-Agent Memory.

**Status:** Memory architecture protocol for Absolute Max OS. Complements Evidence-linked memory and Correct-and-forget.

## Core Rule
**Preserve at write, resolve at read.**

Recall is largely solved; the remaining failure is *resolution* (entity identity, temporal currency, whether to answer or abstain).

## Write Path (strictly additive)
- Immutable per-actor event log is sole source of truth.
- Materialize rebuildable derived views:
  - Entity-family graph: confusable entities linked (SIMILAR_NAME) but **never merged**.
  - Bi-temporal fact store: superseded values soft-invalidated (valid-from/valid-to, expired_at) and retained; never dropped.
  - Episodic layer linked to entities and session timeline.
- Schema-free extraction; open-vocabulary attributes.
- Every view regenerable from the log. Extra nodes (drift) are safe; irreversible merges are not.

## Read Path (agentic navigation)
Zero-LLM (or low-LLM) tool surface over the graph. Navigate then commit **exactly one** gated terminal action:

1. **Answer** — earned by sufficient, resolved evidence.
2. **Update** — propose correction to memory (feeds Correct-and-forget / FGSE).
3. **Clarify** — ask for disambiguation when entities/time are ambiguous.
4. **Abstain** — when evidence insufficient or question unanswerable from memory.

Gates: EarnedAnswerGate, EarnedAbstainGate, DeclineRouter, near-miss guard. Prefer abstention calibration over forced answer.

## Integration
- Write path feeds Evidence-linked memory (lessons still require evidence_ref).
- Soft-invalidation + retention supports Correct-and-forget without destructive deletes.
- Entity non-merge reduces memory-induced degradation (complements WikiTrace-style linking).
- Read navigation is structure-aware (aligns with STAIR-MAX / DecisionRAG patterns).
- Abstain is first-class; three-valued evidence (Supported/Unsupported/Contradicted) maps cleanly.

## Effect Size Notes
On ENT-310: best abstention calibration (F1 0.924 vs ≤0.802 baselines); leads macro correctness (0.861 vs 0.806), driven by entity resolution (0.800 vs ≤0.40). Zero-tuning transfer to LoCoMo also leads. Read policy (not store) drives the gain.

## Fail-closed
Never merge entities at write. Never drop superseded facts. On ambiguous entity/time → Clarify or Abstain, not Answer.