#!/usr/bin/env python3
"""Thin AntiGem PostToolUse adapter -> SHA-256 audit chain + SPIDES taint + GrepMem lossless log."""
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

from omega_core import ensure_dirs, get_paths
from omega_core.compact_anchor import update_anchor_from_tool
from omega_core.memory import KnowledgeFabric

MAX_AUDIT_LINES = 500
WEB_RX = re.compile(
    r"\b(?:web_gather\.py|deep_crawl\.py|search_web|read_url_content|omega\s+(?:crawl|research|feed)|curl|browser_)\b",
    re.IGNORECASE,
)
TEST_PASS_RX = re.compile(r"\b(?:unittest|pytest|omega\s+suite)\b", re.IGNORECASE)
WRITE_TOOL_NAMES = {"write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content"}


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
    cmd = str(args.get("CommandLine") or args.get("command") or args.get("Path") or args.get("TargetFile") or "")
    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("conversationId") or "default"))[:48] or "default"
    err = str(payload.get("error") or "")

    # Populate lossless post-compact anchor (<5ms, 0 LLM tokens) so /compact never loses verbatim paths/URLs/fails
    try:
        update_anchor_from_tool(conv_id, tool, args, ok=not bool(err), err=err, paths=paths)
    except Exception:
        pass

    cmd_hash = hashlib.sha256(f"{tool}:{cmd}".encode("utf-8")).hexdigest()[:16]
    prev = _last_hash(paths.audit_log)
    rec = {
        "ts": int(time.time()),
        "conv": conv_id,
        "tool": tool,
        "cmd_hash": cmd_hash,
        "cmd_preview": cmd[:120],
        "ok": not bool(err),
        "err": err[:160],
        "prev": prev,
    }
    rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True).encode("utf-8")).hexdigest()

    try:
        with open(paths.audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        with open(paths.audit_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_AUDIT_LINES + 100:
            tmp = paths.audit_log + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_AUDIT_LINES:])
            os.replace(tmp, paths.audit_log)
    except Exception:
        pass

    # Append compact record to GrepMem lossless exact-recall log
    try:
        kf = KnowledgeFabric(paths)
        kf.append_grepmem(
            "TOOL_CALL",
            {"tool": tool, "cmd_preview": cmd[:120], "ok": rec["ok"], "err": rec["err"]},
            task_family="runtime",
        )
    except Exception:
        pass

    # Update per-session SPIDES taint + repeat-failure tracker + Stop-hook verification state
    st_path = os.path.join(paths.state_dir, f"{conv_id}.json")
    state = {
        "tainted_web": False,
        "last_fail_hash": "",
        "fail_streak": 0,
        "code_edited": False,
        "tests_passed": False,
        "stop_continues": 0,
    }
    if os.path.exists(st_path):
        try:
            with open(st_path, "r", encoding="utf-8") as sf:
                state.update(json.load(sf))
        except Exception:
            pass

    if WEB_RX.search(tool) or WEB_RX.search(cmd):
        state["tainted_web"] = True
    if tool in WRITE_TOOL_NAMES and cmd.endswith(".py") and not err:
        state["code_edited"] = True
        state["tests_passed"] = False
        state["stop_continues"] = 0
    if tool == "run_command" and not err and TEST_PASS_RX.search(cmd):
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

    try:
        tmp = st_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, st_path)
    except Exception:
        pass

    print("{}")


if __name__ == "__main__":
    main()
