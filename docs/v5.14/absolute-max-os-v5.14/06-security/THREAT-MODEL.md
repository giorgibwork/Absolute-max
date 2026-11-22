# Threat Model & Capability Rings — Absolute Max OS v5.3.0

## Assets

- System rules and goals
- Persistent memory integrity
- Credentials / host access
- SPR verification integrity
- User intent continuity

## Threats → mitigations

| Threat | Mitigation |
|--------|------------|
| Memory poisoning / MSMP | pagegram-guard + source_class + SMSR spirit; EXTERNAL_TOOL cannot set rules |
| Prompt injection via tools/web | Origin tags; never promote web_untrusted to system rules |
| False “done” | SPR S=1 with positive + negative probes |
| Privilege creep | Capability rings + domain isolation |
| RSI regression / false evolution | TRUST-hardened gate + Meta-Skill |
| LotL tool abuse | Ring-0 deterministic guards for dangerous ops; model is not authority |
| Stuck but alive workers | Watchdog no-progress detection |
| Token burn without progress | Cost rules + Watchdog |

## Capability rings (map to T0–T3)

| Ring / Tier | Authority | Examples |
|-------------|-----------|----------|
| **Ring 0 / T0** | Deterministic security & verification | spr-verify, pagegram-guard, fail-closed policy |
| **Ring 1 / T1** | Core OS primitives | os-daemon, mem, search, tree-toc, compact-log |
| **Ring 2 / T2** | Host helpers | dsh-anti-kill, UI plugins |
| **Ring 3 / T3** | Domain engines | polymarket, scouts, combat-tweaks |

**Rule:** Intelligence (model) proposes; Authority (Ring 0 / T0) permits. No silent Ring3→Ring1 promotion.

## Incident response

1. Stop promoting new memory  
2. Quarantine recent EXTERNAL_TOOL / web items  
3. Re-run SPR on critical claims  
4. Watchdog-mark stuck tickets  
5. Report what was quarantined

---

## v5.4 extensions

- PREPARE_ONLY absolute for live consequential actions (`PREPARE-ONLY.md`)
- Fail-closed unknown capabilities (`FAIL-CLOSED-POLICY.md`)
- Memory poisoning: prefer SMSR-style provenance + AMG-style write screens (`03-plugins/`)
- Model strength is not a privilege ring upgrade
