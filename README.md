# Absolute Max

Persistent agent configuration: **Absolute Max OS v2** — master instructions, the MRIP v3 recursive improvement protocol, and five specialized skills. Installed from `absolute-max-os-v2-1.zip` and active in this workspace.

## What is active

| Layer | File | Status |
|---|---|---|
| Master instructions | `AGENTS.md` | Always loaded (root) |
| GitHub Copilot mirror | `.github/copilot-instructions.md` | Byte-identical |
| Recursive improvement protocol | `absolute-max-os-v2/01-core/MRIP_v3.md` | Always loaded |
| Orchestrator skill | `absolute-max-os-v2/01-core/absolute-max.md` | Always loaded |
| Research engines | `02-skills/arkon-hyperresearch.md`, `02-skills/hyperresearch.md` | On research/deep/audit/maximize |
| Retrieval | `02-skills/structure-aware-retrieval.md` | On hierarchical documents |
| Optimization | `02-skills/eye-of-god.md` | On "absolute best free" requests |
| Output shape | `02-skills/i-have-adhd.md` | On until "stop adhd mode" |

## Operating contract

- Every response ends with five blocks: `Deliverable`, `State Delta`, `Score Vector`, `Compounding Asset Added`, `Next Iteration Hook`.
- Any of the six scored axes at or below 7 forces a revision before release.
- At least one permanent, reusable artifact per turn. Plateau is treated as failure.
- Every major claim needs verified source support; hallucinated citations are a hard failure.
- Free and open tools and sources first.

## Activation phrases

`absolute max` · `maximize this` · `hyperresearch` · `arkon-hyperresearch` · `full pipeline` · `deep research` · `adversarial audit` · `eye of god` · `Arena agent`

## Repository layout

```
AGENTS.md                        master config (load first)
.github/copilot-instructions.md  mirror for Copilot
absolute-max-os-v2/
├── README.md                    package guide
├── 00-LOAD-ME-FIRST.txt         load order
├── AGENTS.md                    mirror of root master
├── 01-core/                     AGENTS.md, MRIP_v3.md, absolute-max.md
├── 02-skills/                   five skills
├── 03-transfer/                 portable builds for other platforms
├── 04-docs/                     free space for durable artifacts
└── 05-improvement/              baseline scores + patch log
absolute-max-os-v2-1.zip         original install source
```

## Changing the configuration

1. Edit `absolute-max-os-v2/AGENTS.md`.
2. Copy it over `AGENTS.md`, `absolute-max-os-v2/01-core/AGENTS.md`, and `.github/copilot-instructions.md`.
3. Log the change in `absolute-max-os-v2/05-improvement/FUTURE-PATCHES.md` and re-score `CURRENT-BASELINE.md`.

The four `AGENTS.md` files must stay byte-identical; verify with `md5sum AGENTS.md absolute-max-os-v2/AGENTS.md absolute-max-os-v2/01-core/AGENTS.md .github/copilot-instructions.md`.
