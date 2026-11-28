#!/usr/bin/env python3
"""Backward-compatible AntiGem Memory Vault CLI backed by omega_core.memory (Scoped-ORC + Weakest-Agent rings)."""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.expanduser("~/projects/Absolute-max")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import R2_WORKSPACE, OmegaPaths, get_paths
from omega_core.memory import VALID_AUTHORITIES, KnowledgeFabric, connect_vault

DB_PATH = os.path.expanduser("~/.antigem/memory/omega_vault.db")


def _paths_for(db_path: str) -> OmegaPaths:
    base = get_paths()
    if os.path.abspath(os.path.expanduser(db_path)) == os.path.abspath(base.vault_db):
        return base
    return OmegaPaths(
        omega_home=base.omega_home,
        missions_db=base.missions_db,
        vault_db=os.path.abspath(os.path.expanduser(db_path)),
        models_db=base.models_db,
        evolution_db=base.evolution_db,
        grepmem_log=base.grepmem_log,
        audit_log=base.audit_log,
        state_dir=base.state_dir,
        pinned_constraints=base.pinned_constraints,
        repo_root=base.repo_root,
        tmpdir=base.tmpdir,
    )


def cmd_add(args):
    kf = KnowledgeFabric(_paths_for(args.db))
    fam = args.family
    global_ov = args.global_override or (fam == "global" and args.authority in ("user_explicit", "verified_log"))
    res = kf.add_memory(
        args.key,
        args.text,
        tags=args.tags,
        authority=args.authority,
        task_family=fam,
        capability_ring=args.ring,
        origin_uri=args.origin,
        global_override=global_ov,
    )
    if res["status"] != "COMMITTED":
        print(f"QUARANTINED: {args.key.strip()} ({res.get('reason')})")
        sys.exit(10)
    print(f"SAVED: {args.key.strip()} [authority={args.authority}|family={fam}|ring=R{args.ring}]")


def cmd_revoke(args):
    kf = KnowledgeFabric(_paths_for(args.db))
    res = kf.revoke_memory(args.key, superseded_by=args.superseded_by)
    print(f"REVOKED: {res['key']} (rows={res['rows']}, superseded_by={res['superseded_by'] or 'none'})")


def cmd_search(args):
    kf = KnowledgeFabric(_paths_for(args.db))
    out = kf.search_memory(
        args.query,
        task_family=args.family,
        caller_ring=args.ring,
        include_global=not args.strict_family,
        include_revoked=args.include_revoked,
        limit=args.limit,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_list(args):
    conn = connect_vault(_paths_for(args.db))
    where = "" if args.include_revoked else "WHERE status = 'active'"
    rows = conn.execute(
        f"SELECT key, authority, status, task_family, capability_ring, text FROM memories {where} ORDER BY key ASC LIMIT ?",
        (args.limit,),
    ).fetchall()
    conn.close()
    for r in rows:
        snippet = r["text"].replace("\n", " ")[:180]
        print(f"- [{r['key']}] ({r['authority']}|{r['status']}|{r['task_family']}|R{r['capability_ring']}): {snippet}")


def cmd_delete(args):
    conn = connect_vault(_paths_for(args.db))
    cur = conn.execute("DELETE FROM memories WHERE key = ?", (args.key.strip(),))
    conn.commit()
    conn.close()
    print(f"DELETED: {args.key.strip()} (rows={cur.rowcount})")


def cmd_stats(args):
    conn = connect_vault(_paths_for(args.db))
    active = conn.execute("SELECT COUNT(*) FROM memories WHERE status='active'").fetchone()[0]
    revoked = conn.execute("SELECT COUNT(*) FROM memories WHERE status='revoked'").fetchone()[0]
    evidence = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    conn.close()
    print(json.dumps({"db": args.db, "active": active, "revoked": revoked, "evidence": evidence}))


def main():
    p = argparse.ArgumentParser(description="AntiGem Scoped-ORC Revocable Memory Vault")
    p.add_argument("--db", default=DB_PATH)
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add")
    pa.add_argument("--key", required=True)
    pa.add_argument("--tags", default="")
    pa.add_argument("--text", required=True)
    pa.add_argument("--authority", choices=VALID_AUTHORITIES, default="verified_log")
    pa.add_argument("--family", default="general")
    pa.add_argument("--ring", type=int, default=R2_WORKSPACE)
    pa.add_argument("--origin", default="local://memory_vault")
    pa.add_argument("--global-override", action="store_true")
    pa.set_defaults(func=cmd_add)

    pr = sub.add_parser("revoke")
    pr.add_argument("--key", required=True)
    pr.add_argument("--superseded-by", default="")
    pr.set_defaults(func=cmd_revoke)

    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("--limit", type=int, default=8)
    ps.add_argument("--family", default=None)
    ps.add_argument("--ring", type=int, default=R2_WORKSPACE)
    ps.add_argument("--strict-family", action="store_true")
    ps.add_argument("--include-revoked", action="store_true")
    ps.set_defaults(func=cmd_search)

    pl = sub.add_parser("list")
    pl.add_argument("--limit", type=int, default=15)
    pl.add_argument("--include-revoked", action="store_true")
    pl.set_defaults(func=cmd_list)

    pd = sub.add_parser("delete")
    pd.add_argument("--key", required=True)
    pd.set_defaults(func=cmd_delete)

    pt = sub.add_parser("stats")
    pt.set_defaults(func=cmd_stats)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
