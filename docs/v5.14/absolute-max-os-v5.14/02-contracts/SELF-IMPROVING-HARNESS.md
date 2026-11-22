# Self-Improving Agent Harnesses — Unifying Framework

**Source:** Shah & Kathrotia, Harnesses That Improve Themselves: A Unifying Framework for Self-Improving Agent Harnesses (arXiv:2611.22299, 17 Nov 2026).

**Status:** Protocol for Absolute Max OS RSI / harness evolution. Free-only, model weights fixed. Complements FGSE, RSI dual gate, Harness Anatomy, and existing modular evolution notes.

## Core Claim
Agent success depends as much on the runtime harness (context/memory, control, action interfaces, verification) as on model weights. Static harnesses stall or regress across models/tasks. Self-improving harnesses inspect execution traces, separate runtime bugs from model limits, and rewrite their own code under gates.

## Four Editable Runtime Components
1. **Context and State** — multi-turn history, working vs experiential memory, compaction.
2. **Agent Control** — turn budgets, loop detection/breakers, planning vs execution, subagent delegation.
3. **Action Interface** — ACI, sandboxed tool/shell, observation formatting, on-demand schema loading.
4. **Verification and Recovery** — pre-stop checks, tests, repair routing before termination.

## Four-Stage Closed-Loop Self-Improvement
1. **Diagnose Failures** — cluster verifier errors and diff trajectories; root-cause runtime bugs vs model limits.
2. **Propose Edits** — synthesize hook or module code patches (not full-harness rewrites).
3. **Validate & Filter** — check runtime execution + held-out generalization; anti-overfitting gates.
4. **Deploy or Route** — merge verified edit, archive, or route by model/task.

## Design Principles (paper-aligned)
- Prefer modular updates with validation gates over full-harness rewrites (overfit or break across modules).
- Modular gated evolution generalizes across models while bounding token cost.
- Defenses against prompt bloat, benchmark gaming, and evaluator tampering.
- Discover reusable mechanisms: pre-stop verifiers, loop breakers, persistent memory.

## Integration
- Outer loop sits under RSI dual gate + FGSE (hypotheses as structured precondition + change + effect + verifier; temporary probe before commit).
- Aligns with Harness Anatomy invariants (testable decisions at turn end, tool completion, stop propagation).
- For Absolute Max: land only dual-gated modular patches; record trajectory evidence for diagnosis.
- Composes with BAVAR for budgeted validation of candidate patches.

## Effect Size Notes
Experiments on SWE-bench Lite: gated modular evolution outperforms prompt reflection and full-harness rewrites across models and repositories at a fraction of the token cost.

## Fail-closed
No held-out validation or anti-overfitting gate pass → do not deploy. Full rewrite proposal → reject or force modular decomposition. Evaluator tampering risk → independent critic required.
