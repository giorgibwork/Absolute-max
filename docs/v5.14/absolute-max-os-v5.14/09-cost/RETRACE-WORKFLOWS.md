# ReTrace-Style Workflows — v5.5 (arXiv:2611.14492)

Extends HarnessMM-lite: named workflows from repeated successful runs.

1. After ≥2 similar successes, propose workflow (steps + guards + tool_class + success).
2. Land only via RSI dual gate.
3. When guards match, checklist/code advances — model only on mismatch.
4. Store in Meta-Skill or host-local workflow dir.
