"""OMEGA APEX / Absolute Max OS v6.0 — Host-Independent Pure-Stdlib Core.

All runtime state defaults to ~/.antigem/omega (with existing vault at
~/.antigem/memory/omega_vault.db), and can be fully isolated for testing or
Evolution Lab runs via the OMEGA_HOME environment variable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

VERSION = "6.4.0-apex"

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
