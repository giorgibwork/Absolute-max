# ActiveSec / Compositional Security for Agentic Harnesses

**Source:** From Attack Surface to Defense Architecture: Compositional Security for Agentic Coding Harnesses (arXiv:2611.13960, 10 Nov 2026). ActiveSecHarness reference architecture.

**Status:** Protocol for Absolute Max OS coding/tool harness security. Free-only. Complements fail-closed policy, capability rings, Shadow Invocation Guard, MCPShield notes.

## Core Claim
Security in agentic systems is a **structural property of cognitive architecture and permission composition**, not an emergent property of the model. Coding harnesses that couple LLMs to shells, filesystems, and network become Living-off-the-Land platforms once instructions are injected. Regex blacklists miss structural evasions; pure LLM judges are slow and over-block.

## Architecture Principles
1. **Separation of Intelligence and Authority** — model proposes; authority rings decide.
2. **Capability tokens** (Macaroon-style HMAC) across Trust and Authority Rings; attenuation, not ambient authority.
3. **2D product taint lattice** $\mathcal{L} = \mathcal{L}_{\mathrm{trust}} \times \mathcal{L}_{\mathrm{sens}}$ + workspace provenance ledger — prevent secret laundering across disk and tool outputs.
4. **Deterministic Ring-0 OS/tool guards** — microsecond path for hard denies; do not rely on LLM judge for the critical path.
5. **Bytecode certificates, split-horizon audit, self-healing security tests, adaptive user policy wiki** as supporting layers.

## Integration
- Map Absolute Max capability rings (T0–T3) and default-dark tool classes onto Ring model.
- Ring-0 guards before SHELL / NET / sensitive file writes; LLM path only for soft advice.
- Provenance ledger pairs with LEDGER / origin-bound memory and PCM-style evidence.
- Fail-closed remains law: unknown capability = DENY.

## Effect Size Notes
N=252 fixtures (attack/benign/kill chains): live LLM judge refused 98.3% of *benign* work at ~142 ms; Ring-0 achieved ABR=1.000, FPR=0.000 at ~12.7 µs (~11,200× faster).

## Fail-closed
No Ring-0 deterministic guard for a high-authority action → do not execute via model-only judgment. Taint / provenance gap on sensitive data → treat as elevated risk; contain or escalate.
