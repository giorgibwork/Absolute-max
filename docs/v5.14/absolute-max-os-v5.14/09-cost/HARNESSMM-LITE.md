# HarnessMM-Lite — Guarded Decision Reuse — v5.4

Inspired by HarnessMM (guarded decision reuse; actor weights fixed).  
OS form: step machines + guards, not a claim of full paper reimplementation on device.

## Pattern

1. Router (or prior successful ticket) emits an ordered step list with **guard conditions**.
2. Worker executes next step without new LLM call if guard matches.
3. On guard fail / new semantics / abstain → call model again.
4. Log reuse hits for RSI and cost metrics.

## Example

```text
STEPS:
  1. write code → guard: files exist
  2. compile → guard: exit 0
  3. test → guard: exit 0
  4. report
```

If step 2 already succeeded in-session, do not re-plan compile.

## Rules

- Never reuse across contradictory evidence
- Never reuse consequential live actions under PREPARE_ONLY without approval still valid
- Truncate tool spam; keep tails + hashes
- RSI may improve step libraries only via dual gate

## Metrics

Track: reuse_hit_rate, tokens_per_success, callbacks_per_success.
