# SearchTome Benchmark — Construction Notes

## Composition
- 18 books across 6 domains
- Hierarchical ToC per book
- Train/dev/test splits per book (no cross-book leakage)

## Evaluation Protocol
- Recall@1, Recall@3, nDCG@3 on held-out queries
- Structural hallucination rate: fraction of outputs that are not a real leaf title
- Ablation: with-ToC (STAIR) vs without-ToC (DSI baseline)
- Statistical significance vs strongest baseline (paired bootstrap, p<0.01)

## Rebuilding for a New Corpus
1. Obtain or induce a clean hierarchical ToC.
2. Map each leaf title to its full text span.
3. Generate synthetic queries (≥2 per paragraph) using a strong teacher model.
4. Split per-document into train/dev/test (80/10/10).
5. Build trie over leaf titles (see scripts/build_toc_trie.py).
6. Fine-tune with LoRA (r=16, α=32) on ingestion + retrieval tasks.
7. Evaluate with trie-constrained decoding.
8. Report R@1, R@3, nDCG@3, hallucination rate, and ablations.

## Extending to Multi-Level
- If ToC is very large (>10k leaves), use hierarchical routing:
  1. Route to chapter first (coarse trie).
  2. Then route to section within that chapter (fine trie).
- Parent path can be included in the output to disambiguate same-titled sections.
