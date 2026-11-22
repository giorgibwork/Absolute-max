# State-Transfer Auditing (arXiv:2611.23346)

**Status:** Implemented 2026-11-20 | Free / harness-level  
**Source:** Shah & Kathrotia, “Securing and Auditing Long-Horizon LLM Agents: State-Transfer Auditing and Controls in the Agent Harness”

## Problem

Critical failures occur at **state-transfer boundaries**, not only at tool calls:

- context ↔ session history
- session ↔ persistent memory
- memory ↔ external tools / environment
- workspace rollback ↔ inference-server KV / cache state

Conventional traces miss what crosses these boundaries, so attribution and monitors fail.

## Architecture (minimal viable)

At every transfer boundary the harness emits a **hash-chained audit record**:

- what was moved (summary or content hash)
- source and destination stores
- deterministic checks (schema, size, capability token validity)
- optional model-based semantic check (budgeted)
- binding of internal state to external side-effects

Deterministic checks run at microsecond overhead; semantic checks are selective.

## Absolute Max requirements

1. **Audit point definition** for each transfer type used by the stack (context compaction, memory write/read, tool result ingestion, rollback/restore).
2. **Hash chain** so records are tamper-evident and orderable.
3. **Separation**: deterministic vs semantic; never let model-based checks be the only gate for high-privilege transfers.
4. **Reuse for controls**: the same records power least-privilege capabilities, replay-resistant authorization, information-flow labels, obligation monitors, and transactional recovery.
5. **Failure localization**: when a multi-step trajectory fails, the transfer log is the primary diagnostic (not just the final tool error).

## Integration with existing stack

- **HarnessMM / ActiveSec / Harness Anatomy** — state-transfer records become first-class evidence for guarded reuse and Ring-0 guards.
- **TAME / DISCERN / LEDGER** — memory write and read are audited transfers; preserve-at-write is checkable.
- **Formal verification / VFM / Soteria** — transfer records supply the durable state needed for recovery and conformance.
- **Anti-failure playbook** — “missing transfer audit” is itself a failure mode to flag on high-stakes runs.

## Operational minimum (prompt + host)

When the host cannot emit real hash chains, simulate the contract:

- On every memory write / context compaction / tool-result ingest: emit a short structured log entry (transfer-id, from, to, hash-or-summary, deterministic-ok?).
- Prefer hosts that can persist these logs across turns.
- Treat absence of transfer records on long-horizon work as incomplete fidelity (PARTIAL claim only).

See also: `ACTIVESEC-HARNESS.md`, `HARNESS-ANATOMY-INVARIANTS.md`, `HARNESSMM` protocols.
