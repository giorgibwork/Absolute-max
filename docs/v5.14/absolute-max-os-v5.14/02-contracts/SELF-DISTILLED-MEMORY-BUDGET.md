# Self-Distilled Memory Budget (arXiv:2611.26361)

**Status:** Implemented 2026-11-20 | Free / prompt-only  
**Source:** Jayaram et al., “How Much Should an Agent Remember? Deployment Lessons from Self-Distilled Memory for LLM Agents”

## Central finding

**The right amount of memory is a property of the model, not of the memory system.**

- Strong models continue to gain as more guidelines are added.
- Weaker models often peak with a *selected subset*; the full set can dilute or introduce backfires.

## Pipeline (open-source altk-evolve style)

1. Mine **lessons** (1–3 short, concrete items) from each trajectory / episode.
2. Consolidate lessons into **guidelines**; each guideline records support count (how many lessons it absorbed).
3. At inference, serve either:
   - full guideline set, or
   - model-conditioned selected subset (support + recency + non-regression filter).
4. Track provenance; never silently drop source during consolidation.

## Absolute Max operational rules

- **Budget gate before load**: estimate model strength (or use host fidelity class). Strong → allow larger set; weak / cost-constrained → select top-k by support + recent success.
- **Backfire monitor**: any high-support guideline that correlates with regression is demoted or rewritten (aligns with Soft-HURT / FGSE).
- **Provenance mandatory**: every guideline carries evidence_refs; consolidation that drops provenance is rejected.
- **Cost vs accuracy trade-off is measured**, not assumed. Record delta in CURRENT-BASELINE or Meta-Skill when a budget policy is adopted.

## Integration

- Complements ARISE (ARISE produces the evolving content; this contract decides *how much* to inject).
- Complements BRIDGE (minimal notes) and SoMem/LEDGER (structured stores) by adding a selection / sizing policy.
- HarnessMM: selected guidelines become the guarded reusable set; excess stays in cold storage.

## Practical defaults (until measured)

| Host / model class | Default guideline budget |
|--------------------|--------------------------|
| High-fidelity (Claude-class, strong Grok/Gemini) | Full accepted set |
| Medium / cost-sensitive | Top ~25–40 by support + non-regression |
| Weak / experimental | Top ~15–30; aggressive backfire demotion |

Always re-measure after model change.
