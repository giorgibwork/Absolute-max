#!/usr/bin/env python3
"""Unified OMEGA APEX / Absolute Max OS v9.0 Command Line Interface (`omega`).

Zero eager submodule imports: every subcommand lazy-imports ONLY the single module
it needs, slashing CLI cold-start latency by >100ms on Android.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Ensure repo root is importable when invoked via symlink in ~/.local/bin/omega
_REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_VENV_DIR = os.path.join(_REPO, ".venv")
_VENV_PY = os.path.join(_VENV_DIR, "bin", "python3")

# Auto-upgrade to isolated .venv ONLY for live-network/parser commands (NEVER double-exec for --query-only / --offline / --fast!)
_argv = sys.argv[1:]
_cmd = _argv[0] if _argv else ""
_needs_venv = (
    (_cmd in ("feed", "yt", "doc"))
    or (_cmd == "crawl" and "--query-only" not in _argv)
    or (_cmd == "research" and "--offline" not in _argv)
    or (_cmd == "expert" and "--acquire" in _argv)
)
if (
    _needs_venv
    and os.path.isfile(_VENV_PY)
    and os.path.realpath(sys.prefix) != os.path.realpath(_VENV_DIR)
):
    os.execv(_VENV_PY, [_VENV_PY, os.path.realpath(__file__), *_argv])

if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import R2_WORKSPACE, VERSION, get_paths


def _jprint(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_status(args) -> None:
    from omega_core.evo import EvolutionLab
    from omega_core.fabric import IntelligenceFabric
    from omega_core.mission import MissionKernel

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
            "primary_model": "gemini-4-neon-xhigh",
            "critic_model": "gemini-4-carbon-high",
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
    from omega_core.mission import MissionKernel

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
    from omega_core.mission import MissionKernel

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
    from omega_core.mission import MissionKernel

    mk = MissionKernel()
    if args.action == "list":
        _jprint(mk.list_approvals(status=None if args.all else "PENDING"))
    elif args.action in ("accept", "reject"):
        dec = "APPROVED" if args.action == "accept" else "REJECTED"
        _jprint(mk.resolve_approval(args.approval_id, dec, note=args.note))


def cmd_mem(args) -> None:
    from omega_core.memory import KnowledgeFabric

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
    elif args.action == "graph":
        _jprint(
            kf.graph_search(
                args.query,
                task_family=args.family,
                caller_ring=args.ring,
                hops=args.hops,
                limit=args.limit,
            )
        )
    elif args.action == "link":
        _jprint(kf.link_memories(args.src, args.rel, args.dst, weight=args.weight))
    elif args.action == "feedback":
        _jprint(kf.record_memory_feedback(args.key, positive=(args.outcome == "pos"), note=args.note))


def cmd_models(args) -> None:
    from omega_core.fabric import IntelligenceFabric

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
    from omega_core.obsidian import ObsidianSync

    obs = ObsidianSync(vault_dir=args.vault)
    if args.action == "sync":
        _jprint(obs.sync_all(force_config=args.force_config))
    elif args.action == "ingest":
        _jprint(obs.ingest_user_notes())


def cmd_code(args) -> None:
    from omega_core.codegraph import CodeGraph

    cg = CodeGraph()
    if args.action == "index":
        _jprint(cg.index_directory(args.directory))
    elif args.action == "find":
        _jprint(cg.find_symbol(args.query, limit=args.limit))
    elif args.action == "callers":
        _jprint(cg.trace_callers(args.symbol, max_hops=args.hops, limit=args.limit))
    elif args.action == "outline":
        _jprint(cg.file_outline(args.file))


def cmd_dream(args) -> None:
    from omega_core.dream import DreamEngine

    de = DreamEngine()
    if args.action == "run":
        _jprint(de.run_dream(sync_obsidian=not args.no_obsidian, index_code=not args.no_code))
    elif args.action == "failures":
        _jprint(de.list_failure_signatures(limit=args.limit))


def cmd_calc(args) -> None:
    from omega_core.bavar import verified_calc

    _jprint(verified_calc(args.expression, label=args.label, mission_id=args.mission_id, record_evidence=not args.no_record))


def cmd_bavar(args) -> None:
    from omega_core.bavar import allocate_verification

    _jprint(
        allocate_verification(
            args.action_class,
            uncertainty=args.uncertainty,
            irreversible=args.irreversible,
            budget_remaining=args.budget,
        )
    )


def cmd_mcp_mode(args) -> None:
    import subprocess

    toggle = os.path.expanduser("~/tools/mcp_toggle.py")
    if not os.path.isfile(toggle):
        _jprint({"ok": False, "error": f"missing:{toggle}"})
        sys.exit(1)
    r_st = subprocess.run(["python3", toggle, "status"], capture_output=True, text=True, timeout=5)
    configured = set()
    try:
        st_obj = json.loads(r_st.stdout)
        configured = set((st_obj.get("servers") or {}).keys())
    except Exception:
        pass
    if args.mode == "light":
        targets = [("disable", s) for s in ("browser_mcp", "gemini-api-docs", "google-developer-knowledge") if s in configured]
    elif args.mode == "ultra":
        targets = [("disable", s) for s in configured]
    else:
        targets = [("enable", s) for s in configured]
    if not configured:
        _jprint({"ok": True, "mode": args.mode, "configured_servers": [], "note": "No MCP servers configured in mcp_config.json (0 schema tokens)."})
        return
    for action, srv in targets:
        subprocess.run(["python3", toggle, action, srv], capture_output=True, text=True, timeout=5)
    r = subprocess.run(["python3", toggle, "status"], capture_output=True, text=True, timeout=5)
    print(r.stdout.strip())


def cmd_crawl(args) -> None:
    from omega_core.omni import bulk_crawl, query_local_corpus

    if args.query_only:
        _jprint(query_local_corpus(args.topic, top_k=args.top))
    else:
        _jprint(bulk_crawl(args.topic, target_pages=args.pages, follow_bfs_pages=args.bfs, max_workers=args.workers, top_k=args.top))


def cmd_yt(args) -> None:
    from omega_core.omni import fetch_youtube_transcript

    _jprint(fetch_youtube_transcript(args.url))


def cmd_doc(args) -> None:
    from omega_core.omni import read_document

    _jprint(read_document(args.path, max_chars=args.max_chars))


def cmd_handoff(args) -> None:
    from omega_core.rtk import generate_handoff

    _jprint(generate_handoff(note=args.note))


def cmd_dag(args) -> None:
    from omega_core.dag import MissionDAG

    dag = MissionDAG(args.mission_id)
    if args.action == "add":
        _jprint(dag.add_task(args.task_id, args.title, depends_on=args.depends_on or []))
    elif args.action == "list":
        _jprint(dag.list_tasks())
    elif args.action == "validate":
        _jprint({"ok": True, "topo_order": dag.validate_acyclic(), "ready": [t["task_id"] for t in dag.ready_tasks()]})


def cmd_forge(args) -> None:
    from omega_core.forge import SkillForge

    sf = SkillForge()
    if args.action == "admit":
        _jprint(
            sf.admit_skill(
                args.skill_id,
                args.trigger,
                args.procedure,
                expected_outcome=args.expected,
                task_family=args.family,
                evidence_ref=args.evidence_ref,
                verification_passed=args.verified,
            )
        )
    elif args.action == "match":
        _jprint(sf.match_skills(args.query, task_family=args.family, limit=args.limit))
    elif args.action == "outcome":
        _jprint(sf.record_outcome(args.skill_id, success=(args.result == "pos")))
    elif args.action == "prune":
        _jprint(sf.prune_dead_skills())


def cmd_rtk(args) -> None:
    from omega_core.rtk import run_compressed

    cmd = list(args.command or [])
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise SystemExit("omega rtk requires a command to run")
    res = run_compressed(cmd, timeout_s=args.timeout)
    print(res["text"])
    print(f"[RTK rc={res['rc']} ms={res['ms']} saved={res['saved_pct']}% ({res['orig_chars']}->{res['compressed_chars']} chars)]")
    sys.exit(res["rc"])


def cmd_feed(args) -> None:
    from omega_core.omni import ingest_ai_pulse

    _jprint(ingest_ai_pulse(query=args.query, limit=args.limit))


def cmd_research(args) -> None:
    from omega_core.research import ResearchEngine

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


def cmd_critic(args) -> None:
    from omega_core.critic import critique_response, extract_last_turn_from_transcript

    req = args.request or ""
    draft = args.draft or ""
    tool_events: list[str] = []
    failed_tools: list[str] = []
    ver_ran = False
    if args.transcript:
        turn = extract_last_turn_from_transcript(args.transcript)
        req = req or turn["user_request"]
        draft = draft or turn["assistant_response"]
        tool_events = turn["tool_events"]
        failed_tools = turn["failed_tools"]
        ver_ran = bool(turn["verification_ran"])
    if args.draft_file and os.path.isfile(os.path.expanduser(args.draft_file)):
        with open(os.path.expanduser(args.draft_file), "r", encoding="utf-8", errors="replace") as f:
            draft = f.read()

    res = critique_response(
        req,
        draft,
        tool_events=tool_events,
        failed_tools=failed_tools,
        verification_ran=ver_ran,
        use_llm=args.llm,
        critic_model=args.model,
        timeout_s=args.timeout,
    )
    _jprint(res)
    sys.exit(0 if res.get("verdict") == "PASS" else 2)


def cmd_expert(args) -> None:
    from omega_core.expert import build_expert_brief

    res = build_expert_brief(
        args.topic,
        acquire=args.acquire,
        auto_acquire_if_cold=(not args.fast and not args.acquire),
        pages=args.pages,
        top_k=args.top,
        save_skill=not args.no_save,
        export_obsidian=args.obsidian,
    )
    if args.markdown:
        print(res["brief_markdown"])
    else:
        _jprint(res)


def cmd_suite(args) -> None:
    from omega_core.suite import run_suite

    paths = get_paths()
    out_md = os.path.join(paths.repo_root, "BASELINE.md") if args.write_baseline else None
    rep = run_suite(write_baseline_path=out_md)
    _jprint(rep)
    sys.exit(0 if rep["passed"] == rep["total"] else 1)


def cmd_gate(args) -> None:
    from omega_core.kernel import evaluate_tool_call

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
    from omega_core.fabric import IntelligenceFabric
    from omega_core.mission import MissionKernel

    paths = get_paths()
    mk = MissionKernel(paths)
    fab = IntelligenceFabric(paths)
    missions = mk.list_missions(state="ACTIVE", limit=5)
    approvals = mk.list_approvals(status="PENDING")
    models = fab.list_models()
    res = fab.host_resources()
    chain = mk.verify_event_chain()

    print(f"OMEGA APEX / Absolute Max OS ({VERSION})")
    print(f"- Primary: gemini-4-neon-xhigh | Critic: gemini-4-carbon-high | Cost $0.00")
    print(f"- Host: RAM {res.get('ram_avail_mb', 0)}/{res.get('ram_total_mb', 0)} MB | Disk free {res.get('disk_free_mb', 0)} MB | DB {res.get('omega_db_kb', 0)} KB")
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
    pools = {b["quota_pool"] for b in base_models}
    print(f"- Base Models: {len(q_base)}/{len(base_models)} QUALIFIED ({len(models)} effort-tier endpoints across {len(pools)} Gemini quota pools)")
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

    # problem (Pro2)
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
    pk_gr = pk_sub.add_parser("graph")
    pk_gr.add_argument("query")
    pk_gr.add_argument("--family", default=None)
    pk_gr.add_argument("--ring", type=int, default=R2_WORKSPACE)
    pk_gr.add_argument("--hops", type=int, default=2)
    pk_gr.add_argument("--limit", type=int, default=10)
    pk_lk = pk_sub.add_parser("link")
    pk_lk.add_argument("src")
    pk_lk.add_argument("rel")
    pk_lk.add_argument("dst")
    pk_lk.add_argument("--weight", type=float, default=1.0)
    pk_fb = pk_sub.add_parser("feedback")
    pk_fb.add_argument("key")
    pk_fb.add_argument("--outcome", choices=["pos", "neg"], required=True)
    pk_fb.add_argument("--note", default="")
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
    pr.add_argument("--web-ground", action="store_true")
    pr.add_argument("--no-live-search", action="store_true")
    pr.add_argument("--challenge", action="store_true")
    pr.add_argument("--no-challenge", action="store_true")
    pr.add_argument("--offline", action="store_true")
    pr.add_argument("--obsidian", action="store_true")
    pr.set_defaults(func=cmd_research)

    # critic (Independent Skeptical Critic Engine)
    pcrit = sub.add_parser("critic", help="Independent skeptical critique against user request (<5ms deterministic or separate Gemini model)")
    pcrit.add_argument("--request", default="", help="User original request text")
    pcrit.add_argument("--draft", default="", help="Draft answer text to critique")
    pcrit.add_argument("--draft-file", default="", help="Path to Markdown/text draft file to critique")
    pcrit.add_argument("--transcript", default="", help="Path to Antigravity transcript.jsonl to extract last turn")
    pcrit.add_argument("--llm", action="store_true", help="Escalate to isolated separate Gemini critic model (`agy -p` or `GEMINI_API_KEY`)")
    pcrit.add_argument("--model", default="gemini-4-carbon-high")
    pcrit.add_argument("--timeout", type=int, default=35)
    pcrit.set_defaults(func=cmd_critic)

    # expert (Universal Instant-Expert Domain Engine)
    pexp = sub.add_parser("expert", help="Instant domain-expert briefing & zero-token 18-lane playbook acquisition for ANY topic")
    pexp.add_argument("topic")
    pexp.add_argument("--fast", action="store_true", help="Warm local-only lookup (<5ms, 0 network, 0 LLM tokens)")
    pexp.add_argument("--acquire", action="store_true", help="Force live 18-lane multilingual + hostile crawl & forge reusable SkillForge playbook")
    pexp.add_argument("--pages", type=int, default=120)
    pexp.add_argument("--top", type=int, default=10)
    pexp.add_argument("--no-save", action="store_true")
    pexp.add_argument("--obsidian", action="store_true")
    pexp.add_argument("--markdown", action="store_true", help="Print formatted expert Markdown brief directly")
    pexp.set_defaults(func=cmd_expert)

    # obsidian
    po = sub.add_parser("obsidian", help="Two-way Obsidian Knowledge Graph & Canvas sync")
    po.add_argument("--vault", default="/sdcard/Documents/OmegaVault")
    po_sub = po.add_subparsers(dest="action", required=True)
    po_sync = po_sub.add_parser("sync")
    po_sync.add_argument("--force-config", action="store_true")
    po_sub.add_parser("ingest")
    po.set_defaults(func=cmd_obsidian)

    # code (AST CodeGraph)
    pc = sub.add_parser("code", help="Vectorless AST Code-Graph & Recursive-CTE caller navigator")
    pc_sub = pc.add_subparsers(dest="action", required=True)
    pc_i = pc_sub.add_parser("index")
    pc_i.add_argument("directory", nargs="?", default=os.path.expanduser("~/projects/Absolute-max/omega_core"))
    pc_f = pc_sub.add_parser("find")
    pc_f.add_argument("query")
    pc_f.add_argument("--limit", type=int, default=12)
    pc_c = pc_sub.add_parser("callers")
    pc_c.add_argument("symbol")
    pc_c.add_argument("--hops", type=int, default=2)
    pc_c.add_argument("--limit", type=int, default=25)
    pc_o = pc_sub.add_parser("outline")
    pc_o.add_argument("file")
    pc.set_defaults(func=cmd_code)

    # dream
    pdrm = sub.add_parser("dream", help="Offline Dreaming consolidation & failure-signature clustering")
    pdrm_sub = pdrm.add_subparsers(dest="action", required=True)
    pdrm_r = pdrm_sub.add_parser("run")
    pdrm_r.add_argument("--no-obsidian", action="store_true")
    pdrm_r.add_argument("--no-code", action="store_true")
    pdrm_f = pdrm_sub.add_parser("failures")
    pdrm_f.add_argument("--limit", type=int, default=15)
    pdrm.set_defaults(func=cmd_dream)

    # calc
    pcalc = sub.add_parser("calc", help="FinVeriQA deterministic Python AST calculator with evidence logging")
    pcalc.add_argument("expression")
    pcalc.add_argument("--label", default="calculation")
    pcalc.add_argument("--mission-id", default="")
    pcalc.add_argument("--no-record", action="store_true")
    pcalc.set_defaults(func=cmd_calc)

    # bavar
    pbav = sub.add_parser("bavar", help="BAVAR adaptive verification tier allocator")
    pbav.add_argument("action_class")
    pbav.add_argument("--uncertainty", type=float, default=0.2)
    pbav.add_argument("--irreversible", action="store_true")
    pbav.add_argument("--budget", type=float, default=1.0)
    pbav.set_defaults(func=cmd_bavar)

    # mcp-mode
    pmcp = sub.add_parser("mcp-mode", help="Toggle MCP server profile (light, ultra, full) to save context tokens")
    pmcp.add_argument("mode", choices=["light", "ultra", "full"])
    pmcp.set_defaults(func=cmd_mcp_mode)

    # crawl
    pcr = sub.add_parser("crawl", help="Bulk-crawl up to 500+ public pages into local SQLite FTS5 (0 LLM tokens)")
    pcr.add_argument("topic")
    pcr.add_argument("--pages", type=int, default=500)
    pcr.add_argument("--bfs", type=int, default=80)
    pcr.add_argument("--workers", type=int, default=16)
    pcr.add_argument("--top", type=int, default=8)
    pcr.add_argument("--query-only", action="store_true")
    pcr.set_defaults(func=cmd_crawl)

    # feed
    pfd = sub.add_parser("feed", help="Ingest live AI X/Twitter digest & multilingual practitioner feeds into local FTS5 (0 LLM tokens)")
    pfd.add_argument("--query", default="")
    pfd.add_argument("--limit", type=int, default=12)
    pfd.set_defaults(func=cmd_feed)

    # yt
    pyt = sub.add_parser("yt", help="Fetch instant timestamped YouTube captions (<1.5s, 0 download)")
    pyt.add_argument("url")
    pyt.set_defaults(func=cmd_yt)

    # doc
    pdc = sub.add_parser("doc", help="Read PDF, DOCX, XLSX, or text document cleanly")
    pdc.add_argument("path")
    pdc.add_argument("--max-chars", type=int, default=12000)
    pdc.set_defaults(func=cmd_doc)

    # handoff
    pho = sub.add_parser("handoff", help="Generate <750-char Session Handoff Card for fresh chat")
    pho.add_argument("--note", default="")
    pho.set_defaults(func=cmd_handoff)

    # rtk
    prtk = sub.add_parser("rtk", help="Run a command with RTK stdout compression (strips progress spam, keeps all errors)")
    prtk.add_argument("--timeout", type=int, default=30)
    prtk.add_argument("command", nargs=argparse.REMAINDER)
    prtk.set_defaults(func=cmd_rtk)

    # dag
    pdag = sub.add_parser("dag", help="Manage crash-resumable Mission Task DAGs (OAPX-SYS-05)")
    pdag_sub = pdag.add_subparsers(dest="action", required=True)
    pdag_add = pdag_sub.add_parser("add")
    pdag_add.add_argument("mission_id")
    pdag_add.add_argument("task_id")
    pdag_add.add_argument("title")
    pdag_add.add_argument("--depends-on", action="append")
    pdag_ls = pdag_sub.add_parser("list")
    pdag_ls.add_argument("mission_id")
    pdag_val = pdag_sub.add_parser("validate")
    pdag_val.add_argument("mission_id")
    pdag.set_defaults(func=cmd_dag)

    # forge
    pfg = sub.add_parser("forge", help="ANCHOR-gated executable Skill Forge (Doctrine §30)")
    pfg_sub = pfg.add_subparsers(dest="action", required=True)
    pfg_adm = pfg_sub.add_parser("admit")
    pfg_adm.add_argument("skill_id")
    pfg_adm.add_argument("--trigger", required=True)
    pfg_adm.add_argument("--procedure", required=True)
    pfg_adm.add_argument("--expected", default="")
    pfg_adm.add_argument("--family", default="general")
    pfg_adm.add_argument("--evidence-ref", default="")
    pfg_adm.add_argument("--verified", action="store_true")
    pfg_m = pfg_sub.add_parser("match")
    pfg_m.add_argument("query")
    pfg_m.add_argument("--family", default=None)
    pfg_m.add_argument("--limit", type=int, default=5)
    pfg_out = pfg_sub.add_parser("outcome")
    pfg_out.add_argument("skill_id")
    pfg_out.add_argument("--result", choices=["pos", "neg"], required=True)
    pfg_sub.add_parser("prune")
    pfg.set_defaults(func=cmd_forge)

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
