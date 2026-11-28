"""OMEGA APEX / Absolute Max OS v6.0 — Host-Independent Pure-Stdlib Core.

All runtime state defaults to ~/.antigem/omega (with existing vault at
~/.antigem/memory/omega_vault.db), and can be fully isolated for testing or
Evolution Lab runs via the OMEGA_HOME environment variable.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

VERSION = "9.0.0-apex"

# Fast SQLite schema-ready bitmask stored in PRAGMA user_version (avoids write-locked DDL on every hot-path read)
SCHEMA_EPOCH = 9 << 16
SCHEMA_BIT_MEMORY = 1 << 0
SCHEMA_BIT_FORGE = 1 << 1
SCHEMA_BIT_MISSION = 1 << 2
SCHEMA_BIT_DAG = 1 << 3
SCHEMA_BIT_FABRIC = 1 << 4
SCHEMA_BIT_CODEGRAPH = 1 << 5
SCHEMA_BIT_CORPUS = 1 << 6
SCHEMA_BIT_EVO = 1 << 7
SCHEMA_BIT_DREAM = 1 << 8
SCHEMA_BIT_DELEGATION = 1 << 9

_ENSURED_DIRS: set[str] = set()

# Capability Rings (Weakest-Agent Safety Invariant)
R0_READONLY = 0
R1_SANDBOX = 1
R2_WORKSPACE = 2
R3_EXTERNAL_APPROVED = 3

# Five-Level Action Reversibility Classes (arXiv:2611.22075)
REV0_NO_EFFECT = "REV0_NO_EFFECT"
REV1_RESTORABLE = "REV1_RESTORABLE"
REV2_COMPENSABLE = "REV2_COMPENSABLE"
REV3_HARD_TO_RECOVER = "REV3_HARD_TO_RECOVER"
REV4_IRREVERSIBLE = "REV4_IRREVERSIBLE"

RING_NAMES = {
    R0_READONLY: "R0_READONLY",
    R1_SANDBOX: "R1_SANDBOX",
    R2_WORKSPACE: "R2_WORKSPACE",
    R3_EXTERNAL_APPROVED: "R3_EXTERNAL_APPROVED",
}


@dataclass(frozen=True)
class OmegaPaths:
    omega_home: str
    missions_db: str
    vault_db: str
    models_db: str
    evolution_db: str
    grepmem_log: str
    audit_log: str
    state_dir: str
    pinned_constraints: str
    repo_root: str
    tmpdir: str


def get_paths(omega_home: str | None = None) -> OmegaPaths:
    home = os.path.expanduser("~")
    env_home = omega_home or os.environ.get("OMEGA_HOME")
    if env_home:
        base = os.path.abspath(os.path.expanduser(env_home))
        vault_db = os.path.join(base, "omega_vault.db")
        audit_log = os.path.join(base, "audit_chain.jsonl")
        state_dir = os.path.join(base, "state")
        pinned = os.path.join(base, "pinned_constraints.json")
    else:
        base = os.path.join(home, ".antigem", "omega")
        vault_db = os.path.join(home, ".antigem", "memory", "omega_vault.db")
        audit_log = os.path.join(home, ".antigem", "memory", "audit_chain.jsonl")
        state_dir = os.path.join(home, ".antigem", "state")
        pinned = os.path.join(home, ".antigem", "memory", "pinned_constraints.json")

    tmpdir = os.environ.get("TMPDIR") or os.path.join(home, ".antigem", "vfs")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return OmegaPaths(
        omega_home=base,
        missions_db=os.path.join(base, "missions.db"),
        vault_db=vault_db,
        models_db=os.path.join(base, "models.db"),
        evolution_db=os.path.join(base, "evolution.db"),
        grepmem_log=os.path.join(base, "grepmem.jsonl"),
        audit_log=audit_log,
        state_dir=state_dir,
        pinned_constraints=pinned,
        repo_root=repo_root,
        tmpdir=tmpdir,
    )


def ensure_dirs(paths: OmegaPaths) -> None:
    if paths.omega_home in _ENSURED_DIRS:
        return
    for d in (
        paths.omega_home,
        os.path.dirname(paths.vault_db),
        os.path.dirname(paths.audit_log),
        paths.state_dir,
        paths.tmpdir,
    ):
        os.makedirs(d, exist_ok=True)
    _ENSURED_DIRS.add(paths.omega_home)


def tune_sqlite(conn, *, read_only: bool = False) -> None:
    """Apply low-latency SQLite WAL + 64MB mmap + memory temp_store pragmas (skip WAL write lock on reads)."""
    if not read_only:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA mmap_size=67108864;")
    conn.execute("PRAGMA cache_size=-8000;")
    conn.execute("PRAGMA busy_timeout=5000;")


def schema_has_bit(conn, bit: int) -> bool:
    """Return True if SQLite DB header user_version already has the current epoch & module bit set (<0.05ms)."""
    uv = int(conn.execute("PRAGMA user_version;").fetchone()[0])
    return (uv & 0xFFFF0000) == SCHEMA_EPOCH and bool(uv & bit)


def mark_schema_bit(conn, bit: int) -> None:
    """Persist module schema initialization bit into SQLite header PRAGMA user_version."""
    uv = int(conn.execute("PRAGMA user_version;").fetchone()[0])
    flags = (uv & 0xFFFF) if (uv & 0xFFFF0000) == SCHEMA_EPOCH else 0
    conn.execute(f"PRAGMA user_version = {SCHEMA_EPOCH | flags | bit};")


_WORD_RX = re.compile(r"[^\W_](?:[\w.+\-]*[^\W_])?", re.UNICODE)
_CJK_RUN_RX = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]{2,}")


def tokenize_multilingual(text: str, *, min_latin: int = 2, min_cjk: int = 2, max_tokens: int = 24) -> list[str]:
    """Extract Unicode-complete tokens (Latin+diacritics, CJK w/ 2-char bigrams, Cyrillic, Georgian, Arabic, Greek, etc.)."""
    raw = (text or "").strip()
    if not raw:
        return []
    out: list[str] = []
    # Preserve technical symbols like C++, C#, .NET cleanly (avoid \b after non-word +/#)
    for special in re.findall(r"(?<!\w)(?:C\+\+|C#|\.NET)(?!\w)", raw, re.IGNORECASE):
        out.append(special)
    for m in _WORD_RX.findall(raw):
        # Skip pure CJK runs here (handled below with overlapping 2-char bigrams)
        if _CJK_RUN_RX.fullmatch(m):
            continue
        cleaned = m.strip("._-")
        if len(cleaned) >= min_latin:
            out.append(cleaned)
    for run in _CJK_RUN_RX.findall(raw):
        if len(run) >= min_cjk:
            out.append(run)
            if len(run) >= 4:
                # Emit overlapping 2-char CJK bigrams so unspaced Chinese/Japanese/Korean phrases match cleanly
                for i in range(0, min(len(run) - 1, 8)):
                    out.append(run[i : i + 2])
    return list(dict.fromkeys(out))[:max_tokens]


def safe_fts_query(raw: str, *, mode: str = "OR", max_terms: int = 6, raw_fts: bool = False) -> str:
    """Build a crash-proof SQLite FTS5 MATCH expression that quotes hyphens/colons/non-ASCII cleanly."""
    q = (raw or "").strip()
    if not q:
        return ""
    # Only pass through caller-crafted FTS syntax when explicitly requested AND syntactically balanced
    if raw_fts and q.count('"') % 2 == 0 and ":" not in q and not re.search(r"(?:^|\s)(?:AND|OR|NOT)\s*$", q):
        return q
    # Preserve simple pre-built `"t1" OR "t2"` queries if balanced and free of column-selector `:` or dangling operators
    if (
        '"' in q
        and q.count('"') % 2 == 0
        and ":" not in q
        and not re.search(r"[?!;()*]", q)
        and re.fullmatch(r'(?:"[^"]+"\s*(?:(?:OR|AND)\s+)?)+', q)
        and not re.search(r"(?:OR|AND)\s*$", q)
    ):
        return q
    toks = tokenize_multilingual(q, min_latin=2, min_cjk=2, max_tokens=max_terms)
    if not toks:
        escaped = re.sub(r'["*:^()]', " ", q).strip()
        return f'"{escaped}"' if escaped else ""
    quoted = [f'"{t.replace(chr(34), "")}"' for t in toks[:max_terms] if t.replace('"', "").strip()]
    if not quoted:
        return ""
    joiner = " AND " if mode.upper() == "AND" else " OR "
    return joiner.join(quoted)


def atomic_json_write(path: str, data: Any, *, indent: int | None = None) -> None:
    """Write JSON atomically using a PID-unique temp file + os.replace (safe under parallel hooks)."""
    import json

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{id(data) & 0xFFFF:04x}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def locked_file_op(lock_path: str, fn):
    """Execute fn() while holding an exclusive advisory flock (prevents parallel hook RMW clobber)."""
    import fcntl

    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def append_grepmem_fast(
    paths: OmegaPaths,
    event: str,
    data: dict,
    task_family: str = "general",
    mission_id: str = "",
    max_lines: int = 5000,
) -> None:
    """Zero-SQLite, flock-safe append to grepmem.jsonl (<1ms, safe for parallel PostToolUse hooks)."""
    import json
    import time

    ensure_dirs(paths)
    rec = {
        "ts": int(time.time()),
        "event": event,
        "family": task_family,
        "mission_id": mission_id,
        "data": data,
    }
    line = json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n"
    lock_path = paths.grepmem_log + ".lock"

    def _op() -> None:
        with open(paths.grepmem_log, "a", encoding="utf-8") as f:
            f.write(line)
        try:
            if os.path.getsize(paths.grepmem_log) > 2_000_000:
                with open(paths.grepmem_log, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                if len(lines) > max_lines:
                    tmp = f"{paths.grepmem_log}.{os.getpid()}.tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.writelines(lines[-max_lines:])
                    os.replace(tmp, paths.grepmem_log)
        except OSError:
            pass

    locked_file_op(lock_path, _op)
