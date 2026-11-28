"""Async 'Dreaming' Consolidation & Execution-Signature Failure Clustering ($0.00, stdlib).

Separates the hot session path (static prefix-cached prompt) from an offline/idle
consolidation pass that:
1. Clusters recurring error traces in audit_chain.jsonl into deterministic
   failure_signatures (scar-tissue memory so solved bugs are recognized instantly).
2. Auto-builds GraphRAG memory_edges (related_to / supersedes) in omega_vault.db
   from shared tags and revoked/superseded chains.
3. Refreshes the incremental AST CodeGraph on ~/projects/Absolute-max and ~/tools.
4. Syncs the unified Obsidian Knowledge Graph (when vault exists).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from typing import Any

from . import (
    SCHEMA_BIT_DREAM,
    OmegaPaths,
    ensure_dirs,
    get_paths,
    mark_schema_bit,
    schema_has_bit,
    tune_sqlite,
)
from .codegraph import CodeGraph
from .forge import SkillForge
from .memory import KnowledgeFabric, connect_vault
from .obsidian import DEFAULT_VAULT_DIR, ObsidianSync

VOLATILE_RX = re.compile(
    r"(?:0x[0-9a-fA-F]+|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
    r"(?:/[a-zA-Z0-9_./-]+)?/(?:tmp|vfs)/[a-zA-Z0-9_./-]+|"
    r"\bline\s+\d+\b|"
    r"\b\d{4,}\b)",
    re.IGNORECASE,
)


def _connect_evo(paths: OmegaPaths, *, read_only: bool = False) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(paths.evolution_db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    if schema_has_bit(conn, SCHEMA_BIT_DREAM):
        tune_sqlite(conn, read_only=read_only)
        return conn
    tune_sqlite(conn, read_only=False)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS failure_signatures (
            sig_hash TEXT PRIMARY KEY,
            tool TEXT NOT NULL,
            normalized_error TEXT NOT NULL,
            sample_cmd TEXT NOT NULL DEFAULT '',
            occurrences INTEGER NOT NULL DEFAULT 1,
            first_seen INTEGER NOT NULL,
            last_seen INTEGER NOT NULL,
            known_fix TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS dream_seen_audit (
            rec_hash TEXT PRIMARY KEY,
            ts INTEGER NOT NULL
        );
        """
    )
    mark_schema_bit(conn, SCHEMA_BIT_DREAM)
    conn.commit()
    return conn


def normalize_error(tool: str, err: str) -> tuple[str, str]:
    norm = VOLATILE_RX.sub("<N>", (err or "").strip())
    norm = re.sub(r"\s+", " ", norm)[:180]
    sig = hashlib.sha256(f"{tool}|{norm}".encode("utf-8")).hexdigest()[:16]
    return sig, norm


