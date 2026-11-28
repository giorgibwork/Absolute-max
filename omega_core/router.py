"""Natural-Language Intent Auto-Router & KV-Cache-Safe JIT Hydrator (OMEGA APEX v9.0).

Design invariants:
1. Lossless Post-Compact Anchor Restore ALWAYS runs BEFORE user-input dedup, so mid-turn
   compaction (same `lastUserInput`, new `CHECKPOINT` step) NEVER gets skipped!
2. Implicit KV-Cache Hygiene (Gemini 4 Neon 95% cache discount):
   - Injects each intent directive, memory key, and forged skill AT MOST ONCE per
     conversation compaction window (tracked in `<conv_id>_router.json` with flock).
   - Tight, high-signal intent regexes (never spams common dev nouns like "bug"/"current").
   - Never truncates directives mid-command; caps cleanly at top 2 whole directives.
   - Infers `task_family` so JIT hydration honors Scoped-ORC domain isolation.
3. Universal Instant-Expert & Independent Skeptical Critic Auto-Routing:
   - Automatically surfaces `omega expert "<topic>"` & `omega critic` / `omega-prosecutor`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from . import (
    R2_WORKSPACE,
    OmegaPaths,
    atomic_json_write,
    ensure_dirs,
    get_paths,
    locked_file_op,
    safe_fts_query,
    tokenize_multilingual,
)
from .compact_anchor import maybe_post_compact_message
from .forge import SkillForge
from .memory import KnowledgeFabric

# Synonym bridge + task_family inference so everyday speech hits exact vault keys & respects Scoped-ORC
JIT_SYNONYMS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(?:phone|poco|f6|roblox|touch|fps|hyperos|adb|ladb|shizuku|axmanager)\b", re.I), "vermeer", "vermeer"),
    (re.compile(r"\b(?:tsb|saitama|claw|dash|combo)\b", re.I), "saitama", "vermeer"),
    (re.compile(r"\b(?:money|bet|odds|kelly|polygon|usdc|cashout|binance|bank|gel|polymarket)\b", re.I), "polymarket", "finance"),
    (re.compile(r"\b(?:bounty|bounties|pr|issue|github\s+earn)\b", re.I), "bounty", "finance"),
    (re.compile(r"\b(?:gym|workout|armwrestl\w*|pronation|hook|cable|protein|diet|steps|weight)\b", re.I), "armwrestling", "life"),
    (re.compile(r"\b(?:uk|ielts|lydia|travel|marriage|visa)\b", re.I), "active_goals", "life"),
    (re.compile(r"\b(?:mcp|bridge|tunnl|termux)\b", re.I), "tunnl", "os"),
    (re.compile(r"\b(?:backup|vault|drive|restore|cloud|google\s+pro|round\s+sync)\b", re.I), "backup", "os"),
    (re.compile(r"\b(?:omega|os|harness|kernel|jury|non[- ]?consensus|codegraph|neon|kv[- ]?cache|critic)\b", re.I), "repos", "os"),
]

JIT_STOP = {"the", "and", "for", "with", "what", "how", "can", "you", "our", "this", "that", "from", "have", "about", "just", "make", "need", "want"}

HANDOFF_RX = re.compile(r"\b(?:handoff|wrap\s+up\s+for\s+new\s+chat|session\s+handoff|prepare\s+new\s+chat)\b", re.IGNORECASE)
CRAWL_RX = re.compile(r"\b(?:scrape|bulk\s+crawl|mass\s+scrape|500\+\s+pages|youtube\s+transcript|transcript\s+of)\b", re.IGNORECASE)
CODEGRAPH_RX = re.compile(r"\b(?:codegraph|call\s+graph|who\s+calls|find\s+callers|where\s+is\s+\w+\s+defined)\b", re.IGNORECASE)
FEED_RX = re.compile(r"\b(?:x\s+feed|twitter\s+feed|ai\s+news|daily\s+pulse|ai\s+pulse|latest\s+ai\s+news|smol\s+ai)\b", re.IGNORECASE)
EXPERT_RX = re.compile(
    r"\b(?:become\s+an\s+expert|expert\s+(?:at|on|in|brief|playbook)|master\s+this|teach\s+me\s+(?:everything|deeply)|"
    r"shizuku|axmanager|armwrestl\w*\s+(?:split|program|protocol|biomechanics)|tweak(?:ing)?\s+my\s+phone)\b",
    re.IGNORECASE,
)
CRITIC_RX = re.compile(
    r"\b(?:skeptical\s+critic|red[- ]?team\s+(?:this|our)|critique\s+(?:this|your|the)\s+(?:answer|work|plan|code)|"
    r"separate\s+critic|independent\s+critic|hostile\s+audit)\b",
    re.IGNORECASE,
)

# Tightened research regexes (eliminates per-turn spam on common dev words like "current"/"compare"/"bug"/"error")
DEEP_RESEARCH_RX = re.compile(
    r"\b(?:deep\s+research|dig\s+deep|full\s+breakdown|investigate\s+deeply|absolute\s+ceiling|eye\s+of\s+god|research\s+everything|comprehensive\s+research|hyperresearch)\b",
    re.IGNORECASE,
)
FAST_RESEARCH_RX = re.compile(
    r"\b(?:research\s+(?:this|how|what)|look\s+up\s+online|check\s+online|search\s+online|what'?s\s+new\s+in|release\s+date\s+of|current\s+price\s+of)\b",
    re.IGNORECASE,
)
MISSION_RX = re.compile(
    r"\b(?:start\s+a\s+mission|new\s+mission|track\s+this\s+mission|multi[- ]step\s+project|keep\s+track\s+of\s+this\s+project)\b",
    re.IGNORECASE,
)
STATUS_RX = re.compile(
    r"\b(?:how\s+are\s+our\s+tools|check\s+system\s+status|system\s+health|omega\s+dashboard|pending\s+approvals)\b",
    re.IGNORECASE,
)
OBSIDIAN_RX = re.compile(
    r"\b(?:obsidian\s+sync|sync\s+my\s+(?:vault|notes)|update\s+my\s+vault|inbox\s+notes|rebuild\s+knowledge\s+graph)\b",
    re.IGNORECASE,
)
DREAM_RX = re.compile(
    r"\b(?:run\s+dreaming|consolidate\s+memory|dream\s+pass|cluster\s+failures)\b",
    re.IGNORECASE,
)
MCP_MODE_RX = re.compile(
    r"\b(?:light\s+mcp\s+mode|ultra\s+light\s+mode|full\s+mcp\s+mode|toggle\s+mcp)\b",
    re.IGNORECASE,
)
DEBUG_RX = re.compile(
    r"\b(?:debug\s+protocol|reproduce\s+this\s+crash|root[- ]cause\s+this|502\s+error|503\s+error)\b",
    re.IGNORECASE,
)
COMPACT_RX = re.compile(
    r"(?:^|\s)/compact\b|\b(?:compact\s+(?:this\s+chat|now)|run\s+compact|do\s+compact)\b",
    re.IGNORECASE,
)


def classify_user_intent(user_input: str) -> list[dict[str, str]]:
    """Map natural everyday phrasing to crisp, zero-bloat internal OMEGA directives."""
    txt = (user_input or "").strip()
    if not txt:
        return []

    routes: list[dict[str, str]] = []
    if DEEP_RESEARCH_RX.search(txt):
        routes.append({
            "intent": "DEEP_RESEARCH",
            "directive": "[Omega->DEEP] Use `omega expert \"<topic>\" --acquire` or `omega crawl \"<topic>\" --pages 200` (0 tokens, 18 multilingual/hostile lanes) + `non_consensus_gate.py --strict`.",
        })
    elif FAST_RESEARCH_RX.search(txt):
        routes.append({
            "intent": "FAST_RESEARCH",
            "directive": "[Omega->FAST] Query `omega crawl \"<topic>\" --query-only` (<5ms, 0 tokens) before running repeated `search_web`.",
        })

    if EXPERT_RX.search(txt):
        routes.append({
            "intent": "DOMAIN_EXPERT",
            "directive": "[Omega->EXPERT] Run `omega expert \"<topic>\" --acquire` (0 tokens, EN/ZH/JA/RU/KO + hostile traps -> saves reusable SkillForge playbook for <3ms future recall).",
        })

    if CRITIC_RX.search(txt):
        routes.append({
            "intent": "SKEPTICAL_CRITIC",
            "directive": "[Omega->CRITIC] Invoke clean-slate `omega-prosecutor` subagent (and/or `omega critic --transcript <path> --llm`) against user's exact request before declaring done.",
        })

    if CODEGRAPH_RX.search(txt):
        routes.append({
            "intent": "CODEGRAPH",
            "directive": "[Omega->AST] Run `omega code find|callers <sym>` (<5ms) before reading whole files.",
        })

    if FEED_RX.search(txt):
        routes.append({
            "intent": "AI_FEED",
            "directive": "[Omega->FEED] Run `omega feed` (0 tokens: smol.ai X/Twitter digest + HF Daily Papers + Lobsters + Simon Willison + Google AI + V2EX/Habr/GeekNews).",
        })

    if MISSION_RX.search(txt):
        routes.append({
            "intent": "MISSION",
            "directive": "[Omega->MISSION] Track goal persistently via `omega mission new` and `omega problem add`.",
        })

    if STATUS_RX.search(txt):
        routes.append({
            "intent": "STATUS",
            "directive": "[Omega->STATUS] Run `omega dashboard` and `omega suite` (live measured health) and summarize plainly.",
        })

    if OBSIDIAN_RX.search(txt):
        routes.append({
            "intent": "OBSIDIAN_SYNC",
            "directive": "[Omega->OBSIDIAN] Run `omega obsidian sync` (two-way Inbox ingest + Knowledge Graph rebuild).",
        })

    if DREAM_RX.search(txt):
        routes.append({
            "intent": "DREAM",
            "directive": "[Omega->DREAM] Run `omega dream run` (failure clustering, GraphRAG edges, AST CodeGraph, skill pruning).",
        })

    if MCP_MODE_RX.search(txt):
        routes.append({
            "intent": "MCP_MODE",
            "directive": "[Omega->MCP] Run `python3 ~/tools/mcp_toggle.py status` or `omega mcp-mode light|ultra|full`.",
        })

    if COMPACT_RX.search(txt):
        routes.append({
            "intent": "COMPACT_HANDOFF",
            "directive": "[Omega->COMPACT] Native `/compact` preserves lossless anchor automatically; use `omega handoff` for a <750-char fresh-chat card.",
        })

    if DEBUG_RX.search(txt):
        routes.append({
            "intent": "DEBUG",
            "directive": "[Omega->DEBUG] Reproduce with timestamp, read exact logs/code first, verify failure+healthy cases with tests before claiming fixed.",
        })

    if HANDOFF_RX.search(txt):
        routes.append({
            "intent": "HANDOFF",
            "directive": "[Omega->HANDOFF] Run `omega handoff` and return a crisp copy-ready fresh-chat handoff card.",
        })

    if CRAWL_RX.search(txt):
        routes.append({
            "intent": "BULK_CRAWL",
            "directive": "[Omega->CRAWL] Run `omega crawl \"<topic>\" --pages 300` (0 tokens, local SQLite FTS5) and synthesize from top lane-diverse BM25 hits.",
        })

    return routes


def infer_task_family(user_input: str) -> str | None:
    """Infer Scoped-ORC task_family from natural language so JIT hydration avoids cross-domain bleed."""
    for rx, _, fam in JIT_SYNONYMS:
        if rx.search(user_input):
            return fam
    return None


def jit_hydrate_memories(
    user_input: str,
    paths: OmegaPaths,
    *,
    max_chars: int = 850,
    exclude_keys: set[str] | None = None,
    exclude_skills: set[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    """Zero-tool-call Multilingual Scoped-ORC JIT Context + SkillForge Hydration (returns text, new_keys, new_skills)."""
    if len(user_input.strip()) < 2:
        return "", [], []
    ex_keys = exclude_keys or set()
    ex_skills = exclude_skills or set()

    terms = [w for w in tokenize_multilingual(user_input, min_latin=3, min_cjk=2, max_tokens=10) if w.lower() not in JIT_STOP]
    inferred_fam = infer_task_family(user_input)
    for rx, syn, _ in JIT_SYNONYMS:
        if rx.search(user_input) and syn not in terms:
            terms.insert(0, syn)
    if not terms:
        return "", [], []

    query = safe_fts_query(" ".join(dict.fromkeys(terms[:5])), mode="OR", max_terms=5)
    try:
        kf = KnowledgeFabric(paths)
        hits = kf.graph_search(query, task_family=inferred_fam, caller_ring=R2_WORKSPACE, hops=1, limit=4)
    except Exception:
        hits = []
    try:
        skills = SkillForge(paths).match_skills(query, task_family=inferred_fam, limit=3)
    except Exception:
        skills = []

    hits = [h for h in hits if h["key"] not in ex_keys][:3]
    skills = [s for s in skills if s["skill_id"] not in ex_skills][:2]
    if not hits and not skills:
        return "", [], []

    blocks: list[str] = []
    added_keys: list[str] = []
    added_skills: list[str] = []

    if hits:
        lines = ["<jit_hydrated_context>"]
        used = len(lines[0]) + len("</jit_hydrated_context>") + 2
        for h in hits:
            entry = f"- [{h['key']}|h{h.get('match_hop', 0)}] {h['text'].replace(chr(10), ' ')[:240]}"
            if used + len(entry) + 1 > max_chars:
                break
            lines.append(entry)
            used += len(entry) + 1
            added_keys.append(h["key"])
        lines.append("</jit_hydrated_context>")
        if added_keys:
            blocks.append("\n".join(lines))

    if skills:
        slines = ["<jit_forged_skills>"]
        sused = len(slines[0]) + len("</jit_forged_skills>") + 2
        for s in skills:
            entry = f"- [{s['skill_id']}|u={s['utility_score']:.2f}] {s['procedure'].replace(chr(10), ' ')[:160]}"
            if sused + len(entry) + 1 > 380:
                break
            slines.append(entry)
            sused += len(entry) + 1
            added_skills.append(s["skill_id"])
        slines.append("</jit_forged_skills>")
        if added_skills:
            blocks.append("\n".join(slines))

    return "\n".join(blocks), added_keys, added_skills


def route_invocation(payload: dict[str, Any], paths: OmegaPaths | None = None) -> dict[str, Any]:
    """Stateful KV-cache-safe hook router + Lossless Post-Compact Anchor + Scoped JIT Hydrator."""
    p = paths or get_paths()
    user_input = str(payload.get("lastUserInput") or "").strip()
    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("conversationId") or "default"))[:48] or "default"
    ensure_dirs(p)

    # P0 FIX: ALWAYS check post-compact anchor BEFORE user_input dedup!
    # Compaction happens mid-turn while lastUserInput is unchanged; previously dedup skipped restore!
    anchor_msg = maybe_post_compact_message(conv_id, p)
    compacted_now = bool(anchor_msg)

    if not user_input and not compacted_now:
        return {}

    msg_hash = hashlib.sha256(user_input.encode("utf-8")).hexdigest()[:16] if user_input else ""
    st_path = os.path.join(p.state_dir, f"{conv_id}_router.json")

    def _run_locked() -> dict[str, Any]:
        st: dict[str, Any] = {
            "last_msg_hash": "",
            "injected_keys": [],
            "injected_skills": [],
            "injected_intents": [],
        }
        if os.path.exists(st_path):
            try:
                with open(st_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    st.update(loaded)
            except Exception:
                pass

        # On a fresh compaction checkpoint, reset session-injected sets so post-compact turns can re-hydrate if needed
        if compacted_now:
            st["injected_keys"] = []
            st["injected_skills"] = []
            st["injected_intents"] = []

        parts: list[str] = []
        if anchor_msg:
            parts.append(anchor_msg)

        is_new_user_msg = bool(user_input) and (st.get("last_msg_hash") != msg_hash)
        if is_new_user_msg:
            st["last_msg_hash"] = msg_hash
            seen_intents = set(st.get("injected_intents") or [])
            routes = [r for r in classify_user_intent(user_input) if r["intent"] not in seen_intents][:2]
            if routes:
                parts.append("\n".join(r["directive"] for r in routes))
                st["injected_intents"] = list(seen_intents | {r["intent"] for r in routes})[-20:]

            jit_txt, new_keys, new_skills = jit_hydrate_memories(
                user_input,
                p,
                exclude_keys=set(st.get("injected_keys") or []),
                exclude_skills=set(st.get("injected_skills") or []),
            )
            if jit_txt:
                parts.append(jit_txt)
                st["injected_keys"] = list(dict.fromkeys(list(st.get("injected_keys") or []) + new_keys))[-40:]
                st["injected_skills"] = list(dict.fromkeys(list(st.get("injected_skills") or []) + new_skills))[-20:]

        if is_new_user_msg or compacted_now:
            try:
                atomic_json_write(st_path, st)
            except Exception:
                pass

        if not parts:
            return {}
        return {"injectSteps": [{"systemMessage": {"systemMessage": "\n".join(parts)}}]}

    return locked_file_op(st_path + ".lock", _run_locked)
