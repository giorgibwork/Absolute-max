# Super-agent+ — Router / Worker / Watchdog

**Status:** active in v5.3.0  
**Evidence base:** DeepSeek Super-agent design (Router–Worker, event-driven, continuous identity, external Watchdog); Absolute Max fidelity constraints (SPR, memory guard, cost rules).

## Goal

One continuous agent identity that handles multiple complex tasks without context smash, without blocking the user on long work, and without “alive but stuck” loops.

## Roles

### 1. Router
- Owns user-facing conversation and policy.
- Accepts or rejects work; creates a **Ticket** with a clear mandate.
- Dispatches one Worker per Ticket.
- Does **not** run long shells or heavy tool loops itself.
- Routes follow-ups on an existing Ticket back to the same Worker when possible.
- Keeps replies short; progress lives on the Ticket.

### 2. Worker
- Isolated context per Ticket (logical isolation even on single-session hosts).
- Full tools for execution.
- Reports progress and final outcome to Router.
- Must end with SPR-style verification when claiming done.
- May spawn short-lived sub-helpers; still owns the Ticket result.

### 3. Watchdog
- Observes Workers from outside the execution loop.
- Triggers on: no progress for N turns, repeated identical actions, goal drift, token burn without state change.
- Actions: demand status, mark stuck, request Router re-dispatch, or fail the Ticket closed.
- Never silently continues a non-progressing loop.

## Ticket (minimum fields)

```
ticket_id, mandate, source_channel, status,
worker_id, created_at, last_progress_at,
acceptance_mode (off | observe | auto),
result_summary, spr_receipt_ref
```

## Acceptance modes (proactive work)

| Mode | Behavior |
|------|----------|
| off | Only explicit user asks |
| observe | Log what would be accepted; do not act |
| auto | May pick up allowed work without @mention (strict policy only) |

Default for general use: **off** or **observe**. Auto only with explicit user policy.

## Single-session hosts (Grok / pure Gemini / Claude)

Emulate roles in one thread:
1. Label phases: `ROUTER:`, `WORKER:`, `WATCHDOG:`.
2. Never mix Ticket contexts in one reasoning block.
3. Watchdog checklist every few turns on long tasks: progress? drift? repeated actions?
4. Close Ticket only with S=1 evidence.

## Multi-session / DSH hosts

Prefer real isolation (separate worker session or directory per Ticket) when the platform allows it.

## Hard constraints

- Router does not bypass SPR.
- Worker cannot elevate domain tools into core authority.
- Watchdog cannot be the only verifier — SPR still required for “done”.
- Memory writes from Workers still go through origin-bound guard.

---

## v5.4 Watchdog triggers

- Same tool/action repeated without new evidence
- Plan restated with no SPR progress
- Token/turn budget exceeded
- Worker expands tool_class or risk without Router

Action: structural stop, status Blocked or report, do not "try harder" monologue.
