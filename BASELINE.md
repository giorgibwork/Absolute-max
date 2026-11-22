# OMEGA APEX / Absolute Max OS — Measured Acceptance Baseline (6.1.0-apex)

- **Run ID:** `SUITE-1795332824-652a2a`
- **Host:** `AntiGem-Android-POCO-F6-Pro`
- **Timestamp (UTC epoch):** `1795332824`
- **Score:** `10/10` (100.0%)
- **Total runtime:** `255.59 ms`
- **Cost incurred:** `$0.00`

## Integrated Acceptance Missions (Doctrine Part XVI, Section 66)

- **Mission A [PASS] (8.23 ms):** Direct-response lightest routing
- **Mission B [PASS] (16.87 ms):** Unfamiliar-problem Intent + Pro2 Problem State
- **Mission C [PASS] (9.87 ms):** Scoped-ORC memory isolation + GrepMem exact recall
- **Mission D [PASS] (11.42 ms):** Deep investigation contradiction preservation
- **Mission E [PASS] (9.57 ms):** Multi-model qualification + automatic fallback
- **Mission F [PASS] (10.49 ms):** Tool composition + Weakest-Agent capability rings
- **Mission G [PASS] (33.12 ms):** Crash-resume checkpoints + tamper fail-closed + idempotency
- **Mission H [PASS] (1.48 ms):** Adversarial prompt-injection, secrets, spend & fail-closed gate
- **Mission I [PASS] (21.61 ms):** Isolated Evolution Lab (SIM + RRSI + non-regression)
- **Mission J [PASS] (132.36 ms):** Resource stress concurrency + strict context budget

## Raw Measured JSON

```json
{
  "run_id": "SUITE-1795332824-652a2a",
  "version": "6.1.0-apex",
  "host": "AntiGem-Android-POCO-F6-Pro",
  "timestamp": 1795332824,
  "passed": 10,
  "total": 10,
  "success_rate": 1.0,
  "total_ms": 255.59,
  "results": [
    {
      "id": "A",
      "title": "Direct-response lightest routing",
      "ok": true,
      "ms": 8.23,
      "detail": {
        "ok": true,
        "route": "fast_default",
        "primary": "gemini-4-hydrogen-low"
      }
    },
    {
      "id": "B",
      "title": "Unfamiliar-problem Intent + Pro2 Problem State",
      "ok": true,
      "ms": 16.87,
      "detail": {
        "ok": true,
        "unknowns": 2,
        "blocked_unproven_complete": true
      }
    },
    {
      "id": "C",
      "title": "Scoped-ORC memory isolation + GrepMem exact recall",
      "ok": true,
      "ms": 9.87,
      "detail": {
        "ok": true,
        "blocked_unapproved_global": true,
        "cross_family_bleed": 0,
        "scoped_hits": 1,
        "grepmem_hits": 1
      }
    },
    {
      "id": "D",
      "title": "Deep investigation contradiction preservation",
      "ok": true,
      "ms": 11.42,
      "detail": {
        "ok": true,
        "evidence_ids": [
          "EV-44a47792c8",
          "EV-feedf6fb0a"
        ],
        "conflicts_surfaced": 1
      }
    },
    {
      "id": "E",
      "title": "Multi-model qualification + automatic fallback",
      "ok": true,
      "ms": 9.57,
      "detail": {
        "ok": true,
        "qualified": "QUALIFIED",
        "model_used": "gemini-4-neon-high",
        "calls": [
          "gemini-4-neon-high",
          "gemini-4-neon-high"
        ]
      }
    },
    {
      "id": "F",
      "title": "Tool composition + Weakest-Agent capability rings",
      "ok": true,
      "ms": 10.49,
      "detail": {
        "ok": true,
        "effective_ring": 0,
        "write_denied": "deny",
        "r0_mem_leak": 0
      }
    },
    {
      "id": "G",
      "title": "Crash-resume checkpoints + tamper fail-closed + idempotency",
      "ok": true,
      "ms": 33.12,
      "detail": {
        "ok": true,
        "side_effect_runs": 1,
        "tamper_rejected": true,
        "event_chain_ok": true
      }
    },
    {
      "id": "H",
      "title": "Adversarial prompt-injection, secrets, spend & fail-closed gate",
      "ok": true,
      "ms": 1.48,
      "detail": {
        "ok": true,
        "injection_quarantined": "QUARANTINED",
        "fail_closed_bad_json": "deny",
        "spend_blocked": "deny",
        "tmp_blocked": "deny",
        "taint_gated": "ask",
        "secret_write_blocked": "deny"
      }
    },
    {
      "id": "I",
      "title": "Isolated Evolution Lab (SIM + RRSI + non-regression)",
      "ok": true,
      "ms": 21.61,
      "detail": {
        "ok": true,
        "regression_decision": "REJECTED_REGRESSION",
        "bloat_decision": "REJECTED_PRUNED",
        "win_decision": "PROPOSED",
        "live_untouched": true
      }
    },
    {
      "id": "J",
      "title": "Resource stress concurrency + strict context budget",
      "ok": true,
      "ms": 132.36,
      "detail": {
        "ok": true,
        "concurrent_writes": 24,
        "compiled_chars": 1199,
        "memories_dropped": 19,
        "host_ram_avail_mb": 2894
      }
    }
  ]
}
```
