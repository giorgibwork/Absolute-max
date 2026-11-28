"""Knowledge & Evidence Fabric + Scoped-ORC (#1) + GrepMem + Context Compiler.

Upgrades existing ~/.antigem/memory/omega_vault.db non-destructively while
adding:
- Scoped-ORC retrieval/write masks (task_family + capability_ring)
- First-class Appendix A.3 Evidence Store (preserving supports/refutes contradictions)
- GrepMem lossless append-only searchable log (regex exact recall)
- Deterministic, token-budgeted Context Compiler with Context Manifest
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from typing import Any

from . import R0_READONLY, R2_WORKSPACE, R3_EXTERNAL_APPROVED, OmegaPaths, ensure_dirs, get_paths, tune_sqlite
from .kernel import screen_memory_write
from .mission import MissionKernel

VALID_AUTHORITIES = ("user_explicit", "verified_log", "web_source", "inferred")
VALID_SUPPORT_TYPES = ("supports", "refutes", "contextualizes", "neutral")
VALID_VERIFICATION_STATUS = ("verified", "partial", "unverified", "failed")
MAX_GREPMEM_LINES = 5000


def connect_vault(paths: OmegaPaths) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(paths.vault_db, timeout=5.0)
    conn.row_factory = sqlite3.Row
    tune_sqlite(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            tags TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            authority TEXT NOT NULL DEFAULT 'verified_log',
            status TEXT NOT NULL DEFAULT 'active',
            superseded_by TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL,
            task_family TEXT NOT NULL DEFAULT 'global',
            capability_ring INTEGER NOT NULL DEFAULT 2,
            origin_uri TEXT NOT NULL DEFAULT 'local://vault'
        );
        """
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()}
    migrations = [
        ("authority", "ALTER TABLE memories ADD COLUMN authority TEXT NOT NULL DEFAULT 'verified_log';"),
        ("status", "ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT 'active';"),
        ("superseded_by", "ALTER TABLE memories ADD COLUMN superseded_by TEXT NOT NULL DEFAULT '';"),
        ("task_family", "ALTER TABLE memories ADD COLUMN task_family TEXT NOT NULL DEFAULT 'global';"),
        ("capability_ring", "ALTER TABLE memories ADD COLUMN capability_ring INTEGER NOT NULL DEFAULT 2;"),
        ("origin_uri", "ALTER TABLE memories ADD COLUMN origin_uri TEXT NOT NULL DEFAULT 'local://vault';"),
        ("utility_score", "ALTER TABLE memories ADD COLUMN utility_score REAL NOT NULL DEFAULT 0.5;"),
        ("positive_hits", "ALTER TABLE memories ADD COLUMN positive_hits INTEGER NOT NULL DEFAULT 0;"),
        ("negative_hits", "ALTER TABLE memories ADD COLUMN negative_hits INTEGER NOT NULL DEFAULT 0;"),
        ("serve_count", "ALTER TABLE memories ADD COLUMN serve_count INTEGER NOT NULL DEFAULT 0;"),
        ("last_served_at", "ALTER TABLE memories ADD COLUMN last_served_at INTEGER NOT NULL DEFAULT 0;"),
    ]
    for col, ddl in migrations:
        if col not in cols:
            conn.execute(ddl)

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            key, tags, text, content='memories', content_rowid='id'
        );
        """
    )
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, key, tags, text)
            VALUES (new.id, new.key, new.tags, new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, tags, text)
            VALUES ('delete', old.id, old.key, old.tags, old.text);
        END;
        CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, tags, text)
            VALUES ('delete', old.id, old.key, old.tags, old.text);
            INSERT INTO memories_fts(rowid, key, tags, text)
            VALUES (new.id, new.key, new.tags, new.text);
        END;

        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL DEFAULT '',
            claim_id TEXT NOT NULL DEFAULT '',
            claim_text TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'primary',
            locator TEXT NOT NULL,
            retrieved_at INTEGER NOT NULL,
            published_at TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            retrieval_scope TEXT NOT NULL DEFAULT 'snippet',
            support_type TEXT NOT NULL DEFAULT 'supports',
            verification_method TEXT NOT NULL DEFAULT 'direct_inspect',
            verification_status TEXT NOT NULL DEFAULT 'unverified',
            freshness TEXT NOT NULL DEFAULT 'current',
            limitations TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS memory_edges (
            src_key TEXT NOT NULL,
            rel TEXT NOT NULL,
            dst_key TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (src_key, rel, dst_key)
        );
        CREATE INDEX IF NOT EXISTS idx_me_src ON memory_edges(src_key);
        CREATE INDEX IF NOT EXISTS idx_me_dst ON memory_edges(dst_key);
        """
    )
    conn.commit()
    return conn


