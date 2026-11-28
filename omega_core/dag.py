"""Cognitive Runtime Task-Dependency DAG Scheduler & Parallel Wave Executor (Doctrine OAPX-SYS-05).

Pure Python 3.14 stdlib + SQLite ($0.00):
- Directed Acyclic Graph (DAG) task scheduler persisted inside missions.db
- Fail-closed cycle detection before execution
- Ready-frontier computation + bounded parallel wave execution (`ThreadPoolExecutor`)
- Bounded per-task retries, idempotency, and crash-resumable SQLite state
"""
from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import time
from typing import Any, Callable

from . import OmegaPaths, ensure_dirs, get_paths, tune_sqlite

VALID_NODE_STATES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED")


def _connect(paths: OmegaPaths) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(paths.missions_db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    tune_sqlite(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dag_tasks (
            mission_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            title TEXT NOT NULL,
            depends_on_json TEXT NOT NULL DEFAULT '[]',
            payload_json TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 2,
            result_json TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (mission_id, task_id)
        );
        CREATE INDEX IF NOT EXISTS idx_dag_mission ON dag_tasks(mission_id, state);
        """
    )
    conn.commit()
    return conn


class MissionDAG:
    """Crash-resumable parallel Task-Graph scheduler for multi-step OMEGA missions."""

    def __init__(self, mission_id: str, paths: OmegaPaths | None = None):
        self.mission_id = mission_id.strip()
        self.paths = paths or get_paths()
        conn = _connect(self.paths)
        conn.close()

    def add_task(
        self,
        task_id: str,
        title: str,
        *,
        depends_on: list[str] | None = None,
        payload: dict[str, Any] | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        tid = task_id.strip()
        deps = [d.strip() for d in (depends_on or []) if d.strip() and d.strip() != tid]
        now = int(time.time())
        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO dag_tasks
                    (mission_id, task_id, title, depends_on_json, payload_json, state, attempts, max_retries, updated_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?, ?)
                ON CONFLICT(mission_id, task_id) DO UPDATE SET
                    title=excluded.title,
                    depends_on_json=excluded.depends_on_json,
                    payload_json=excluded.payload_json,
                    max_retries=excluded.max_retries,
                    updated_at=excluded.updated_at
                """,
                (self.mission_id, tid, title.strip(), json.dumps(deps), json.dumps(payload or {}), int(max_retries), now),
            )
            conn.commit()
        finally:
            conn.close()
        return {"mission_id": self.mission_id, "task_id": tid, "depends_on": deps, "state": "PENDING"}

    def list_tasks(self) -> list[dict[str, Any]]:
        conn = _connect(self.paths)
        try:
            rows = conn.execute(
                "SELECT * FROM dag_tasks WHERE mission_id = ? ORDER BY task_id ASC",
                (self.mission_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["depends_on"] = json.loads(d.pop("depends_on_json"))
                d["payload"] = json.loads(d.pop("payload_json"))
                d["result"] = json.loads(d.pop("result_json"))
                out.append(d)
            return out
        finally:
            conn.close()

    def validate_acyclic(self) -> list[str]:
        """Topological Kahn sort; raises ValueError fail-closed on dependency cycles or missing deps."""
        tasks = {t["task_id"]: t for t in self.list_tasks()}
        indeg: dict[str, int] = {k: 0 for k in tasks}
        adj: dict[str, list[str]] = {k: [] for k in tasks}
        for tid, t in tasks.items():
            for dep in t["depends_on"]:
                if dep not in tasks:
                    raise ValueError(f"Task '{tid}' depends on unknown task '{dep}'.")
                adj[dep].append(tid)
                indeg[tid] += 1

        q = [k for k, v in indeg.items() if v == 0]
        order: list[str] = []
        while q:
            cur = q.pop(0)
            order.append(cur)
            for nxt in adj[cur]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    q.append(nxt)
        if len(order) != len(tasks):
            raise ValueError("Cycle detected in MissionDAG; execution aborted fail-closed.")
        return order

    def ready_tasks(self) -> list[dict[str, Any]]:
        """Return all PENDING tasks whose dependencies are all COMPLETED."""
        tasks = {t["task_id"]: t for t in self.list_tasks()}
        done = {k for k, t in tasks.items() if t["state"] == "COMPLETED"}
        return [
            t
            for t in tasks.values()
            if t["state"] == "PENDING" and all(dep in done for dep in t["depends_on"])
        ]

    def _update_node(self, task_id: str, state: str, *, attempts: int, result: Any = None, error: str = "") -> None:
        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                UPDATE dag_tasks
                SET state=?, attempts=?, result_json=?, error=?, updated_at=?
                WHERE mission_id=? AND task_id=?
                """,
                (state, int(attempts), json.dumps(result if result is not None else {}), error[:300], int(time.time()), self.mission_id, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def execute_parallel(
        self,
        runner: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        *,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        """Execute ready DAG waves concurrently until completion or dependency deadlock."""
        t0 = time.monotonic()
        topo = self.validate_acyclic()
        waves = 0

        while True:
            frontier = self.ready_tasks()
            if not frontier:
                break
            waves += 1
            completed_map = {t["task_id"]: t["result"] for t in self.list_tasks() if t["state"] == "COMPLETED"}

            def _run_one(node: dict[str, Any]) -> tuple[str, bool, int, Any, str]:
                tid = node["task_id"]
                max_tries = max(1, int(node.get("max_retries", 2)) + 1)
                dep_results = {d: completed_map.get(d, {}) for d in node["depends_on"]}
                last_err = ""
                for attempt in range(int(node.get("attempts", 0)) + 1, max_tries + 1):
                    try:
                        out = runner(node, dep_results)
                        if isinstance(out, dict) and out.get("ok", True):
                            return tid, True, attempt, out, ""
                        last_err = str((out or {}).get("error") or "runner_returned_not_ok")
                    except Exception as e:
                        last_err = f"{type(e).__name__}: {e}"
                return tid, False, max_tries, {}, last_err

            with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(frontier))) as ex:
                for tid, ok, att, res, err in ex.map(_run_one, frontier):
                    self._update_node(tid, "COMPLETED" if ok else "FAILED", attempts=att, result=res, error=err)

        final_tasks = self.list_tasks()
        done_cnt = sum(1 for t in final_tasks if t["state"] == "COMPLETED")
        failed_ids = [t["task_id"] for t in final_tasks if t["state"] == "FAILED"]
        pending_ids = [t["task_id"] for t in final_tasks if t["state"] == "PENDING"]
        return {
            "ok": done_cnt == len(final_tasks),
            "mission_id": self.mission_id,
            "topo_order": topo,
            "waves": waves,
            "completed": done_cnt,
            "total": len(final_tasks),
            "failed": failed_ids,
            "blocked_pending": pending_ids,
            "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 2),
        }
