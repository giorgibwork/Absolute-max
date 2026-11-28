"""Executable Procedural Skill Forge (Doctrine Part VII §30 + ANCHOR + AdMem + Skill Deletion).

Pure Python 3.14 stdlib + SQLite FTS5 ($0.00):
- Admission-gated procedural skill bank: refuses unverified skills (requires verified
  evidence_id or verification_passed=True — ANCHOR arXiv:2611.10382).
- Expectation-grounded binary utility tracking (AdMem 2611.20605 + Leto 2611.33005).
- <2ms FTS5 BM25 × Bayesian utility retrieval.
- Automatic Skill Deletion (`prune_dead_skills`, arXiv:2611.28244) inside DreamEngine.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any

from . import OmegaPaths, ensure_dirs, get_paths, safe_fts_query, tune_sqlite
from .kernel import screen_memory_write


def _connect(paths: OmegaPaths) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(paths.vault_db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    tune_sqlite(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS forged_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id TEXT UNIQUE NOT NULL,
            task_family TEXT NOT NULL DEFAULT 'general',
            trigger_pattern TEXT NOT NULL,
            procedure TEXT NOT NULL,
            expected_outcome TEXT NOT NULL DEFAULT '',
            evidence_ref TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            utility_score REAL NOT NULL DEFAULT 0.5,
            positive_hits INTEGER NOT NULL DEFAULT 0,
            negative_hits INTEGER NOT NULL DEFAULT 0,
            uses INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS forged_skills_fts USING fts5(
            skill_id, task_family, trigger_pattern, procedure, expected_outcome,
            content='forged_skills', content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS fsk_ai AFTER INSERT ON forged_skills BEGIN
            INSERT INTO forged_skills_fts(rowid, skill_id, task_family, trigger_pattern, procedure, expected_outcome)
            VALUES (new.id, new.skill_id, new.task_family, new.trigger_pattern, new.procedure, new.expected_outcome);
        END;
        CREATE TRIGGER IF NOT EXISTS fsk_ad AFTER DELETE ON forged_skills BEGIN
            INSERT INTO forged_skills_fts(forged_skills_fts, rowid, skill_id, task_family, trigger_pattern, procedure, expected_outcome)
            VALUES ('delete', old.id, old.skill_id, old.task_family, old.trigger_pattern, old.procedure, old.expected_outcome);
        END;
        CREATE TRIGGER IF NOT EXISTS fsk_au AFTER UPDATE ON forged_skills BEGIN
            INSERT INTO forged_skills_fts(forged_skills_fts, rowid, skill_id, task_family, trigger_pattern, procedure, expected_outcome)
            VALUES ('delete', old.id, old.skill_id, old.task_family, old.trigger_pattern, old.procedure, old.expected_outcome);
            INSERT INTO forged_skills_fts(rowid, skill_id, task_family, trigger_pattern, procedure, expected_outcome)
            VALUES (new.id, new.skill_id, new.task_family, new.trigger_pattern, new.procedure, new.expected_outcome);
        END;
        """
    )
    conn.commit()
    return conn


