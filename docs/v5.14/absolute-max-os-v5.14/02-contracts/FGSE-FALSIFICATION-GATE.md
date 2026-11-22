# FGSE — Falsification-Gated Self-Evolution

**Source:** Tang et al., arXiv:2611.14326 (2026-11-10). When Should Agents Remember? Falsification-Gated Self-Evolution for LLM Agents.

**Status:** Protocol for Absolute Max OS memory/RSI admission. Free-only, no new weights.

## Core Claim
Local episode success is an unreliable signal for persistent behavioral updates. Many useful-looking lessons overgeneralize, encode shortcuts, or regress archived skills.

## Structured Hypothesis
Every candidate lesson is a hypothesis \( h \) with:
- **Precondition** \( c_h \): when it applies (explicit, testable)
- **Behavior change**: what the agent does differently
- **Expected effect**: measurable outcome
- **Verifier** \( v_h \): executable check (task success, constraint, regression)

## Gate (temporary state only)
Apply \( h \) only in a temporary agent state \( \Theta_t \oplus h \). Probe before any persistent write:

1. **Target-transfer** \( \mathcal{T}(h) \): similar high-level pattern, different surface/instance. Require positive gain \( \Delta_h \ge \eta \).
2. **Falsification** \( \mathcal{F}(h) \): boundary, precondition violation, decoy, near-miss. Fail rate \( \le \delta \).
3. **Archived-regression** \( \mathcal{R}(h) \): previously solved tasks. Damage \( \le \beta \).

**Commit / Refine / Reject**
- Commit only if transfer gain holds, falsification rate low, regression damage low.
- Refine precondition when transfer succeeds but falsification fails on separable cases.
- Reject otherwise. Log the rejection reason (origin-bound).

## Defaults (paper-aligned, tunable)
- Target probes: 8; Falsification: 16; Regression: 16
- Min target gain \( \eta = 0.03 \)
- Max falsification rate \( \delta = 0.05 \)
- Max regression damage \( \beta = 0.01 \)

## Integration
- Runs **before** any write into Evidence-linked memory, SoMem, or skill store.
- Composes with existing RSI dual gate (`05-rsi/STATISTICAL-GATE.md`) and RSI Tax.
- Temporary state = copy of relevant memory slice + candidate; never mutates live store until gate passes.
- On conflict with Evidence-linked descent or Correct-and-forget, FGSE evidence wins for new admissions; existing evidence_ref still required on commit.

## Effect Size Notes
Paper reports strong task gains (WebArena 39.8, AppWorld 78.8 avg, τ-Retail/Airline Pass¹ 0.724/0.487) while cutting falsification failures to ~5%, regression damage to ~1.3%, harmful committed updates to ~3.6%. Plasticity–safety frontier favorable under modest verifier budgets.

## Fail-closed
No verifier available → cannot gate → do not admit as persistent behavioral update (stay as ephemeral note or reject). Missing probes → reject.