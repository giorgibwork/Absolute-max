# Meta-Skill M — Reusable harness-evolution knowledge (v5.3.0)

**Evidence base:** Meta² (arXiv:2611.05139) — precomputed guidance for when to EVOLVE vs KEEP.

Update this file only through the RSI statistical gate. It is guidance for the evolver, not free-form personality text.

## When to KEEP (do not evolve)

- Failure is missing data or user ambiguity, not harness structure.
- Same edit was tried and rejected recently on similar tasks.
- Change would weaken SPR, memory guard, or capability rings.
- Only one lucky run supports the edit.
- Cost rises sharply with flat quality.

## When to EVOLVE

- Repeated same failure class across ≥2 tasks (pattern, not one-off).
- Clear missing primitive (e.g. always re-deriving the same shell pipeline → synthesize tool).
- Hold-out evidence already exists that a small edit helps.
- Watchdog flags systematic no-progress loops tied to harness behavior.

## Preferred interventions (cheap → expensive)

1. Truncate / filter tool output (cost)
2. Add or tighten a guard condition
3. Reuse a resolved decision (HarnessMM spirit)
4. Synthesize a small tested helper (BOXBOX)
5. Adjust Router vs Worker split for this task type
6. Larger prompt/plugin rewrite (last resort; full gate)

## Interventions to avoid

- Broad AGENTS rewrites from a single failure
- Removing negative probes “to go faster”
- Promoting domain tools into core PATH
- Memory writes without source_class
- Auto acceptance mode without explicit user policy

## Log template (append-only)

```
date | pattern | decision KEEP/EVOLVE | evidence | result
```

Start empty of anecdotes; only gate-passed entries.

---

## v5.4 log format

```text
RSI_ENTRY:
  date:
  change:
  positive:
  negative:
  decision: LAND|REJECT
  suite_ref:
  revert_if:
```
