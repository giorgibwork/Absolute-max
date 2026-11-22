# SIM — Self-Improvement Memory for Harness Optimizers (arXiv:2611.18856)

**Status:** Implemented 2026-11-22 | Free / structured memory for RSI  
**Source:** Yu et al. (Google Cloud AI / DeepMind / Penn State) — “Self-Improvement Memory Enables Continual Recursive Self-Improvement”

## Core idea

Memory for the **harness optimizer**, not for the task-solving policy.  

When continuing Recursive Self-Improvement (RSI) across a new model or new benchmark, the evolved harness alone is insufficient: the optimizer needs the *why*, the predicted outcome, the observed outcome, and the evaluation context of prior edits.

SIM groups edits by recurring harness problem and stores:

- Rationale (why the edit was made)  
- Predicted outcome  
- Observed outcome  
- Evaluation context (model, benchmark, probe set, metrics)  
- Provenance (source run, date, evidence refs)

New attempts extend the same history. Proposer and selector both read SIM.

## Why it compounds

- Direct transfer of an evolved harness often *hurts* on a new model (e.g., Opus-evolved → Gemini start below seed).  
- With SIM, continuation recovers and exceeds: workspace example 84.75 vs 73.42 harness-only (+11.33).  
- Coding: +2.36 mean points over harness-only continuation across 10 paired runs (p=0.003); 9/10 wins.  
- Enables Continual RSI (CRSI) without weight updates and without losing institutional knowledge of the harness.

## Operational protocol

1. **On every accepted harness edit** (prompt, tool rule, memory policy, skill admission, verification gate):  
   - Record problem class (e.g., “premature completion”, “tool schema mismatch”, “memory bloat”).  
   - Store rationale, predicted delta, observed delta, evaluation context, origin.  
2. **Group** by recurring problem; keep full history (do not collapse to final state only).  
3. **On continuation** (new model, new benchmark, or new domain):  
   - Load relevant SIM entries for the proposer and selector.  
   - Prefer reuse when predicted/observed match current context; revise or drop when contradicted.  
4. **Gate** new edits with the existing dual statistical gate (positive + negative check, non-regression).  
5. **Never** treat SIM content as SYSTEM law without three-valued verification; it is optimizer experience, not policy.

## Integration points

- **05-rsi / STATISTICAL-GATE / META-SKILL**: SIM is the persistent experience store that conditions future RSI proposals.  
- **GUARD / FGSE / ARISE**: directional regret and held-out gates still apply; SIM supplies the historical evidence those gates need.  
- **HarnessMM**: resolved step machines can cite the SIM entry that justified them.  
- **State-Transfer Audit**: SIM records themselves are transfer artifacts; hash-chain optional for high-assurance.  
- **Meta Self-Improving Memory**: SIM is the concrete record that meta-agents search over when discovering better LOAD/OFFLOAD policies.

## Minimal record shape (markdown or JSON)

```
## Problem: premature completion
- Edit: added explicit “do not claim done until SPR gate” reminder
- Rationale: observed early termination on multi-step tickets
- Predicted: +completion rate, no accuracy drop
- Observed: +4.1 pp completion, 0 regression on held-out
- Context: model=Gemini-3.8-Flash, bench=workspace-subset, date=2026-11-15
- Origin: TOOL (measured probe)
```

## When to use

- Any multi-generation or multi-model harness evolution.  
- When the same class of failure reappears after a model or benchmark change.  
- To prevent silent loss of why a previous fix was applied.

## Limitations

- Requires discipline to write the record at edit time (preserve-at-write).  
- Cross-model gains are largest when interfaces remain compatible.  
- Does not replace measurement; SIM guides search, gates still decide.

## Non-regression

SIM is additive memory for the optimizer. Do not auto-apply prior edits without re-measurement on the current model/benchmark.
