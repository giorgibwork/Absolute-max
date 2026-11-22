# ARISE — Practical Self-Evolving Memory (arXiv:2611.23588)

**Status:** Implemented 2026-11-20 | Free / prompt-only + optional teacher  
**Source:** Zhang et al., “ARISE: Practical Self-Evolving Memory for Accurate and Cost-Efficient Enterprise Agents”

## Core loop (no weight updates, no tool/workflow rewrite)

1. **Fail** — agent produces incorrect or incomplete outcome on a task.
2. **Attribute** — model (self) or stronger teacher attributes the failure to a concrete, retrievable cause (missing rule, wrong retrieval, procedural slip).
3. **Micro memory** — store the correction as a short, retrievable micro-item (lesson / patch).
4. **Consolidate** — periodically cluster micros into candidate **macro rules**.
5. **Gate** — accept a macro-rule update **only if held-out accuracy rises**. Reject otherwise.
6. **Serve** — at inference, retrieve relevant micros + accepted macros; prefer macros for stable guidance.

## Design invariants for Absolute Max

- Memory evolution is **evidence-gated** (held-out rise required). Aligns with FGSE temporary-probe + Soft-HURT non-regression.
- Prefer **ARISE-Self** (deployment model as attributor) when teacher cost is unjustified; use teacher only for high-stakes domains.
- Micro items remain origin-bound and three-valued (proven / unproven / failed).
- Macro acceptance is a permanent compounding event → record in Meta-Skill / CURRENT-BASELINE.
- Cost posture: measured ~4% fewer calls / ~5% fewer tokens at comparable or better accuracy in original work.

## Integration points

- **TAME / SoMem / BRIDGE / LEDGER / DISCERN** — ARISE sits above them as the *evolution* layer. Write path still obeys preserve-at-write; ARISE only proposes new rules.
- **RSI / GUARD / FGSE** — ARISE provides the concrete memory-update primitive that those gates protect.
- **HarnessMM** — accepted macros become guarded reusable decisions; micros stay low-privilege until consolidated.

## Operational recipe (prompt-only)

```
On failure or after N episodes:
1. Extract 1–3 concrete failure attributions (what should have been remembered / applied).
2. Store as micro-memory with evidence_ref and three-valued status.
3. After threshold: propose consolidation → candidate macro rule.
4. Evaluate candidate on held-out or synthetic probe set.
5. Commit only on measured accuracy lift; otherwise discard or keep as micro.
```

## When to prefer ARISE vs BRIDGE

- BRIDGE: cheap default retrieval + chronological notes (most sessions).
- ARISE: when the agent is repeating the same class of procedural or rule-application error and a durable rule would compound.

See also: `FGSE-FALSIFICATION-GATE.md`, `GUARD-REGRET-RSI.md`, `BRIDGE-MINIMAL-MEMORY.md`.
