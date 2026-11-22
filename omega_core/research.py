"""Adaptive Research Engine (FAST / STANDARD / DEEP) — Doctrine Part V Implementation.

Implements:
- Date-sensitivity detection (prevents stale training-cutoff answers on current topics)
- Step 2: Prior knowledge & Evidence Store lookup before rediscovery
- Step 4: Parallel $0.00 live web discovery (HN Algolia, arXiv, DuckDuckGo Instant,
  plus optional live `agy` search_web grounding) + URL deduplication
- Step 7: Selective full-text fetch via ~/tools/web_gather.py -> Appendix A.3 Evidence Store
- Section 20: Anti-loop content-hash / URL freshness verification cache
- Section 20/21: One-pass cross-family adversarial challenge (grounded ONLY in live evidence)
  + explicit stop_reason + honest readiness_status (VERIFIED / PARTIAL / PROVISIONAL / UNVERIFIED)
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from . import OmegaPaths, get_paths
from .fabric import IntelligenceFabric
from .memory import KnowledgeFabric, connect_vault

MODE_CAPS = {
    "FAST": {"max_urls": 4, "timeout_s": 25, "use_challenge": False, "use_swarm": False},
    "STANDARD": {"max_urls": 8, "timeout_s": 45, "use_challenge": True, "use_swarm": False},
    "DEEP": {"max_urls": 12, "timeout_s": 75, "use_challenge": True, "use_swarm": True},
}

DATE_SENSITIVE_RX = re.compile(
    r"\b(?:latest|newest|current|recent|today|now|release|version|2025|2026|2027|price|roadmap|update|benchmark)\b",
    re.IGNORECASE,
)

UA = "OmegaApexResearch/6.0 (Android; $0.00 pure-stdlib)"


def is_date_sensitive(question: str) -> bool:
    return bool(DATE_SENSITIVE_RX.search(question))


def _http_get_json(url: str, timeout: int = 8) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(131072).decode("utf-8", errors="replace"))
    except Exception:
        return None


def _discover_hn(query: str, date_sensitive: bool, limit: int = 4) -> list[dict[str, str]]:
    ep = "search_by_date" if date_sensitive else "search"
    url = f"https://hn.algolia.com/api/v1/{ep}?query={urllib.parse.quote(query)}&tags=story&hitsPerPage={limit}"
    data = _http_get_json(url, timeout=8)
    if not data:
        return []
    out = []
    for h in data.get("hits", []):
        u = (h.get("url") or "").strip()
        if u.startswith(("http://", "https://")):
            out.append(
                {
                    "source": "hn_algolia",
                    "url": u,
                    "title": str(h.get("title") or "")[:180],
                    "published_at": str(h.get("created_at") or "")[:20],
                }
            )
    return out


def _discover_ddg(query: str, limit: int = 3) -> list[dict[str, str]]:
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    data = _http_get_json(url, timeout=8)
    if not data:
        return []
    out = []
    abs_url = str(data.get("AbstractURL") or "").strip()
    if abs_url.startswith(("http://", "https://")):
        out.append(
            {
                "source": "ddg_instant",
                "url": abs_url,
                "title": str(data.get("Heading") or query)[:180],
                "snippet": str(data.get("AbstractText") or "")[:400],
            }
        )
    for topic in data.get("RelatedTopics", []):
        if len(out) >= limit:
            break
        if isinstance(topic, dict) and str(topic.get("FirstURL", "")).startswith(("http://", "https://")):
            out.append(
                {
                    "source": "ddg_instant",
                    "url": topic["FirstURL"],
                    "title": str(topic.get("Text") or "")[:180],
                }
            )
    return out[:limit]


def _discover_arxiv(query: str, limit: int = 3) -> list[dict[str, str]]:
    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query=all:{urllib.parse.quote(query)}&max_results={limit}&sortBy=submittedDate&sortOrder=descending"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            xml_raw = r.read(131072)
        root = ET.fromstring(xml_raw)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for entry in root.findall("a:entry", ns):
            eid = (entry.findtext("a:id", "", ns) or "").strip()
            title = re.sub(r"\s+", " ", (entry.findtext("a:title", "", ns) or "")).strip()
            pub = (entry.findtext("a:published", "", ns) or "")[:20]
            if eid.startswith(("http://", "https://")):
                out.append({"source": "arxiv", "url": eid, "title": title[:180], "published_at": pub})
        return out
    except Exception:
        return []


def live_discover_urls(query: str, *, date_sensitive: bool, max_urls: int = 4) -> list[dict[str, str]]:
    """Run parallel $0.00 live API discovery (HN Algolia, DDG Instant, arXiv) with strict timeout."""
    discovered: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = [
            ex.submit(_discover_hn, query, date_sensitive, max_urls),
            ex.submit(_discover_ddg, query, 2),
            ex.submit(_discover_arxiv, query, 2),
        ]
        for f in futs:
            try:
                discovered.extend(f.result(timeout=10))
            except Exception:
                pass
    return discovered


class ResearchEngine:
    def __init__(self, paths: OmegaPaths | None = None, fabric: IntelligenceFabric | None = None):
        self.paths = paths or get_paths()
        self.kf = KnowledgeFabric(self.paths)
        self.fabric = fabric or IntelligenceFabric(self.paths)
        self.tools_dir = os.path.expanduser("~/tools")

    def _find_cached_evidence(self, locator: str, freshness_ttl_s: int) -> dict[str, Any] | None:
        """Section 20 Anti-Loop Cache: reuse verified evidence if URL is fresh and unchanged."""
        conn = connect_vault(self.paths)
        try:
            row = conn.execute(
                """
                SELECT evidence_id, content_hash, retrieved_at, verification_status
                FROM evidence
                WHERE locator = ? AND verification_status = 'verified'
                ORDER BY retrieved_at DESC LIMIT 1
                """,
                (locator,),
            ).fetchone()
            if row and (int(time.time()) - int(row["retrieved_at"]) <= freshness_ttl_s):
                return dict(row)
            return None
        finally:
            conn.close()

    def _web_grounded_discovery(self, question: str, today: str, timeout_s: int = 30) -> dict[str, Any]:
        """Run a live web-search-grounded model call via `agy` so answers NEVER rely on stale cutoff weights."""
        prompt = (
            f"Today's date is {today}. Use live web search (search_web) to answer this question with up-to-date primary sources. "
            "Do NOT rely on stale training memory for current versions, dates, or releases. "
            "Return concise bullets with exact inline URLs and publication dates, plus an UNVERIFIED line for anything unconfirmed.\n"
            f"Question: {question}"
        )
        # Prefer fast qualified flash/sonnet model from live pool
        return self.fabric.execute_with_fallback(
            "fast live web grounded lookup",
            prompt,
            timeout_s=timeout_s,
            max_attempts=2,
        )

    def _cross_family_challenge(
        self,
        question: str,
        today: str,
        evidence_snippets: list[str],
        timeout_s: int = 35,
    ) -> dict[str, Any]:
        """Section 20 One-Pass Cross-Family Adversarial Challenge grounded strictly in retrieved evidence."""
        joined = "\n\n".join(evidence_snippets)[:8000]
        prompt = (
            f"Today's date is {today}. Act as an independent adversarial reviewer.\n"
            f"Question: {question}\n\n"
            f"GROUNDED LIVE EVIDENCE (do NOT invent facts outside this evidence; flag stale or missing info explicitly):\n{joined}\n\n"
            "Write concise, mobile-safe markdown with these EXACT headings:\n"
            "## Evidence\n## Contrarian / Non-Consensus Point\n## Falsification Check\n## UNVERIFIED\n"
        )
        # Route through security_audit (prefers claude-opus/sonnet/gpt-oss cross-family pool)
        return self.fabric.execute_with_fallback(
            "adversarial security audit review",
            prompt,
            timeout_s=timeout_s,
            max_attempts=2,
        )

    def run(
        self,
        question: str,
        *,
        mode: str = "FAST",
        urls: list[str] | None = None,
        mission_id: str = "",
        corpus_query: str = "",
        task_family: str = "general",
        live_search: bool = True,
        web_ground: bool = False,
        challenge: bool | None = None,
        offline: bool = False,
    ) -> dict[str, Any]:
        m = mode.upper().strip()
        if m not in MODE_CAPS:
            raise ValueError(f"Unsupported research mode: {mode}. Choose FAST, STANDARD, or DEEP.")
        cfg = MODE_CAPS[m]
        t0 = time.monotonic()
        t_first: float | None = None
        today = time.strftime("%Y-%m-%d")
        date_sens = is_date_sensitive(question)
        freshness_ttl_s = 3600 if date_sens else 86400

        evidence_ids: list[str] = []
        evidence_snippets: list[str] = []
        errors: list[str] = []
        cache_hits = 0

        # Step 2: Prior knowledge & memory retrieval BEFORE paying rediscovery cost
        # Build BM25-friendly OR query from salient keywords so natural-language questions match
        stop = {"the", "and", "for", "with", "what", "how", "does", "from", "that", "this", "are", "was", "were", "into", "about"}
        kw = [w for w in re.findall(r"[A-Za-z0-9_]{3,}", question.lower()) if w not in stop]
        fts_q = " OR ".join(dict.fromkeys(kw[:6])) if kw else question
        prior_mems = self.kf.search_memory(fts_q, task_family=task_family, limit=5)
        if prior_mems:
            t_first = round((time.monotonic() - t0) * 1000.0, 1)
            for pm in prior_mems:
                evidence_snippets.append(f"[prior_memory:{pm['key']}|auth={pm['authority']}] {pm['text'][:300]}")

        # Local FTS5 corpus query (<5ms, $0.00)
        deep_crawl = os.path.join(self.tools_dir, "deep_crawl.py")
        if corpus_query and os.path.exists(deep_crawl):
            try:
                r = subprocess.run(
                    ["python3", deep_crawl, "query", corpus_query, "--limit", "8"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if r.returncode == 0 and r.stdout.strip():
                    if t_first is None:
                        t_first = round((time.monotonic() - t0) * 1000.0, 1)
                    ev = self.kf.record_evidence(
                        claim_text=f"Local corpus match for: {question[:140]}",
                        source_id="local_fts5_corpus",
                        locator=f"corpus://{corpus_query}",
                        content_sample=r.stdout[:2000],
                        mission_id=mission_id,
                        source_type="dataset",
                        retrieval_scope="snippet",
                        support_type="contextualizes",
                        verification_method="fts5_query",
                        verification_status="verified",
                    )
                    evidence_ids.append(ev["evidence_id"])
                    evidence_snippets.append(f"[corpus:{corpus_query}] {r.stdout[:1200]}")
            except Exception as e:
                errors.append(f"corpus_query:{e}")

        # Step 4: Parallel live discovery (API search + optional live search_web grounded model)
        discovered_meta: list[dict[str, str]] = []
        if not offline and live_search:
            discovered_meta = live_discover_urls(question, date_sensitive=date_sens, max_urls=cfg["max_urls"])
            if discovered_meta and t_first is None:
                t_first = round((time.monotonic() - t0) * 1000.0, 1)

        grounded_summary = ""
        if not offline and web_ground:
            wg = self._web_grounded_discovery(question, today, timeout_s=min(35, cfg["timeout_s"]))
            if wg.get("ok") and wg.get("text"):
                grounded_summary = wg["text"]
                if t_first is None:
                    t_first = round((time.monotonic() - t0) * 1000.0, 1)
                ev = self.kf.record_evidence(
                    claim_text=f"Live search_web grounded discovery ({today}): {question[:120]}",
                    source_id=f"search_web:{wg['model_used']}",
                    locator=f"search_web://{today}/{hashlib.sha256(question.encode()).hexdigest()[:10]}",
                    content_sample=grounded_summary[:4000],
                    mission_id=mission_id,
                    source_type="secondary",
                    published_at=today,
                    retrieval_scope="snippet",
                    support_type="supports",
                    verification_method="live_search_web",
                    verification_status="partial",
                    limitations="Search-grounded synthesis; inspect primary URLs for full verification.",
                )
                evidence_ids.append(ev["evidence_id"])
                evidence_snippets.append(f"[live_search_web:{wg['model_used']}] {grounded_summary[:2500]}")
                # Extract any discovered URLs from the grounded response for primary full-text verification
                for u in re.findall(r"https?://[^\s\)\]>\"']+", grounded_summary):
                    discovered_meta.append({"source": "search_web", "url": u.rstrip(".,;:"), "title": ""})
            else:
                errors.append(f"web_ground_failed:{wg.get('error', 'unknown')}")

        # Step 5: Deduplication across user URLs + discovered URLs
        raw_urls = list(urls or []) + [d["url"] for d in discovered_meta if d.get("url")]
        dedup_urls: list[str] = []
        seen: set[str] = set()
        duplicates_dropped = 0
        for u in raw_urls:
            cu = u.strip().rstrip("/")
            if not cu:
                continue
            if cu in seen:
                duplicates_dropped += 1
                continue
            seen.add(cu)
            dedup_urls.append(u.strip())
            if len(dedup_urls) >= cfg["max_urls"]:
                break

        # Section 20 Anti-Loop: skip re-fetching URLs already verified within freshness TTL
        urls_to_fetch: list[str] = []
        for u in dedup_urls:
            cached = self._find_cached_evidence(u, freshness_ttl_s)
            if cached:
                cache_hits += 1
                evidence_ids.append(cached["evidence_id"])
            else:
                urls_to_fetch.append(u)

        # Step 7: Selective full-text retrieval via ~/tools/web_gather.py
        web_gather = os.path.join(self.tools_dir, "web_gather.py")
        fetched_ok = 0
        if not offline and urls_to_fetch and os.path.exists(web_gather):
            try:
                r = subprocess.run(
                    ["python3", web_gather, *urls_to_fetch, "--max-chars", "2500"],
                    capture_output=True,
                    text=True,
                    timeout=cfg["timeout_s"],
                )
                if r.returncode == 0 and r.stdout.strip():
                    if t_first is None:
                        t_first = round((time.monotonic() - t0) * 1000.0, 1)
                    try:
                        pages = json.loads(r.stdout)
                    except json.JSONDecodeError:
                        pages = []
                    for pg in pages:
                        if pg.get("status", 0) == 200 and pg.get("text"):
                            fetched_ok += 1
                            ev = self.kf.record_evidence(
                                claim_text=f"Primary page [{pg.get('title', '')[:80]}] for: {question[:100]}",
                                source_id="web_gather",
                                locator=pg["url"],
                                content_sample=pg["text"][:3000],
                                mission_id=mission_id,
                                source_type="primary",
                                retrieval_scope="full_text",
                                support_type="supports",
                                verification_method="live_http_fetch",
                                verification_status="verified",
                            )
                            evidence_ids.append(ev["evidence_id"])
                            evidence_snippets.append(
                                f"[primary:{pg['url']}|title={pg.get('title','')[:80]}] {pg['text'][:1200]}"
                            )
                        elif pg.get("error"):
                            errors.append(f"fetch:{pg.get('url','')[:60]}:{pg['error']}")
                else:
                    errors.append(f"web_gather_rc={r.returncode}")
            except subprocess.TimeoutExpired:
                errors.append(f"web_gather_timeout_{cfg['timeout_s']}s")

        # Step 12: Optional one-pass cross-family adversarial challenge grounded ONLY in live evidence
        do_challenge = cfg["use_challenge"] if challenge is None else bool(challenge)
        challenge_report = ""
        gate_passed: bool | None = None
        if not offline and do_challenge and evidence_snippets:
            ch = self._cross_family_challenge(question, today, evidence_snippets, timeout_s=min(40, cfg["timeout_s"]))
            if ch.get("ok") and ch.get("text"):
                challenge_report = ch["text"]
                gate_py = os.path.join(self.tools_dir, "non_consensus_gate.py")
                if os.path.exists(gate_py):
                    tmp_md = os.path.join(self.paths.tmpdir, f"omega_gate_{int(time.time())}.md")
                    try:
                        with open(tmp_md, "w", encoding="utf-8") as f:
                            f.write(challenge_report)
                        gr = subprocess.run(["python3", gate_py, tmp_md], capture_output=True, text=True, timeout=10)
                        gate_passed = gr.returncode == 0
                    finally:
                        if os.path.exists(tmp_md):
                            os.remove(tmp_md)
            else:
                errors.append(f"challenge_failed:{ch.get('error', 'unknown')}")

        # Step 13: Explicit stopping decision & honest readiness status (Section 21 & 22)
        conflicts = self.kf.detect_claim_conflicts(mission_id) if mission_id else []
        total_verified = fetched_ok + cache_hits
        if offline:
            stop_reason = "offline_mode_prior_and_local_only"
        elif total_verified >= cfg["max_urls"]:
            stop_reason = f"mode_cap_reached ({cfg['max_urls']} sources for {m})"
        elif total_verified > 0 or grounded_summary:
            stop_reason = "sufficient_live_evidence_within_mode_budget"
        else:
            stop_reason = "no_live_sources_retrieved"

        if total_verified > 0 and not conflicts and (gate_passed is not False):
            readiness = "VERIFIED" if (not date_sens or fetched_ok > 0 or cache_hits > 0) else "PARTIAL"
        elif grounded_summary or prior_mems or evidence_ids:
            readiness = "PARTIAL" if not conflicts else "PROVISIONAL"
        else:
            readiness = "UNVERIFIED"

        total_ms = round((time.monotonic() - t0) * 1000.0, 1)
        return {
            "mode": m,
            "date": today,
            "date_sensitive": date_sens,
            "freshness_ttl_s": freshness_ttl_s,
            "question": question,
            "prior_memory_hits": len(prior_mems),
            "live_discovered_urls": len(discovered_meta),
            "urls_deduped": len(dedup_urls),
            "duplicates_dropped": duplicates_dropped,
            "verification_cache_hits": cache_hits,
            "primary_pages_fetched": fetched_ok,
            "evidence_ids": evidence_ids,
            "conflicts": conflicts,
            "readiness_status": readiness,
            "stop_reason": stop_reason,
            "non_consensus_gate_passed": gate_passed,
            "grounded_summary": grounded_summary[:1200] if grounded_summary else "",
            "challenge_report": challenge_report[:2000] if challenge_report else "",
            "time_to_first_ms": t_first if t_first is not None else total_ms,
            "total_ms": total_ms,
            "errors": errors,
        }