class DreamEngine:
    def __init__(self, paths: OmegaPaths | None = None):
        self.paths = paths or get_paths()

    def cluster_failures(self) -> dict[str, Any]:
        """Extract deterministic failure signatures from audit_chain.jsonl with rotation-safe incremental counting."""
        conn = _connect_evo(self.paths)
        seen_sigs: dict[str, dict[str, Any]] = {}
        try:
            already = {r[0] for r in conn.execute("SELECT rec_hash FROM dream_seen_audit").fetchall()}
            new_hashes: list[tuple[str, int]] = []
            if os.path.exists(self.paths.audit_log):
                with open(self.paths.audit_log, "r", encoding="utf-8", errors="replace") as f:
                    for raw in f:
                        try:
                            rec = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("ok", True) or not rec.get("err"):
                            continue
                        rhash = str(rec.get("hash") or hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24])
                        if rhash in already:
                            continue
                        already.add(rhash)
                        ts = int(rec.get("ts") or time.time())
                        new_hashes.append((rhash, ts))
                        tool = str(rec.get("tool") or "unknown")
                        sig, norm = normalize_error(tool, str(rec.get("err") or ""))
                        entry = seen_sigs.setdefault(
                            sig,
                            {"tool": tool, "norm": norm, "cmd": str(rec.get("cmd_preview") or "")[:120], "count": 0, "first": ts, "last": ts},
                        )
                        entry["count"] += 1
                        entry["first"] = min(entry["first"], ts)
                        entry["last"] = max(entry["last"], ts)

            for sig, d in seen_sigs.items():
                conn.execute(
                    """
                    INSERT INTO failure_signatures
                        (sig_hash, tool, normalized_error, sample_cmd, occurrences, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(sig_hash) DO UPDATE SET
                        occurrences=occurrences + excluded.occurrences,
                        last_seen=MAX(last_seen, excluded.last_seen)
                    """,
                    (sig, d["tool"], d["norm"], d["cmd"], d["count"], d["first"], d["last"]),
                )
            if new_hashes:
                conn.executemany("INSERT OR IGNORE INTO dream_seen_audit (rec_hash, ts) VALUES (?, ?)", new_hashes)
                # Keep seen watermark bounded to latest 5000 error hashes
                conn.execute(
                    "DELETE FROM dream_seen_audit WHERE rec_hash NOT IN (SELECT rec_hash FROM dream_seen_audit ORDER BY ts DESC LIMIT 5000)"
                )
            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM failure_signatures").fetchone()[0]
        finally:
            conn.close()
        return {"signatures_parsed": len(seen_sigs), "total_signatures": total}

    def rebuild_memory_edges(self) -> dict[str, Any]:
        """Auto-derive GraphRAG edges (supersedes + tag-overlap related_to) in a single batched transaction."""
        conn = connect_vault(self.paths)
        edges_to_upsert: list[tuple[str, str, str, float, int]] = []
        now = int(time.time())
        try:
            rows = conn.execute("SELECT key, tags, status, superseded_by FROM memories").fetchall()
            tag_map: dict[str, list[str]] = {}
            for r in rows:
                if r["superseded_by"]:
                    edges_to_upsert.append((r["superseded_by"].strip(), "supersedes", r["key"].strip(), 1.0, now))
                if r["status"] == "active":
                    for t in [x.strip().lower() for x in r["tags"].split(",") if x.strip()]:
                        tag_map.setdefault(t, []).append(r["key"])

            for tag, keys in tag_map.items():
                uniq = sorted(set(keys))
                if 2 <= len(uniq) <= 8:
                    for i in range(len(uniq)):
                        for j in range(i + 1, len(uniq)):
                            edges_to_upsert.append((uniq[i].strip(), "related_to", uniq[j].strip(), 0.6, now))

            if edges_to_upsert:
                conn.executemany(
                    """
                    INSERT INTO memory_edges (src_key, rel, dst_key, weight, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(src_key, rel, dst_key) DO UPDATE SET
                        weight=excluded.weight, created_at=excluded.created_at
                    """,
                    edges_to_upsert,
                )
                conn.commit()
        finally:
            conn.close()
        return {"edges_upserted": len(edges_to_upsert)}

    def prune_low_utility_memories(self, *, min_negatives: int = 3, max_utility: float = 0.25) -> dict[str, Any]:
        """Skill Deletion (arXiv:2611.28244 + Leto 2611.33005): revoke persistently harmful memories."""
        kf = KnowledgeFabric(self.paths)
        conn = connect_vault(self.paths)
        pruned: list[str] = []
        try:
            rows = conn.execute(
                """
                SELECT key, utility_score, positive_hits, negative_hits
                FROM memories
                WHERE status = 'active' AND negative_hits >= ? AND utility_score < ?
                """,
                (int(min_negatives), float(max_utility)),
            ).fetchall()
        finally:
            conn.close()
        for r in rows:
            kf.revoke_memory(r["key"], superseded_by="pruned:low_utility")
            pruned.append(r["key"])
        if pruned:
            kf.append_grepmem("SKILL_DELETION_PRUNED", {"pruned_keys": pruned}, task_family="runtime")
        return {"pruned_count": len(pruned), "pruned_keys": pruned}

    def run_dream(self, *, sync_obsidian: bool = True, index_code: bool = True, vault_dir: str = DEFAULT_VAULT_DIR) -> dict[str, Any]:
        """Execute full offline consolidation pass without touching live session prompts."""
        t0 = time.monotonic()
        failures = self.cluster_failures()
        pruned = self.prune_low_utility_memories()
        pruned_skills = SkillForge(self.paths).prune_dead_skills()
        edges = self.rebuild_memory_edges()

        # Keep SQLite query planner statistics sharp across vault & evolution DBs
        for db_conn in (connect_vault(self.paths), _connect_evo(self.paths)):
            try:
                db_conn.execute("PRAGMA optimize;")
            finally:
                db_conn.close()

        code_stats: dict[str, Any] = {}
        if index_code:
            cg = CodeGraph(self.paths)
            code_stats["omega_core"] = cg.index_directory(os.path.join(self.paths.repo_root, "omega_core"))
            adapters_dir = os.path.join(self.paths.repo_root, "adapters")
            if os.path.isdir(adapters_dir):
                code_stats["adapters"] = cg.index_directory(adapters_dir)
            tests_dir = os.path.join(self.paths.repo_root, "tests")
            if os.path.isdir(tests_dir):
                code_stats["tests"] = cg.index_directory(tests_dir)
            tools_dir = os.path.expanduser("~/tools")
            if os.path.isdir(tools_dir):
                code_stats["tools"] = cg.index_directory(tools_dir)

        obs_stats: dict[str, Any] = {}
        if sync_obsidian and os.path.isdir(vault_dir):
            obs_stats = ObsidianSync(vault_dir=vault_dir, paths=self.paths).sync_all(force_config=False)

        kf = KnowledgeFabric(self.paths)
        kf.append_grepmem(
            "DREAM_CONSOLIDATION",
            {"failures": failures, "pruned": pruned, "pruned_skills": pruned_skills, "edges": edges},
            task_family="runtime",
        )
        return {
            "ok": True,
            "failures": failures,
            "pruned": pruned,
            "pruned_skills": pruned_skills,
            "memory_edges": edges,
            "codegraph": code_stats,
            "obsidian": {"nodes_written": obs_stats.get("nodes_written", 0)} if obs_stats else {},
            "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 2),
        }

    def list_failure_signatures(self, limit: int = 15) -> list[dict[str, Any]]:
        conn = _connect_evo(self.paths)
        try:
            rows = conn.execute(
                "SELECT * FROM failure_signatures ORDER BY occurrences DESC, last_seen DESC LIMIT ?", (int(limit),)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
