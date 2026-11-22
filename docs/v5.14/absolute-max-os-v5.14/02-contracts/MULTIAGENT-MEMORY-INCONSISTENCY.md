# Multi-Agent Memory Inconsistency — Conflict Visibility Protocol (arXiv:2611.22245)

**Status:** Implemented 2026-11-21 | Free / diagnostic + prompt protocol  
**Source:** Zhang et al., “Multi-Agent Memory Inconsistency: Where Factual Conflicts Disappear in LLM Agents”

## Core finding
Requiring multi-agent delegation increases retrieval of both sides of a factual conflict (50.2% → 68.7%) yet decreases conflict detection by the lead (16.2% → 13.2%). Workers report both claims for only 35.2% of retrieved pairs. Handoffs are the central failure point: split evidence disappears before joint conclusion.

Related: preserving and surfacing ranked conflict sets outperforms collapsing to a single winner (arXiv:2611.22461, +0.340 F1 in debate setting).

## Protocol for Absolute Max
On any multi-agent evidence collection:

1. **Conflict flag at write** — when a worker retrieves or generates a claim that may contradict existing graph / memory, tag it explicitly as potential conflict with source refs for both sides.
2. **Mandatory dual reporting** — worker handoff to lead must include both conflicting claims (or an explicit “only one side found”) rather than a resolved summary.
3. **Lead conflict check** — lead must run an explicit “do these conflict?” step before final conclusion when dual claims are present.
4. **Surfacing over resolution** — for debate or high-stakes synthesis, pass the ranked conflict set into the prompt rather than pre-resolving.
5. **Evidence-flow audit** — log which claims each worker saw vs what the lead received (State-Transfer style).

## Design invariants
- Aligns with SciMARS shared evidence graph (graph makes dual claims visible by construction).
- Origin-bound and three-valued: conflicting claims stay Unsupported until resolved by higher evidence.
- Complements Surfacing Disagreement principle: do not hide inconsistency.
- Watchdog can trigger on missing dual-report or absent lead conflict check.

## Integration points
- **SciMARS** — shared graph is the preferred substrate that prevents disappearance.
- **Router-Worker-Watchdog** — Watchdog monitors handoff completeness for conflicts.
- **LEDGER / DISCERN** — preserve-at-write keeps both sides; resolve-at-read only after explicit lead check.
- **Three-valued evidence** — conflict → both sides remain open until Supported resolution.

## Operational recipe
```
Worker:
- On retrieval of claim C that may conflict with known C': emit both + provenance.
Lead:
- On receipt of dual claims: run explicit conflict detection before conclusion.
- Prefer surfacing ranked set when synthesis is the goal.
```

## Fail-closed
Missing dual-report on detected conflict pair → handoff rejected, re-request. Lead concludes without conflict check when dual claims present → PARTIAL fidelity + flag. Collapsing conflict before lead sees it → non-compliant.
