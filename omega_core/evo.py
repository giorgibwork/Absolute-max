"""Evolution Laboratory: SIM + RRSI (#3) + ModularRSI (#4).

Implements governed recursive self-improvement strictly in an isolated
$TMPDIR/omega_lab workspace:
- ModularRSI: 5 distinct harness axes (agent_loop, tool_use, observation_mgmt,
  context_mgmt, completion_detect)
- RRSI: temporally annealed edit budget + pruner rejecting bloated or
  low-ROI patches before promotion
- SIM (Self-Improvement Memory): records rationale, predicted delta, observed
  delta, baseline vs candidate suite score, and decision
- PREPARE_ONLY: never overwrites live OS files; winning candidates emit a
  diff artifact + pending Approval Ticket for the human operator.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from typing import Any, Callable

from . import OmegaPaths, ensure_dirs, get_paths
from .mission import MissionKernel

MODULAR_AXES = (
    "agent_loop",
    "tool_use",
    "observation_mgmt",
    "context_mgmt",
    "completion_detect",
)


def _connect(paths: OmegaPaths) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(paths.evolution_db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sim_experiments (
            exp_id TEXT PRIMARY KEY,
            ts INTEGER NOT NULL,
            module TEXT NOT NULL,
            rationale TEXT NOT NULL,
            predicted_delta REAL NOT NULL,
            observed_delta REAL NOT NULL,
            round_num INTEGER NOT NULL,
            edit_budget_lines INTEGER NOT NULL,
            actual_edit_lines INTEGER NOT NULL,
            baseline_score REAL NOT NULL,
            candidate_score REAL NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            diff_path TEXT NOT NULL DEFAULT '',
            approval_id TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.commit()
    return conn


def annealed_edit_budget(round_num: int, base_budget: int = 80, decay: float = 0.85, floor: int = 10) -> int:
    """RRSI (#3): temporally annealed edit budget decays over rounds to fight overfitting."""
    return max(floor, int(round(base_budget * (decay ** max(0, int(round_num))))))


class EvolutionLab:
    def __init__(self, paths: OmegaPaths | None = None):
        self.paths = paths or get_paths()
        conn = _connect(self.paths)
        conn.close()

    def current_round(self, module: str) -> int:
        conn = _connect(self.paths)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM sim_experiments WHERE module = ?", (module,)
            ).fetchone()
            return int(row["c"])
        finally:
            conn.close()

    def run_candidate(
        self,
        *,
        module: str,
        target_file: str,
        candidate_content: str,
        rationale: str,
        predicted_delta: float,
        evaluator: Callable[[str], dict[str, Any]],
        baseline_score: float,
        base_budget: int = 80,
        min_roi_delta: float = 0.0,
    ) -> dict[str, Any]:
        """Evaluate a candidate file edit in an isolated sandbox copy (PREPARE_ONLY).

        The live target_file is NEVER modified. Its SHA-256 before and after is verified.
        """
        if module not in MODULAR_AXES:
            raise ValueError(f"Invalid ModularRSI axis '{module}'. Choose from {MODULAR_AXES}.")
        abs_target = os.path.abspath(os.path.expanduser(target_file))
        if not os.path.isfile(abs_target):
            raise FileNotFoundError(f"Target file not found: {abs_target}")

        with open(abs_target, "r", encoding="utf-8") as f:
            orig_text = f.read()
        orig_sha = hashlib.sha256(orig_text.encode("utf-8")).hexdigest()

        exp_id = f"EVO-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        round_n = self.current_round(module)
        budget = annealed_edit_budget(round_n, base_budget=base_budget)

        diff_lines = list(
            difflib.unified_diff(
                orig_text.splitlines(keepends=True),
                candidate_content.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(abs_target)}",
                tofile=f"b/{os.path.basename(abs_target)}",
            )
        )
        changed_lines = sum(
            1 for ln in diff_lines if (ln.startswith("+") or ln.startswith("-")) and not ln.startswith(("+++", "---"))
        )

        # RRSI Pre-Gate Pruner: reject bloated or zero-diff edits before running suite
        if changed_lines == 0:
            return self._record(
                exp_id, module, rationale, predicted_delta, 0.0, round_n, budget, 0,
                baseline_score, baseline_score, "REJECTED_PRUNED", "Zero-change candidate pruned.", "", ""
            )
        if changed_lines > budget:
            return self._record(
                exp_id, module, rationale, predicted_delta, 0.0, round_n, budget, changed_lines,
                baseline_score, baseline_score, "REJECTED_PRUNED",
                f"RRSI budget exceeded: {changed_lines} changed lines > round-{round_n} cap {budget}.", "", ""
            )

        # Isolated copy in $TMPDIR/omega_lab_<exp_id>
        lab_dir = os.path.join(self.paths.tmpdir, f"omega_lab_{exp_id}")
        os.makedirs(lab_dir, exist_ok=True)
        cand_path = os.path.join(lab_dir, os.path.basename(abs_target))
        diff_path = os.path.join(self.paths.omega_home, f"{exp_id}.patch")
        try:
            with open(cand_path, "w", encoding="utf-8") as f:
                f.write(candidate_content)
            eval_res = evaluator(cand_path)
            cand_score = float(eval_res.get("score", 0.0))
            passed_all = bool(eval_res.get("passed_all", False))
            delta = round(cand_score - baseline_score, 4)

            # Verify live target untouched
            with open(abs_target, "rb") as f:
                after_sha = hashlib.sha256(f.read()).hexdigest()
            if after_sha != orig_sha:
                raise RuntimeError("ISOLATION BREACH: live file hash changed during lab run!")

            if not passed_all or delta < 0.0:
                return self._record(
                    exp_id, module, rationale, predicted_delta, delta, round_n, budget, changed_lines,
                    baseline_score, cand_score, "REJECTED_REGRESSION",
                    f"Non-regression gate failed (passed_all={passed_all}, delta={delta}).", "", ""
                )
            if delta < min_roi_delta:
                return self._record(
                    exp_id, module, rationale, predicted_delta, delta, round_n, budget, changed_lines,
                    baseline_score, cand_score, "REJECTED_PRUNED",
                    f"RRSI low-ROI prune: delta={delta} < min_roi={min_roi_delta}.", "", ""
                )

            with open(diff_path, "w", encoding="utf-8") as f:
                f.writelines(diff_lines)

            mk = MissionKernel(self.paths)
            apr = mk.request_approval(
                action_class="EVOLUTION_PROMOTE",
                summary=f"[{exp_id}] Promote {module} patch (+{delta:.3f}, {changed_lines} lines): {rationale[:120]}",
                command_or_payload=f"apply_patch:{diff_path} -> {abs_target}",
            )
            return self._record(
                exp_id, module, rationale, predicted_delta, delta, round_n, budget, changed_lines,
                baseline_score, cand_score, "PROPOSED",
                f"Qualified in isolated lab (+{delta:.3f}); PREPARE_ONLY patch awaits operator approval.",
                diff_path, apr["approval_id"]
            )
        finally:
            shutil.rmtree(lab_dir, ignore_errors=True)

    def _record(
        self,
        exp_id: str,
        module: str,
        rationale: str,
        predicted_delta: float,
        observed_delta: float,
        round_num: int,
        budget: int,
        actual_lines: int,
        baseline_score: float,
        candidate_score: float,
        decision: str,
        reason: str,
        diff_path: str,
        approval_id: str,
    ) -> dict[str, Any]:
        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO sim_experiments (
                    exp_id, ts, module, rationale, predicted_delta, observed_delta,
                    round_num, edit_budget_lines, actual_edit_lines,
                    baseline_score, candidate_score, decision, reason, diff_path, approval_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exp_id, int(time.time()), module, rationale, predicted_delta, observed_delta,
                    round_num, budget, actual_lines, baseline_score, candidate_score,
                    decision, reason, diff_path, approval_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "exp_id": exp_id,
            "module": module,
            "round": round_num,
            "edit_budget_lines": budget,
            "actual_edit_lines": actual_lines,
            "baseline_score": baseline_score,
            "candidate_score": candidate_score,
            "observed_delta": observed_delta,
            "decision": decision,
            "reason": reason,
            "diff_path": diff_path,
            "approval_id": approval_id,
        }

    def list_experiments(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = _connect(self.paths)
        try:
            rows = conn.execute(
                "SELECT * FROM sim_experiments ORDER BY ts DESC LIMIT ?", (int(limit),)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
