"""Intent Compiler, Mission Kernel, Pro² Problem State, Approvals, Idempotency & Checkpoints.

Implements OMEGA APEX Appendix A.1 (Mission), A.2 (Task), A.5 (Checkpoint),
Pro² Agent primary Problem State (#7), PREPARE_ONLY Approval Queue,
Operation Idempotency Ledger, and SHA-256 Hash-Chained Event Journal.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from typing import Any, Callable

from . import R2_WORKSPACE, OmegaPaths, ensure_dirs, get_paths

VALID_MISSION_STATES = (
    "DRAFT",
    "ACTIVE",
    "BLOCKED",
    "WAITING_APPROVAL",
    "VERIFIED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)

VALID_TASK_STATES = (
    "PENDING",
    "RUNNING",
    "VERIFIED",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
)

VALID_PROBLEM_STATES = ("OPEN", "TESTING", "RESOLVED", "WONTFIX")


def _connect(paths: OmegaPaths) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(paths.missions_db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS missions (
            mission_id TEXT PRIMARY KEY,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            original_request TEXT NOT NULL,
            objective TEXT NOT NULL,
            scope_json TEXT NOT NULL DEFAULT '[]',
            exclusions_json TEXT NOT NULL DEFAULT '[]',
            constraints_json TEXT NOT NULL DEFAULT '[]',
            autonomy_mode TEXT NOT NULL DEFAULT 'PREPARE_ONLY',
            risk_class TEXT NOT NULL DEFAULT 'LOW',
            deliverables_json TEXT NOT NULL DEFAULT '[]',
            acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
            unknowns_json TEXT NOT NULL DEFAULT '[]',
            priority INTEGER NOT NULL DEFAULT 5,
            state TEXT NOT NULL DEFAULT 'ACTIVE',
            revision INTEGER NOT NULL DEFAULT 1,
            task_family TEXT NOT NULL DEFAULT 'general',
            capability_ring INTEGER NOT NULL DEFAULT 2,
            resource_budget_json TEXT NOT NULL DEFAULT '{}',
            checkpoint_head TEXT NOT NULL DEFAULT '',
            completion_record_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
            problem_id TEXT NOT NULL DEFAULT '',
            objective TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT 'worker',
            dependencies_json TEXT NOT NULL DEFAULT '[]',
            acceptance_criteria_json TEXT NOT NULL DEFAULT '[]',
            capability_ring INTEGER NOT NULL DEFAULT 2,
            retry_max INTEGER NOT NULL DEFAULT 2,
            retry_count INTEGER NOT NULL DEFAULT 0,
            idempotency_key TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'PENDING',
            result_json TEXT NOT NULL DEFAULT '{}',
            failure_record_json TEXT NOT NULL DEFAULT '{}',
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS problem_state (
            problem_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
            blocker TEXT NOT NULL,
            severity INTEGER NOT NULL DEFAULT 5,
            status TEXT NOT NULL DEFAULT 'OPEN',
            hypotheses_json TEXT NOT NULL DEFAULT '[]',
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL DEFAULT '',
            action_class TEXT NOT NULL,
            action_hash TEXT NOT NULL,
            summary TEXT NOT NULL,
            command_or_payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at INTEGER NOT NULL,
            resolved_at INTEGER NOT NULL DEFAULT 0,
            operator_note TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS operation_ledger (
            idempotency_key TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL,
            task_id TEXT NOT NULL DEFAULT '',
            op_name TEXT NOT NULL,
            status TEXT NOT NULL,
            result_hash TEXT NOT NULL,
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mission_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            ts INTEGER NOT NULL,
            prev_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            parent_checkpoint TEXT NOT NULL DEFAULT '',
            event_sequence INTEGER NOT NULL,
            state_snapshot_json TEXT NOT NULL,
            artifact_hashes_json TEXT NOT NULL DEFAULT '{}',
            integrity_hash TEXT NOT NULL,
            restore_status TEXT NOT NULL DEFAULT 'NOT_TESTED',
            created_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def _append_event(conn: sqlite3.Connection, mission_id: str, event_type: str, payload: dict[str, Any]) -> int:
    row = conn.execute("SELECT event_hash FROM mission_events ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = row["event_hash"] if row else ("0" * 64)
    ts = int(time.time())
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest_input = f"{prev_hash}|{mission_id}|{event_type}|{ts}|{payload_str}"
    event_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    cur = conn.execute(
        """
        INSERT INTO mission_events (mission_id, event_type, payload_json, ts, prev_hash, event_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (mission_id, event_type, payload_str, ts, prev_hash, event_hash),
    )
    return int(cur.lastrowid)


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class MissionKernel:
    """Authoritative persistent mission & problem-state engine."""

    def __init__(self, paths: OmegaPaths | None = None):
        self.paths = paths or get_paths()
        conn = _connect(self.paths)
        conn.close()

    def compile_intent(
        self,
        original_request: str,
        *,
        objective: str | None = None,
        task_family: str = "general",
        scope: list[str] | None = None,
        exclusions: list[str] | None = None,
        constraints: list[str] | None = None,
        deliverables: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        unknowns: list[str] | None = None,
        risk_class: str = "LOW",
        autonomy_mode: str = "PREPARE_ONLY",
        capability_ring: int = R2_WORKSPACE,
        priority: int = 5,
        resource_budget: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Intent Compiler: convert raw operator request into a Mission Contract."""
        req = original_request.strip()
        if not req:
            raise ValueError("Cannot compile empty request into a mission.")

        mission_id = f"M-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        now = int(time.time())
        obj = (objective or req).strip()
        inferred_unknowns = list(unknowns or [])
        if not acceptance_criteria:
            inferred_unknowns.append("Acceptance criteria not explicitly specified by operator.")
        if not scope:
            inferred_unknowns.append("Exact file/domain scope left general; confirm before broad edits.")

        default_constraints = ["cost_floor=$0.00", f"autonomy_mode={autonomy_mode}"]
        merged_constraints = sorted(set(default_constraints + list(constraints or [])))

        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO missions (
                    mission_id, created_at, updated_at, original_request, objective,
                    scope_json, exclusions_json, constraints_json, autonomy_mode, risk_class,
                    deliverables_json, acceptance_criteria_json, unknowns_json, priority,
                    state, revision, task_family, capability_ring, resource_budget_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 1, ?, ?, ?)
                """,
                (
                    mission_id,
                    now,
                    now,
                    req,
                    obj,
                    json.dumps(scope or []),
                    json.dumps(exclusions or []),
                    json.dumps(merged_constraints),
                    autonomy_mode,
                    risk_class,
                    json.dumps(deliverables or []),
                    json.dumps(acceptance_criteria or []),
                    json.dumps(inferred_unknowns),
                    int(priority),
                    task_family.strip() or "general",
                    int(capability_ring),
                    json.dumps(resource_budget or {"max_cost_usd": 0.0, "max_retries": 2}),
                ),
            )
            _append_event(
                conn,
                mission_id,
                "MISSION_CREATED",
                {"objective": obj, "task_family": task_family, "autonomy_mode": autonomy_mode},
            )
            conn.commit()
        finally:
            conn.close()

        return self.get_mission(mission_id)

    def get_mission(self, mission_id: str) -> dict[str, Any]:
        conn = _connect(self.paths)
        try:
            row = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,)).fetchone()
            if not row:
                raise KeyError(f"Mission not found: {mission_id}")
            tasks = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM tasks WHERE mission_id = ? ORDER BY rowid ASC", (mission_id,)
                ).fetchall()
            ]
            problems = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM problem_state WHERE mission_id = ? ORDER BY severity DESC, rowid ASC",
                    (mission_id,),
                ).fetchall()
            ]
            approvals = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM approvals WHERE mission_id = ? ORDER BY created_at DESC", (mission_id,)
                ).fetchall()
            ]
        finally:
            conn.close()

        m = dict(row)
        for k in (
            "scope_json",
            "exclusions_json",
            "constraints_json",
            "deliverables_json",
            "acceptance_criteria_json",
            "unknowns_json",
            "resource_budget_json",
            "completion_record_json",
        ):
            m[k.replace("_json", "")] = json.loads(m.pop(k))
        for t in tasks:
            t["dependencies"] = json.loads(t.pop("dependencies_json"))
            t["acceptance_criteria"] = json.loads(t.pop("acceptance_criteria_json"))
            t["result"] = json.loads(t.pop("result_json"))
            t["failure_record"] = json.loads(t.pop("failure_record_json"))
        for pr in problems:
            pr["hypotheses"] = json.loads(pr.pop("hypotheses_json"))
            pr["evidence_refs"] = json.loads(pr.pop("evidence_refs_json"))
        m["tasks"] = tasks
        m["problems"] = problems
        m["approvals"] = approvals
        return m

    def list_missions(self, state: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        conn = _connect(self.paths)
        try:
            if state:
                rows = conn.execute(
                    "SELECT mission_id, objective, task_family, state, revision, priority, updated_at FROM missions WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                    (state, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT mission_id, objective, task_family, state, revision, priority, updated_at FROM missions ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_mission_state(
        self,
        mission_id: str,
        new_state: str,
        completion_record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if new_state not in VALID_MISSION_STATES:
            raise ValueError(f"Invalid mission state: {new_state}")
        if new_state == "COMPLETED" and not completion_record:
            raise ValueError("Evidence before assertion: COMPLETED state requires a completion_record.")

        now = int(time.time())
        conn = _connect(self.paths)
        try:
            cur = conn.execute(
                """
                UPDATE missions
                SET state = ?, revision = revision + 1, updated_at = ?,
                    completion_record_json = CASE WHEN ? != '' THEN ? ELSE completion_record_json END
                WHERE mission_id = ?
                """,
                (
                    new_state,
                    now,
                    json.dumps(completion_record) if completion_record else "",
                    json.dumps(completion_record or {}),
                    mission_id,
                ),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Mission not found: {mission_id}")
            _append_event(conn, mission_id, "MISSION_STATE", {"state": new_state})
            conn.commit()
        finally:
            conn.close()
        return self.get_mission(mission_id)

    # --- Pro² Agent Problem State (#7) ---
    def add_problem(
        self,
        mission_id: str,
        blocker: str,
        *,
        severity: int = 7,
        hypotheses: list[dict[str, Any]] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        pid = f"P-{uuid.uuid4().hex[:8]}"
        now = int(time.time())
        hyps = []
        for idx, h in enumerate(hypotheses or [], 1):
            hyps.append(
                {
                    "id": h.get("id") or f"H{idx}",
                    "proposal": h.get("proposal", ""),
                    "expected_benefit": float(h.get("expected_benefit", 0.5)),
                    "status": h.get("status", "CANDIDATE"),
                    "test_result": h.get("test_result", ""),
                }
            )
        hyps.sort(key=lambda x: x["expected_benefit"], reverse=True)

        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO problem_state
                    (problem_id, mission_id, blocker, severity, status, hypotheses_json, evidence_refs_json, updated_at)
                VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?)
                """,
                (
                    pid,
                    mission_id,
                    blocker.strip(),
                    max(1, min(10, int(severity))),
                    json.dumps(hyps, ensure_ascii=False),
                    json.dumps(evidence_refs or []),
                    now,
                ),
            )
            _append_event(conn, mission_id, "PROBLEM_ADDED", {"problem_id": pid, "blocker": blocker[:160]})
            conn.commit()
        finally:
            conn.close()
        return {"problem_id": pid, "mission_id": mission_id, "blocker": blocker, "severity": severity, "hypotheses": hyps}

    def update_problem(
        self,
        problem_id: str,
        *,
        status: str | None = None,
        hypothesis_id: str | None = None,
        hypothesis_status: str | None = None,
        test_result: str | None = None,
        new_benefit: float | None = None,
        evidence_ref: str | None = None,
    ) -> dict[str, Any]:
        if status and status not in VALID_PROBLEM_STATES:
            raise ValueError(f"Invalid problem status: {status}")
        now = int(time.time())
        conn = _connect(self.paths)
        try:
            row = conn.execute("SELECT * FROM problem_state WHERE problem_id = ?", (problem_id,)).fetchone()
            if not row:
                raise KeyError(f"Problem not found: {problem_id}")
            hyps = json.loads(row["hypotheses_json"])
            refs = json.loads(row["evidence_refs_json"])
            if hypothesis_id:
                for h in hyps:
                    if h["id"] == hypothesis_id:
                        if hypothesis_status:
                            h["status"] = hypothesis_status
                        if test_result is not None:
                            h["test_result"] = test_result
                        if new_benefit is not None:
                            h["expected_benefit"] = float(new_benefit)
                hyps.sort(key=lambda x: x.get("expected_benefit", 0.0), reverse=True)
            if evidence_ref and evidence_ref not in refs:
                refs.append(evidence_ref)
            new_status = status or row["status"]
            conn.execute(
                """
                UPDATE problem_state
                SET status = ?, hypotheses_json = ?, evidence_refs_json = ?, updated_at = ?
                WHERE problem_id = ?
                """,
                (new_status, json.dumps(hyps, ensure_ascii=False), json.dumps(refs), now, problem_id),
            )
            _append_event(
                conn,
                row["mission_id"],
                "PROBLEM_UPDATED",
                {"problem_id": problem_id, "status": new_status, "hypothesis_id": hypothesis_id},
            )
            conn.commit()
            return {
                "problem_id": problem_id,
                "mission_id": row["mission_id"],
                "status": new_status,
                "hypotheses": hyps,
                "evidence_refs": refs,
            }
        finally:
            conn.close()

    # --- Task Graph & Idempotency ---
    def add_task(
        self,
        mission_id: str,
        objective: str,
        *,
        owner: str = "worker",
        problem_id: str = "",
        dependencies: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        capability_ring: int = R2_WORKSPACE,
        retry_max: int = 2,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        tid = f"T-{uuid.uuid4().hex[:8]}"
        now = int(time.time())
        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, mission_id, problem_id, objective, owner, dependencies_json,
                    acceptance_criteria_json, capability_ring, retry_max, idempotency_key,
                    state, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    tid,
                    mission_id,
                    problem_id,
                    objective.strip(),
                    owner,
                    json.dumps(dependencies or []),
                    json.dumps(acceptance_criteria or []),
                    int(capability_ring),
                    max(0, int(retry_max)),
                    idempotency_key or f"{mission_id}:{tid}",
                    now,
                ),
            )
            _append_event(conn, mission_id, "TASK_ADDED", {"task_id": tid, "problem_id": problem_id, "objective": objective[:160]})
            conn.commit()
        finally:
            conn.close()
        return {"task_id": tid, "mission_id": mission_id, "problem_id": problem_id, "state": "PENDING"}

    def execute_idempotent(
        self,
        mission_id: str,
        task_id: str,
        idempotency_key: str,
        op_name: str,
        fn: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Run a side-effecting operation at most once per idempotency_key."""
        conn = _connect(self.paths)
        try:
            existing = conn.execute(
                "SELECT status, result_json, result_hash FROM operation_ledger WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing and existing["status"] == "COMMITTED":
                return {
                    "replayed": True,
                    "executed": False,
                    "idempotency_key": idempotency_key,
                    "result": json.loads(existing["result_json"]),
                    "result_hash": existing["result_hash"],
                }
        finally:
            conn.close()

        result = fn()
        result_str = json.dumps(result, sort_keys=True, ensure_ascii=False)
        rhash = hashlib.sha256(result_str.encode("utf-8")).hexdigest()[:16]
        now = int(time.time())

        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO operation_ledger
                    (idempotency_key, mission_id, task_id, op_name, status, result_hash, result_json, created_at)
                VALUES (?, ?, ?, ?, 'COMMITTED', ?, ?, ?)
                """,
                (idempotency_key, mission_id, task_id, op_name, rhash, result_str, now),
            )
            if task_id:
                conn.execute(
                    "UPDATE tasks SET state = 'COMPLETED', result_json = ?, updated_at = ? WHERE task_id = ?",
                    (result_str, now, task_id),
                )
            _append_event(
                conn,
                mission_id,
                "OP_COMMITTED",
                {"task_id": task_id, "idempotency_key": idempotency_key, "op_name": op_name, "result_hash": rhash},
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "replayed": False,
            "executed": True,
            "idempotency_key": idempotency_key,
            "result": result,
            "result_hash": rhash,
        }

    # --- PREPARE_ONLY Approval Queue ---
    def request_approval(
        self,
        action_class: str,
        summary: str,
        command_or_payload: str,
        mission_id: str = "",
    ) -> dict[str, Any]:
        aid = f"APR-{uuid.uuid4().hex[:8]}"
        ahash = hashlib.sha256(command_or_payload.encode("utf-8")).hexdigest()[:16]
        now = int(time.time())
        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO approvals
                    (approval_id, mission_id, action_class, action_hash, summary, command_or_payload, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (aid, mission_id, action_class, ahash, summary[:240], command_or_payload, now),
            )
            if mission_id:
                _append_event(conn, mission_id, "APPROVAL_REQUESTED", {"approval_id": aid, "action_class": action_class})
            conn.commit()
        finally:
            conn.close()
        return {"approval_id": aid, "status": "PENDING", "action_class": action_class, "action_hash": ahash}

    def resolve_approval(self, approval_id: str, decision: str, note: str = "") -> dict[str, Any]:
        dec = decision.upper().strip()
        if dec not in ("APPROVED", "REJECTED"):
            raise ValueError("Approval decision must be APPROVED or REJECTED.")
        now = int(time.time())
        conn = _connect(self.paths)
        try:
            cur = conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ?, operator_note = ? WHERE approval_id = ?",
                (dec, now, note[:240], approval_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Approval ticket not found: {approval_id}")
            row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            if row["mission_id"]:
                _append_event(conn, row["mission_id"], f"APPROVAL_{dec}", {"approval_id": approval_id})
            conn.commit()
            return dict(row)
        finally:
            conn.close()

    def list_approvals(self, status: str | None = "PENDING") -> list[dict[str, Any]]:
        conn = _connect(self.paths)
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC LIMIT 30").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # --- Cryptographic Crash-Safe Checkpoints (Appendix A.5) ---
    def create_checkpoint(self, mission_id: str, artifact_paths: list[str] | None = None) -> dict[str, Any]:
        mission = self.get_mission(mission_id)
        cid = f"CKP-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        now = int(time.time())

        artifact_hashes: dict[str, str] = {}
        for ap in artifact_paths or []:
            fp = os.path.abspath(os.path.expanduser(ap))
            if os.path.isfile(fp):
                artifact_hashes[fp] = _file_sha256(fp)

        conn = _connect(self.paths)
        try:
            ev_row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS s FROM mission_events WHERE mission_id = ?", (mission_id,)
            ).fetchone()
            ev_seq = int(ev_row["s"])
            parent = mission.get("checkpoint_head", "")
            snapshot_str = json.dumps(mission, sort_keys=True, ensure_ascii=False)
            art_str = json.dumps(artifact_hashes, sort_keys=True, ensure_ascii=False)
            integrity_hash = hashlib.sha256(
                f"{cid}|{mission_id}|{mission['revision']}|{ev_seq}|{snapshot_str}|{art_str}".encode("utf-8")
            ).hexdigest()

            conn.execute(
                """
                INSERT INTO checkpoints (
                    checkpoint_id, mission_id, revision, parent_checkpoint, event_sequence,
                    state_snapshot_json, artifact_hashes_json, integrity_hash, restore_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NOT_TESTED', ?)
                """,
                (cid, mission_id, mission["revision"], parent, ev_seq, snapshot_str, art_str, integrity_hash, now),
            )
            conn.execute(
                "UPDATE missions SET checkpoint_head = ?, updated_at = ? WHERE mission_id = ?",
                (cid, now, mission_id),
            )
            _append_event(conn, mission_id, "CHECKPOINT_CREATED", {"checkpoint_id": cid, "integrity_hash": integrity_hash[:16]})
            conn.commit()
        finally:
            conn.close()

        return {
            "checkpoint_id": cid,
            "mission_id": mission_id,
            "revision": mission["revision"],
            "event_sequence": ev_seq,
            "integrity_hash": integrity_hash,
            "artifact_hashes": artifact_hashes,
        }

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        """Verify cryptographic integrity (fail-closed) and restore mission + tasks + problems."""
        conn = _connect(self.paths)
        try:
            row = conn.execute("SELECT * FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)).fetchone()
            if not row:
                raise KeyError(f"Checkpoint not found: {checkpoint_id}")

            expected = hashlib.sha256(
                f"{row['checkpoint_id']}|{row['mission_id']}|{row['revision']}|{row['event_sequence']}|{row['state_snapshot_json']}|{row['artifact_hashes_json']}".encode(
                    "utf-8"
                )
            ).hexdigest()
            if expected != row["integrity_hash"]:
                conn.execute("UPDATE checkpoints SET restore_status = 'REJECTED' WHERE checkpoint_id = ?", (checkpoint_id,))
                conn.commit()
                raise ValueError(f"Checkpoint integrity verification FAILED (tampered/corrupt): {checkpoint_id}")

            snap = json.loads(row["state_snapshot_json"])
            now = int(time.time())
            mid = row["mission_id"]

            conn.execute(
                """
                UPDATE missions
                SET objective = ?, scope_json = ?, exclusions_json = ?, constraints_json = ?,
                    deliverables_json = ?, acceptance_criteria_json = ?, unknowns_json = ?,
                    state = ?, revision = ?, checkpoint_head = ?, updated_at = ?
                WHERE mission_id = ?
                """,
                (
                    snap["objective"],
                    json.dumps(snap.get("scope", [])),
                    json.dumps(snap.get("exclusions", [])),
                    json.dumps(snap.get("constraints", [])),
                    json.dumps(snap.get("deliverables", [])),
                    json.dumps(snap.get("acceptance_criteria", [])),
                    json.dumps(snap.get("unknowns", [])),
                    snap["state"],
                    int(snap["revision"]),
                    checkpoint_id,
                    now,
                    mid,
                ),
            )
            # Restore task & problem states cleanly
            conn.execute("DELETE FROM tasks WHERE mission_id = ?", (mid,))
            for t in snap.get("tasks", []):
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, mission_id, problem_id, objective, owner, dependencies_json,
                        acceptance_criteria_json, capability_ring, retry_max, retry_count,
                        idempotency_key, state, result_json, failure_record_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t["task_id"],
                        mid,
                        t.get("problem_id", ""),
                        t["objective"],
                        t.get("owner", "worker"),
                        json.dumps(t.get("dependencies", [])),
                        json.dumps(t.get("acceptance_criteria", [])),
                        int(t.get("capability_ring", R2_WORKSPACE)),
                        int(t.get("retry_max", 2)),
                        int(t.get("retry_count", 0)),
                        t.get("idempotency_key", ""),
                        t["state"],
                        json.dumps(t.get("result", {})),
                        json.dumps(t.get("failure_record", {})),
                        int(t.get("updated_at", now)),
                    ),
                )
            conn.execute("DELETE FROM problem_state WHERE mission_id = ?", (mid,))
            for pr in snap.get("problems", []):
                conn.execute(
                    """
                    INSERT INTO problem_state
                        (problem_id, mission_id, blocker, severity, status, hypotheses_json, evidence_refs_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pr["problem_id"],
                        mid,
                        pr["blocker"],
                        int(pr.get("severity", 5)),
                        pr.get("status", "OPEN"),
                        json.dumps(pr.get("hypotheses", []), ensure_ascii=False),
                        json.dumps(pr.get("evidence_refs", [])),
                        int(pr.get("updated_at", now)),
                    ),
                )
            conn.execute("UPDATE checkpoints SET restore_status = 'VERIFIED' WHERE checkpoint_id = ?", (checkpoint_id,))
            _append_event(conn, mid, "CHECKPOINT_RESTORED", {"checkpoint_id": checkpoint_id, "revision": snap["revision"]})
            conn.commit()
        finally:
            conn.close()

        return {"status": "VERIFIED", "checkpoint_id": checkpoint_id, "mission_id": mid, "revision": snap["revision"]}

    def verify_event_chain(self) -> dict[str, Any]:
        """Verify cryptographic hash chain across all mission events."""
        conn = _connect(self.paths)
        try:
            rows = conn.execute("SELECT * FROM mission_events ORDER BY seq ASC").fetchall()
        finally:
            conn.close()
        prev = "0" * 64
        for r in rows:
            if r["prev_hash"] != prev:
                return {"ok": False, "broken_at_seq": r["seq"], "checked": len(rows)}
            calc = hashlib.sha256(
                f"{r['prev_hash']}|{r['mission_id']}|{r['event_type']}|{r['ts']}|{r['payload_json']}".encode("utf-8")
            ).hexdigest()
            if calc != r["event_hash"]:
                return {"ok": False, "broken_at_seq": r["seq"], "checked": len(rows)}
            prev = r["event_hash"]
        return {"ok": True, "checked": len(rows), "head_hash": prev[:16]}
