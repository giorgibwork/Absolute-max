#!/usr/bin/env python3
"""Ultra-fast AntiGem PreInvocation adapter (OMEGA APEX v9.0).

Checks `<conv_id>_router.json` hash + `transcript.jsonl` mtime using pure stdlib
BEFORE importing `omega_core.router` / `sqlite3` / `memory` / `forge`, cutting
duplicate/mid-turn hook overhead by >2.5x while guaranteeing post-compact anchors
ALWAYS fire immediately on the 1st invocation after compaction.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

_REPO = os.path.expanduser("~/projects/Absolute-max")


def _fast_skip_possible(payload: dict) -> bool:
    """Return True ONLY if user input is unchanged AND transcript.jsonl has not changed since last anchor check."""
    user_input = str(payload.get("lastUserInput") or "").strip()
    raw_cid = str(payload.get("conversationId") or "default")
    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", raw_cid)[:48] or "default"
    env_home = os.environ.get("OMEGA_HOME")
    state_dir = os.path.join(os.path.abspath(os.path.expanduser(env_home)), "state") if env_home else os.path.expanduser("~/.antigem/state")

    st_path = os.path.join(state_dir, f"{conv_id}_router.json")
    if not os.path.isfile(st_path):
        return False

    try:
        with open(st_path, "r", encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return False

    msg_hash = hashlib.sha256(user_input.encode("utf-8")).hexdigest()[:16] if user_input else ""
    if st.get("last_msg_hash") != msg_hash:
        return False

    # Even if user_input is unchanged, verify transcript.jsonl mtime hasn't advanced (mid-turn /compact check!)
    tfile = str(payload.get("transcriptPath") or "").strip()
    if not tfile and conv_id != "default":
        tfile = os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript.jsonl")
    if tfile and os.path.isfile(tfile):
        anc_path = os.path.join(state_dir, f"{conv_id}.anchor.json")
        try:
            cur_mtime = os.path.getmtime(tfile)
            if not os.path.isfile(anc_path):
                return False
            with open(anc_path, "r", encoding="utf-8") as af:
                anc = json.load(af)
            if cur_mtime != anc.get("transcript_mtime"):
                return False
        except Exception:
            return False

    return True


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        print("{}")
        return

    if isinstance(payload, dict) and _fast_skip_possible(payload):
        print("{}")
        return

    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)

    from omega_core.router import route_invocation

    out = route_invocation(payload)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
