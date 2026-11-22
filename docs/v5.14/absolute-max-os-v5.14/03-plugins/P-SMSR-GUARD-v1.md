# P-SMSR-GUARD-v1

**Status:** active  
**Date:** 2026-11-10  
**Evidence base:** SMSR (arXiv:2606.12703) + OWASP Agent Memory Guard (ASI06 Reference Implementation)

## Role
Provide certified defense against Multi-Session Memory Poisoning (MSMP) and runtime prompt injection through write-time HMAC-SHA256 provenance tagging, source class separation, and retrieval-time smoothed verdict-based voting.

## Contract
1. **Write-Time Provenance:**
   - Every write to persistent memory must declare `source_class`: `SYSTEM`, `USER`, `AGENT`, or `EXTERNAL_TOOL`.
   - `EXTERNAL_TOOL` inputs (web fetch, git repos, third-party logs, API returns) are strictly quarantined and cannot set or override system rules, tool permissions, or execution goals.
   - An HMAC-SHA256 tag binding `(content, source_class, session_id, timestamp)` is calculated and stored.
2. **Retrieval-Time Smoothed Voting:**
   - On high-stakes actions (privilege escalation, credential access, external mutations), over-fetch $m$ candidates ($m > k$).
   - Run $N$ independent random ablations without replacement.
   - Judge outcomes via **verdict-based majority voting** (categorizing candidate actions as `SAFE`, `MALICIOUS`, or `NEUTRAL`) rather than string equality to defeat the Consistent Minority Effect.
3. **Invalidation:**
   - Any memory item missing verifiable provenance or flagged by OWASP AMG injection rules is marked `FAILED` and excluded from model context.

## Location in Stack
- Sits between the Tool/Memory boundary and the Executor context.
- Pre-requisite gate before `TAME-MEMORY-LOOP` commits.

## Measurement Log
| Date | Variant | Evidence / Notes | Decision |
|---|---|---|---|
| 2026-11-10 | v1 | Drops unsigned injection ASR from 93–100% to 0%; bounds authenticated attacks to 8% | active |