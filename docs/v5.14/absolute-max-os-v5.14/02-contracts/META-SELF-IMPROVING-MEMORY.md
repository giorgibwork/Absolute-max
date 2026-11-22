# Meta Self-Improving Memory — Harness Discovery of LOAD/OFFLOAD Policies

**Status:** Implemented 2026-11-21 | Free / prompt-only (distillation optional, not required)  
**Source:** Meta FAIR RAM, “Self-Improving Memory: Meta-Optimization and Harness Distillation for Continual Learning Agents” (blog + related, Nov 2026)

## Core idea (free portion)
A meta-agent (same model) reads task-agent trajectories, memory directory state, and scores, then rewrites the LOAD (pre-subtask retrieval) and OFFLOAD (post-subtask write) prompts. Candidates are evaluated; only higher-scoring versions are retained. No weight updates required for the discovery stage.

## Results (paper / blog)
- Optimized (model-discovered) prompts: 56.0 average on Continual Learning Bench (Database, Codebase, Spectrum).
- Best human-written: 44.6.
- Generic: 36.1.
- Distillation (optional LoRA) retains part of the gain under generic prompts (43.1).

## Design invariants for Absolute Max
- Discovery is a closed-loop search over LOAD/OFFLOAD instruction text only.
- Evaluation uses real task outcomes or held-out probes; no fluency scoring.
- Accepted prompts become guarded reusable decisions (HarnessMM).
- Origin-bound: discovered policies carry evidence refs.
- Prefer discovery when memory policy is the bottleneck and human-written rules underperform across tasks.
- Distillation is out-of-scope for free stack (requires weights); treat as optional future note only.

## Integration points
- **ARISE / Recuris / Self-Distilled Memory Budget** — discovery can seed better micro/macro or Working/Experiential policies.
- **BRIDGE** — LOAD/OFFLOAD can be the thin instruction layer over chronological notes.
- **RSI dual gate** — new LOAD/OFFLOAD versions land only after measured lift.

## Operational recipe (prompt-only)
```
Periodically or on memory-related failure cluster:
1. Meta-agent reviews recent trajectories + final memory state + scores.
2. Propose revised LOAD and OFFLOAD prompts (concrete instructions for what to read/write).
3. Probe on held-out or next episodes.
4. Keep only versions that raise task success or reduce repeated failures.
5. Install accepted prompts as the active memory policy.
```

## Fail-closed
No measured lift on probe → retain prior LOAD/OFFLOAD. Policy that violates origin-binding or three-valued evidence → reject.
