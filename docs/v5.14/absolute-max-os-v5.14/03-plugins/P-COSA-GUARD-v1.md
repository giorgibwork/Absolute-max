# P-COSA-GUARD-v1

**Status:** active  
**Date:** 2026-11-10  
**Evidence base:** CoSA: Conflict of Skills Attack (arXiv:2610.35082, Oct 2026) + RAT (arXiv:2611.12300, Nov 2026)

## Role
Prevent policy violations arising from the composition of multiple independently benign agent skills. When multiple skills interact, outputs from an unprivileged skill must not be fed into high-privilege execution tools without authorization.

## Contract
1. **Skill Taint Tracking:**
   - Tag all artifacts, data, and parameters produced by third-party, web-retrieved, or unverified skills with `taint: UNTRUSTED_SKILL`.
2. **Authorization Boundary:**
   - Consequential tools (`bash`, `edit`, `mcp__phone__*`, `terminal_send`) must inspect the taint status of incoming arguments.
   - If an argument is derived from an untrusted skill or external input without explicit human/supervisor validation, the execution is blocked.
3. **Formal Composition Invariant (RAT):**
   - Adding a skill must not mutate or invalidate the preconditions or causal laws of existing core safety skills.

## Measurement Log
| Date | Variant | Evidence / Notes | Decision |
|---|---|---|---|
| 2026-11-10 | v1 | Cuts cross-skill policy violations from 65.28% to 6.67% on CoSA-Bench | active |