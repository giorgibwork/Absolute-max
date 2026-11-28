#!/usr/bin/env python3
"""Ultra-fast Flock-Safe AntiGem PostToolUse adapter (OMEGA APEX v9.0 — Zero SQLite DDL on hot path).

Eliminates the 80ms SQLite KnowledgeFabric init & parallel-hook race conditions:
- Flock-protected SHA-256 audit chain + bounded size-triggered rotation
- Flock-protected zero-SQLite GrepMem append (`append_grepmem_fast`)
- Flock-protected lossless post-compact anchor update
- Accurate SPIDES web-taint (ignores local `--query-only`) & accurate `tests_passed` tracking
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time

_REPO = os.path.expanduser("~/projects/Absolute-max")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import append_grepmem_fast, atomic_json_write, ensure_dirs, get_paths, locked_file_op
from omega_core.compact_anchor import update_anchor_from_tool

MAX_AUDIT_LINES = 500
WEB_RX = re.compile(
    r"\b(?:web_gather\.py|deep_crawl\.py|search_web|read_url_content|omega\s+(?:crawl|research|feed|expert\b[^\n]*--acquire)|curl|browser_)\b",
    re.IGNORECASE,
)
LOCAL_ONLY_RX = re.compile(r"--(?:query-only|offline|fast)\b", re.IGNORECASE)
TEST_EXEC_RX = re.compile(
    r"(?:^|[;&|]\s*)(?:python3?\s+-m\s+(?:unittest|pytest)|pytest\b|omega\s+suite\b)",
    re.IGNORECASE,
)
NON_TEST_PREFIX_RX = re.compile(r"^\s*(?:echo|printf|grep|rg|cat|head|tail|sed|awk)\b", re.IGNORECASE)
WRITE_TOOL_NAMES = {"write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content"}
CODE_EXTS = (".py", ".sh", ".js", ".ts")


def _last_hash(audit_path: str) -> str:
    if not os.path.exists(audit_path):
        return "0" * 64
    try:
        with open(audit_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            for ln in reversed(f.read().decode("utf-8", "replace").splitlines()):
                if ln.strip():
                    return json.loads(ln).get("hash", "0" * 64)
    except Exception:
        pass
    return "0" * 64


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        print("{}")
        return

    paths = get_paths()
    ensure_dirs(paths)

    tc = payload.get("toolCall") or {}
    tool = str(tc.get("name") or "")
    args = tc.get("args") or {}
    cmd = str(
        args.get("CommandLine")
        or args.get("command")
        or args.get("cmd")
        or args.get("Path")
        or args.get("TargetFile")
        or args.get("AbsolutePath")
        or args.get("file_path")
        or ""
    )
    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("conversationId") or "default"))[:48] or "default"
    err = str(payload.get("error") or "")

    # 1. Flock-safe lossless post-compact anchor update (<3ms, 0 LLM tokens)
    try:
        update_anchor_from_tool(conv_id, tool, args, ok=not bool(err), err=err, paths=paths)
    except Exception as e:
        sys.stderr.write(f"[omega post_tool_audit anchor_err] {type(e).__name__}: {e}\n")

    # 2. Flock-safe SHA-256 hash-chained audit log (rotates ONLY when >120KB, zero whole-file read per call)
    cmd_hash = hashlib.sha256(f"{tool}:{cmd}".encode("utf-8")).hexdigest()[:16]
    rec = {
        "ts": int(time.time()),
        "conv": conv_id,
        "tool": tool,
        "cmd_hash": cmd_hash,
        "cmd_preview": cmd[:120],
        "ok": not bool(err),
        "err": err[:160],
    }

    def _append_audit() -> None:
        rec["prev"] = _last_hash(paths.audit_log)
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()
        with open(paths.audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if os.path.getsize(paths.audit_log) > 120_000:
            with open(paths.audit_log, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if len(lines) > MAX_AUDIT_LINES + 100:
                tmp = f"{paths.audit_log}.{os.getpid()}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(lines[-MAX_AUDIT_LINES:])
                os.replace(tmp, paths.audit_log)

    try:
        locked_file_op(paths.audit_log + ".lock", _append_audit)
    except Exception as e:
        sys.stderr.write(f"[omega post_tool_audit log_err] {type(e).__name__}: {e}\n")

    # 3. Zero-SQLite flock-safe GrepMem append (<1ms)
    try:
        append_grepmem_fast(
            paths,
            "TOOL_CALL",
            {"tool": tool, "cmd_preview": cmd[:120], "ok": rec["ok"], "err": rec["err"]},
            task_family="runtime",
        )
    except Exception as e:
        sys.stderr.write(f"[omega post_tool_audit grepmem_err] {type(e).__name__}: {e}\n")

    # 4. Flock-safe per-session SPIDES taint + circuit-breaker + Stop-hook verification state
    st_path = os.path.join(paths.state_dir, f"{conv_id}.json")

    def _update_state() -> None:
        state = {
            "tainted_web": False,
            "last_fail_hash": "",
            "fail_streak": 0,
            "code_edited": False,
            "tests_passed": False,
            "stop_continues": 0,
            "critic_continues": 0,
            "last_critiqued_user_hash": "",
        }
        if os.path.exists(st_path):
            try:
                with open(st_path, "r", encoding="utf-8") as sf:
                    loaded = json.load(sf)
                if isinstance(loaded, dict):
                    state.update(loaded)
            except Exception:
                pass

        # Do NOT taint on local zero-network `--query-only` / `--offline` / `--fast` commands
        if (WEB_RX.search(tool) or WEB_RX.search(cmd)) and not LOCAL_ONLY_RX.search(cmd):
            state["tainted_web"] = True

        if tool in WRITE_TOOL_NAMES and cmd.endswith(CODE_EXTS) and not err:
            state["code_edited"] = True
            state["tests_passed"] = False
            state["stop_continues"] = 0

        if tool in ("run_command", "bash") and not err and TEST_EXEC_RX.search(cmd) and not NON_TEST_PREFIX_RX.match(cmd):
            state["tests_passed"] = True
            state["code_edited"] = False
            state["stop_continues"] = 0

        if err:
            if state.get("last_fail_hash") == cmd_hash:
                state["fail_streak"] = int(state.get("fail_streak", 0)) + 1
            else:
                state["last_fail_hash"] = cmd_hash
                state["fail_streak"] = 1
        else:
            state["last_fail_hash"] = ""
            state["fail_streak"] = 0

        atomic_json_write(st_path, state)

    try:
        locked_file_op(st_path + ".lock", _update_state)
    except Exception as e:
        sys.stderr.write(f"[omega post_tool_audit state_err] {type(e).__name__}: {e}\n")

    print("{}")


if __name__ == "__main__":
    main()