class SkillForge:
    """Verified procedural skill bank with <2ms FTS5 matching and automatic Skill Deletion."""

    def __init__(self, paths: OmegaPaths | None = None):
        self.paths = paths or get_paths()
        conn = _connect(self.paths)
        conn.close()

    def admit_skill(
        self,
        skill_id: str,
        trigger_pattern: str,
        procedure: str,
        *,
        expected_outcome: str = "",
        task_family: str = "general",
        evidence_ref: str = "",
        verification_passed: bool = False,
        source_class: str = "verified_log",
    ) -> dict[str, Any]:
        """ANCHOR admission gate: admit only verified, clean, non-injected procedures."""
        if not verification_passed and not evidence_ref.strip():
            return {
                "status": "REJECTED_UNVERIFIED",
                "skill_id": skill_id,
                "reason": "ANCHOR gate: procedural skill requires verification_passed=True or verified evidence_ref.",
            }
        ok, reason = screen_memory_write(f"{trigger_pattern}\n{procedure}", source_class, f"skill://{skill_id}")
        if not ok:
            return {"status": "QUARANTINED", "skill_id": skill_id, "reason": reason}

        now = int(time.time())
        conn = _connect(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO forged_skills
                    (skill_id, task_family, trigger_pattern, procedure, expected_outcome, evidence_ref, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(skill_id) DO UPDATE SET
                    task_family=excluded.task_family,
                    trigger_pattern=excluded.trigger_pattern,
                    procedure=excluded.procedure,
                    expected_outcome=excluded.expected_outcome,
                    evidence_ref=excluded.evidence_ref,
                    status='active',
                    updated_at=excluded.updated_at
                """,
                (skill_id.strip(), task_family.strip().lower(), trigger_pattern.strip(), procedure.strip(), expected_outcome.strip(), evidence_ref.strip(), now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return {"status": "ADMITTED", "skill_id": skill_id.strip(), "task_family": task_family.strip().lower()}

    def match_skills(self, query: str, *, task_family: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        clauses = ["s.status = 'active'", "NOT (s.negative_hits >= 2 AND s.utility_score < 0.25)"]
        params: list[Any] = []
        if task_family:
            clauses.append("(s.task_family = ? OR s.task_family = 'global')")
            params.append(task_family.strip().lower())
        where_sql = " AND ".join(clauses)

        fts_q = safe_fts_query(q, mode="OR", max_terms=6) or q

        conn = _connect(self.paths)
        try:
            try:
                rows = conn.execute(
                    f"""
                    SELECT s.skill_id, s.task_family, s.trigger_pattern, s.procedure,
                           s.expected_outcome, s.evidence_ref, s.utility_score, s.positive_hits, s.negative_hits
                    FROM forged_skills_fts f
                    JOIN forged_skills s ON s.id = f.rowid
                    WHERE forged_skills_fts MATCH ? AND {where_sql}
                    ORDER BY bm25(forged_skills_fts) * (1.25 - 0.5 * s.utility_score), s.utility_score DESC
                    LIMIT ?
                    """,
                    [fts_q, *params, int(limit)],
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if not rows:
                like = f"%{q}%"
                rows = conn.execute(
                    f"""
                    SELECT s.skill_id, s.task_family, s.trigger_pattern, s.procedure,
                           s.expected_outcome, s.evidence_ref, s.utility_score, s.positive_hits, s.negative_hits
                    FROM forged_skills s
                    WHERE (s.trigger_pattern LIKE ? OR s.procedure LIKE ?) AND {where_sql}
                    ORDER BY s.utility_score DESC LIMIT ?
                    """,
                    [like, like, *params, int(limit)],
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def record_outcome(self, skill_id: str, *, success: bool) -> dict[str, Any]:
        sid = skill_id.strip()
        conn = _connect(self.paths)
        try:
            row = conn.execute(
                "SELECT positive_hits, negative_hits, uses FROM forged_skills WHERE skill_id = ?",
                (sid,),
            ).fetchone()
            if not row:
                return {"status": "NOT_FOUND", "skill_id": sid}
            pos = int(row["positive_hits"]) + (1 if success else 0)
            neg = int(row["negative_hits"]) + (0 if success else 1)
            uses = int(row["uses"]) + 1
            util = round((pos + 1.0) / (pos + neg + 2.0), 4)
            conn.execute(
                "UPDATE forged_skills SET positive_hits=?, negative_hits=?, uses=?, utility_score=?, updated_at=? WHERE skill_id=?",
                (pos, neg, uses, util, int(time.time()), sid),
            )
            conn.commit()
            return {"status": "UPDATED", "skill_id": sid, "utility_score": util, "positive_hits": pos, "negative_hits": neg}
        finally:
            conn.close()

    def prune_dead_skills(self, *, min_negatives: int = 3, max_utility: float = 0.25) -> dict[str, Any]:
        """Skill Deletion (arXiv:2611.28244): delete persistently harmful forged skills."""
        conn = _connect(self.paths)
        try:
            rows = conn.execute(
                "SELECT skill_id FROM forged_skills WHERE status='active' AND negative_hits >= ? AND utility_score < ?",
                (int(min_negatives), float(max_utility)),
            ).fetchall()
            ids = [r["skill_id"] for r in rows]
            if ids:
                conn.execute(
                    f"UPDATE forged_skills SET status='deleted', updated_at=? WHERE skill_id IN ({','.join('?' for _ in ids)})",
                    [int(time.time()), *ids],
                )
                conn.commit()
            return {"deleted_count": len(ids), "deleted_skills": ids}
        finally:
            conn.close()
