"""Independent Skeptical Critic Engine (OMEGA APEX v9.0 — Zero Circular Self-Praise).

Implements Giorgi's hard skepticism mandate: the main model NEVER gets to rubber-stamp
its own work with "yes, we fixed this and everything is good." Every substantive answer
or code change can be evaluated against the user's ACTUAL request via 3 clean tiers:

1. Tier 0 — Millisecond Deterministic Skeptic (`<5ms`, 0 LLM tokens, ALWAYS runs):
   Checks request-clause coverage, unverified victory claims ("all tests pass", "fixed"
   without passing test/tool evidence), whitewashed tool errors, consensus fluff clichés,
   missing citations on research/audit tasks, and model-policy violations.
2. Tier 1 — Separate Headless Gemini Critic via `agy -p` (`gemini-4-carbon-high` ->
   `gemini-4-hydrogen-xhigh`, isolated clean-slate context, `--output-format json` +
   strict `--json-schema` verdict).
3. Tier 2 — Direct Gemini REST API Critic (`GEMINI_API_KEY` / `GOOGLE_API_KEY`, pure
   Python stdlib `urllib.request`, `responseMimeType: application/json` + JSON schema).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from . import OmegaPaths, get_paths, tokenize_multilingual
from .fabric import invoke_agy

DEFAULT_CRITIC_MODEL = "gemini-4-carbon-high"
FALLBACK_CRITIC_MODELS = ("gemini-4-hydrogen-xhigh", "gemini-4-neon-xhigh")

CRITIC_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "REVISE"]},
        "score": {"type": "number"},
        "missed_requirements": {"type": "array", "items": {"type": "string"}},
        "unverified_claims": {"type": "array", "items": {"type": "string"}},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["P0", "P1", "P2"]},
                    "code": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["severity", "code", "detail"],
            },
        },
        "critique": {"type": "string"},
    },
    "required": ["verdict", "score", "missed_requirements", "unverified_claims", "defects", "critique"],
}

VICTORY_CLAIM_RX = re.compile(
    r"\b(?:everything\s+(?:is\s+)?(?:fixed|working|good|verified|passing|ready)|"
    r"all\s+(?:tests?|checks?|bugs?)\s+(?:pass(?:ed|ing)?|fixed|resolved)|"
    r"fully\s+(?:fixed|verified|resolved|working)|"
    r"100%\s+(?:pass|working|verified|fixed)|"
    r"zero\s+(?:bugs?|errors?|issues?)\s+remain(?:ing)?)\b",
    re.IGNORECASE,
)

RESEARCH_REQ_RX = re.compile(
    r"\b(?:research|audit|analyze|compare|benchmark|verify|investigate|deep\s+dive|expert|skeptical|critic|plan)\b",
    re.IGNORECASE,
)

CONSENSUS_CLICHE_RX = re.compile(
    r"\b(?:it\s+depends|as\s+an\s+ai|generally\s+speaking|best\s+practices|"
    r"there\s+is\s+no\s+one[- ]size[- ]fits[- ]all|pros\s+and\s+cons\s+to\s+both|"
    r"consult\s+(?:a|an)\s+(?:professional|expert))\b",
    re.IGNORECASE,
)

EVIDENCE_LOCATOR_RX = re.compile(
    r"(?:https?://\S+|file://\S+|/[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+\.[a-z0-9]{1,5}|"
    r"`[^`]+\.(?:py|md|json|sh|db|sql|txt)`|\b\d+(?:\.\d+)?\s*(?:ms|s|%|KB|MB|GB|docs|PASS|FAIL)\b)",
    re.IGNORECASE,
)

FORBIDDEN_MODEL_RX = re.compile(
    r"\b(?:claude-[a-z0-9.-]+|gpt-[45][a-z0-9.-]*|o3-mini|o4-mini|gemini-4-argon|gemini-3\.8-flash)\b",
    re.IGNORECASE,
)

USER_REQ_TAG_RX = re.compile(r"<USER_REQUEST>([\s\S]*?)</USER_REQUEST>", re.IGNORECASE)
EXPANSION_TAG_RX = re.compile(r"<antigem-expansion\b[^>]*>[\s\S]*?</antigem-expansion>", re.IGNORECASE)
REQ_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "about", "just",
    "make", "sure", "need", "want", "please", "also", "like", "really", "very",
    "into", "when", "what", "where", "which", "your", "ours", "everything", "something",
    "actually", "basically", "literally", "should", "could", "would", "can", "will",
}


def extract_last_turn_from_transcript(transcript_path: str, max_tail_bytes: int = 98304) -> dict[str, Any]:
    """Read tail of Antigravity transcript.jsonl (<3ms) and extract last user request, reply, and tool trace."""
    out: dict[str, Any] = {
        "user_request": "",
        "assistant_response": "",
        "tool_events": [],
        "failed_tools": [],
        "verification_ran": False,
        "model": "",
    }
    if not transcript_path:
        return out
    tp = os.path.expanduser(transcript_path)
    if not os.path.isfile(tp):
        return out

    try:
        size = os.path.getsize(tp)
        with open(tp, "rb") as f:
            if size > max_tail_bytes:
                f.seek(size - max_tail_bytes)
                _ = f.readline()  # discard partial leading line
            raw_lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return out

    steps: list[dict[str, Any]] = []
    for ln in raw_lines:
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                steps.append(obj)
        except json.JSONDecodeError:
            continue

    if not steps:
        return out

    # Find last USER_INPUT step index within tail
    last_u_idx = -1
    for i in range(len(steps) - 1, -1, -1):
        if steps[i].get("type") == "USER_INPUT":
            last_u_idx = i
            raw_u = str(steps[i].get("content") or "")
            m = USER_REQ_TAG_RX.search(raw_u)
            req = m.group(1) if m else raw_u
            req = EXPANSION_TAG_RX.sub("", req).strip()
            out["user_request"] = req[:2500]
            break

    slice_steps = steps[last_u_idx + 1 :] if last_u_idx >= 0 else steps[-25:]
    for st in slice_steps:
        stype = str(st.get("type") or "")
        if stype == "PLANNER_RESPONSE":
            if st.get("model"):
                out["model"] = str(st["model"])
            content = str(st.get("content") or "").strip()
            if content:
                out["assistant_response"] = content[:10000]
            tcs = st.get("tool_calls") or []
            if isinstance(tcs, list):
                for tc in tcs:
                    if isinstance(tc, dict):
                        name = str(tc.get("name") or tc.get("tool") or "")
                        args = str(tc.get("args") or tc.get("arguments") or "")[:140]
                        ev = f"{name}: {args}"
                        out["tool_events"].append(ev)
                        if re.search(r"\b(?:unittest|pytest|omega\s+suite|non_consensus_gate)\b", ev, re.I):
                            out["verification_ran"] = True
        elif stype == "GENERIC":
            c = str(st.get("content") or "")
            if re.search(r"Command exited with code [1-9]|Traceback \(most recent|FAILED \(|AssertionError|Encountered error", c):
                out["failed_tools"].append(re.sub(r"\s+", " ", c)[:180])
            if re.search(r"\bRan \d+ tests? in\b.*\bOK\b|\"passed\":\s*10,\s*\"total\":\s*10|\"passed\":\s*true", c, re.S):
                out["verification_ran"] = True
        elif stype == "ERROR_MESSAGE":
            err = str(st.get("error") or st.get("content") or "")
            if err:
                out["failed_tools"].append(err[:180])

    return out


def _extract_requirement_anchors(user_request: str) -> list[str]:
    """Extract high-signal topical requirement anchors from a user request."""
    toks = tokenize_multilingual(user_request, min_latin=4, min_cjk=2, max_tokens=20)
    out = []
    for t in toks:
        tl = t.lower()
        if tl in REQ_STOPWORDS or tl.isdigit():
            continue
        if tl not in out:
            out.append(tl)
    return out[:10]


def deterministic_critique(
    user_request: str,
    draft_response: str,
    *,
    tool_events: list[str] | None = None,
    failed_tools: list[str] | None = None,
    verification_ran: bool = False,
    code_edited: bool = False,
    tests_passed: bool = False,
) -> dict[str, Any]:
    """Tier-0 zero-token millisecond skeptical pre-critic (<5ms, zero false praise)."""
    t0 = time.perf_counter()
    req = (user_request or "").strip()
    resp = (draft_response or "").strip()
    fails = list(failed_tools or [])
    events = list(tool_events or [])

    defects: list[dict[str, str]] = []
    missed: list[str] = []
    unverified: list[str] = []

    if not resp:
        defects.append({"severity": "P0", "code": "empty_response", "detail": "Draft response is empty."})

    # 1. Code edited without passing verification tests
    if code_edited and not tests_passed and not verification_ran:
        defects.append({
            "severity": "P0",
            "code": "code_edit_without_tests",
            "detail": "Python/code files were modified without a verified passing test run after the edit.",
        })
        unverified.append("Code modifications lack post-edit test verification.")

    # 2. Unverified victory / rubber-stamp claims
    vic_m = VICTORY_CLAIM_RX.search(resp)
    if vic_m and ((code_edited and not tests_passed and not verification_ran) or (fails and "unverified" not in resp.lower())):
        claim = vic_m.group(0)
        unverified.append(f"Victory claim '{claim}' made without clean passing verification.")
        defects.append({
            "severity": "P0",
            "code": "unverified_victory_claim",
            "detail": f"Response asserts '{claim}' despite unverified edits or unresolved tool errors.",
        })

    # 3. Whitewashed tool failures (recent tool error ignored in final response)
    if fails and not re.search(r"\b(?:error|fail(?:ed|ure)?|unverified|blocked|auth|retry|fixed|resolved|limitation)\b", resp, re.I):
        defects.append({
            "severity": "P1",
            "code": "failed_tool_whitewash",
            "detail": f"{len(fails)} tool error(s) occurred in this turn without acknowledgment or resolution in the final answer.",
        })

    # 4. Consensus fluff clichés on technical/research/audit requests
    is_research = bool(RESEARCH_REQ_RX.search(req))
    if is_research:
        cm = CONSENSUS_CLICHE_RX.search(resp)
        if cm:
            defects.append({
                "severity": "P1",
                "code": "consensus_fluff",
                "detail": f"Mainstream consensus cliché '{cm.group(0)}' detected on a rigorous technical/research request.",
            })
        if len(resp) > 350 and not EVIDENCE_LOCATOR_RX.search(resp):
            unverified.append("Substantive technical/research reply lacks concrete URLs, file paths, or measured metrics.")
            defects.append({
                "severity": "P1",
                "code": "missing_evidence_citations",
                "detail": "Research/audit answer has no grounded URLs, file locators, or measured numbers.",
            })

    # 5. Requirement anchor coverage check (flags skipped parts of multi-part user requests)
    if len(req) >= 40 and resp:
        anchors = _extract_requirement_anchors(req)
        resp_low = resp.lower()
        missing_anchors = [a for a in anchors if a not in resp_low]
        if len(anchors) >= 4 and (len(missing_anchors) / len(anchors)) >= 0.6:
            missed.append(f"Request anchors absent from answer: {', '.join(missing_anchors[:6])}")
            defects.append({
                "severity": "P1",
                "code": "unaddressed_request_clauses",
                "detail": f"Over 60% of key user request terms ({', '.join(missing_anchors[:6])}) are not addressed.",
            })

    # 6. Model-policy drift check (prohibits proposing sunset or third-party models as solutions)
    for m in FORBIDDEN_MODEL_RX.finditer(resp):
        tok = m.group(0)
        # Allow mentioning forbidden models strictly when stating they are banned/purged/zero
        ctx_start = max(0, m.start() - 60)
        ctx = resp[ctx_start : m.end() + 40].lower()
        if not re.search(r"\b(?:zero|no|ban|purg|remov|exclud|never|not|block|sunset|avoid|forbid|without)\b", ctx):
            defects.append({
                "severity": "P2",
                "code": "model_policy_drift",
                "detail": f"Non-Gemini / deprecated model '{tok}' referenced outside exclusion context.",
            })
            break

    p0_count = sum(1 for d in defects if d["severity"] == "P0")
    p1_count = sum(1 for d in defects if d["severity"] == "P1")
    p2_count = sum(1 for d in defects if d["severity"] == "P2")
    score = max(0.0, round(1.0 - (0.45 * p0_count) - (0.22 * p1_count) - (0.08 * p2_count), 3))
    verdict = "REVISE" if (p0_count > 0 or p1_count >= 2) else "PASS"

    if verdict == "REVISE":
        critique = "; ".join(f"[{d['severity']}:{d['code']}] {d['detail']}" for d in defects[:4])
    elif defects:
        critique = "Minor warnings only: " + "; ".join(f"[{d['severity']}:{d['code']}] {d['detail']}" for d in defects[:2])
    else:
        critique = "Deterministic skeptic checks passed (no unverified victory claims, whitewashed errors, or obvious omissions)."

    return {
        "verdict": verdict,
        "mode": "deterministic",
        "critic_model": "deterministic_skeptic_v9",
        "score": score,
        "missed_requirements": missed,
        "unverified_claims": unverified,
        "defects": defects,
        "critique": critique,
        "tool_events_checked": len(events),
        "failed_tools_checked": len(fails),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
    }


def _build_hostile_critic_prompt(
    user_request: str,
    draft_response: str,
    tool_events: list[str] | None = None,
    failed_tools: list[str] | None = None,
) -> str:
    tools_blob = "\n".join(f"- {t}" for t in (tool_events or [])[-12:]) or "- (none)"
    fails_blob = "\n".join(f"- {f}" for f in (failed_tools or [])[-6:]) or "- (none)"
    return (
        "ROLE: INDEPENDENT HOSTILE SKEPTICAL CRITIC.\n"
        "You have ZERO relationship to the model that drafted the response below. Assume the draft "
        "contains missed requirements, unverified claims, superficial fixes, or hidden flaws until proven otherwise.\n\n"
        "STRICT RULES:\n"
        "1. Compare DRAFT_RESPONSE line-by-line against USER_REQUEST.\n"
        "2. Check TOOL_TRACE and FAILED_TOOLS: if the draft claims something is fixed/verified without evidence "
        "in TOOL_TRACE, or glosses over a failure, verdict MUST be REVISE.\n"
        "3. Flag any mainstream consensus fluff, missing concrete verification, or skipped parts of USER_REQUEST.\n"
        "4. Return ONLY valid JSON matching the exact schema. Return PASS ONLY if genuinely thorough and verified.\n\n"
        f"<USER_REQUEST>\n{(user_request or '')[:2500]}\n</USER_REQUEST>\n\n"
        f"<TOOL_TRACE>\n{tools_blob}\n</TOOL_TRACE>\n\n"
        f"<FAILED_TOOLS>\n{fails_blob}\n</FAILED_TOOLS>\n\n"
        f"<DRAFT_RESPONSE>\n{(draft_response or '')[:8000]}\n</DRAFT_RESPONSE>\n"
    )


def _load_gemini_api_key() -> str:
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = (os.environ.get(var) or "").strip()
        if val:
            return val
    env_file = os.path.expanduser("~/.omega_env")
    if os.path.isfile(env_file):
        try:
            with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
                for ln in f:
                    m = re.match(r"^(?:export\s+)?(?:GEMINI_API_KEY|GOOGLE_API_KEY)=['\"]?([^'\"\s#]+)", ln.strip())
                    if m:
                        return m.group(1).strip()
        except OSError:
            pass
    return ""


def _invoke_gemini_rest_critic(model_id: str, prompt: str, timeout_s: int = 30) -> dict[str, Any]:
    """Tier-2 pure-stdlib Gemini REST API critic (`responseMimeType: application/json` + JSON schema)."""
    api_key = _load_gemini_api_key()
    if not api_key:
        return {"ok": False, "error": "no_gemini_api_key"}

    base_model = re.sub(r"-(?:xhigh|high|medium|low|minimal)$", "", model_id.strip().lower())
    effort_m = re.search(r"-(xhigh|high|medium|low|minimal)$", model_id.strip().lower())
    thinking_level = effort_m.group(1) if effort_m else "high"
    if base_model == "gemini-4-carbon" and thinking_level == "xhigh":
        thinking_level = "high"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{base_model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": CRITIC_JSON_SCHEMA,
            "thinkingConfig": {"thinkingLevel": thinking_level},
            "temperature": 0.1,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        cands = body.get("candidates") or []
        parts = (((cands[0] if cands else {}).get("content") or {}).get("parts") or [])
        txt = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
        parsed = json.loads(txt) if txt else None
        if isinstance(parsed, dict) and parsed.get("verdict") in ("PASS", "REVISE"):
            return {"ok": True, "mode": "gemini_rest", "critic_model": model_id, "structured": parsed, "latency_ms": elapsed_ms}
        return {"ok": False, "error": "invalid_json_schema_response", "latency_ms": elapsed_ms}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"http_{e.code}:{e.reason}", "latency_ms": round((time.perf_counter() - t0) * 1000.0, 1)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}", "latency_ms": round((time.perf_counter() - t0) * 1000.0, 1)}


def critique_response(
    user_request: str,
    draft_response: str,
    *,
    tool_events: list[str] | None = None,
    failed_tools: list[str] | None = None,
    verification_ran: bool = False,
    code_edited: bool = False,
    tests_passed: bool = False,
    use_llm: bool = False,
    critic_model: str = DEFAULT_CRITIC_MODEL,
    timeout_s: int = 35,
    paths: OmegaPaths | None = None,
    invoker: Any | None = None,
) -> dict[str, Any]:
    """Run Tier-0 deterministic skeptic; optionally escalate to isolated separate Gemini critic model.

    If `use_llm=True`:
    - First tries `agy -p --model <critic_model> --output-format json --json-schema ...`
    - If `agy` CLI auth is missing, tries direct `GEMINI_API_KEY` REST API
    - If neither CLI/API credential is present, returns deterministic verdict + explicit `llm_critic_status`
      (NEVER silently pretends an LLM critic ran when it didn't!).
    """
    _ = paths or get_paths()
    det = deterministic_critique(
        user_request,
        draft_response,
        tool_events=tool_events,
        failed_tools=failed_tools,
        verification_ran=verification_ran,
        code_edited=code_edited,
        tests_passed=tests_passed,
    )
    if not use_llm:
        det["llm_critic_status"] = "skipped_fast_mode"
        return det

    prompt = _build_hostile_critic_prompt(user_request, draft_response, tool_events, failed_tools)
    fn = invoker or invoke_agy

    # Try Tier-1 headless separate model via `agy -p --json-schema`
    llm_errors: list[str] = []
    models_to_try = [critic_model, *[m for m in FALLBACK_CRITIC_MODELS if m != critic_model]]
    for mid in models_to_try[:2]:
        try:
            if invoker is not None:
                res = fn(mid, prompt, timeout_s)
            else:
                res = invoke_agy(mid, prompt, timeout_s=timeout_s, json_schema=CRITIC_JSON_SCHEMA)
        except Exception as e:
            llm_errors.append(f"agy:{mid}:{type(e).__name__}:{e}")
            continue

        if res.get("ok"):
            structured = res.get("structured_output")
            if not isinstance(structured, dict):
                raw_txt = str(res.get("text") or "").strip()
                m = re.search(r"\{.*\}", raw_txt, re.DOTALL)
                if m:
                    try:
                        structured = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        structured = None
            if isinstance(structured, dict) and structured.get("verdict") in ("PASS", "REVISE"):
                # Combine: if deterministic found P0 OR LLM critic returned REVISE -> REVISE
                merged_verdict = "REVISE" if (det["verdict"] == "REVISE" or structured["verdict"] == "REVISE") else "PASS"
                merged_defects = list(det["defects"]) + list(structured.get("defects") or [])
                return {
                    "verdict": merged_verdict,
                    "mode": "agy_headless",
                    "critic_model": mid,
                    "score": min(float(det["score"]), float(structured.get("score", 0.5))),
                    "missed_requirements": list(dict.fromkeys(det["missed_requirements"] + list(structured.get("missed_requirements") or []))),
                    "unverified_claims": list(dict.fromkeys(det["unverified_claims"] + list(structured.get("unverified_claims") or []))),
                    "defects": merged_defects,
                    "critique": str(structured.get("critique") or det["critique"]),
                    "deterministic_verdict": det["verdict"],
                    "llm_critic_status": "ok:agy_headless",
                    "usage": res.get("usage") or {},
                    "elapsed_ms": round(float(det["elapsed_ms"]) + float(res.get("latency_ms", 0.0)), 1),
                }
            llm_errors.append(f"agy:{mid}:unparseable_structured_output")
        else:
            err_s = str(res.get("error") or f"rc={res.get('rc')}")
            llm_errors.append(f"agy:{mid}:{err_s}")
            if "auth_required" in err_s or res.get("rc") == 401:
                break  # Don't retry second model if CLI OAuth isn't signed in

    # Try Tier-2 direct Gemini REST API if GEMINI_API_KEY is available
    rest_res = _invoke_gemini_rest_critic(critic_model, prompt, timeout_s=timeout_s)
    if rest_res.get("ok"):
        st = rest_res["structured"]
        merged_verdict = "REVISE" if (det["verdict"] == "REVISE" or st["verdict"] == "REVISE") else "PASS"
        return {
            "verdict": merged_verdict,
            "mode": "gemini_rest",
            "critic_model": critic_model,
            "score": min(float(det["score"]), float(st.get("score", 0.5))),
            "missed_requirements": list(dict.fromkeys(det["missed_requirements"] + list(st.get("missed_requirements") or []))),
            "unverified_claims": list(dict.fromkeys(det["unverified_claims"] + list(st.get("unverified_claims") or []))),
            "defects": list(det["defects"]) + list(st.get("defects") or []),
            "critique": str(st.get("critique") or det["critique"]),
            "deterministic_verdict": det["verdict"],
            "llm_critic_status": "ok:gemini_rest",
            "elapsed_ms": round(float(det["elapsed_ms"]) + float(rest_res.get("latency_ms", 0.0)), 1),
        }
    if rest_res.get("error"):
        llm_errors.append(f"rest:{rest_res['error']}")

    # Honest fallback: NEVER fake LLM critic approval when headless credentials are unavailable
    det["llm_critic_status"] = "unavailable_fallback_deterministic"
    det["llm_errors"] = llm_errors
    det["setup_hint"] = (
        "Run `agy` interactively once in Termux to cache CLI OAuth OR set GEMINI_API_KEY in ~/.omega_env "
        "to enable automatic separate-model headless critique. Native `omega-prosecutor` subagent works right now."
    )
    return det
