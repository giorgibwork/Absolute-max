#!/usr/bin/env python3
"""Thin AntiGem PreInvocation adapter -> omega_core.router.route_invocation (natural speech -> silent OMEGA tools)."""
from __future__ import annotations

import json
import os
import sys

_REPO = os.path.expanduser("~/projects/Absolute-max")
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from omega_core.router import route_invocation


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        print("{}")
        return

    out = route_invocation(payload)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
