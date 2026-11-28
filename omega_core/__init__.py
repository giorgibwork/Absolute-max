"""OMEGA APEX / Absolute Max OS v6.0 — Host-Independent Pure-Stdlib Core.

All runtime state defaults to ~/.antigem/omega (with existing vault at
~/.antigem/memory/omega_vault.db), and can be fully isolated for testing or
Evolution Lab runs via the OMEGA_HOME environment variable.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

VERSION = "8.0.0-apex"

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
    for d in (
        paths.omega_home,
        os.path.dirname(paths.vault_db),
        os.path.dirname(paths.audit_log),
        paths.state_dir,
        paths.tmpdir,
    ):
        os.makedirs(d, exist_ok=True)


def tune_sqlite(conn) -> None:
    """Apply production low-latency SQLite WAL + 64MB mmap + memory temp_store pragmas."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA mmap_size=67108864;")
    conn.execute("PRAGMA cache_size=-8000;")
    conn.execute("PRAGMA busy_timeout=5000;")


_LATIN_CYR_GEO_RX = re.compile(r"[A-Za-z0-9_\u0400-\u04ff\u10a0-\u10ff][A-Za-z0-9._\-\u0400-\u04ff\u10a0-\u10ff]{1,}")
_CJK_RUN_RX = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]{2,}")


def tokenize_multilingual(text: str, *, min_latin: int = 2, min_cjk: int = 2, max_tokens: int = 24) -> list[str]:
    """Extract Latin, CJK (ZH/JA/KO), Cyrillic (RU), and Georgian tokens without dropping non-ASCII scripts."""
    raw = (text or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for m in _LATIN_CYR_GEO_RX.findall(raw):
        cleaned = m.strip("._-")
        if len(cleaned) >= min_latin:
            out.append(cleaned)
    for run in _CJK_RUN_RX.findall(raw):
        if len(run) >= min_cjk:
            out.append(run)
            if len(run) >= 4:
                # Emit overlapping 2-char CJK bigrams so unspaced Chinese/Japanese phrases match cleanly
                for i in range(0, min(len(run) - 1, 8)):
                    out.append(run[i : i + 2])
    return list(dict.fromkeys(out))[:max_tokens]


def safe_fts_query(raw: str, *, mode: str = "OR", max_terms: int = 6) -> str:
    """Build a safe SQLite FTS5 MATCH expression that quotes hyphens/dots/non-ASCII cleanly."""
    q = (raw or "").strip()
    if not q:
        return ""
    # Preserve explicit FTS boolean syntax if caller already quoted or structured it safely
    if ('"' in q or "*" in q) and not re.search(r"[?!;()]", q):
        return q
    if (" OR " in q or " AND " in q) and not re.search(r"[a-zA-Z0-9]-[a-zA-Z0-9]", q):
        return q
    toks = tokenize_multilingual(q, min_latin=2, min_cjk=2, max_tokens=max_terms)
    if not toks:
        escaped = q.replace('"', "")
        return f'"{escaped}"' if escaped else ""
    quoted = [f'"{t.replace(chr(34), "")}"' for t in toks[:max_terms]]
    joiner = " AND " if mode.upper() == "AND" else " OR "
    return joiner.join(quoted)
