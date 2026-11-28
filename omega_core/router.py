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

from . import R2_WORKSPACE, OmegaPaths, ensure_dirs, get_paths, safe_fts_query, tokenize_multilingual
from .compact_anchor import maybe_post_compact_message
from .forge import SkillForge
from .memory import KnowledgeFabric

# Synonym bridge so natural speech ("my phone", "backup", "money") hits exact vault keys via JIT Hydration
JIT_SYNONYMS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:phone|poco|f6|roblox|touch|fps|hyperos|adb|ladb|shizuku|axmanager)\b", re.I), "vermeer"),
    (re.compile(r"\b(?:tsb|saitama|claw|dash|combo)\b", re.I), "saitama"),
    (re.compile(r"\b(?:money|bet|odds|kelly|polygon|usdc|cashout|binance|bank|gel)\b", re.I), "polymarket"),
    (re.compile(r"\b(?:bounty|bounties|pr|issue|github\s+earn)\b", re.I), "bounty"),
    (re.compile(r"\b(?:gym|workout|arm|hook|cable|protein|diet|steps|weight)\b", re.I), "armwrestling"),
    (re.compile(r"\b(?:uk|ielts|lydia|travel|marriage)\b", re.I), "active_goals"),
    (re.compile(r"\b(?:mcp|bridge|tunnl|termux)\b", re.I), "tunnl"),
    (re.compile(r"\b(?:backup|vault|drive|restore|cloud|google\s+pro)\b", re.I), "backup"),
    (re.compile(r"\b(?:omega|os|harness|kernel|jury|non[- ]?consensus|grok|codegraph)\b", re.I), "repos"),
]

JIT_STOP = {"the", "and", "for", "with", "what", "how", "can", "you", "our", "this", "that", "from", "have", "about", "just", "make", "need", "want"}

HANDOFF_RX = re.compile(r"\b(?:handoff|wrap\s+up\s+for\s+new\s+chat|session\s+handoff|prepare\s+new\s+chat)\b", re.IGNORECASE)
CRAWL_RX = re.compile(r"\b(?:scrape|crawl|bulk\s+crawl|mass\s+scrape|500\+\s+pages|youtube\s+transcript|transcript\s+of)\b", re.IGNORECASE)
CODEGRAPH_RX = re.compile(r"\b(?:codegraph|call\s+graph|who\s+calls|find\s+callers|where\s+is\s+\w+\s+defined)\b", re.IGNORECASE)
FEED_RX = re.compile(r"\b(?:x\s+feed|twitter\s+feed|ai\s+news|daily\s+pulse|ai\s+pulse|latest\s+ai\s+news|smol\s+ai)\b", re.IGNORECASE)

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

DREAM_RX = re.compile(
    r"\b(?:run\s+dreaming|consolidate\s+memory|dream\s+pass|cluster\s+failures)\b",
    re.IGNORECASE,
)

MCP_MODE_RX = re.compile(
    r"\b(?:light\s+mode|ultra\s+light\s+mode|save\s+tokens|full\s+mcp\s+mode)\b",
    re.IGNORECASE,
)

DEBUG_RX = re.compile(
    r"\b(?:debug|broken|not\s+working|fix\s+this|timeout|502|503|crash|bug|patch|error)\b",
    re.IGNORECASE,
)

