# Soteria — Formally Verified Planning + Runtime Enforcement

**Source:** He et al., Soteria: Formally Verified Planning with Runtime Enforcement for Safe LLM Agents (arXiv:2611.17880, 13 Nov 2026).

**Status:** Protocol for Absolute Max OS safe tool-use. Free-only, no new weights. Complements FCP, BAVAR, Harness Anatomy, fail-closed policy.

## Core Claim
Utility and safety are in tension: blocking an unsafe action prevents a violation but can leave the agent with no recovery path. Soteria reconciles them via (1) hierarchical plan generation, (2) formal verification of the plan against domain policies *before any tool invocation*, and (3) runtime enforcement that uses the verified plan both as a conformance guard and as recovery guidance when an action is blocked.

## Protocol Sketch
1. **Plan before act.** Agent emits a structured hierarchical plan (goals → subgoals → candidate tool sequences).
2. **Verify plan offline.** Check the plan against specifications (policy constraints, invariants, ordering) using available formal or structured checkers. Reject or repair plan until it passes.
3. **Execute under monitor.** Runtime enforcer allows only actions consistent with the verified plan; blocked actions return a structured reason tied to the plan node.
4. **Recover via plan.** When blocked, replan from the last verified node or follow plan-provided alternatives instead of free-form improvisation.
5. **SPR still required.** Terminal claim of done still needs positive + negative evidence (existing SPR gate).

## Integration
- Insert before irreversible tool classes (SHELL, NET, DEVICE, high-risk EDIT).
- Composes with BAVAR (budget verification effort on plan criticality) and FCP (artifact/request conformance after generation).
- Aligns with Harness Anatomy stop-propagation and permission-precedence invariants.
- Fail-closed: no verified plan → no high-risk tool call; escalate or Abstain (DISCERN).

## Effect Size Notes
Across tool-use benchmarks: ~1.7× average task success vs best baselines, with **zero** policy-specification violations.

## Fail-closed
Unverified plan or verifier unavailable for a high-criticality action → do not execute; report and replan or escalate.
