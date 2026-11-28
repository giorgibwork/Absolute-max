#!/usr/bin/env python3
"""KV-Cache-Stable AntiGem SessionStart adapter (OMEGA APEX v9.0).

Maximizes Gemini 4 Neon 95%-discount Implicit Prefix Caching by keeping Step 0
100% deterministic & static (`task_family="global"`, no cross-session mutable mission
bleed into unrelated chats or subagents). Dynamic memories & forged expert skills
auto-hydrate on-demand per turn via PreInvocation JIT hydration.
"""
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


def main() -> None:
    try:
        _ = sys.stdin.read()
    except Exception:
        pass

    # Keep permanent Gemini App MCP bridge awake (guarded by flock inside start_mcp_bridge.sh)
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.08):
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

    # Strictly deterministic static global L1 prefix -> maximizes cross-turn & cross-session KV-cache hits!
    kf = KnowledgeFabric()
    compiled = kf.compile_context(
        task_family="global",
        mission_id=None,
        caller_ring=R2_WORKSPACE,
        budget_chars=2200,
        telegraphic=True,
    )
    ctx = compiled["context"].strip()
    if not ctx:
        print("{}")
        return
    print(json.dumps({"injectSteps": [{"systemMessage": {"systemMessage": ctx}}]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
