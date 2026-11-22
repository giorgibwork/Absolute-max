# P-DECISIONRAG-NAVIGATOR-v1

**Status:** active  
**Date:** 2026-11-10  
**Evidence base:** DecisionRAG (arXiv:2610.35868) + STAIR-MAX (arXiv:2609.03874)

## Role
Perform zero-hallucination, retriever-free document and repository navigation by walking hierarchical trees (ToC / file directories) using shared-context binary branch decisions, eliminating vector database overhead and false chunk retrievals.

## Contract
1. **Tree Construction:** Extract or induce a clean hierarchical Table of Contents (ToC) or directory tree.
2. **Shared-Context Decision:**
   - At each level, present the query alongside all sibling node summaries within a single prompt context.
   - Instruct the model to emit only the exact IDs/titles of valid branches to expand.
3. **Irreversible Pruning:** Unselected branches are permanently pruned from subsequent steps.
4. **Leaf Verification:**
   - Selected leaf addresses (`Chapter > Section > Leaf` or `dir/subdir/file.ts`) are validated against the known trie.
   - Any hallucinated or non-existent section path results in an immediate retry or hard failure.

## Location in Stack
- Invoked by `Arkon-Hyperresearch` on large documents or codebases.
- Integrated into `02-skills/structure-aware-retrieval/`.

## Measurement Log
| Date | Variant | Evidence / Notes | Decision |
|---|---|---|---|
| 2026-11-10 | v1 | +13.8 R@1 on MultiDoc2Dial, +17.4 Hit@1 on NQ over dense + 8B reranker | active |