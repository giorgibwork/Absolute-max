# OMEGA APEX / Absolute Max OS (v6.0.0-apex)

**Host-independent, model-disposable, `$0.00` pure-stdlib Universal Intelligence & Operations OS.**

> *"Intelligence is a resource. Models are replaceable workers. Tools are conditional capabilities. Memory is governed institutional knowledge. The operating system is the contract. Evidence is the currency of truth. The human remains the authority."*

## What Changed in v6.0 (From Paper Inflation to Executable Core)

Through `v5.8`–`v5.14`, contracts accumulated in Markdown while `BASELINE.md` remained `EMPTY`.
`v6.0.0-apex` turns the OMEGA APEX Doctrine + highest-ROI research upgrades into **one pure Python 3.14 stdlib + SQLite core (`omega_core/`)** with thin host adapters (`adapters/antigem/`), a unified CLI (`omega`), a machine-readable **Implementation Status Ledger (`ledger/status.json`)**, and a real **10-Mission Integrated Acceptance Suite (`BASELINE.md`)**.

## Repository Layout

- `omega_core/` — Portable, zero-dependency Python engine (runs on AntiGem Android today; any Linux/macOS/VPS tomorrow):
  - `kernel.py` — Fail-closed Constitutional Gate (`PREPARE_ONLY`, `$0.00` spend floor, Weakest-Agent capability rings `R0`–`R3`, prompt-injection & secret scanners, SPIDES taint & circuit breaker).
  - `mission.py` — Intent Compiler, Mission & Task Contracts (`missions.db`), **Pro² Problem State**, Approval Queue, Idempotency Operation Ledger, SHA-256 Event Journal, and integrity-verified Crash-Resume Checkpoints.
  - `memory.py` — **Scoped-ORC** (`task_family` + `capability_ring`) SQLite FTS5 Vault, Appendix A.3 **Evidence Store** (contradiction-preserving), **GrepMem** lossless append-only exact-recall log, and deterministic Context Compiler with manifest.
  - `fabric.py` — Live **Model Qualification Registry** (`models.db`), cross-family fallback routing, and real host telemetry.
  - `research.py` — Adaptive `FAST / STANDARD / DEEP` research writing directly to the Evidence Store.
  - `suite.py` — Integrated **10-Mission Acceptance Suite (Missions A–J)** from Doctrine Part XVI.
  - `evo.py` — Isolated Evolution Laboratory (**SIM** + **RRSI** annealed edit budget/pruner + **ModularRSI** 5-module split, strictly `PREPARE_ONLY`).
  - `cli.py` — Unified `omega` CLI (`~/.local/bin/omega`).
- `adapters/antigem/` — Thin runtime hook adapters (`pre_tool_guard.py`, `session_start.py`, `post_tool_audit.py`, `memory_vault_adapter.py`).
- `tests/` — Unit & adversarial tests (`python3 -m unittest discover -s tests -v`).
- `ledger/` — Appendix D Implementation Status Ledger (`status.json` + `STATUS.md`).
- `BASELINE.md` — First real measured acceptance baseline on host hardware.
- `docs/` — Archived Doctrine (`OMEGA_APEX` v1.0, Supreme Constitution draft, Technical Architecture Spec v0.1, `ABSOLUTE_MAX_OMEGA_DOCTRINE.md`) and `v5.14` reference contracts.

## Quickstart (`$0.00`, Pure Stdlib)

```bash
omega status
omega suite --write-baseline
omega mission new "Ship verified patch" --family coding --accept "all unit tests pass"
omega problem add <mission_id> "Timeout under load" --severity 8 --hypothesis "Add bounded backoff"
omega mem add --key "coding/rule1" --family coding --ring 1 --text "Snapshot before edit"
omega mem search "Snapshot" --family coding --ring 1
omega grep "MEMORY_SAVED"
omega models list
omega models qualify gemini-4-hydrogen-low
omega approve list
omega ledger
```

## Research Intake Freeze Rule

Per Doctrine Law 6.13 (*"Complexity must earn its place"*) and 6.15 (*"Improvement requires evidence"*), no new unbuilt research contracts are added to the active prompt layer unless `omega suite` or a live mission trace demonstrates a measured bottleneck that the candidate solves in `omega_core/evo.py`.
