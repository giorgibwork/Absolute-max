# P-DECISION-CONTEXT-v1

**Status:** active  
**Date:** 2026-11-10  
**Evidence base:** Forge Decision Context / forge_dc (arXiv:2611.08644, Nov 2026) + Agency (arXiv:2611.12122, Nov 2026)

## Role
Enable persistent behavioral learning across sessions without polluting the prompt context. Captures user corrections and self-assessed tool failures, compiles them into imperative `RULE` directives, and injects them only at the specific decision points where they apply.

## Contract
1. **Behavioral Signal Extraction:**
   - On human correction (e.g., "don't use sudo", "always use English", "compile with -O3"): extract the invariant constraint.
   - Formulate as a compact `RULE: WHEN <decision_point> DO <action> INSTEAD_OF <avoid>`.
2. **Point-of-Decision Injection:**
   - Rather than loading all rules into global memory (~10x token bloat), inject the relevant `RULE` directly into the subagent/tool prompt only when the matching tool or domain is invoked.
3. **Agency Output Compaction:**
   - Compact verbose tool outputs (strip repetitive test headers, package manager logs, empty lines) before passing back to context, saving up to 35% tokens per turn.

## Measurement Log
| Date | Variant | Evidence / Notes | Decision |
|---|---|---|---|
| 2026-11-10 | v1 | 95% compliance (vs 55% naive retrieval) with ~10x fewer tokens injected | active |