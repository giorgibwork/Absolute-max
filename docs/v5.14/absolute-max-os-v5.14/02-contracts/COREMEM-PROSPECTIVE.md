# CoReMem — Cost-Internalizing Prospective Memory

**Source:** Li et al., arXiv:2611.17316 (2026-11-12). CoReMem: Cost-Internalizing Memory for Successive Coding Tasks with Prospective Valuation.

**Status:** Protocol for Absolute Max OS memory selection on successive / repository-style tasks. Free-only, no new weights required for the gate; post-training optional and out of scope.

## Core Claim
On successive tasks over an evolving repository (or any long-horizon shared state), writing and reading memory has measurable cost. Memory should be selected by prospective value on the *next* task, not by local success of the current episode. Anchors (repository locations + executable checks) are higher-leverage than raw trajectory dumps.

## Prospective Valuation
Before committing a trajectory segment to durable memory:
1. Identify candidate anchors: file paths, function names, test commands, or executable checks that appeared useful.
2. Estimate prospective value: on a held-out or next-task proxy, measure resolution / step-count delta with vs without the segment.
3. Internalize cost: write cost + read cost + storage cost must be outweighed by expected future utility (resolve-rate gain or step reduction).

**Keep** only segments whose measured or estimated next-task value exceeds a cost threshold. Prefer compact anchor lists over full histories.

## Actor Adaptation (optional, free)
When using memory:
- Prefer steps that act on memory-supplied anchors (provenance-gated credit).
- Penalize unnecessary steps even on successful runs (cost-internalizing reward shape).
- On conflict or low value, fall back to DISCERN terminal action (Clarify / Abstain) or FGSE reject.

## Integration
- Runs **after** FGSE temporary probes and **before** Evidence-linked / DISCERN commit.
- Composes with RSI Tax (reject expensive unused self-change) and HarnessMM (reuse resolved steps).
- For coding / file-heavy tickets: require at least one executable check anchor if memory is written.
- Missing valuation data → treat as low-trust; prefer ephemeral or ask.

## Defaults (paper-aligned, tunable)
- Prefer anchors over raw segments.
- Target step reduction ≥ 10% or resolve-rate gain ≥ 3 pp on next-task proxy before durable keep.
- Count cache-aware tokens (including memory module calls).

## Effect Size Notes
On ChainSWE, CoReMem raised a 27B actor’s resolve rate from 21.0% to 25.7% with 17% fewer steps and 11% fewer total cache-aware tokens relative to no-memory baseline. Gains come from measured next-task value, not from storing everything.

## Fail-closed
No prospective valuation or no executable anchor on a high-cost write → do not promote to durable memory; keep as ticket-local note.
