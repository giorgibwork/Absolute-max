#!/usr/bin/env python3
"""Thin AntiGem PreToolUse adapter -> omega_core.kernel.evaluate_tool_call (fail-closed)."""
from __future__ import annotations

import json
import os
import sys

_REPO = os.path.expanduser("~/projects/Absolute-max")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import R2_WORKSPACE
from omega_core.kernel import evaluate_tool_call


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        # Empty stdin on dry hook ping -> fail-closed unless explicit empty object
        print(json.dumps({"decision": "deny", "reason": "Fail-closed PreToolUse gate: empty hook payload."}))
        return
    try:
        payload = json.loads(raw)
        parse_err = False
    except Exception:
        payload = None
        parse_err = True

    ring = int(os.environ.get("OMEGA_CALLER_RING", str(R2_WORKSPACE)))
    dec = evaluate_tool_call(payload, caller_ring=ring, raw_parse_error=parse_err)
    print(json.dumps(dec.to_hook_json(), ensure_ascii=False))


if __name__ == "__main__":
    main()
