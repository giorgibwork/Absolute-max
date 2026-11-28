# OMEGA APEX / Absolute Max OS — Measured Acceptance Baseline (9.0.0-apex)

- **Run ID:** `SUITE-1795881218-adc045`
- **Host:** `AntiGem-Android-POCO-F6-Pro`
- **Timestamp (UTC epoch):** `1795881218`
- **Score:** `10/10` (100.0%)
- **Total runtime:** `121.2 ms`
- **Cost incurred:** `$0.00`

## Integrated Acceptance Missions (Doctrine Part XVI, Section 66)

- **Mission A [PASS] (6.05 ms):** Direct-response lightest routing
- **Mission B [PASS] (11.39 ms):** Unfamiliar-problem Intent + Pro2 Problem State
- **Mission C [PASS] (7.45 ms):** Scoped-ORC memory isolation + GrepMem exact recall
- **Mission D [PASS] (8.22 ms):** Deep investigation contradiction preservation
- **Mission E [PASS] (8.78 ms):** Multi-model qualification + automatic fallback
- **Mission F [PASS] (7.54 ms):** Tool composition + Weakest-Agent capability rings
- **Mission G [PASS] (22.03 ms):** Crash-resume checkpoints + tamper fail-closed + idempotency
- **Mission H [PASS] (0.94 ms):** Adversarial prompt-injection, secrets, spend & fail-closed gate
- **Mission I [PASS] (14.8 ms):** Isolated Evolution Lab (SIM + RRSI + non-regression)
- **Mission J [PASS] (33.44 ms):** Resource stress concurrency + strict context budget

## Raw Measured JSON

```json
{
  "run_id": "SUITE-1795881218-adc045",
  "version": "9.0.0-apex",
  "host": "AntiGem-Android-POCO-F6-Pro",
  "timestamp": 1795881218,
  "passed": 10,
  "total": 10,
  "success_rate": 1.0,
  "total_ms": 121.2,
  "results": [
    {
      "id": "A",
      "title": "Direct-response lightest routing",
      "ok": true,
      "ms": 6.05,
      "detail": {
        "ok": true,
        "route": "fast_default",
        "primary": "gemini-4-neon-xhigh"
      }
    },
    {
      "id": "B",
      "title": "Unfamiliar-problem Intent + Pro2 Problem State",
      "ok": true,
      "ms": 11.39,
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
      "ms": 7.45,
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
      "ms": 8.22,
      "detail": {
        "ok": true,
        "evidence_ids": [
          "EV-d4227c5c09",
          "EV-8a74a6a5f2"
        ],
        "conflicts_surfaced": 1
      }
    },
    {
      "id": "E",
      "title": "Multi-model qualification + automatic fallback",
      "ok": true,
      "ms": 8.78,
      "detail": {
        "ok": true,
        "qualified": "QUALIFIED",
        "model_used": "gemini-4-neon-xhigh",
        "calls": [
          "gemini-4-carbon-high",
          "gemini-4-neon-xhigh",
          "gemini-4-carbon-high",
          "gemini-4-neon-xhigh"
        ]
      }
    },
    {
      "id": "F",
      "title": "Tool composition + Weakest-Agent capability rings",
      "ok": true,
      "ms": 7.54,
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
      "ms": 22.03,
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
      "ms": 0.94,
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
      "ms": 14.8,
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
      "ms": 33.44,
      "detail": {
        "ok": true,
        "concurrent_writes": 24,
        "compiled_chars": 1199,
        "memories_dropped": 19,
        "host_ram_avail_mb": 3109
      }
    }
  ]
}
```
