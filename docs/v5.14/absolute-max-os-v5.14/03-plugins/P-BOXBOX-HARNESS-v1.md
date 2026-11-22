# P-BOXBOX-HARNESS-v1

**Status:** active  
**Date:** 2026-11-10  
**Evidence base:** BOXBOX (arXiv:2611.09218) + Meta² (arXiv:2611.05139)

## Role
Enable online, test-gated runtime self-tooling and meta-knowledge caching during long-horizon tasks. When the agent detects repetitive shell pipelines or missing environment primitives, it synthesizes, tests, and caches a local helper utility to collapse multi-turn shell loops into single-shot binary executions.

## Contract
1. **Trigger Condition:** Repetitive shell commands or data munging exceeding 3 similar iterations within a single session.
2. **Tool Synthesis:**
   - Synthesize a deterministic, standalone Python or shell script in `/root/workspace/.bin/` or project scripts directory.
   - Include clear CLI arguments and exit codes.
3. **Sandbox Test Gate:**
   - Execute the synthesized tool on a synthetic sample or isolated test input.
   - Must return exit code 0 and correct output format before being adopted.
4. **Meta-Knowledge Registration:**
   - Record the tool in the local tool registry with metadata: trigger pattern, argument schema, and failure archetype.
5. **Execution Replacement:** Subsequent iterations invoke the compiled tool directly, avoiding repeated multi-step code generation.

## Location in Stack
- Sits alongside `06-plugins/builders/NEW-PLUGIN-BUILDER.md`.
- Callable by Worker agents during complex repository operations.

## Measurement Log
| Date | Variant | Evidence / Notes | Decision |
|---|---|---|---|
| 2026-11-10 | v1 | +22.4% task completion on long-horizon system admin/repo migrations | active |