# Ticket and Tool Projection — v5.4

## Ticket shape (mandatory for non-trivial work)

```text
TICKET:
  goal: <one sentence>
  success: <observable check>
  fail: <hard stop conditions>
  max_turns: <N>
  tool_class: NONE | READ | EDIT | SHELL | NET | DEVICE
  risk: T0 | T1 | T2 | T3
  model_tier: light | standard | heavy   # optional
```

No ticket → no high-impact tools.

## Tool classes

| Class | Allowed |
|-------|---------|
| NONE | Reason only |
| READ | List, read, search within workspace |
| EDIT | + write/patch in scope |
| SHELL | + bounded shell |
| NET | + fetch/search |
| DEVICE | + phone UI / accessibility (explicit T3) |

Default session state: **NONE** until Router assigns a class.

## Projection rules

1. Start dark.
2. Expand only to the minimum class needed for the ticket.
3. Never inject full MCP/plugin catalogs into every turn.
4. Truncate tool results: head/tail + hash unless debug ticket.
5. Domain engines and optional plugins are off default PATH.

## Status vocabulary

- **Draft** — produced, not checked
- **Reviewed** — checked against requirements
- **Verified** — important claims checked with evidence/tests
- **Blocked** — cannot complete with available authority/evidence
- **Rejected** — failed requirement or operator reject

## Truth categories (memory / claims)

directly_observed | externally_sourced | independently_verified | inferred | estimated | assumed | disputed | stale | unknown

Repetition does not upgrade truth category.
