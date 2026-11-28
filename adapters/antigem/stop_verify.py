#!/usr/bin/env python3
"""AntiGem Stop Hook — Real Production Verification & Independent Skeptical Critic Gate (OMEGA APEX v9.0).

Fixes P0 live-runtime defect where `agy` emits `terminationReason: "NO_TOOL_CALL"` (and `continuationActive`)
rather than `"model_stop"`.

Execution flow (bounded, 0% Q&A false positives, zero infinite loops):
1. Short-circuits immediately when `fullyIdle == False`, `continuationActive == True`, or non-stop termination.
2. Checks code-edit verification state (`code_edited && !tests_passed` -> bounded max 2 continues).
3. Runs Tier-0 Millisecond Deterministic Skeptical Critic (`<5ms`, 0 LLM tokens) on `transcriptPath`:
   catches unverified victory claims ("everything is fixed / all tests pass" without verification),
   whitewashed tool errors, and skipped multi-part user requirements.
4. When `OMEGA_LIVE_CRITIC=1` (and `agy` CLI auth or `GEMINI_API_KEY` is configured), escalates
   substantive turns to an isolated separate Gemini model (`gemini-4-carbon-high`) once per user turn
   to critique the draft strictly against `lastUserInput` before allowing stop!
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any

_REPO = os.path.expanduser("~/projects/Absolute-max")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import OmegaPaths, atomic_json_write, ensure_dirs, get_paths, locked_file_op

MAX_STOP_CONTINUES = 2
MAX_CRITIC_CONTINUES = 1
VALID_STOP_REASONS = {"", "NO_TOOL_CALL", "EXECUTOR_TERMINATION_REASON_NO_TOOL_CALL", "model_stop"}


def evaluate_stop(payload: dict[str, Any], paths: OmegaPaths | None = None) -> dict[str, Any]:
    """Evaluate Stop hook: verify code edits + run skeptical critic against actual user request."""
    if not isinstance(payload, dict):
        return {"decision": "stop"}
    if not payload.get("fullyIdle", False):
        return {"decision": "stop"}
    if payload.get("continuationActive", False):
        return {"decision": "stop"}
    reason = str(payload.get("terminationReason") or "").strip()
    if reason not in VALID_STOP_REASONS:
        return {"decision": "stop"}

    p = paths or get_paths()
    ensure_dirs(p)
    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("conversationId") or "default"))[:48] or "default"
    st_path = os.path.join(p.state_dir, f"{conv_id}.json")
    tpath = str(payload.get("transcriptPath") or "").strip()
    last_user = str(payload.get("lastUserInput") or "").strip()

    def _eval_locked() -> dict[str, Any]:
        state: dict[str, Any] = {}
        if os.path.exists(st_path):
            try:
                with open(st_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    state = loaded
            except Exception:
                state = {}

        code_edited = bool(state.get("code_edited"))
        tests_passed = bool(state.get("tests_passed"))
        continues = int(state.get("stop_continues") or 0)

        # 1. Hard verification guard on unverified code edits (max 2 auto-continues)
        if code_edited and not tests_passed:
            if continues >= MAX_STOP_CONTINUES:
                return {"decision": "stop"}
            state["stop_continues"] = continues + 1
            try:
                atomic_json_write(st_path, state)
            except Exception:
                pass
            return {
                "decision": "continue",
                "reason": (
                    "[Omega Stop Verification Guard] Code files were modified without a verified passing test run "
                    "(`python3 -m unittest` / `pytest` / `omega suite`). Run verification tests before stopping."
                ),
            }

        # 2. Independent Skeptical Critic check on transcript (at most once per distinct user turn)
        if tpath and os.path.isfile(os.path.expanduser(tpath)):
            user_hash = hashlib.sha256((last_user or conv_id).encode("utf-8")).hexdigest()[:16]
            if state.get("last_critiqued_user_hash") == user_hash and int(state.get("critic_continues") or 0) >= MAX_CRITIC_CONTINUES:
                return {"decision": "stop"}

            from omega_core.critic import critique_response, extract_last_turn_from_transcript

            turn = extract_last_turn_from_transcript(tpath)
            req = last_user or turn["user_request"]
            draft = turn["assistant_response"]
            if len(draft) >= 240:
                live_llm = os.environ.get("OMEGA_LIVE_CRITIC", "0") == "1" and (len(draft) >= 600 or tests_passed)
                crit = critique_response(
                    req,
                    draft,
                    tool_events=turn["tool_events"],
                    failed_tools=turn["failed_tools"],
                    verification_ran=bool(turn["verification_ran"] or tests_passed),
                    code_edited=code_edited,
                    tests_passed=tests_passed,
                    use_llm=live_llm,
                    paths=p,
                )
                if crit.get("verdict") == "REVISE":
                    state["last_critiqued_user_hash"] = user_hash
                    state["critic_continues"] = int(state.get("critic_continues") or 0) + 1
                    try:
                        atomic_json_write(st_path, state)
                    except Exception:
                        pass
                    return {
                        "decision": "continue",
                        "reason": (
                            f"[OMEGA Independent Skeptical Critic ({crit.get('critic_model')}) -> REVISE] "
                            f"{crit.get('critique', '')[:500]}"
                        ),
                    }

        return {"decision": "stop"}

    return locked_file_op(st_path + ".lock", _eval_locked)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        print(json.dumps({"decision": "stop"}))
        return
    print(json.dumps(evaluate_stop(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
