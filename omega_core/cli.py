#!/usr/bin/env python3
"""Unified OMEGA APEX / Absolute Max OS Command Line Interface (`omega`)."""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure repo root is importable when invoked via symlink in ~/.local/bin/omega
_REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import R2_WORKSPACE, VERSION, get_paths
from omega_core.evo import EvolutionLab
from omega_core.fabric import IntelligenceFabric
from omega_core.kernel import evaluate_tool_call
from omega_core.memory import KnowledgeFabric
from omega_core.mission import MissionKernel
from omega_core.obsidian import DEFAULT_VAULT_DIR, ObsidianSync
from omega_core.research import ResearchEngine
from omega_core.suite import run_suite


def _jprint(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_status(args) -> None:
    paths = get_paths()
    mk = MissionKernel(paths)
    fab = IntelligenceFabric(paths)
    lab = EvolutionLab(paths)
    active = mk.list_missions(state="ACTIVE", limit=10)
    pending_apr = mk.list_approvals(status="PENDING")
    models = fab.list_models()
    base_models = fab.list_base_models()
    qualified_base = [m["base_model"] for m in base_models if m["qualification_state"] == "QUALIFIED"]
    _jprint(
        {
            "version": VERSION,
            "omega_home": paths.omega_home,
            "active_missions": len(active),
            "pending_approvals": len(pending_apr),
            "base_models_total": len(base_models),
            "base_models_qualified": len(qualified_base),
            "effort_endpoints_total": len(models),
            "qualified_base_models": qualified_base,
            "experiments_recorded": len(lab.list_experiments(limit=50)),
            "event_chain": mk.verify_event_chain(),
            "host_resources": fab.host_resources(),
        }
    )


def cmd_mission(args) -> None:
    mk = MissionKernel()
    if args.action == "new":
        m = mk.compile_intent(
            args.request,
            task_family=args.family,
            scope=args.scope or [],
            constraints=args.constraint or [],
            acceptance_criteria=args.accept or [],
            risk_class=args.risk,
        )
        _jprint(m)
    elif args.action == "list":
        _jprint(mk.list_missions(state=args.state, limit=args.limit))
    elif args.action == "show":
        _jprint(mk.get_mission(args.mission_id))
    elif args.action == "state":
        crec = json.loads(args.completion_json) if args.completion_json else None
        _jprint(mk.update_mission_state(args.mission_id, args.new_state, completion_record=crec))
    elif args.action == "checkpoint":
        _jprint(mk.create_checkpoint(args.mission_id))
    elif args.action == "restore":
        _jprint(mk.restore_checkpoint(args.checkpoint_id))


def cmd_problem(args) -> None:
    mk = MissionKernel()
    if args.action == "add":
        hyps = [{"proposal": h, "expected_benefit": 0.7} for h in (args.hypothesis or [])]
        _jprint(mk.add_problem(args.mission_id, args.blocker, severity=args.severity, hypotheses=hyps))
    elif args.action == "update":
        _jprint(
            mk.update_problem(
                args.problem_id,
                status=args.status,
                hypothesis_id=args.hypothesis_id,
                hypothesis_status=args.hypothesis_status,
                test_result=args.result,
                evidence_ref=args.evidence_ref,
            )
        )


def cmd_approve(args) -> None:
    mk = MissionKernel()
    if args.action == "list":
        _jprint(mk.list_approvals(status=None if args.all else "PENDING"))
    elif args.action in ("accept", "reject"):
        dec = "APPROVED" if args.action == "accept" else "REJECTED"
        _jprint(mk.resolve_approval(args.approval_id, dec, note=args.note))


def cmd_mem(args) -> None:
    kf = KnowledgeFabric()
    if args.action == "add":
        _jprint(
            kf.add_memory(
                args.key,
                args.text,
                tags=args.tags,
                authority=args.authority,
                task_family=args.family,
                capability_ring=args.ring,
                origin_uri=args.origin,
                global_override=args.global_override,
            )
        )
    elif args.action == "search":
        _jprint(
            kf.search_memory(
                args.query,
                task_family=args.family,
                caller_ring=args.ring,
                include_global=not args.strict_family,
                limit=args.limit,
            )
        )
    elif args.action == "revoke":
        _jprint(kf.revoke_memory(args.key, superseded_by=args.superseded_by))
    elif args.action == "grep":
        _jprint(kf.grep_history(args.pattern, task_family=args.family, mission_id=args.mission_id, limit=args.limit))
    elif args.action == "context":
        _jprint(
            kf.compile_context(
                task_family=args.family,
                mission_id=args.mission_id,
                caller_ring=args.ring,
                budget_chars=args.budget,
            )
        )


def cmd_models(args) -> None:
    fab = IntelligenceFabric()
    if args.action == "list":
        _jprint(fab.list_base_models() if not args.variants else fab.list_models())
    elif args.action == "sync":
        _jprint(fab.sync_live_catalog())
    elif args.action == "qualify":
        targets = args.models or [m["model_id"] for m in fab.list_models()]
        out = [fab.qualify_model(mid, timeout_s=args.timeout) for mid in targets]
        _jprint(out)
    elif args.action == "route":
        _jprint(fab.select_chain(args.task))


def cmd_obsidian(args) -> None:
    obs = ObsidianSync(vault_dir=args.vault)
    if args.action == "sync":
        _jprint(obs.sync_all(force_config=args.force_config))
    elif args.action == "ingest":
        _jprint(obs.ingest_user_notes())


def cmd_research(args) -> None:
    eng = ResearchEngine()
    _jprint(
        eng.run(
            args.question,
            mode=args.mode,
            urls=args.url or [],
            mission_id=args.mission_id,
            corpus_query=args.corpus_query,
            task_family=args.family,
            live_search=not args.no_live_search,
            web_ground=args.web_ground,
            challenge=True if args.challenge else (False if args.no_challenge else None),
            offline=args.offline,
            export_obsidian=args.obsidian,
        )
    )


def cmd_suite(args) -> None:
    paths = get_paths()
    out_md = os.path.join(paths.repo_root, "BASELINE.md") if args.write_baseline else None
    rep = run_suite(write_baseline_path=out_md)
    _jprint(rep)
    sys.exit(0 if rep["passed"] == rep["total"] else 1)


def cmd_gate(args) -> None:
    d = evaluate_tool_call(
        {"toolCall": {"name": "run_command", "args": {"CommandLine": args.command}}},
        caller_ring=args.ring,
    )
    _jprint(d.to_dict())


def cmd_ledger(args) -> None:
    paths = get_paths()
    lp = os.path.join(paths.repo_root, "ledger", "status.json")
    if not os.path.exists(lp):
        print(json.dumps({"error": "ledger_missing", "path": lp}))
        sys.exit(1)
    with open(lp, "r", encoding="utf-8") as f:
        print(f.read())


def cmd_dashboard(args) -> None:
    """Compact mobile-safe operator summary of missions, blockers, approvals, models, and host."""
    paths = get_paths()
    mk = MissionKernel(paths)
    fab = IntelligenceFabric(paths)
    missions = mk.list_missions(state="ACTIVE", limit=5)
    approvals = mk.list_approvals(status="PENDING")
    models = fab.list_models()
    res = fab.host_resources()
    chain = mk.verify_event_chain()

    print(f"OMEGA APEX / Absolute Max OS ({VERSION})")
    print(f"- Host: RAM {res.get('ram_avail_mb', 0)}/{res.get('ram_total_mb', 0)} MB | Disk free {res.get('disk_free_mb', 0)} MB | DB {res.get('omega_db_kb', 0)} KB | Cost $0.00")
    print(f"- Event chain: {'OK' if chain['ok'] else 'BROKEN'} ({chain['checked']} events)")
    print(f"- Active missions: {len(missions)}")
    for m in missions:
        full = mk.get_mission(m["mission_id"])
        open_p = [p for p in full.get("problems", []) if p["status"] in ("OPEN", "TESTING")]
        print(f"  * {m['mission_id']} [{m['task_family']}] {m['objective'][:70]} (open blockers: {len(open_p)})")
        for pr in open_p[:2]:
            print(f"    - [sev {pr['severity']}] {pr['blocker'][:70]}")
    print(f"- Pending approvals: {len(approvals)}")
    for a in approvals[:5]:
        print(f"  * {a['approval_id']} [{a['action_class']}] {a['summary'][:70]}")
    base_models = fab.list_base_models()
    q_base = [m for m in base_models if m["qualification_state"] == "QUALIFIED"]
    print(f"- Base Models: {len(q_base)}/{len(base_models)} QUALIFIED ({len(models)} effort-tier endpoints across 3 quota pools)")
    for bm in base_models:
        lat = f"{bm['best_latency_ms']:.0f}ms" if bm["best_latency_ms"] else "untested"
        tiers = ",".join(bm["effort_tiers"])
        print(f"  * {bm['base_model']} [{bm['quota_pool']}]: {bm['qualification_state']} ({lat}; tiers: {tiers})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="omega", description=f"OMEGA APEX / Absolute Max OS CLI ({VERSION})")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("status", help="System status, missions, approvals, resources")
    ps.set_defaults(func=cmd_status)

    # mission
    pm = sub.add_parser("mission", help="Manage missions and checkpoints")
    pm_sub = pm.add_subparsers(dest="action", required=True)
    pm_new = pm_sub.add_parser("new")
    pm_new.add_argument("request")
    pm_new.add_argument("--family", default="general")
    pm_new.add_argument("--scope", action="append")
    pm_new.add_argument("--constraint", action="append")
    pm_new.add_argument("--accept", action="append")
    pm_new.add_argument("--risk", default="LOW")
    pm_list = pm_sub.add_parser("list")
    pm_list.add_argument("--state", default=None)
    pm_list.add_argument("--limit", type=int, default=20)
    pm_show = pm_sub.add_parser("show")
    pm_show.add_argument("mission_id")
    pm_st = pm_sub.add_parser("state")
    pm_st.add_argument("mission_id")
    pm_st.add_argument("new_state")
    pm_st.add_argument("--completion-json", default="")
    pm_ckp = pm_sub.add_parser("checkpoint")
    pm_ckp.add_argument("mission_id")
    pm_rst = pm_sub.add_parser("restore")
    pm_rst.add_argument("checkpoint_id")
    pm.set_defaults(func=cmd_mission)

    # problem (Pro²)
    pp = sub.add_parser("problem", help="Manage Pro2 Problem State blockers & hypotheses")
    pp_sub = pp.add_subparsers(dest="action", required=True)
    pp_add = pp_sub.add_parser("add")
    pp_add.add_argument("mission_id")
    pp_add.add_argument("blocker")
    pp_add.add_argument("--severity", type=int, default=7)
    pp_add.add_argument("--hypothesis", action="append")
    pp_upd = pp_sub.add_parser("update")
    pp_upd.add_argument("problem_id")
    pp_upd.add_argument("--status", default=None)
    pp_upd.add_argument("--hypothesis-id", default=None)
    pp_upd.add_argument("--hypothesis-status", default=None)
    pp_upd.add_argument("--result", default=None)
    pp_upd.add_argument("--evidence-ref", default=None)
    pp.set_defaults(func=cmd_problem)

    # approve
    pa = sub.add_parser("approve", help="Manage PREPARE_ONLY approval queue")
    pa_sub = pa.add_subparsers(dest="action", required=True)
    pa_list = pa_sub.add_parser("list")
    pa_list.add_argument("--all", action="store_true")
    for act in ("accept", "reject"):
        p_act = pa_sub.add_parser(act)
        p_act.add_argument("approval_id")
        p_act.add_argument("--note", default="")
    pa.set_defaults(func=cmd_approve)

    # mem
    pk = sub.add_parser("mem", help="Scoped-ORC memory, GrepMem, and Context Compiler")
    pk_sub = pk.add_subparsers(dest="action", required=True)
    pk_add = pk_sub.add_parser("add")
    pk_add.add_argument("--key", required=True)
    pk_add.add_argument("--text", required=True)
    pk_add.add_argument("--tags", default="")
    pk_add.add_argument("--authority", default="verified_log")
    pk_add.add_argument("--family", default="general")
    pk_add.add_argument("--ring", type=int, default=R2_WORKSPACE)
    pk_add.add_argument("--origin", default="local://omega-cli")
    pk_add.add_argument("--global-override", action="store_true")
    pk_search = pk_sub.add_parser("search")
    pk_search.add_argument("query")
    pk_search.add_argument("--family", default=None)
    pk_search.add_argument("--ring", type=int, default=R2_WORKSPACE)
    pk_search.add_argument("--strict-family", action="store_true")
    pk_search.add_argument("--limit", type=int, default=8)
    pk_rev = pk_sub.add_parser("revoke")
    pk_rev.add_argument("--key", required=True)
    pk_rev.add_argument("--superseded-by", default="")
    pk_grep = pk_sub.add_parser("grep")
    pk_grep.add_argument("pattern")
    pk_grep.add_argument("--family", default=None)
    pk_grep.add_argument("--mission-id", default=None)
    pk_grep.add_argument("--limit", type=int, default=25)
    pk_ctx = pk_sub.add_parser("context")
    pk_ctx.add_argument("--family", default="general")
    pk_ctx.add_argument("--mission-id", default=None)
    pk_ctx.add_argument("--ring", type=int, default=R2_WORKSPACE)
    pk_ctx.add_argument("--budget", type=int, default=5600)
    pk.set_defaults(func=cmd_mem)

    # models
    pmod = sub.add_parser("models", help="Model qualification registry & routing")
    pmod_sub = pmod.add_subparsers(dest="action", required=True)
    pmod_l = pmod_sub.add_parser("list")
    pmod_l.add_argument("--variants", action="store_true", help="Show all effort-tier endpoints instead of grouped base models")
    pmod_sub.add_parser("sync")
    pmod_q = pmod_sub.add_parser("qualify")
    pmod_q.add_argument("models", nargs="*")
    pmod_q.add_argument("--timeout", type=int, default=25)
    pmod_r = pmod_sub.add_parser("route")
    pmod_r.add_argument("task")
    pmod.set_defaults(func=cmd_models)

    # research
    pr = sub.add_parser("research", help="Adaptive FAST/STANDARD/DEEP research with live web grounding")
    pr.add_argument("question")
    pr.add_argument("--mode", default="FAST", choices=["FAST", "STANDARD", "DEEP"])
    pr.add_argument("--url", action="append")
    pr.add_argument("--mission-id", default="")
    pr.add_argument("--corpus-query", default="")
    pr.add_argument("--family", default="general")
    pr.add_argument("--web-ground", action="store_true", help="Run live search_web grounded discovery pass")
    pr.add_argument("--no-live-search", action="store_true", help="Skip free live API URL discovery")
    pr.add_argument("--challenge", action="store_true", help="Force one-pass cross-family adversarial challenge")
    pr.add_argument("--no-challenge", action="store_true", help="Skip cross-family adversarial challenge")
    pr.add_argument("--offline", action="store_true", help="Prior memory + local corpus only")
    pr.add_argument("--obsidian", action="store_true", help="Export research dossier to Obsidian vault")
    pr.set_defaults(func=cmd_research)

    # obsidian
    po = sub.add_parser("obsidian", help="Two-way Obsidian Knowledge Graph & Canvas sync")
    po.add_argument("--vault", default=DEFAULT_VAULT_DIR)
    po_sub = po.add_subparsers(dest="action", required=True)
    po_sync = po_sub.add_parser("sync")
    po_sync.add_argument("--force-config", action="store_true", help="Overwrite .obsidian graph/theme settings")
    po_sub.add_parser("ingest")
    po.set_defaults(func=cmd_obsidian)

    # suite
    psu = sub.add_parser("suite", help="Run 10-Mission Integrated Acceptance Suite (A-J)")
    psu.add_argument("--write-baseline", action="store_true")
    psu.set_defaults(func=cmd_suite)

    # gate
    pg = sub.add_parser("gate", help="Dry-run Constitutional Gate on a command")
    pg.add_argument("command")
    pg.add_argument("--ring", type=int, default=R2_WORKSPACE)
    pg.set_defaults(func=cmd_gate)

    # ledger
    pl = sub.add_parser("ledger", help="Show Implementation Status Ledger")
    pl.set_defaults(func=cmd_ledger)

    pdash = sub.add_parser("dashboard", help="Compact mobile-safe live operator view")
    pdash.set_defaults(func=cmd_dashboard)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
