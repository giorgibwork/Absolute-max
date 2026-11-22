# SciMARS — Multi-Agent Recursive Self-Improvement via Shared Evidence Graph (arXiv:2611.12552)

**Status:** Implemented 2026-11-21 | Free / harness-only  
**Source:** Wu & Liu, “SciMARS: Multi-Agent Recursive Self-Improvement for Closed-Loop Scientific Discovery”

## Core problem solved
Multi-agent scientific / research teams lose observations across role handoffs and repeat ineffective procedures even when evidence of failure is retained. Fixed role contracts and memory policies perpetuate errors.

## Architecture
1. **Shared Evidence Graph** (SciMARS + Memory) — active context store of observations, findings, plans, unresolved questions with provenance. All roles can record / retrieve / subscribe beyond current handoff.
2. **Separate Component Editors** (propose–probe–compose loop):
   - Role editor — adapts role procedures.
   - Coordination editor — adapts handoff and communication contracts.
   - Memory-policy editor ( + Memory only) — adapts how agents record, retrieve, and receive evidence while preserving graph provenance rules.
3. **Public probes** — each candidate change is evaluated on public execution evidence before composition.
4. **Composer + Selector** — combine or retain candidates; select next harness.
5. **Reflector** — extracts lessons that guide subsequent rounds.

## Design invariants for Absolute Max
- Evidence graph is origin-bound and three-valued; EXTERNAL/WEB claims stay non-SYSTEM.
- Adaptation is task-local and recursive over the execution harness, not a meta-rewriter of the meta-optimizer.
- Candidate probes required before any live selection; no fluency-based promote.
- Composes with existing multi-agent (Router-Worker-Watchdog) and research pipelines (Arkon-Hyperresearch).
- Prefer SciMARS + Memory when closed-loop research or multi-role evidence accumulation is active; fall back to fixed contracts otherwise.

## Effect size (paper)
- Autonomous Science Bench: 12/18 (GPT-6-Astra) and 2/18 (GLM-5.3) vs 8/18 and 1/18 base multi-agent.
- ScienceAgentBench: 14/38 vs 11/38.
- AppWorld: 11/20 vs 5/20.

## Integration points
- **Arkon-Hyperresearch / multi-agent research** — use as the shared evidence layer and adaptive coordination for long scientific tasks.
- **SoMem / LEDGER / DISCERN / ARISE** — graph preserves raw evidence; ARISE can still evolve macros on top.
- **RSI dual gate** — editor proposals land only after probe + held-out / statistical gate.
- **State-Transfer Auditing** — every graph write and handoff emits audit record.

## Operational recipe (prompt-only)
```
On multi-agent research / discovery task:
1. Maintain shared evidence graph (observations + provenance + unresolved questions).
2. After reference execution or failure cluster:
   - Spawn scoped editors (role / coordination / memory-policy).
   - Generate candidate probes on public evidence.
   - Compose and select only candidates that improve probe metrics.
3. Apply selected harness for next round; extract reflector lessons.
4. Never rewrite the selector itself without dual-gate.
```

## Fail-closed
No public probe pass or statistical gate → retain prior harness. Graph provenance violation → reject write. Isolated role memory (no shared graph) on multi-agent research → PARTIAL fidelity only.
