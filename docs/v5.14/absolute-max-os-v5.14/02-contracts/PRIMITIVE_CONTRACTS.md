# Absolute Max OS v5.2.0 — Complete Primitive Contracts

Every callable binary or shim must have a contract. Missing contract = do not treat as core.

## Trust tiers

| Tier | Meaning |
|------|---------|
| T0 | Security / verification. Fail closed. |
| T1 | Core OS. Always available when OS_READY. |
| T2 | Optional / host-specific. |
| T3 | Domain engine. Load on demand only. |

---

## Core binaries (T0 / T1)

| Binary | Tier | Inputs | Outputs | Success | Failure modes (non-zero) |
|--------|------|--------|---------|---------|---------------------------|
| **spr-verify** | T0 | `[--strict]` | JSON receipt (`terminal_gate_S`, sha256) | Exit 0 + S=1 | Syntax drift, mock/stub detected, positive or negative probe fail |
| **pagegram-guard** | T0 | `check <key> <content> --source <cls> --origin <uri>` | `{decision, sha256, reason}` | allow | Exit 10 injection, 11 bad source, 12 empty origin |
| **pagegram-mem** | T1 | `store` / `recall` / `stats` (store must go through guard) | slot JSON | Exit 0 | Exit 10 quarantined, 1 key missing |
| **os-daemon** | T1 | `call <service> <action> [args]` | JSON status | Exit 0 | 1 missing, 2/3 HCP violation |
| **tree-toc** | T1 | `[--json] <path>` | TOC / tree | Exit 0 | 1 path missing |
| **compact-log** | T1 | stdin | compacted stdout | Exit 0 | 1 non-UTF8 / broken pipe |
| **auto-checkpoint** | T1 | none (reads spr_receipt) | checkpoint + sha256 | Exit 0 | 1 missing/failed/stale receipt |
| **domain-load** | T1 | `<engine>` | shell exports | Exit 0 | 1 unknown engine |
| **dsh-health** | T1 | `[--check]` | health report | Exit 0 | non-zero on failed checks |
| **open-search** | T1 | query | results | Exit 0 | network / parse errors |
| **scrapling-v2** / **scrape** | T1 | URL / args | extracted content | Exit 0 | fetch / parse fail |
| **git-checkpoint** | T1 | none | git state anchor | Exit 0 | dirty / error |
| **verify** | T1 | shim → spr-verify | same as spr-verify | — | — |
| **mem** | T1 | shim → pagegram-mem + guard | same | — | — |
| **search** | T1 | shim → open-search | same | — | — |
| **research** | T1 | research helper | notes / results | Exit 0 | — |
| **box** / **agent-box** | T1 | sandbox args | isolated run | Exit 0 | isolation fail |
| **os-benchmark** | T1 | none / suite | scorecard JSON | Exit 0 | — |
| **perf-wrapper** | T1 | command | timed output | Exit 0 | wrapped command fail |
| **arkon-link** / **arkon-daemon** | T1/T2 | IPC | messages | Exit 0 | socket / shm errors |
| **pagegram-v2** / **pagegram-rs** | T1 | put/get | value | Exit 0 | key missing / size |
| **graphrag-rs** | T1 | query / add-node / add-edge | JSON | Exit 0 | malformed / missing |
| **tool-registry** | T1 | list / register | catalog | Exit 0 | bad args |
| **fs-prober** | T1 | [dir] | JSON listing + timings | Exit 0 | unreadable path |
| **pagegram-sync** | T1 | daemon | sync status | Exit 0 | — |
| **dsh-anti-kill.sh** | T2 | none | background survival | — | host-specific |
| **os-daemon** services | T1 | graphrag, registry, hcp, prober, telemetry | JSON | Exit 0 | service-specific |

## Domain engines (T3) — load only via `domain-load`

| Engine | Binaries (examples) | Contract requirement |
|--------|---------------------|----------------------|
| polymarket | poly-scout, poly-trader, poly-*, … | Each must document inputs, risk, and that it is not core OS |
| scouts | alpha-scout, x-scout, hyper-search, … | Same |
| combat-tweaks | god41, armwrestling/TSB notes | Same |

## Rules for new binaries

1. Add a row to this table before shipping.
2. Provide at least one positive and one negative test.
3. Assign trust tier.
4. If it can write memory or change privileges, it must call or sit behind pagegram-guard / SPR.

---

## v5.4 additions

See also:

- `TICKET-AND-TOOLS.md` — mandatory ticket shape, tool classes, status, truth categories
- `PRECEDENCE-AND-CHALLENGE.md` — hierarchy, faithful interpretation, challenge protocol
- `06-security/PREPARE-ONLY.md` — autonomy boundary
- `09-cost/HARNESSMM-LITE.md` — step machines and guarded reuse
