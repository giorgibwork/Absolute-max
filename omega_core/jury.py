"""Pure Gemini + Antigravity Parallel Asymmetric Jury + Dual-Pool Spillover Engine.

Maximizes Gemini capability by splitting adversarial roles across 3 distinct Gemini
architectures and both independent Antigravity Gemini quota pools, with Builder &
Hostile Prosecutor executing IN PARALLEL (cutting wall-clock latency ~50%):
- Builder (`gemini-4-neon-xhigh`, gemini_models pool): synthesizes strongest mechanism
  from primary + Chinese + English evidence.
- Hostile Prosecutor (`gemini-4-argon-high`, gemini_argon pool): receives ONLY bug
  reports, GitHub issues, HN critiques, and failure evidence to red-team without
  confirmation bias.
- Evidence Judge (`gemini-4-hydrogen-xhigh` / `gemini-pro-orchestrator-neon`):
  reconciles Builder vs Prosecutor strictly on fetched evidence, tags [ALPHA / NON-CONSENSUS]
  insights, preserves unresolved conflicts, and enforces `non_consensus_gate.py`.
"""
from __future__ import annotations

import concurrent.futures
import os
import subprocess
import time
from typing import Any

from . import OmegaPaths, get_paths
from .fabric import IntelligenceFabric
from .obsidian import DEFAULT_VAULT_DIR, ObsidianSync


class AsymmetricJury:
    def __init__(self, paths: OmegaPaths | None = None, fabric: IntelligenceFabric | None = None):
        self.paths = paths or get_paths()
        self.fabric = fabric or IntelligenceFabric(self.paths)
        self.tools_dir = os.path.expanduser("~/tools")

    def deliberate(
        self,
        question: str,
        *,
        positive_evidence: str,
        hostile_evidence: str,
        builder_model: str = "gemini-4-neon-xhigh",
        prosecutor_model: str = "gemini-4-argon-high",
        judge_model: str = "gemini-4-hydrogen-xhigh",
        timeout_s: int = 45,
        export_obsidian: bool = False,
        vault_dir: str = DEFAULT_VAULT_DIR,
    ) -> dict[str, Any]:
        """Run a parallel Gemini cross-pool asymmetric deliberation grounded strictly in retrieved evidence."""
        t0 = time.monotonic()
        today = time.strftime("%Y-%m-%d")

        b_prompt = (
            f"Today is {today}. Role: PRIMARY BUILDER.\n"
            f"Question: {question}\n\n"
            f"PRIMARY & CHINESE/GITHUB EVIDENCE:\n{positive_evidence[:6000]}\n\n"
            "Synthesize the highest-leverage, non-obvious mechanisms strictly backed by the evidence above. "
            "Include inline URLs/locators. Max 8 sharp bullets. Do NOT invent unsupported stats."
        )
        p_prompt = (
            f"Today is {today}. Role: HOSTILE PROSECUTOR (RED-TEAM).\n"
            f"Question: {question}\n\n"
            f"FAILURE, ISSUE & CRITIQUE EVIDENCE:\n{(hostile_evidence or positive_evidence)[:6000]}\n\n"
            "Expose every hidden trap, rate limit, regression, maintenance decay, or contradiction shown in the evidence. "
            "Cite exact URLs/locators. Max 8 sharp bullets. Zero generic filler."
        )

        def _run_builder() -> tuple[str, dict[str, Any]]:
            res = self.fabric.invoker(builder_model, b_prompt, timeout_s)
            if not res.get("ok"):
                return "gemini-4-neon-high", self.fabric.invoker("gemini-4-neon-high", b_prompt, timeout_s)
            return builder_model, res

        def _run_prosecutor() -> tuple[str, dict[str, Any]]:
            res = self.fabric.invoker(prosecutor_model, p_prompt, timeout_s)
            if not res.get("ok"):
                return "gemini-pro-orchestrator-g1-pro", self.fabric.invoker("gemini-pro-orchestrator-g1-pro", p_prompt, timeout_s)
            return prosecutor_model, res

        # Run Builder & Hostile Prosecutor in parallel across independent Gemini quota pools
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fb = ex.submit(_run_builder)
            fp = ex.submit(_run_prosecutor)
            builder_used, b_res = fb.result()
            prosecutor_used, p_res = fp.result()

        j_prompt = (
            f"Today is {today}. Role: INDEPENDENT EVIDENCE JUDGE (3rd Gemini architecture).\n"
            f"Question: {question}\n\n"
            f"=== BUILDER ({builder_used}) ===\n{b_res.get('text', '')[:3500]}\n\n"
            f"=== HOSTILE PROSECUTOR ({prosecutor_used}) ===\n{p_res.get('text', '')[:3500]}\n\n"
            "Reconcile strictly on evidence. Compress obvious mainstream advice to 1 line; expand ONLY verified "
            "[ALPHA / NON-CONSENSUS] insights with exact URLs/locators. Preserve unresolved contradictions.\n"
            "Output plain-English mobile-safe vertical bullets starting with `NEXT:` and these EXACT headings:\n"
            "## Evidence\n## Contrarian / Non-Consensus Point\n## Falsification Check\n## UNVERIFIED\n"
        )
        j_res = self.fabric.invoker(judge_model, j_prompt, timeout_s)
        if not j_res.get("ok"):
            j_res = self.fabric.invoker("gemini-pro-orchestrator-neon", j_prompt, timeout_s)
            judge_used = "gemini-pro-orchestrator-neon"
        else:
            judge_used = judge_model

        final_md = (j_res.get("text") or "").strip()

        gate_passed = None
        gate_py = os.path.join(self.tools_dir, "non_consensus_gate.py")
        if final_md and os.path.exists(gate_py):
            tmp_md = os.path.join(self.paths.tmpdir, f"omega_jury_{int(time.time())}.md")
            try:
                with open(tmp_md, "w", encoding="utf-8") as f:
                    f.write(final_md + "\n")
                gr = subprocess.run(["python3", gate_py, tmp_md], capture_output=True, text=True, timeout=10)
                gate_passed = gr.returncode == 0
            finally:
                if os.path.exists(tmp_md):
                    os.remove(tmp_md)

        dossier_path = ""
        if export_obsidian and final_md:
            obs = ObsidianSync(vault_dir=vault_dir, paths=self.paths)
            dossier_path = obs.export_dossier(
                question[:80],
                final_md,
                tags=["jury", "non-consensus"],
                links=[f"Model-{builder_used}", f"Model-{prosecutor_used}", f"Model-{judge_used}"],
            )

        return {
            "ok": bool(j_res.get("ok") and final_md),
            "builder_model": builder_used,
            "prosecutor_model": prosecutor_used,
            "judge_model": judge_used,
            "non_consensus_gate_passed": gate_passed,
            "dossier_path": dossier_path,
            "total_ms": round((time.monotonic() - t0) * 1000.0, 1),
            "report": final_md,
        }
