# HEAMS — Holistic Evaluation of Agent Memory Systems

**Source:** Goel et al., HEAMS: Holistic Evaluation of Agent Memory Systems (arXiv:2611.20144, 15 Nov 2026). Open-source framework.

**Status:** Protocol for Absolute Max OS memory evaluation and governance. Free-only. Complements CoReMem, DISCERN, AGENT-MEMORY-GUARD, SoMem, and origin-bound memory.

## Core Claim
Memory systems are custodians of persistent user information. Evaluating only task performance and efficiency hides trade-offs in privacy, user sovereignty, and security. Strong performance can coexist with poor privacy/sovereignty/security scores. Governance (recall and retention policies) strongly influences results.

## Five Dimensions (report side-by-side, do not aggregate)
1. **Performance** — recall, update, long-horizon task improvement.
2. **Efficiency** — latency, tokens, storage cost (measured alongside every benchmark).
3. **Security** — resistance to poisoning / adversarial influence on later behavior.
4. **Privacy** — disclosure only in appropriate contexts.
5. **User Sovereignty** — inspect, correct, delete, retention limits honored.

## Protocol Sketch
- Treat memory system as having its own responsibilities independent of querying agents (agents are untrusted).
- Use common interface for controlled comparison (retain / recall / delete / consolidate configurable).
- Governance layer (retention + recall policies) can wrap any store; both improve poisoning resistance; recall policies trade helpfulness for reduced inappropriate disclosure.
- Prefer purpose-built scenarios for each desideratum (deletion tests need deletion requests; poisoning tests need planted content).
- Document architectural properties (portability, control surfaces, hosting) via AMS-style card alongside quantitative results.

## Integration
- Apply before promoting a memory configuration or MCP memory server as preferred.
- Aligns with AGENT-MEMORY-GUARD (write-time screening) and SMSR.
- CoReMem prospective anchors can be evaluated under HEAMS dimensions (next-task value vs cost, privacy of anchors).
- DISCERN resolve-at-read can incorporate sovereignty checks (user-requested forget / correct).
- For Absolute Max ranking of free memory MCPs: require at least partial coverage across the five dimensions; do not rank on performance alone.

## Effect Size Notes
No memory system leads every performance benchmark. Governance strongly influences: recall policies reduce inappropriate disclosure (at helpfulness cost); both recall and retention policies improve poisoning resistance.

## Fail-closed
No evidence on privacy/sovereignty/security dimensions → do not claim a memory system is “best” or promote for high-sensitivity use. Poisoning resistance unmeasured → treat as high risk for persistent writes.
