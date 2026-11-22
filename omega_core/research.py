"""Adaptive Research Engine (FAST / STANDARD / DEEP) backed by Evidence Store.

Wraps existing ~/tools/web_gather.py, ~/tools/deep_crawl.py, and
~/tools/swarm_research.py while enforcing:
- URL deduplication and bounded source caps (stopping rules)
- Automatic Appendix A.3 Evidence Record creation with SHA-256 hashes
- Contradiction preservation (never collapses conflicting claims)
- Measured time-to-first-result and total latency
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

from . import OmegaPaths, get_paths
from .memory import KnowledgeFabric

MODE_CAPS = {
    "FAST": {"max_urls": 3, "timeout_s": 20, "use_swarm": False},
    "STANDARD": {"max_urls": 6, "timeout_s": 40, "use_swarm": False},
    "DEEP": {"max_urls": 12, "timeout_s": 75, "use_swarm": True},
}


class ResearchEngine:
    def __init__(self, paths: OmegaPaths | None = None):
        self.paths = paths or get_paths()
        self.kf = KnowledgeFabric(self.paths)
        self.tools_dir = os.path.expanduser("~/tools")

    def run(
        self,
        question: str,
        *,
        mode: str = "FAST",
        urls: list[str] | None = None,
        mission_id: str = "",
        corpus_query: str = "",
    ) -> dict[str, Any]:
        m = mode.upper().strip()
        if m not in MODE_CAPS:
            raise ValueError(f"Unsupported research mode: {mode}. Choose FAST, STANDARD, or DEEP.")
        cfg = MODE_CAPS[m]
        t0 = time.monotonic()
        t_first: float | None = None

        dedup_urls: list[str] = []
        seen: set[str] = set()
        for u in urls or []:
            cu = u.strip()
            if cu and cu not in seen:
                seen.add(cu)
                dedup_urls.append(cu)
            if len(dedup_urls) >= cfg["max_urls"]:
                break

        evidence_ids: list[str] = []
        errors: list[str] = []

        # 1. Local FTS5 corpus query first (<5ms, $0.00)
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
            except Exception as e:
                errors.append(f"corpus_query:{e}")

        # 2. Live URL fetch via web_gather.py (with stopping-rule cap)
        web_gather = os.path.join(self.tools_dir, "web_gather.py")
        if dedup_urls and os.path.exists(web_gather):
            try:
                r = subprocess.run(
                    ["python3", web_gather, *dedup_urls],
                    capture_output=True,
                    text=True,
                    timeout=cfg["timeout_s"],
                )
                if r.returncode == 0 and r.stdout.strip():
                    if t_first is None:
                        t_first = round((time.monotonic() - t0) * 1000.0, 1)
                    ev = self.kf.record_evidence(
                        claim_text=f"Fetched primary web evidence for: {question[:140]}",
                        source_id="web_gather",
                        locator=",".join(dedup_urls[:3]),
                        content_sample=r.stdout[:4000],
                        mission_id=mission_id,
                        source_type="primary",
                        retrieval_scope="full_text",
                        support_type="supports",
                        verification_method="live_http_fetch",
                        verification_status="verified",
                    )
                    evidence_ids.append(ev["evidence_id"])
                else:
                    errors.append(f"web_gather_rc={r.returncode}")
            except subprocess.TimeoutExpired:
                errors.append(f"web_gather_timeout_{cfg['timeout_s']}s")

        # 3. DEEP mode optional 3-worker adversarial swarm
        swarm_out = ""
        swarm_py = os.path.join(self.tools_dir, "swarm_research.py")
        if cfg["use_swarm"] and os.path.exists(swarm_py):
            out_file = os.path.join(self.paths.tmpdir, f"omega_research_{int(time.time())}.md")
            cmd = ["python3", swarm_py, question, "--out", out_file]
            if corpus_query:
                cmd += ["--corpus-query", corpus_query]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg["timeout_s"])
                if r.returncode == 0 and os.path.exists(out_file):
                    swarm_out = out_file
                    if t_first is None:
                        t_first = round((time.monotonic() - t0) * 1000.0, 1)
                    with open(out_file, "r", encoding="utf-8", errors="replace") as f:
                        txt = f.read()
                    ev = self.kf.record_evidence(
                        claim_text=f"3-worker adversarial synthesis: {question[:120]}",
                        source_id="swarm_research",
                        locator=f"file://{out_file}",
                        content_sample=txt[:4000],
                        mission_id=mission_id,
                        source_type="secondary",
                        retrieval_scope="full_text",
                        support_type="contextualizes",
                        verification_method="cross_family_swarm",
                        verification_status="partial",
                    )
                    evidence_ids.append(ev["evidence_id"])
            except subprocess.TimeoutExpired:
                errors.append("swarm_timeout")

        total_ms = round((time.monotonic() - t0) * 1000.0, 1)
        conflicts = self.kf.detect_claim_conflicts(mission_id) if mission_id else []
        return {
            "mode": m,
            "question": question,
            "urls_processed": len(dedup_urls),
            "evidence_ids": evidence_ids,
            "conflicts": conflicts,
            "swarm_report": swarm_out,
            "time_to_first_ms": t_first if t_first is not None else total_ms,
            "total_ms": total_ms,
            "errors": errors,
        }
