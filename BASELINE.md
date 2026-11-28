# OMEGA APEX / Absolute Max OS — Measured Acceptance Baseline (6.5.0-apex)

- **Run ID:** `SUITE-1795871361-99f171`
- **Host:** `AntiGem-Android-POCO-F6-Pro`
- **Timestamp (UTC epoch):** `1795871361`
- **Score:** `10/10` (100.0%)
- **Total runtime:** `361.85 ms`
- **Cost incurred:** `$0.00`

## Integrated Acceptance Missions (Doctrine Part XVI, Section 66)

- **Mission A [PASS] (6.45 ms):** Direct-response lightest routing
- **Mission B [PASS] (21.01 ms):** Unfamiliar-problem Intent + Pro2 Problem State
- **Mission C [PASS] (13.0 ms):** Scoped-ORC memory isolation + GrepMem exact recall
- **Mission D [PASS] (18.04 ms):** Deep investigation contradiction preservation
- **Mission E [PASS] (15.62 ms):** Multi-model qualification + automatic fallback
- **Mission F [PASS] (21.42 ms):** Tool composition + Weakest-Agent capability rings
- **Mission G [PASS] (75.45 ms):** Crash-resume checkpoints + tamper fail-closed + idempotency
- **Mission H [PASS] (2.78 ms):** Adversarial prompt-injection, secrets, spend & fail-closed gate
- **Mission I [PASS] (46.89 ms):** Isolated Evolution Lab (SIM + RRSI + non-regression)
- **Mission J [PASS] (139.2 ms):** Resource stress concurrency + strict context budget

## Raw Measured JSON

```json
{
  "run_id": "SUITE-1795871361-99f171",
  "version": "6.5.0-apex",
  "host": "AntiGem-Android-POCO-F6-Pro",
  "timestamp": 1795871361,
  "passed": 10,
  "total": 10,
  "success_rate": 1.0,
  "total_ms": 361.85,
  "results": [
    {
      "id": "A",
      "title": "Direct-response lightest routing",
      "ok": true,
      "ms": 6.45,
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
      "ms": 21.01,
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
      "ms": 13.0,
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
      "ms": 18.04,
      "detail": {
        "ok": true,
        "evidence_ids": [
          "EV-2d09e485c3",
          "EV-dca0d0ab90"
        ],
        "conflicts_surfaced": 1
      }
    },
    {
      "id": "E",
      "title": "Multi-model qualification + automatic fallback",
      "ok": true,
      "ms": 15.62,
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
      "ms": 21.42,
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
      "ms": 75.45,
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
      "ms": 2.78,
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
      "ms": 46.89,
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
      "ms": 139.2,
      "detail": {
        "ok": true,
        "concurrent_writes": 24,
        "compiled_chars": 1199,
        "memories_dropped": 19,
        "host_ram_avail_mb": 3091
      }
    }
  ]
}
```
