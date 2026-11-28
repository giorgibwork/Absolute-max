#!/usr/bin/env python3
"""AntiGem Stop Hook — Deterministic Verification Guard (bounded max 2 auto-continues, 0% Q&A false positives).

Fires when Antigravity attempts to stop (`fullyIdle == True` and `terminationReason == "model_stop"`).
- If Python code was edited during the session and no test command (`unittest`/`pytest`/`omega suite`)
  has passed since the last edit -> returns `{"decision": "continue", "reason": ...}` (max 2 times).
- Pure Q&A turns or verified turns -> returns `{"decision": "stop"}` immediately (<15ms, 0 LLM tokens).
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

_REPO = os.path.expanduser("~/projects/Absolute-max")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import OmegaPaths, ensure_dirs, get_paths

MAX_STOP_CONTINUES = 2


def evaluate_stop(payload: dict[str, Any], paths: OmegaPaths | None = None) -> dict[str, Any]:
    """Return `{"decision": "continue", "reason": ...}` only when edits remain unverified."""
    if not isinstance(payload, dict):
        return {"decision": "stop"}
    if not payload.get("fullyIdle", False):
        return {"decision": "stop"}
    reason = str(payload.get("terminationReason") or "")
    if reason and reason != "model_stop":
        return {"decision": "stop"}

    p = paths or get_paths()
    ensure_dirs(p)
    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("conversationId") or "default"))[:48] or "default"
    st_path = os.path.join(p.state_dir, f"{conv_id}.json")
    if not os.path.exists(st_path):
        return {"decision": "stop"}

    try:
        with open(st_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        return {"decision": "stop"}

    if not state.get("code_edited") or state.get("tests_passed"):
        return {"decision": "stop"}

    continues = int(state.get("stop_continues") or 0)
    if continues >= MAX_STOP_CONTINUES:
        return {"decision": "stop"}

    state["stop_continues"] = continues + 1
    try:
        tmp = st_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, st_path)
    except Exception:
        pass

    return {
        "decision": "continue",
        "reason": (
            "[Omega Stop Verification Guard] Python files were modified in this session without a verified "
            "passing test run (`python3 -m unittest` / `pytest` / `omega suite`). Run verification tests before stopping."
        ),
    }


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
