# Cost Rules — Absolute Max OS v5.3.0

**Evidence base:** HarnessMM guarded reuse; Agency harness interposition (cost cuts without accuracy loss); Super-agent short Router replies.

## Mandatory

1. **No redundant LLM callbacks** when the next action and guards are already decided (HarnessMM spirit). Execute directly if guards match.
2. **Truncate tool output** before re-injecting into context (keep head/tail + errors; drop bulk noise via compact-log patterns).
3. **No empty status turns.** If nothing changed, do not burn a full reasoning loop.
4. **Router replies stay short**; long work stays on Worker tickets.
5. **Batch independent steps** in one turn when safe.
6. **Cache resolved decisions** with explicit guard conditions; reuse when inputs match.
7. **Prefer cheaper subagent / flash variant** for parallel sweeps when host allows (DSH-Go).

## RSI cost check

A change that raises tokens-per-success without quality gain is a **regression** under the statistical gate.

## Measurement (when possible)

Log rough tokens or turns per successful Ticket. Prefer lower cost at same S=1 rate.

---

## v5.4

- See `HARNESSMM-LITE.md` for step-machine reuse
- Default-dark tools (see `02-contracts/TICKET-AND-TOOLS.md`)
- Rate-limit degrade: shrink ticket, increase reuse — do not disable gates
