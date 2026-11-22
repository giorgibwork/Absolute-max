"""Natural-Language Intent Auto-Router for OMEGA APEX / Absolute Max OS.

Translates Giorgi's everyday English / voice notes into behind-the-scenes
OMEGA tool routing (FAST/DEEP live grounded research, Mission Kernel,
Dashboard, Debug Protocol) — so the operator NEVER has to type CLI flags.

Deduplicates per (conversationId, lastUserInput) so each user message triggers
routing at most once (zero mid-turn prompt spam).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from . import OmegaPaths, ensure_dirs, get_paths

DEEP_RESEARCH_RX = re.compile(
    r"\b(?:deep\s+research|dig\s+deep|full\s+breakdown|investigate\s+deeply|maximize|optimize|absolute\s+ceiling|eye\s+of\s+god|research\s+everything|comprehensive\s+research)\b",
    re.IGNORECASE,
)

FAST_RESEARCH_RX = re.compile(
    r"\b(?:research|look\s+up|check\s+online|search\s+for|what'?s\s+new|latest|newest|current|right\s+now|price\s+of|release\s+date|compare)\b",
    re.IGNORECASE,
)

MISSION_RX = re.compile(
    r"\b(?:start\s+a\s+mission|new\s+mission|track\s+this|big\s+project|multi[- ]step\s+project|keep\s+track\s+of)\b",
    re.IGNORECASE,
)

STATUS_RX = re.compile(
    r"\b(?:how\s+are\s+our\s+tools|check\s+status|system\s+health|dashboard|pending\s+approvals|what'?s\s+running)\b",
    re.IGNORECASE,
)

OBSIDIAN_RX = re.compile(
    r"\b(?:obsidian|sync\s+my\s+(?:vault|notes)|update\s+my\s+vault|inbox\s+notes|knowledge\s+graph)\b",
    re.IGNORECASE,
)

DEBUG_RX = re.compile(
    r"\b(?:debug|broken|not\s+working|fix\s+this|timeout|502|503|crash|bug|patch|error)\b",
    re.IGNORECASE,
)


def classify_user_intent(user_input: str) -> list[dict[str, str]]:
    """Map natural everyday phrasing to internal OMEGA directives."""
    txt = (user_input or "").strip()
    if not txt:
        return []

    routes: list[dict[str, str]] = []
    if DEEP_RESEARCH_RX.search(txt):
        routes.append(
            {
                "intent": "DEEP_RESEARCH",
                "directive": (
                    "[Omega Intent -> DEEP Research] User asked for deep research/optimization in natural language. "
                    "Run live web grounding FIRST (search_web + ~/tools/web_gather.py + omega research --mode DEEP if useful), "
                    "challenge with a cross-family model (claude_gpt pool), pass non_consensus_gate, and reply in plain English. "
                    "Do NOT tell the user to type CLI commands."
                ),
            }
        )
    elif FAST_RESEARCH_RX.search(txt):
        routes.append(
            {
                "intent": "FAST_RESEARCH",
                "directive": (
                    "[Omega Intent -> FAST Research] User wants fresh/factual info. "
                    "Ground with live web search (search_web / omega research --mode FAST) before answering — never rely on stale training weights. "
                    "Verify material claims once, stop when sufficient, and reply in plain English without asking the user to run CLI commands."
                ),
            }
        )

    if MISSION_RX.search(txt):
        routes.append(
            {
                "intent": "MISSION",
                "directive": (
                    "[Omega Intent -> Mission Kernel] Silently track this goal via `omega mission new` and `omega problem add` "
                    "behind the scenes so state survives across sessions. Do not make the user type flags."
                ),
            }
        )

    if STATUS_RX.search(txt):
        routes.append(
            {
                "intent": "STATUS",
                "directive": (
                    "[Omega Intent -> Live Status] Silently run `omega dashboard` (and `eval_harness.py` if tools health asked) "
                    "and summarize plainly."
                ),
            }
        )

    if OBSIDIAN_RX.search(txt):
        routes.append(
            {
                "intent": "OBSIDIAN_SYNC",
                "directive": (
                    "[Omega Intent -> Obsidian Vault] Silently run `omega obsidian sync` (two-way ingest from 08-Inbox/09-Config "
                    "+ rebuild /sdcard/Documents/OmegaVault Knowledge Graph & Canvas) and report plainly."
                ),
            }
        )

    if DEBUG_RX.search(txt):
        routes.append(
            {
                "intent": "DEBUG",
                "directive": (
                    "[Omega Intent -> Debug Protocol] Follow the 11-Line Debug & Patch Protocol: reproduce with timestamp, "
                    "time hops, read logs first, edit .bak copy, verify failure+healthy cases before claiming fixed."
                ),
            }
        )

    return routes


def route_invocation(payload: dict[str, Any], paths: OmegaPaths | None = None) -> dict[str, Any]:
    """Stateful once-per-user-message hook router for PreInvocation."""
    p = paths or get_paths()
    user_input = str(payload.get("lastUserInput") or "").strip()
    if not user_input:
        return {}

    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("conversationId") or "default"))[:48] or "default"
    msg_hash = hashlib.sha256(user_input.encode("utf-8")).hexdigest()[:16]

    ensure_dirs(p)
    st_path = os.path.join(p.state_dir, f"{conv_id}_router.json")
    last_hash = ""
    if os.path.exists(st_path):
        try:
            with open(st_path, "r", encoding="utf-8") as f:
                last_hash = str(json.load(f).get("last_msg_hash") or "")
        except Exception:
            last_hash = ""

    # Fire at most once per distinct user message (never spam mid-turn tool loops)
    if last_hash == msg_hash:
        return {}

    try:
        tmp = st_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"last_msg_hash": msg_hash}, f)
        os.replace(tmp, st_path)
    except Exception:
        pass

    routes = classify_user_intent(user_input)
    if not routes:
        return {}

    combined = " ".join(r["directive"] for r in routes)
    return {"injectSteps": [{"systemMessage": {"systemMessage": combined}}]}
