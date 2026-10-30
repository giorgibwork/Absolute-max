# Future Patches Log

(Empty at creation. Every self-evolution hook and user-proposed improvement is recorded here.)

## Template
### YYYY-MM-DD — Title
- Observed failure / opportunity:
- Proposed change:
- Expected axis lift:
- Evidence:
- Status: implemented 2026-10-29

### 2026-10-29 — Live Stack Improver Run

#### 1. Recursive Self-Pruning Memory (RSPM)
- Observed failure / opportunity: Long-horizon runs accumulate failures and stale facts that the agent then repeats. Current TTME + trust scoring still keeps too much raw history.
- Proposed change: Add a “sleep” phase after every full or dissertation research run. Cluster recent failures → distill short rules → delete raw episodes. Promote recurring rules. Target ~30% store reduction and fewer retry loops.
- Expected axis lift: Compounding +1, Usability +1, Adversarial +0.5
- Evidence: arXiv 2610.25561 (Oct 18) — +7.6 to +11.9 points across three very different settings; ~93% fewer retry loops.
- Status: implemented 2026-10-29
- Implementation target: arkon-hyperresearch Phase 11 (TTME) + new “Phase 11.5 Sleep”

#### 2. Bayesian Memory Value / BEAM-style belief update
- Observed failure / opportunity: Memory value is currently static or simple trust score. Real value is context-dependent and should be updated from execution feedback.
- Proposed change: Treat each memory item as a belief that is re-calibrated after every use with success/failure evidence. Low-belief items decay faster.
- Expected axis lift: Compounding +1, Specificity +0.5
- Evidence: arXiv 2610.25119 (Oct 18) — Memory as Belief.
- Status: implemented 2026-10-29
- Implementation target: trust-aware Evaluator role inside TTME / TAME module

#### 3. Formal integrity theorems for memory (PerMIT-style)
- Observed failure / opportunity: We have a formal verification gate for math claims but not for the memory itself. Untrusted environment data can still poison the vault.
- Proposed change: Add a lightweight “gate confirmation” step before any environment-derived value is written to high-trust memory. Prefer Lean-checkable invariants where feasible.
- Expected axis lift: Adversarial +1.5, Compounding +0.5
- Evidence: arXiv 2610.28987 (Oct 20) — machine-checked integrity theorems, zero observed attack success on Trojan Hippo.
- Status: implemented 2026-10-29
- Implementation target: arkon-hyperresearch memory write path + formal gate extension

#### 4. High-value MCP Memory servers (production shortlist)
- Observed failure / opportunity: Current memory is file + Arkon Vault. Stronger external MCP memory options now exist with drift detection, temporal graphs, and multi-agent shared memory.
- Proposed change: Evaluate and optionally integrate (or pattern-match) the best of:
  - Official Knowledge Graph Memory Server
  - Graphiti / Zep (temporal)
  - Linksee Memory (drift detection)
  - Memclaw / SPM (governed multi-agent)
- Expected axis lift: Compounding +1, Usability +0.5
- Evidence: Multiple 2026 MCP catalogs + production guides (Coworker, Zenrows, Frontier Wire, MCP Observatory).
- Status: implemented 2026-10-29
- Implementation target: new optional MCP layer documented in 03-transfer + absolute-max

#### 5. Sequential Thinking + Memory reference MCP servers
- Observed failure / opportunity: Official MCP servers now include Sequential Thinking and a solid Memory server (v2.x, Oct 28 release). These are free, maintained, and directly complementary.
- Proposed change: Document how to run the official @modelcontextprotocol/server-memory and server-sequential-thinking alongside Absolute Max for local / Claude / Cursor deployments.
- Expected axis lift: Usability +1, Compounding +0.5
- Evidence: modelcontextprotocol/servers v2.2.0 (28 Oct 2026).
- Status: implemented 2026-10-29
- Implementation target: 03-transfer/TRANSFER-README.md + new short guide

#### 6. Self-pruning + density target already partially covered — reinforce
- Observed failure / opportunity: Literature density target exists but is not yet paired with explicit failure clustering.
- Proposed change: After width sweep, run a lightweight failure-cluster pass on previous runs of the same topic before deciding extra search waves.
- Expected axis lift: Specificity +0.5, Goal compression +0.5
- Evidence: RSPM results + our existing density module.
- Status: implemented 2026-10-29

#### 7. Open deep-research harness patterns (deer-flow, GPT Researcher, multi-agent citation gates)
- Observed failure / opportunity: Strong open systems now gate every report with explicit hallucination + citation validation in a Researcher/Analyst/Critic loop.
- Proposed change: Strengthen our existing critic phase with an explicit “citation validation gate” that must pass before the final report ships (already partially present; make it non-negotiable and logged).
- Expected axis lift: Adversarial +0.5, Specificity +0.5
- Evidence: Multiple high-star open research agents (deer-flow, GPT Researcher lineage, LangGraph multi-agent systems with citation gates).
- Status: implemented 2026-10-29
