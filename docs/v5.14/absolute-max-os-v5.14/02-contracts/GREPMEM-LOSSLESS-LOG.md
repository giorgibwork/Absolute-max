# GrepMem — Lossless Index-Free Memory (arXiv:2611.25123)

**Status:** Implemented 2026-11-22 | Free / tool + prompt-only  
**Source:** Yang, Shi, Zhao — “Forget Freely, Grep Later: Lossless, Index-Free Memory for Long-Horizon LLM Agents”

## Core idea

Keep an **append-only plain-text log** of the complete interaction history (messages, tool calls, outputs, summaries).  
After the first compaction, expose a single `grep_history` tool that performs case-insensitive regular-expression search over the log.  

No embeddings, no retrieval index, no extra model, no lossy extraction. Exact details remain available on demand.

## Why it compounds

- Summarization decides *what to keep before the future question is known* → lossy.  
- GrepMem keeps everything; the agent decides *what to retrieve when the need is known*.  
- Measured: 95–97% on ContextBench exact-recall tasks vs ≤21% for lossy baselines; +8.8 pp on BCP-Multi vs SUPO; stays on accuracy–token-cost Pareto frontier.  
- Complements structured memory (SoMem, ARISE, LEDGER): use GrepMem as the immutable ground-truth substrate; use structured layers for semantic/procedural guidance.

## Operational protocol (prompt + tool)

1. **Log every turn** — append raw message / tool call / tool result / summary to a plain-text history file with clear headers (`[turn N role ...]`).  
2. **Compact normally** when context approaches limit; append the summary to the log.  
3. **Enable grep_history** after first compaction.  
4. **Tool contract**:
   - Input: regex pattern, optional context_lines (default 1, max 3), optional page/offset.  
   - Output: matching lines (oldest first), grouped by source record, with limited context; paginated; capped size.  
   - Skip prior grep results in the log to avoid recursion.  
5. **Agent policy**: use grep when exact values, IDs, prior tool outputs, or precise quotes are needed; do not rely on summary alone for critical facts.  
6. **Fallback**: if regex fails to surface needed detail, fall back to broader pattern or request human/tool clarification — never invent.

## Integration points

- **TAME / origin-bind**: log writes are TOOL or USER origin; never promote log content to SYSTEM rules without three-valued verification.  
- **SoMem / DISCERN**: Source store can be the GrepMem log; Topic files cite block IDs that resolve via grep.  
- **ARISE / Self-Distilled**: micro-lessons and guidelines may reference log locations; grep recovers the original evidence.  
- **State-Transfer Audit**: the append-only log itself is a natural audit chain.  
- **Cost**: pure text + ripgrep-style search is cheap; prefer over embedding indexes for exact-recall heavy workloads.

## When to prefer GrepMem

- Long-horizon sessions with exact key-value, log triage, or prior-tool-output needs.  
- Environments where embedding indexes are unavailable, costly, or untrusted.  
- As the lossless baseline underneath any higher-level structured memory.

## Limitations (explicit)

- Retrieval quality depends on the agent generating a matching regex.  
- No semantic similarity; paraphrase requires broader patterns or hybrid with embedding retrieval.  
- Best evidence is on exact-recall benchmarks; semantic/multi-hop may still benefit from structured layers.

## Non-regression

Do not disable existing structured memory. GrepMem is additive substrate. Measure exact-recall lift on held-out probes before promoting to default path.
