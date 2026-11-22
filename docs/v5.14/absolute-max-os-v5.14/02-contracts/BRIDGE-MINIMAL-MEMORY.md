# BRIDGE — Minimal Agentic Memory (RAG in a Trenchcoat)

**Source:** RAG in a Trenchcoat: When Minimal Memory Is Enough for Agentic Systems, and When It Isn't (arXiv:2611.22179, 17 Nov 2026). NeurIPS 2026.

**Status:** Free-only default memory substrate for Absolute Max when full SoMem / LEDGER / DISCERN overhead is not justified. Complements TAME, SoMem, evidence-linked memory.

## Core Claim
Most extraction / supersession / reflection / graph synthesis primitives do **not** earn their cost on standard memory benchmarks. A deliberately minimal design reaches parity (or better) at far lower token cost.

## BRIDGE Design (copyable)
1. **Chained observation notes** — append-only short notes linked by sequence; no forced entity merge at write.
2. **Hybrid retrieval** — BM25 + cosine over the note store.
3. **Chronological rendering** — present retrieved notes in time order to the reader.
4. **Single LLM call** per ingestion or query.
5. **Token budget** — target ~5–7K reader-prompt tokens per query.

## When to Prefer BRIDGE
- Baseline free path, low host capability, or cost-sensitive runs.
- Pattern-induction / procedural recall tasks (paper: block-summary style wins here).
- When you need a working memory store today without standing up graph or bi-temporal infrastructure.

## When NOT to Prefer BRIDGE Alone
- Strict rule-application that benefits from atomic fact extractors (paper: LangMem-style wins rule application).
- High-stakes entity resolution / abstention under confusable names → prefer DISCERN (preserve-at-write, resolve-at-read).
- Auditable deletion / provenance under change → prefer LEDGER.
- Self-organized topic documents with agent-driven grouping → prefer SoMem.

## Evaluation Shift (mandatory for our stack)
Standard benchmarks score **what memory retrieves**. Agentic value is **what memory enables the agent to do**. Use adversarial probes that can only be solved by applying a remembered rule/pattern the query never mentions. Cross-vendor verification chain preferred.

## Integration
- Default free memory fallback under TAME when richer modules are offline or over-budget.
- Pair with origin-bind + three-valued evidence: BRIDGE notes are EXTERNAL or TOOL until verified.
- Retain raw conversation / observation as retrievable evidence (MAPE pattern); do not discard form of demonstrated patterns.
- Compose retrieved evidence according to query intent before the final reader call.
- BAVAR budgets still apply; do not let minimal memory become unbounded context.

## Implementation Notes (host-agnostic)
- Store: local markdown or JSONL append + simple index (BM25 library or host search).
- No training required. Single-call ingestion: summarize observation into chained note + link.
- Reader prompt: chronological block of hits + explicit instruction to apply any rule/pattern present.