COMPACT_RX = re.compile(
    r"(?:^|\s)/compact\b|\b(?:compact\s+(?:this\s+chat|now)|run\s+compact|do\s+compact)\b",
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
                    "[Omega->DEEP] `omega crawl \"<topic>\" --pages 250` (0 tokens, HTTP/2+trafilatura->FTS5), "
                    "pass `non_consensus_gate.py --strict`, execute directly, zero lecturing."
                ),
            }
        )
    elif FAST_RESEARCH_RX.search(txt):
        routes.append(
            {
                "intent": "FAST_RESEARCH",
                "directive": (
                    "[Omega->FAST] Prefer `omega crawl \"<topic>\" --query-only` (<5ms FTS5) or `--pages 120` (0 tokens) over repeated search_web."
                ),
            }
        )

    if CODEGRAPH_RX.search(txt):
        routes.append(
            {
                "intent": "CODEGRAPH",
                "directive": "[Omega->AST] Run `omega code find|callers <sym>` before opening whole files.",
            }
        )

    if FEED_RX.search(txt):
        routes.append(
            {
                "intent": "AI_FEED",
                "directive": "[Omega->FEED] Run `omega feed` (0 tokens: smol.ai X/Twitter digest + HF Daily Papers + Lobsters + Simon Willison + Google AI + V2EX/Habr/GeekNews).",
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
                    "[Omega Intent -> Obsidian Vault] Silently run `omega obsidian sync` (two-way ingest from Inbox/ "
                    "+ rebuild /sdcard/Documents/OmegaVault Knowledge Graph) and report plainly."
                ),
            }
        )

    if DREAM_RX.search(txt):
        routes.append(
            {
                "intent": "DREAM",
                "directive": (
                    "[Omega Intent -> Dreaming Consolidation] Silently run `omega dream run` (cluster failure signatures, "
                    "rebuild GraphRAG edges, incrementally index AST codegraph, sync Obsidian) without touching hot prompt."
                ),
            }
        )

    if MCP_MODE_RX.search(txt):
        routes.append(
            {
                "intent": "MCP_MODE",
                "directive": (
                    "[Omega Intent -> MCP Diet] Silently run `omega mcp-mode light|ultra|full` matching user request and confirm active servers."
                ),
            }
        )

    if COMPACT_RX.search(txt):
        routes.append(
            {
                "intent": "COMPACT_HANDOFF",
                "directive": (
                    "[Omega Intent -> Lossless Compact Handoff] User requested /compact. "
                    "Immediately run `python3 ~/tools/compact_handoff.py <current_conversation_id>` to generate the exact lossless anchor packet, "
                    "then call `jarvis_new_chat` with `open=true` and `message=<that exact packet>` so the user lands in a fresh ~2k-token chat with zero lost context."
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

    if HANDOFF_RX.search(txt):
        routes.append(
            {
                "intent": "HANDOFF",
                "directive": (
                    "[Omega Intent -> Session Handoff] Silently run `omega handoff` and give Giorgi a crisp copy-ready fresh-chat handoff summary."
                ),
            }
        )

    if CRAWL_RX.search(txt):
        routes.append(
            {
                "intent": "BULK_CRAWL",
                "directive": (
                    "[Omega Intent -> 500+ Page Local Bulk Crawler] Run `omega crawl \"<topic>\" --pages 500` (0 LLM tokens, local SQLite FTS5) "
                    "instead of burning repeated search_web turns, then synthesize ONLY from the top BM25 hits."
                ),
            }
        )

    return routes


def jit_hydrate_memories(user_input: str, paths: OmegaPaths, max_chars: int = 900) -> str:
    """Zero-tool-call Multilingual Pre-Turn JIT Context + SkillForge Hydration (JitMem + HiGram pattern)."""
    if len(user_input.strip()) < 2:
        return ""
    terms = [w for w in tokenize_multilingual(user_input, min_latin=3, min_cjk=2, max_tokens=10) if w.lower() not in JIT_STOP]
    for rx, syn in JIT_SYNONYMS:
        if rx.search(user_input) and syn not in terms:
            terms.insert(0, syn)
    if not terms:
        return ""

    query = safe_fts_query(" ".join(dict.fromkeys(terms[:5])), mode="OR", max_terms=5)
    try:
        kf = KnowledgeFabric(paths)
        hits = kf.graph_search(query, caller_ring=R2_WORKSPACE, hops=1, limit=3)
    except Exception:
        hits = []
    try:
        skills = SkillForge(paths).match_skills(query, limit=2)
    except Exception:
        skills = []
    if not hits and not skills:
        return ""

    blocks: list[str] = []
    if hits:
        lines = ["<jit_hydrated_context>"]
        used = len(lines[0]) + len("</jit_hydrated_context>") + 2
        for h in hits:
            entry = f"- [{h['key']}|h{h.get('match_hop', 0)}] {h['text'].replace(chr(10), ' ')[:270]}"
            if used + len(entry) + 1 > max_chars:
                break
            lines.append(entry)
            used += len(entry) + 1
        lines.append("</jit_hydrated_context>")
        if len(lines) > 2:
            blocks.append("\n".join(lines))
    if skills:
        slines = ["<jit_forged_skills>"]
        sused = len(slines[0]) + len("</jit_forged_skills>") + 2
        for s in skills:
            entry = f"- [{s['skill_id']}|u={s['utility_score']:.2f}] {s['procedure'].replace(chr(10), ' ')[:140]}"
            if sused + len(entry) + 1 > 340:
                break
            slines.append(entry)
            sused += len(entry) + 1
        slines.append("</jit_forged_skills>")
        if len(slines) > 2:
            blocks.append("\n".join(slines))
    return "\n".join(blocks)


def route_invocation(payload: dict[str, Any], paths: OmegaPaths | None = None) -> dict[str, Any]:
    """Stateful once-per-user-message hook router + Pre-Turn JIT Memory Hydrator."""
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

    parts: list[str] = []
    # Lossless post-compact anchor restore (fires ONLY on 1st turn after /compact -> 0 KV-cache hit otherwise)
    anchor_msg = maybe_post_compact_message(conv_id, p)
    if anchor_msg:
        parts.append(anchor_msg)
    routes = classify_user_intent(user_input)
    if routes:
        parts.append(" ".join(r["directive"] for r in routes)[:420])
    jit = jit_hydrate_memories(user_input, p)
    if jit:
        parts.append(jit)

    if not parts:
        return {}

    return {"injectSteps": [{"systemMessage": {"systemMessage": "\n".join(parts)}}]}
