# Recuris — Recursive Experiential–Working Memory Evolution (arXiv:2608.24876)

**Status:** Implemented 2026-11-21 | Free / harness-only  
**Source:** Yu et al., “Recursive Experiential–Working Memory Evolution for Long-Horizon Agent Harnesses”

## Core idea
Long-horizon RSI fails because growing histories obscure task state and misalign skill invocation. Recuris splits memory and evolves only the skill component under validation gates.

## Architecture
Skill Memory \( M = (E, W, \rho, C) \):
- **Working Memory (W)** — tracks verified task progress and current needs; drives skill selection.
- **Experiential Memory (E)** — stores reusable skills; retrieved only when grounded by W.
- **ρ, C** — retrieval and composition policies.
- Structured trajectories \( (w_t, E_t, a_t, o_t) \) localize failures to a specific component.
- Fixed Meta-Agent proposes localized, validation-gated updates to Skill Memory only.
- Bounded recursive loop: updates reshape execution → new evidence → further localized patches.

## Design invariants for Absolute Max
- Working Memory is the sole driver of skill invocation (state-grounded, not history-grounded).
- Updates are component-local and require deterministic validation gate on paired held-out evidence.
- No weight updates; pure harness evolution.
- Complements ARISE (failure→micro→macro) by providing the structured Working/Experiential split that makes attribution precise.
- Aligns with CoReMem prospective anchors and State-Transfer Auditing at memory boundaries.

## Effect size (paper)
- Improves 35 of 37 completed model–benchmark pairs.
- τ²-Bench: +17.8 to GPT-5.6 Sol, +15.6 to Claude Opus 5 (reaching 87.9%).
- SkillFlow: +16.6 / +13.5 on Qwen3.6-27B/35B.
- Advantage widens with horizon (+32.2 on longest tasks); common long-horizon failures fall up to 80%.

## Integration points
- **Long-horizon tickets / multi-turn research** — activate Working Memory tracker + Experiential skill store.
- **ARISE / GUARD / FGSE** — Recuris supplies the failure-localization substrate; gates still required for landing.
- **Harness Anatomy** — Working Memory state is a testable decision card at turn end.
- **BRIDGE / SoMem** — can host the Experiential store; Working Memory stays in active context or short-term file.

## Operational recipe (prompt-only)
```
On long-horizon task:
1. Maintain explicit Working Memory: current progress, verified state, open subgoals.
2. Retrieve Experiential skills only when conditioned on Working Memory state.
3. After failure or episode: Meta-Agent localizes to one component (E / W / ρ / C).
4. Propose minimal patch; validate on held-out pair.
5. Commit only on gate pass; otherwise discard.
```

## Fail-closed
No localization or held-out validation → do not update Skill Memory. Working Memory not driving retrieval → fall back to BRIDGE chronological notes and flag PARTIAL.
