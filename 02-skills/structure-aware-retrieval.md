---
name: structure-aware-retrieval
description: Structure-aware generative retrieval that uses document Table of Contents (ToC) as the index inside LLM parameters instead of length-based chunks. Use for long-document RAG, ToC-based retrieval, zero-hallucination section lookup, SearchTome-style benchmarks, Differentiable Search Index (DSI) with structure, hierarchical document navigation, enterprise help pages, textbooks, technical reports, or any corpus with clear global structure. Triggers include STAIR, structure-aware retrieval, ToC retrieval, section-title retrieval, zero-hallucination retriever, document structure augmentation, hierarchical RAG.
---

# Structure-Aware Retrieval (STAIR-maximized)

Turn any structured long document or corpus into a generative index that lives inside the LLM. The model receives the full Table of Contents + query and is constrained to emit only a real leaf section title. Hallucination of non-existent sections becomes structurally impossible.

## Core Insight (non-negotiable)

Length-based chunking destroys the semantic global structure that humans actually use. STAIR restores it:
- Index = model parameters (DSI lineage)
- Document identifier = real ToC leaf title (not an opaque chunk ID)
- Decoding = trie / constrained generation over the valid section titles only
- Result = section name that answers the query, with <0.05% (often 0.00%) invalid outputs

Paper baseline (SearchTome, 18 books, 6 domains): STAIR 82.6% R@1 vs DSI 76.9% vs DPR 68.7% vs BM25 59.5% vs raw Mistral 13.8%.

## When to Activate

Activate immediately on any request involving:
- Long documents, books, manuals, technical reports, enterprise help, product docs, legal codes, textbooks
- RAG systems that currently suffer from “lost in the middle” or incoherent chunks
- Need for explainable retrieval (user sees real section titles)
- Zero-hallucination retrieval requirement
- Few-shot or low-data regimes for new documents
- Building or evaluating hierarchical retrieval systems

Do not activate for flat, structureless corpora (raw chat logs, unstructured web scrapes) unless a ToC can be induced first.

## Mandatory Pipeline (execute in order)

### Phase 0 — Structure Extraction
1. Obtain or induce a clean hierarchical Table of Contents.
2. Map every leaf title to its full text span.
3. Build a trie (or prefix tree) over all valid leaf titles. This is the hard constraint.
4. Store the ToC + leaf→text mapping as the permanent index artifact.

### Phase 1 — Training / Adaptation Data
Two complementary tasks (paper design):
- Ingestion: passage → its gold leaf title
- Retrieval: (ToC + query) → gold leaf title

Generate synthetic queries with a strong teacher (Mixtral-class or better) conditioned on each paragraph. Prefer 2+ questions per eligible paragraph.

### Phase 2 — Model Adaptation
Preferred path (highest leverage, free-first):
- Start from Mistral-7B-Instruct-v0.2 or stronger open model
- LoRA / QLoRA (r=16, α=32 is sufficient)
- Max sequence length that fits the full ToC + query (8192+ preferred)
- Train until the model reliably maps (ToC, q) → exact leaf title
- At inference force constrained decoding through the trie → 0.00% structural hallucination

Fallback when training is impossible: pure in-context prompting of a long-context model with the full ToC + strong instruction. Expect lower R@1 but still better than unstructured baselines.

### Phase 3 — Inference Contract
Input template (exact):
```
[System / Instruction]
You are a structure-aware retriever. Given the complete Table of Contents and a user query, output ONLY the single most relevant leaf section title that exists in the ToC. Never invent titles.

[Table of Contents]
{full hierarchical ToC}

[Query]
{user question}
```

Decode with trie constraint. Return the section title. Optionally expand to the full text span of that leaf for the downstream generator.

### Phase 4 — Evaluation Protocol
Always report:
- Recall@1, Recall@3, nDCG@3 on held-out queries
- Structural hallucination rate (non-leaf or invented titles)
- Ablation: with-ToC vs without-ToC (DSI baseline)
- Statistical significance vs strongest baseline

Use SearchTome or a SearchTome-style split (train/dev/test per book) when possible.

## Integration with Existing Project Skills

- **hyperresearch / arkon-hyperresearch**: When the user asks for deep research on a structured corpus, first extract ToC, run structure-aware retrieval to surface the precise sections, then feed only those sections into the multi-phase research pipeline. This collapses context and eliminates lost-in-the-middle noise.
- **absolute-max / eye-of-god**: Rank any retrieval design by real-world effect size. STAIR-style constrained ToC retrieval dominates length-chunk + vector DB on structured documents. Prefer it unless the corpus is proven structureless.
- **i-have-adhd**: When activated, surface the next concrete action (extract ToC → build trie → fine-tune or prompt) as the first line.

## Failure Modes & Detection

| Failure | Signature | Mitigation |
|---------|-----------|------------|
| Structureless corpus | No reliable ToC can be induced | Fall back to classic dense retrieval; do not force STAIR |
| Trie not enforced | Model emits non-existent titles | Hard-constrain decoding; never soft-prompt only |
| ToC too large for context | Full ToC exceeds model window | Hierarchical routing (first chapter, then section) or compress ToC |
| Domain shift | New book with different writing style | Few-shot adaptation or retrain LoRA on new ToC |
| Over-confident leaf | Correct title but wrong granularity | Add parent path in output or multi-level ranking |

## Permanent Assets to Maintain

- `references/stair-paper-digest.md` — distilled mechanisms, numbers, ablations
- `references/searchtome-construction.md` — how to rebuild or extend the benchmark
- `scripts/build_toc_trie.py` — deterministic trie construction from any hierarchical ToC
- `scripts/constrained_decode.py` — example constrained generation wrapper
- Any new corpus ToC + leaf mapping becomes a reusable index artifact

## Execution Rule

On every activation:
1. State the exact corpus and whether a clean ToC exists.
2. Choose the highest-leverage path (full LoRA vs in-context) given compute constraints.
3. Produce a measurable R@1 / hallucination rate or a concrete next experiment.
4. Leave at least one permanent artifact (ToC, trie, eval numbers, or improved prompt) in the project.

Never return generic “use RAG” advice. Structure is the differentiator. Enforce it.
