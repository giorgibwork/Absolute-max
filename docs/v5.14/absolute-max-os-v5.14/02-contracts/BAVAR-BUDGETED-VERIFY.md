# BAVAR — Budgeted Adaptive Verification

**Source:** Adeli et al., Strategic Verification for Long-Running LLM Agents (preprint 2026, v2). Budgeted Adaptive Verification with Asymmetric Rewards (BAVAR).

**Status:** Protocol for Absolute Max OS verification allocation. Free-only, no new weights. Complements existing SPR terminal gate, three-valued evidence, and FGSE.

## Core Claim
Uniform dense verification is expensive and can create a “verifier tax.” Adaptive allocation—decide *what*, *when*, *which verifier*, and *how evidence affects action*—based on uncertainty, action criticality, irreversibility, expected value of information, verifier reliability, and remaining budget improves safe success under constrained budgets.

## Allocation Signals (use free signals)
- Actor uncertainty or low confidence.
- Action criticality / irreversibility (T3, write, spend, external side-effect).
- Expected information value of a check.
- Remaining verification / token / latency budget.
- Prior verifier reliability on similar cases.

## Policy Sketch
1. Always run cheap deterministic guards (permission, format, origin-bound).
2. Escalate to stronger verification only on high-criticality or high-uncertainty events.
3. Asymmetric rewards: strong positive process reward for verified safe progress; persistent penalty for path violations.
4. Lifecycle gates: promotion of memories or skills still requires FGSE + RSI dual gate; verification evidence is one input, not sufficient alone.
5. On budget exhaustion: prefer Clarify / Abstain (DISCERN) over un-verified irreversible action.

## Integration
- Inserts into the verification path before irreversible terminal actions.
- Composes with SPR terminal gate (positive + negative check still required; BAVAR decides *which* checks under budget).
- Works with Harness Anatomy invariants (especially T2, S2, P2).
- For long-running or multi-step tickets: record verification budget used and remaining.

## Defaults (paper-aligned, tunable)
- Prefer selective over dense when verification budget is scarce.
- High-criticality actions (T2+) always get at least one independent check.
- Target: match dense safety with substantially fewer judge/verifier calls when possible.

## Effect Size Notes
Runtime experiment (campus-information agent, 77 tasks, 2310 episodes): verification reduced safety violations from 9.5% to 0.9%; BAVAR matched dense verification’s correct-and-safe rate (~91.3%) while using 77% fewer judge calls and ~⅓ median latency. Simulation shows largest gains under scarce verification budgets.

## Fail-closed
Budget exhausted on a high-criticality irreversible action → do not proceed; escalate to human or Abstain. No reliability estimate for a verifier → treat as low-trust.
