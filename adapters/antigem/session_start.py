#!/usr/bin/env python3
"""Thin AntiGem SessionStart adapter -> omega_core.memory.KnowledgeFabric.compile_context + bridge auto-wake."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys

_REPO = os.path.expanduser("~/projects/Absolute-max")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core import R2_WORKSPACE
from omega_core.memory import KnowledgeFabric
from omega_core.mission import MissionKernel


def main() -> None:
    try:
        _ = sys.stdin.read()
    except Exception:
        pass

    # Keep permanent Gemini App MCP bridge awake
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.15):
            pass
    except OSError:
        bridge = os.path.expanduser("~/start_mcp_bridge.sh")
        if os.path.exists(bridge):
            subprocess.Popen(
                ["sh", bridge],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    # Pick latest ACTIVE mission if any so problem state carries across sessions
    active_mid = None
    active_family = "global"
    try:
        mk = MissionKernel()
        active = mk.list_missions(state="ACTIVE", limit=1)
        if active:
            active_mid = active[0]["mission_id"]
            active_family = active[0].get("task_family") or "general"
    except Exception:
        pass

    kf = KnowledgeFabric()
    compiled = kf.compile_context(
        task_family=active_family,
        mission_id=active_mid,
        caller_ring=R2_WORKSPACE,
        budget_chars=2400,
        telegraphic=True,
    )
    ctx = compiled["context"].strip()
    if not ctx:
        print("{}")
        return
    print(json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": ctx}}]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