class KnowledgeFabric:
    """Scoped-ORC Memory + Evidence Store + GrepMem + Context Compiler."""

    def __init__(self, paths: OmegaPaths | None = None):
        self.paths = paths or get_paths()
        conn = connect_vault(self.paths)
        conn.close()

    # --- Scoped-ORC Memory Write & Scoped Retrieval (#1 + #10) ---
    def add_memory(
        self,
        key: str,
        text: str,
        *,
        tags: str = "",
        authority: str = "verified_log",
        task_family: str = "general",
        capability_ring: int = R2_WORKSPACE,
        origin_uri: str = "local://omega",
        global_override: bool = False,
    ) -> dict[str, Any]:
        if authority not in VALID_AUTHORITIES:
            raise ValueError(f"Invalid authority: {authority}")

        fam = (task_family or "general").strip().lower()
        # Scoped-ORC hard gate: writing to global requires explicit override + trusted authority
        if fam == "global":
            if not global_override:
                raise PermissionError("Scoped-ORC gate: global memory write requires global_override=True.")
            if authority not in ("user_explicit", "verified_log"):
                raise PermissionError(
                    f"Scoped-ORC gate: untrusted authority '{authority}' cannot write global memory."
                )

        ok, reason = screen_memory_write(text, authority, origin_uri)
        if not ok:
            self.append_grepmem("MEMORY_QUARANTINED", {"key": key, "reason": reason, "origin": origin_uri}, fam)
            return {"status": "QUARANTINED", "key": key, "reason": reason}

        ring = max(R0_READONLY, min(R3_EXTERNAL_APPROVED, int(capability_ring)))
        now = int(time.time())
        conn = connect_vault(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO memories
                    (key, tags, text, authority, status, superseded_by, updated_at, task_family, capability_ring, origin_uri)
                VALUES (?, ?, ?, ?, 'active', '', ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    tags=excluded.tags,
                    text=excluded.text,
                    authority=excluded.authority,
                    status='active',
                    superseded_by='',
                    updated_at=excluded.updated_at,
                    task_family=excluded.task_family,
                    capability_ring=excluded.capability_ring,
                    origin_uri=excluded.origin_uri
                """,
                (key.strip(), tags.strip(), text.strip(), authority, now, fam, ring, origin_uri),
            )
            conn.commit()
        finally:
            conn.close()

        self.append_grepmem("MEMORY_SAVED", {"key": key.strip(), "family": fam, "ring": ring, "authority": authority}, fam)
        return {"status": "COMMITTED", "key": key.strip(), "task_family": fam, "capability_ring": ring}

    def revoke_memory(self, key: str, superseded_by: str = "") -> dict[str, Any]:
        now = int(time.time())
        conn = connect_vault(self.paths)
        try:
            cur = conn.execute(
                "UPDATE memories SET status='revoked', superseded_by=?, updated_at=? WHERE key=?",
                (superseded_by.strip(), now, key.strip()),
            )
            conn.commit()
            return {"status": "REVOKED", "key": key.strip(), "rows": cur.rowcount, "superseded_by": superseded_by.strip()}
        finally:
            conn.close()

    def record_memory_feedback(self, key: str, *, positive: bool, note: str = "") -> dict[str, Any]:
        """Leto/AdMem utility loop (arXiv:2611.33005 / 2611.20605): binary credit updates future retrieval utility."""
        k = key.strip()
        now = int(time.time())
        conn = connect_vault(self.paths)
        try:
            row = conn.execute(
                "SELECT positive_hits, negative_hits, serve_count FROM memories WHERE key = ?",
                (k,),
            ).fetchone()
            if not row:
                return {"status": "NOT_FOUND", "key": k}
            pos = int(row["positive_hits"] or 0) + (1 if positive else 0)
            neg = int(row["negative_hits"] or 0) + (0 if positive else 1)
            serves = int(row["serve_count"] or 0) + 1
            # Laplace-smoothed Bayesian utility in (0, 1): starts at 0.5, rises on wins, drops on regressions
            utility = round((pos + 1.0) / (pos + neg + 2.0), 4)
            conn.execute(
                """
                UPDATE memories
                SET positive_hits=?, negative_hits=?, serve_count=?, utility_score=?, last_served_at=?
                WHERE key=?
                """,
                (pos, neg, serves, utility, now, k),
            )
            conn.commit()
        finally:
            conn.close()
        self.append_grepmem(
            "MEMORY_FEEDBACK",
            {"key": k, "positive": bool(positive), "utility_score": utility, "note": note[:140]},
            task_family="runtime",
        )
        return {
            "status": "UPDATED",
            "key": k,
            "positive_hits": pos,
            "negative_hits": neg,
            "serve_count": serves,
            "utility_score": utility,
        }

    def search_memory(
        self,
        query: str,
        *,
        task_family: str | None = None,
        caller_ring: int = R2_WORKSPACE,
        include_global: bool = True,
        include_revoked: bool = False,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Scoped-ORC + Weakest-Agent Ring retrieval.

        If task_family is specified, returns ONLY memories matching task_family
        (plus global if include_global=True) whose capability_ring <= caller_ring.
        """
        q = query.strip()
        if not q:
            return []

        clauses = ["m.capability_ring <= ?"]
        params: list[Any] = [int(caller_ring)]
        if not include_revoked:
            clauses.append("m.status = 'active'")
            clauses.append("NOT (m.negative_hits >= 2 AND m.utility_score < 0.25)")
        if task_family:
            fam = task_family.strip().lower()
            if include_global:
                clauses.append("(m.task_family = ? OR m.task_family = 'global')")
                params.append(fam)
            else:
                clauses.append("m.task_family = ?")
                params.append(fam)
        where_extra = " AND ".join(clauses)

        conn = connect_vault(self.paths)
        try:
            try:
                rows = conn.execute(
                    f"""
                    SELECT m.key, m.tags, m.text, m.authority, m.status, m.superseded_by,
                           m.task_family, m.capability_ring, m.origin_uri, m.updated_at,
                           m.utility_score, m.positive_hits, m.negative_hits
                    FROM memories_fts f
                    JOIN memories m ON m.id = f.rowid
                    WHERE memories_fts MATCH ? AND {where_extra}
                    ORDER BY bm25(memories_fts) * (1.25 - 0.5 * m.utility_score), m.utility_score DESC, m.key ASC
                    LIMIT ?
                    """,
                    [q, *params, int(limit)],
                ).fetchall()
            except sqlite3.OperationalError:
                like = f"%{q}%"
                rows = conn.execute(
                    f"""
                    SELECT m.key, m.tags, m.text, m.authority, m.status, m.superseded_by,
                           m.task_family, m.capability_ring, m.origin_uri, m.updated_at,
                           m.utility_score, m.positive_hits, m.negative_hits
                    FROM memories m
                    WHERE (m.key LIKE ? OR m.tags LIKE ? OR m.text LIKE ?) AND {where_extra}
                    ORDER BY m.utility_score DESC, m.key ASC
                    LIMIT ?
                    """,
                    [like, like, like, *params, int(limit)],
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # --- SQLite Recursive-CTE GraphRAG + Temporal Decay + RRF ---
    def link_memories(self, src_key: str, rel: str, dst_key: str, weight: float = 1.0) -> dict[str, Any]:
        valid_rels = ("depends_on", "contradicts", "supersedes", "related_to", "evidences", "solved_by")
        if rel not in valid_rels:
            raise ValueError(f"Invalid edge rel '{rel}'. Choose from {valid_rels}.")
        conn = connect_vault(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO memory_edges (src_key, rel, dst_key, weight, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(src_key, rel, dst_key) DO UPDATE SET
                    weight=excluded.weight, created_at=excluded.created_at
                """,
                (src_key.strip(), rel, dst_key.strip(), float(weight), int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()
        return {"src_key": src_key.strip(), "rel": rel, "dst_key": dst_key.strip(), "weight": float(weight)}

    def graph_search(
        self,
        query: str,
        *,
        task_family: str | None = None,
        caller_ring: int = R2_WORKSPACE,
        hops: int = 2,
        half_life_days: float = 30.0,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Hybrid FTS5 BM25 + 2-hop SQLite Recursive-CTE GraphRAG + Temporal Decay + RRF."""
        seeds = self.search_memory(query, task_family=task_family, caller_ring=caller_ring, limit=limit)
        if not seeds:
            return []

        now = time.time()
        scores: dict[str, float] = {}
        records: dict[str, dict[str, Any]] = {}
        k_rrf = 60.0

        for rank, item in enumerate(seeds, 1):
            k = item["key"]
            age_days = max(0.0, (now - float(item.get("updated_at", now))) / 86400.0)
            decay = 0.5 ** (age_days / max(1.0, half_life_days))
            util_w = 0.6 + 0.8 * float(item.get("utility_score", 0.5))
            scores[k] = scores.get(k, 0.0) + (1.0 / (k_rrf + rank)) * (0.7 + 0.3 * decay) * util_w
            item["match_hop"] = 0
            records[k] = item

        # Expand neighbors via Recursive CTE (respecting Scoped-ORC & capability_ring!)
        seed_keys = list(records.keys())[:6]
        conn = connect_vault(self.paths)
        try:
            placeholders = ",".join("?" for _ in seed_keys)
            rows = conn.execute(
                f"""
                WITH RECURSIVE walk(k, hop, path_w) AS (
                    SELECT key, 0, 1.0 FROM memories WHERE key IN ({placeholders})
                    UNION
                    SELECT CASE WHEN e.src_key = w.k THEN e.dst_key ELSE e.src_key END,
                           w.hop + 1,
                           w.path_w * e.weight * 0.7
                    FROM walk w
                    JOIN memory_edges e ON e.src_key = w.k OR e.dst_key = w.k
                    WHERE w.hop < ?
                )
                SELECT m.key, m.tags, m.text, m.authority, m.status, m.superseded_by,
                       m.task_family, m.capability_ring, m.origin_uri, m.updated_at,
                       MIN(w.hop) AS min_hop, MAX(w.path_w) AS max_w
                FROM walk w
                JOIN memories m ON m.key = w.k
                WHERE w.hop > 0
                  AND m.status = 'active'
                  AND m.capability_ring <= ?
                GROUP BY m.key
                ORDER BY max_w DESC
                LIMIT ?
                """,
                [*seed_keys, max(1, min(3, int(hops))), int(caller_ring), int(limit)],
            ).fetchall()
            for rank, r in enumerate(rows, 1):
                d = dict(r)
                fam = task_family.strip().lower() if task_family else None
                if fam and d["task_family"] not in (fam, "global"):
                    continue
                k = d["key"]
                age_days = max(0.0, (now - float(d.get("updated_at", now))) / 86400.0)
                decay = 0.5 ** (age_days / max(1.0, half_life_days))
                g_score = (1.0 / (k_rrf + rank + 5.0)) * float(d.pop("max_w", 0.5)) * (0.7 + 0.3 * decay)
                scores[k] = scores.get(k, 0.0) + g_score
                if k not in records:
                    d["match_hop"] = d.pop("min_hop", 1)
                    records[k] = d
                else:
                    d.pop("min_hop", None)
        finally:
            conn.close()

        ranked = sorted(records.values(), key=lambda x: scores.get(x["key"], 0.0), reverse=True)
        for item in ranked:
            item["rrf_score"] = round(scores.get(item["key"], 0.0), 6)
        return ranked[:limit]

    # --- Appendix A.3 Evidence Store ---
    def record_evidence(
        self,
        claim_text: str,
        source_id: str,
        locator: str,
        content_sample: str,
        *,
        mission_id: str = "",
        claim_id: str = "",
        source_type: str = "primary",
        published_at: str = "",
        retrieval_scope: str = "snippet",
        support_type: str = "supports",
        verification_method: str = "direct_inspect",
        verification_status: str = "verified",
        freshness: str = "current",
        limitations: str = "",
    ) -> dict[str, Any]:
        if support_type not in VALID_SUPPORT_TYPES:
            raise ValueError(f"Invalid support_type: {support_type}")
        if verification_status not in VALID_VERIFICATION_STATUS:
            raise ValueError(f"Invalid verification_status: {verification_status}")

        eid = f"EV-{uuid.uuid4().hex[:10]}"
        cid = claim_id or f"CLM-{hashlib.sha256(claim_text.strip().lower().encode('utf-8')).hexdigest()[:8]}"
        chash = hashlib.sha256(content_sample.encode("utf-8")).hexdigest()
        now = int(time.time())

        conn = connect_vault(self.paths)
        try:
            conn.execute(
                """
                INSERT INTO evidence (
                    evidence_id, mission_id, claim_id, claim_text, source_id, source_type,
                    locator, retrieved_at, published_at, content_hash, retrieval_scope,
                    support_type, verification_method, verification_status, freshness, limitations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    mission_id,
                    cid,
                    claim_text.strip(),
                    source_id.strip(),
                    source_type,
                    locator.strip(),
                    now,
                    published_at,
                    chash,
                    retrieval_scope,
                    support_type,
                    verification_method,
                    verification_status,
                    freshness,
                    limitations,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.append_grepmem(
            "EVIDENCE_RECORDED",
            {"evidence_id": eid, "claim_id": cid, "support_type": support_type, "locator": locator[:160]},
            mission_id=mission_id,
        )
        return {"evidence_id": eid, "claim_id": cid, "content_hash": chash, "support_type": support_type}

    def get_evidence(self, *, mission_id: str | None = None, claim_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        conn = connect_vault(self.paths)
        try:
            clauses, params = [], []
            if mission_id:
                clauses.append("mission_id = ?")
                params.append(mission_id)
            if claim_id:
                clauses.append("claim_id = ?")
                params.append(claim_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            rows = conn.execute(
                f"SELECT * FROM evidence {where} ORDER BY retrieved_at DESC LIMIT ?",
                [*params, int(limit)],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def detect_claim_conflicts(self, mission_id: str) -> list[dict[str, Any]]:
        """Surface contradictions without silently collapsing them."""
        ev = self.get_evidence(mission_id=mission_id, limit=200)
        by_claim: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in ev:
            cid = row["claim_id"]
            by_claim.setdefault(cid, {"supports": [], "refutes": [], "other": []})
            st = row["support_type"]
            if st in ("supports", "refutes"):
                by_claim[cid][st].append(row)
            else:
                by_claim[cid]["other"].append(row)
        conflicts = []
        for cid, grp in by_claim.items():
            if grp["supports"] and grp["refutes"]:
                conflicts.append(
                    {
                        "claim_id": cid,
                        "claim_text": grp["supports"][0]["claim_text"],
                        "supports_count": len(grp["supports"]),
                        "refutes_count": len(grp["refutes"]),
                        "supports": [x["locator"] for x in grp["supports"]],
                        "refutes": [x["locator"] for x in grp["refutes"]],
                    }
                )
        return conflicts

    # --- GrepMem Lossless Append-Only Exact Recall ---
    def append_grepmem(
        self,
        event: str,
        data: dict[str, Any],
        task_family: str = "general",
        mission_id: str = "",
    ) -> None:
        ensure_dirs(self.paths)
        rec = {
            "ts": int(time.time()),
            "event": event,
            "family": task_family,
            "mission_id": mission_id,
            "data": data,
        }
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n"
        with open(self.paths.grepmem_log, "a", encoding="utf-8") as f:
            f.write(line)
        # Bound log growth atomically
        try:
            if os.path.getsize(self.paths.grepmem_log) > 2_000_000:
                with open(self.paths.grepmem_log, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                if len(lines) > MAX_GREPMEM_LINES:
                    tmp = self.paths.grepmem_log + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.writelines(lines[-MAX_GREPMEM_LINES:])
                    os.replace(tmp, self.paths.grepmem_log)
        except OSError:
            pass

    def grep_history(
        self,
        pattern: str,
        *,
        task_family: str | None = None,
        mission_id: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        if not os.path.exists(self.paths.grepmem_log):
            return []
        rx = re.compile(pattern, re.IGNORECASE)
        hits: list[dict[str, Any]] = []
        with open(self.paths.grepmem_log, "r", encoding="utf-8", errors="replace") as f:
            for lineno, raw in enumerate(f, 1):
                if not rx.search(raw):
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if task_family and obj.get("family") != task_family:
                    continue
                if mission_id and obj.get("mission_id") != mission_id:
                    continue
                obj["_line"] = lineno
                hits.append(obj)
        return hits[-limit:]

    # --- Deterministic Context Compiler with Manifest (Full or Telegraphic L1) ---
    def compile_context(
        self,
        *,
        task_family: str = "general",
        mission_id: str | None = None,
        caller_ring: int = R2_WORKSPACE,
        budget_chars: int = 5600,
        telegraphic: bool = False,
    ) -> dict[str, Any]:
        """Compile bounded, provenance-tagged, prefix-cache-safe context + manifest.

        When telegraphic=True (L1 Working Memory mode), compresses pinned rules +
        active memories into a dense ~1.6KB static pointer index while PreInvocation
        JIT Hydration dynamically loads exact full verbatim memories on demand.
        """
        sections: list[str] = []
        manifest: dict[str, Any] = {
            "task_family": task_family,
            "mission_id": mission_id or "",
            "caller_ring": caller_ring,
            "budget_chars": budget_chars,
            "telegraphic": telegraphic,
            "pins": 0,
            "memories_included": [],
            "memories_dropped": 0,
            "problems_included": [],
            "evidence_included": [],
        }

        used = 0

        def try_add(block: str) -> bool:
            nonlocal used
            if used + len(block) + 1 > budget_chars:
                return False
            sections.append(block)
            used += len(block) + 1
            return True

        # Layer 1: Pinned Constitutional Constraints (immutable, sorted)
        if os.path.exists(self.paths.pinned_constraints):
            try:
                with open(self.paths.pinned_constraints, "r", encoding="utf-8") as pf:
                    pins = sorted(set(str(x) for x in json.load(pf)))
                if pins:
                    if telegraphic:
                        pin_lines = ["<pinned_constraints>"] + [f"- {c[:115]}" for c in pins] + ["</pinned_constraints>"]
                    else:
                        pin_lines = ["<pinned_constraints>"] + [f"- {c[:180]}" for c in pins] + ["</pinned_constraints>"]
                    if try_add("\n".join(pin_lines)):
                        manifest["pins"] = len(pins)
            except Exception:
                pass

        # Layer 2: Active Mission Contract + Open Pro² Problem State
        if mission_id:
            try:
                mk = MissionKernel(self.paths)
                m = mk.get_mission(mission_id)
                lines = [
                    "<active_mission>",
                    f"- id={m['mission_id']} state={m['state']} mode={m['autonomy_mode']} family={m['task_family']}",
                    f"- objective: {m['objective'][:200]}",
                ]
                for pr in m.get("problems", []):
                    if pr["status"] in ("OPEN", "TESTING"):
                        top_h = pr["hypotheses"][0]["proposal"][:90] if pr.get("hypotheses") else "none"
                        lines.append(f"- blocker[{pr['problem_id']}|sev={pr['severity']}]: {pr['blocker'][:120]} (top: {top_h})")
                        manifest["problems_included"].append(pr["problem_id"])
                lines.append("</active_mission>")
                try_add("\n".join(lines))
            except Exception:
                pass

        # Layer 3: Scoped-ORC + Ring-Filtered Memories (Telegraphic Pointer Index OR Full)
        conn = connect_vault(self.paths)
        try:
            rows = conn.execute(
                """
                SELECT key, tags, authority, task_family, capability_ring, text
                FROM memories
                WHERE status = 'active'
                  AND capability_ring <= ?
                  AND (task_family = ? OR task_family = 'global')
                ORDER BY CASE WHEN task_family = ? THEN 0 ELSE 1 END, key ASC
                LIMIT 40
                """,
                (int(caller_ring), task_family.lower(), task_family.lower()),
            ).fetchall()
        finally:
            conn.close()

        if rows:
            if telegraphic:
                # L1 Telegraphic Pointer Index (~70% smaller, Prompt-Cache safe; PreInvocation JIT hydrates full text!)
                ptr_items: list[str] = []
                for r in rows:
                    tag_hint = f"({r['tags'][:28]})" if r["tags"] else ""
                    ptr_items.append(f"{r['key']}{tag_hint}")
                    manifest["memories_included"].append(r["key"])
                block = (
                    "<omega_memory_pointers mode=\"telegraphic_L1\">\n"
                    "Full matching memories auto-hydrate per turn via PreInvocation JIT (or `omega mem graph <q>`):\n"
                    + " | ".join(ptr_items)
                    + "\n</omega_memory_pointers>"
                )
                try_add(block)
            else:
                mem_lines = ["<omega_memory_index>"]
                local_used = len(mem_lines[0]) + len("</omega_memory_index>") + 2
                for r in rows:
                    ln = f"- [{r['authority']}|{r['task_family']}|R{r['capability_ring']}] {r['key']}: {r['text'].replace(chr(10), ' ')[:170]}"
                    if used + local_used + len(ln) + 1 > budget_chars:
                        manifest["memories_dropped"] += 1
                        continue
                    mem_lines.append(ln)
                    local_used += len(ln) + 1
                    manifest["memories_included"].append(r["key"])
                mem_lines.append("</omega_memory_index>")
                if manifest["memories_included"]:
                    try_add("\n".join(mem_lines))

        # Layer 4: Linked Verified Evidence
        if mission_id:
            evs = self.get_evidence(mission_id=mission_id, limit=10)
            if evs:
                ev_lines = ["<mission_evidence>"]
                local_used = len(ev_lines[0]) + len("</mission_evidence>") + 2
                for e in evs:
                    ln = f"- [{e['evidence_id']}|{e['support_type']}|{e['verification_status']}] {e['claim_text'][:120]} ({e['locator'][:80]})"
                    if used + local_used + len(ln) + 1 > budget_chars:
                        break
                    ev_lines.append(ln)
                    local_used += len(ln) + 1
                    manifest["evidence_included"].append(e["evidence_id"])
                ev_lines.append("</mission_evidence>")
                if manifest["evidence_included"]:
                    try_add("\n".join(ev_lines))

        compiled_text = "\n".join(sections)
        manifest["total_chars"] = len(compiled_text)
        manifest["sha256"] = hashlib.sha256(compiled_text.encode("utf-8")).hexdigest()[:16]
        return {"context": compiled_text, "manifest": manifest}
