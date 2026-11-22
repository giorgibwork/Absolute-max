# Evolution Under Fire — Adaptive Safety Harness Evolution

**Source:** Evolution Under Fire: Evolving Agent Safety Harnesses with Adaptive Injection Stressors (arXiv:2611.22583, 17 Nov 2026).

**Status:** RSI / self-improving harness guidance for safety. Free-only protocol layer. Complements ActiveSec, GUARD-regret RSI, Self-Improving Harness.

## Core Claim
Static hand-designed safety harnesses plateau. Couple **harness evolution** with **adaptive stressor evolution**: utility-constrained tree search evolves executable safety harnesses from execution evidence while task model/benchmark/tools stay fixed; then adaptive stressors discover utility-preserving attacks that drive the next evolution stage.

## Practical Rules for Absolute Max
1. Safety harness changes land only through dual gate (STATISTICAL-GATE + Soft-HURT / non-regression) — same as other RSI.
2. Prefer modular updates (ActiveSec rings, capability tokens, Ring-0 guards) over full-harness rewrites.
3. When evolving defenses, also evolve the attack stressors; otherwise you overfit to yesterday’s injection patterns.
4. Measure both attack success rate **and** clean / attacked utility. Pure ASR reduction that kills helpfulness is reject.
5. Transfer of evolved harnesses across models is possible and valuable; re-measure on target host.

## Integration
- Feeds Self-Improving Harness + GUARD regret-guided RSI.
- ActiveSec remains the structural target architecture; Evolution Under Fire is the process for improving the guards.
- PREPARE_ONLY still holds for any live deployment of evolved harness code.
