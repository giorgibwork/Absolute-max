# STAIR (Structure-Aware Retrieval) — Paper Digest

## Source
SearchTome / Differentiable Search Index (DSI) lineage, constrained ToC decoding.

## Core Mechanism
- Index = model parameters (not an external vector DB).
- Document identifier = real leaf section title (not opaque chunk ID).
- Decoding = trie / constrained generation over valid section titles only → structural hallucination becomes impossible.

## Key Numbers (18 books, 6 domains, SearchTome benchmark)
- STAIR: 82.6% R@1
- DSI: 76.9% R@1
- DPR: 68.7% R@1
- BM25: 59.5% R@1
- Raw Mistral (no structure): 13.8% R@1

## Training Recipe (free-first path)
- Base: Mistral-7B-Instruct-v0.2 or stronger open model
- Adaptation: LoRA / QLoRA, r=16, α=32
- Sequence length: ≥8192 to fit full ToC + query
- Synthetic queries: ≥2 per eligible paragraph, teacher-generated
- Tasks: (1) passage → leaf title (ingestion); (2) (ToC + query) → leaf title (retrieval)
- Inference: constrained decoding via trie → ~0.00% structural hallucination

## Fallback
When training is impossible: in-context prompting of a long-context model with the full ToC + strong instruction. Lower R@1, still beats unstructured chunking.

## Failure Modes
- Structureless corpus → fall back to dense retrieval; do not force STAIR
- Trie not enforced → model emits non-existent titles → hard-constrain decoding
- ToC too large → hierarchical routing (chapter → section) or compress ToC
- Domain shift → few-shot adaptation or retrain LoRA

## Integration with Absolute Max
- Hyperresearch/Arkon: extract ToC → STAIR retrieval → feed only retrieved spans into multi-phase pipeline
- Eye of God: rank retrieval designs by effect size; STAIR dominates length-chunk on structured corpora
- ADHD: surface next concrete action first (extract ToC → build trie → fine-tune or prompt)
