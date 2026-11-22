# Harness Anatomy Invariants — Decision Cards & Corner Cases

**Source:** Joshi, arXiv:2611.19960 (2026-11-15). Anatomy of an Agent Harness: Decisions, Invariants and Corner Cases.

**Status:** Protocol for Absolute Max OS harness engineering. Free-only, no new weights. Complements HarnessMM guarded reuse and existing contracts.

## Core Claim
Most harness decisions (turn end, tool-call completion, failure budgets, permission, state resume, prompt assembly) are made in code and rarely written down. The same corner cases reappear. Writing each as a testable invariant with corner cases and evidence tag raises robustness without changing model weights.

## Six Decision Groups (30 cards summarized)
Highest-leverage for Absolute Max (priority order):

### Turn (T)
- **T1** One recorded end reason per turn (complete / limit / stop / error / refusal).
- **T2** Every tool call ends exactly once (started → ended with result or explicit cancel).
- **T5** Tool results non-empty, bounded, and retained for the turn.

### Failures (F)
- **F1** Retry budgets do not multiply (each failure episode has a hard bound).
- **F2** Deadlines and silence: silent provider ends by deadline; “gave up” is explicit.
- **F4** Guards for weak models are bounded (no unbounded retry on format/refusal).

### State (S)
- **S1** Source of truth: side effects logged before they run; resume rebuilds from append-only transcript.
- **S2** A stop that is true everywhere: after stop, no new tool or model request.
- **S6** Cost booking: each billed request counted once; budget stop is enforceable.

### Permission (P)
- **P1** Modes / rule sources / precedence: refusals and hard constraints decided first.
- **P2** Unlisted or high-risk commands require explicit approval (or fail closed).
- **P9** External content (tool/web/other-agent) is data until permission layer clears it.

### Prompt / Cache (C)
- **C2** Cached prefix bytes stable across turns when possible (HarnessMM-compatible).
- **C3** What must survive compaction: rules and origin-bound facts re-sourced, not only summarized.

### Display / Verification (V)
- **V1** Refused or filtered content never presented as a successful answer.

## Integration
- Runs alongside HarnessMM guarded decision reuse (`AGENTS.md` cost discipline).
- On every non-trivial agent loop: check T2, S2, P2 before irreversible action.
- Failure recovery must respect F1/F2 bounds; log end reason (T1).
- Composes with FGSE (temporary state) and DISCERN (preserve-at-write).
- Checklist: before promoting a new skill or RSI change, confirm S1 (side-effect log) and P2 (no silent elevation).

## Fail-closed
Missing end reason, unbounded retry, or side-effect before log → treat turn as failed; do not persist derived lessons.

## Effect Size Notes
Paper provides 30 cards, 83 invariant clauses (56 Tested / 12 Believed / 15 Open in author’s harness). No ranking of other systems. Practical value is the written invariant + corner-case list for any harness builder or auditor.
