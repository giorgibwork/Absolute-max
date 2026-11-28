"""Adaptive Multilingual Non-Consensus Research Engine (v8.0 — EN/ZH/JA/RU/KO + GitHub + Hostile Lane).

Implements Doctrine Part V + Giorgi's Non-Consensus & Multilingual standards:
- 5 Orthogonal Search Lanes ($0.00, pure Python stdlib + gh CLI):
  1. Primary Code & Issues Lane: GitHub Issues/PRs (sorted by reactions/comments) + GitHub Repos
  2. Multilingual Deep Ecosystem Lane: CN GitHub + Gitee + V2EX + JP Qiita + RU Habr + auto-expanded ZH/JA/RU terms
  3. Academic & Technical Papers Lane: arXiv (trimmed anchors) + OpenAlex (250M+ works) + Europe PMC + StackExchange
  4. Hostile Failure & Contrarian Lane: HN Comments (fixed non-OR Algolia queries!) + GitHub Issues + Lobsters anti-hype
  5. Practitioner & Live Pulse Lane: HN Stories (pts >= 5) + DDG Instant + in-process local FTS5 (`query_local_corpus`)
- Date-sensitivity guard + Section 20 Anti-Loop verification cache + per-lane health telemetry
- Optional Pure Gemini 4 Parallel Asymmetric Jury (Neon XHigh + Carbon High + Hydrogen XHigh)
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

from . import OmegaPaths, get_paths, safe_fts_query, tokenize_multilingual
from .fabric import IntelligenceFabric
from .jury import AsymmetricJury
from .memory import KnowledgeFabric, connect_vault
from .obsidian import DEFAULT_VAULT_DIR, ObsidianSync

MODE_CAPS = {
    "FAST": {"max_urls": 6, "timeout_s": 25, "deep_indexes": False, "use_jury": False},
    "STANDARD": {"max_urls": 12, "timeout_s": 45, "deep_indexes": True, "use_jury": False},
    "DEEP": {"max_urls": 24, "timeout_s": 90, "deep_indexes": True, "use_jury": True},
}

DATE_SENSITIVE_RX = re.compile(
    r"\b(?:latest|newest|current|recent|today|now|release|version|2025|2026|2027|price|roadmap|update|benchmark)\b",
    re.IGNORECASE,
)

# Idiomatic Chinese expansion map across 14 technical & personal domains
ZH_TERM_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:agent|harness|memory|llm|ai|model|gemini|antigravity|rag|mcp|prompt)\b", re.I), "大模型 智能体 架构 实测 优化"),
    (re.compile(r"\b(?:trading|quant|polymarket|kelly|market|crypto|alpha|arbitrage|defi|ton)\b", re.I), "量化 交易 策略 预测市场 实战"),
    (re.compile(r"\b(?:android|hyperos|miui|xiaomi|poco|vermeer|kernel|touch|latency|fps|termux)\b", re.I), "澎湃OS 调度 触控 延迟 优化 酷安"),
    (re.compile(r"\b(?:armwrestling|gym|hypertrophy|strength|protein|fat\s*loss|workout|pronation|tendon)\b", re.I), "腕力 力量训练 增肌 减脂 生物力学"),
    (re.compile(r"\b(?:obsidian|knowledge\s*graph|notes|workflow|productivity)\b", re.I), "知识图谱 双链 Obsidian 工作流 配置"),
    (re.compile(r"\b(?:security|audit|injection|sandbox|exploit|vulnerability|auth)\b", re.I), "安全 审计 提示注入 沙箱 防护"),
    (re.compile(r"\b(?:python|rust|go|sqlite|database|performance|benchmark|cache|fts5)\b", re.I), "性能优化 源码 基准测试 踩坑"),
    (re.compile(r"\b(?:react|next|typescript|web|frontend|css|browser|chrome|devtools)\b", re.I), "前端 性能 实战 踩坑 源码"),
    (re.compile(r"\b(?:gpu|cuda|vram|chip|npu|snapdragon|quantization|gguf|vllm)\b", re.I), "显卡 推理 量化 加速 实测"),
    (re.compile(r"\b(?:docker|kubernetes|cloud|firebase|deploy|ci|github\s*actions|serverless)\b", re.I), "云原生 部署 架构 实战 踩坑"),
    (re.compile(r"\b(?:game|roblox|tsb|combo|input|frame|ping|network)\b", re.I), "游戏 帧率 延迟 机制 优化"),
    (re.compile(r"\b(?:linux|bash|zsh|shell|cli|terminal|ssh|git|worktree)\b", re.I), "终端 命令行 效率 脚本 技巧"),
    (re.compile(r"\b(?:paper|arxiv|research|study|proof|theorem|science|biology)\b", re.I), "论文 复现 评测 实验 分析"),
    (re.compile(r"\b(?:visa|ielts|uk|immigration|tax|finance|bank)\b", re.I), "攻略 经验 避坑 实测"),
]

JA_TERM_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:agent|llm|ai|gemini|antigravity|mcp|rag|cli)\b", re.I), "エージェント 実践 検証 開発"),
    (re.compile(r"\b(?:python|rust|sqlite|performance|cache|database)\b", re.I), "高速化 実装 ベンチマーク"),
    (re.compile(r"\b(?:security|sandbox|audit|injection)\b", re.I), "セキュリティ 対策 検証"),
    (re.compile(r"\b(?:android|linux|termux|git|docker)\b", re.I), "環境構築 ハック 実践"),
]

RU_TERM_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:agent|llm|ai|gemini|antigravity|mcp|rag)\b", re.I), "ИИ агенты практика разбор"),
    (re.compile(r"\b(?:android|hyperos|shizuku|axmanager|poco|kernel|linux|security|reverse|perf|sqlite)\b", re.I), "оптимизация разбор практика"),
    (re.compile(r"\b(?:armwrestling|strength|gym|pronation|tendon)\b", re.I), "армрестлинг тренировка биомеханика"),
    (re.compile(r"\b(?:trading|quant|polymarket|crypto|market)\b", re.I), "трейдинг кванты стратегия"),
]

KO_TERM_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:agent|llm|ai|gemini|antigravity|mcp|rag|cli)\b", re.I), "에이전트 실전 벤치마크"),
    (re.compile(r"\b(?:android|hyperos|shizuku|poco|linux|sqlite|python|perf|cache)\b", re.I), "최적화 실전 트러블슈팅"),
    (re.compile(r"\b(?:armwrestling|strength|gym|pronation)\b", re.I), "팔씨름 훈련 생체역학"),
    (re.compile(r"\b(?:trading|quant|polymarket|market)\b", re.I), "퀀트 전략 백테스트"),
]

UA = "OmegaApexResearch/9.0 (Android; $0.00 pure-stdlib)"


def is_date_sensitive(question: str) -> bool:
    return bool(DATE_SENSITIVE_RX.search(question))


STOPWORDS = {
    "the", "and", "for", "with", "what", "how", "does", "from", "that", "this",
    "are", "was", "were", "into", "about", "best", "latest", "newest", "current",
    "benchmark", "comparison", "guide", "tutorial", "review", "2025", "2026",
}


def extract_anchor_terms(question: str, max_terms: int = 4) -> str:
    """Extract top distinctive multilingual anchor keywords preserving key technical nouns (e.g. HyperOS, Shizuku, AxManager)."""
    tokens = tokenize_multilingual(question, min_latin=2, min_cjk=2, max_tokens=24)
    anchors = [t for t in tokens if t.lower() not in STOPWORDS]
    dedup = list(dict.fromkeys(anchors))
    if len(dedup) <= max_terms:
        return " ".join(dedup) if dedup else question.strip()[:60]
    # Keep first core term + prioritize distinctive technical/CamelCase/acronym-with-digit nouns over filler
    picked = [dedup[0]]
    rest = [t for t in dedup[1:] if not re.fullmatch(r"\d+(?:\.\d+)+", t)]
    rest.sort(key=lambda t: (bool(re.search(r"[A-Z][a-z]+[A-Z]|^[A-Z][A-Z0-9]{2,}$", t)), len(t)), reverse=True)
    for t in rest:
        if len(picked) >= max_terms:
            break
        picked.append(t)
    return " ".join(picked)


def expand_korean_query(question: str) -> str:
    """Build a tight Korean technical query for GeekNews / KR developer search."""
    if re.search(r"[\uac00-\ud7af]", question):
        return extract_anchor_terms(question, max_terms=3)
    ko_anchor = "실전"
    for rx, ko in KO_TERM_MAP:
        if rx.search(question):
            ko_anchor = ko.split()[0]
            break
    core_en = extract_anchor_terms(question, max_terms=2)
    return f"{core_en} {ko_anchor}".strip()


def expand_chinese_query(question: str) -> str:
    """Build a tight 2-3 term Chinese query so strict-AND CN GitHub / Gitee actually return high-signal hits."""
    if re.search(r"[\u4e00-\u9fff]", question):
        return extract_anchor_terms(question, max_terms=3)
    zh_anchor = "实测"
    for rx, zh in ZH_TERM_MAP:
        if rx.search(question):
            zh_anchor = zh.split()[0]
            break
    core_en = extract_anchor_terms(question, max_terms=2)
    return f"{core_en} {zh_anchor}".strip()


def expand_japanese_query(question: str) -> str:
    """Build a tight Japanese query for Qiita / Zenn practitioner search."""
    if re.search(r"[\u3040-\u30ff]", question):
        return extract_anchor_terms(question, max_terms=3)
    ja_anchor = "実践"
    for rx, ja in JA_TERM_MAP:
        if rx.search(question):
            ja_anchor = ja.split()[0]
            break
    core_en = extract_anchor_terms(question, max_terms=2)
    return f"{core_en} {ja_anchor}".strip()


def expand_russian_query(question: str) -> str:
    """Build a tight Russian query for Habr / Russian systems & biomechanics search."""
    if re.search(r"[\u0400-\u04ff]", question):
        return extract_anchor_terms(question, max_terms=3)
    ru_anchor = "разбор"
    for rx, ru in RU_TERM_MAP:
        if rx.search(question):
            ru_anchor = ru.split()[0]
            break
    core_en = extract_anchor_terms(question, max_terms=2)
    return f"{core_en} {ru_anchor}".strip()


def _http_get_json(url: str, timeout: int = 8) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(196608).decode("utf-8", errors="replace"))
    except Exception:
        return None


# --- Orthogonal High-Signal Index Connectors ($0.00) ---

def _discover_hn_stories(query: str, date_sensitive: bool, limit: int = 5) -> list[dict[str, str]]:
    """High-signal HN stories only (points >= 5; eliminates pts=0 noise)."""
    ep = "search_by_date" if date_sensitive else "search"
    url = (
        f"https://hn.algolia.com/api/v1/{ep}?query={urllib.parse.quote(query)}"
        f"&tags=story&numericFilters=points%3E%3D5&hitsPerPage={limit}"
    )
    data = _http_get_json(url, timeout=8)
    if not isinstance(data, dict):
        return []
    out = []
    for h in data.get("hits", []):
        u = (h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID','')}").strip()
        if u.startswith(("http://", "https://")):
            out.append(
                {
                    "lane": "practitioner",
                    "source": f"hn_story(pts={h.get('points', 0)})",
                    "url": u,
                    "title": str(h.get("title") or "")[:180],
                    "published_at": str(h.get("created_at") or "")[:20],
                }
            )
    return out


def _discover_hn_comments(query: str, limit: int = 5, *, hostile: bool = False) -> list[dict[str, str]]:
    """HN practitioner comments — fixed Algolia query syntax (no broken literal OR)."""
    queries = [f"{query} broken", f"{query} problem", f"{query} issue"] if hostile else [query]
    per_q = max(2, (limit + len(queries) - 1) // len(queries))
    out: list[dict[str, str]] = []
    seen_oids: set[str] = set()
    for q in queries:
        url = f"https://hn.algolia.com/api/v1/search?query={urllib.parse.quote(q)}&tags=comment&hitsPerPage={per_q}"
        data = _http_get_json(url, timeout=8)
        if not isinstance(data, dict):
            continue
        for h in data.get("hits", []):
            oid = str(h.get("objectID") or "")
            if not oid or oid in seen_oids:
                continue
            txt = re.sub(r"<[^>]+>", " ", str(h.get("comment_text") or ""))
            txt = re.sub(r"\s+", " ", txt).strip()
            if len(txt) > 80:
                seen_oids.add(oid)
                out.append(
                    {
                        "lane": "hostile",
                        "source": "hn_hostile_comment" if hostile else "hn_comment",
                        "url": f"https://news.ycombinator.com/item?id={oid}",
                        "title": str(h.get("story_title") or "HN Comment")[:160],
                        "snippet": txt[:600],
                        "published_at": str(h.get("created_at") or "")[:20],
                    }
                )
                if len(out) >= limit:
                    return out
    return out


def _discover_qiita_jp(query: str, limit: int = 4) -> list[dict[str, str]]:
    """Japanese Qiita public API v2 — deep Japanese engineering guides ($0.00)."""
    q2 = extract_anchor_terms(query, max_terms=2)
    data = _http_get_json(f"https://qiita.com/api/v2/items?page=1&per_page={limit}&query={urllib.parse.quote(q2)}", timeout=8)
    if not isinstance(data, list) or not data:
        q1 = extract_anchor_terms(query, max_terms=1)
        data = _http_get_json(f"https://qiita.com/api/v2/items?page=1&per_page={limit}&query={urllib.parse.quote(q1)}", timeout=8)
    if not isinstance(data, list):
        return []
    out = []
    for it in data[:limit]:
        u = str(it.get("url") or "")
        if u.startswith("http"):
            body = re.sub(r"\s+", " ", str(it.get("body") or ""))[:500]
            out.append(
                {
                    "lane": "multilingual",
                    "source": f"qiita_jp(likes={it.get('likes_count', 0)})",
                    "url": u,
                    "title": str(it.get("title") or "")[:180],
                    "snippet": body,
                    "published_at": str(it.get("updated_at") or "")[:20],
                }
            )
    return out


def _discover_lobsters(query: str, limit: int = 4) -> list[dict[str, str]]:
    """Lobsters senior-engineer anti-hype feed across both newest & AI tags ($0.00)."""
    toks = [t.lower() for t in tokenize_multilingual(query, min_latin=3, max_tokens=6)]
    is_ai = bool(re.search(r"\b(?:ai|llm|agent|gemini|model|rag|mcp|prompt)\b", query, re.I))
    endpoints = ["https://lobste.rs/t/ai.json", "https://lobste.rs/newest.json"] if is_ai else ["https://lobste.rs/newest.json", "https://lobste.rs/hottest.json"]
    out: list[dict[str, str]] = []
    seen_u: set[str] = set()
    for ep in endpoints:
        data = _http_get_json(ep, timeout=8)
        if not isinstance(data, list):
            continue
        for it in data:
            title = str(it.get("title") or "")
            desc = str(it.get("description") or "")
            blob = (title + " " + desc + " " + " ".join(it.get("tags") or [])).lower()
            if toks and not any(t in blob for t in toks):
                continue
            u = str(it.get("url") or it.get("comments_url") or "")
            if u.startswith("http") and u not in seen_u:
                seen_u.add(u)
                out.append(
                    {
                        "lane": "hostile",
                        "source": f"lobsters(score={it.get('score', 0)})",
                        "url": u,
                        "title": title[:180],
                        "snippet": (desc or title)[:500],
                        "published_at": str(it.get("created_at") or "")[:20],
                    }
                )
                if len(out) >= limit:
                    return out
    return out


def _discover_habr_ru(query: str, limit: int = 4) -> list[dict[str, str]]:
    """Russian Habr universal search RSS across ANY domain (Android, biomechanics, systems, AI, $0.00)."""
    ru_q = urllib.parse.quote(expand_russian_query(query))
    url = f"https://habr.com/ru/rss/search/?q={ru_q}&order_by=relevance&target_type=posts"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            xml_raw = r.read(163840)
        root = ET.fromstring(xml_raw)
    except Exception:
        return []
    out = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", (item.findtext("description") or ""))
        desc = re.sub(r"\s+", " ", desc).strip()
        pub = (item.findtext("pubDate") or "")[:25]
        if link.startswith("http"):
            out.append(
                {
                    "lane": "multilingual",
                    "source": "habr_ru",
                    "url": link,
                    "title": title[:180],
                    "snippet": desc[:500],
                    "published_at": pub,
                }
            )
            if len(out) >= limit:
                break
    return out


def _discover_geeknews_kr(query: str, limit: int = 4) -> list[dict[str, str]]:
    """Korean GeekNews RSS filtered by multilingual query anchors ($0.00)."""
    req = urllib.request.Request("https://news.hada.io/rss/news", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            xml_raw = r.read(163840)
        root = ET.fromstring(xml_raw)
    except Exception:
        return []
    toks = [t.lower() for t in tokenize_multilingual(query + " " + expand_korean_query(query), min_latin=3, min_cjk=2, max_tokens=8)]
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for ent in root.findall("a:entry", ns):
        title = (ent.findtext("a:title", "", ns) or "").strip()
        lk_el = ent.find("a:link", ns)
        link = str(lk_el.get("href") or "") if lk_el is not None else ""
        body = re.sub(r"<[^>]+>", " ", (ent.findtext("a:content", "", ns) or ent.findtext("a:summary", "", ns) or ""))
        body = re.sub(r"\s+", " ", body).strip()
        blob = (title + " " + body).lower()
        if toks and not any(t in blob for t in toks):
            continue
        if link.startswith("http"):
            out.append(
                {
                    "lane": "multilingual",
                    "source": "geeknews_kr",
                    "url": link,
                    "title": title[:180],
                    "snippet": (body or title)[:500],
                    "published_at": (ent.findtext("a:updated", "", ns) or "")[:20],
                }
            )
            if len(out) >= limit:
                break
    return out


def _discover_github_issues(query: str, limit: int = 5) -> list[dict[str, str]]:
    """GitHub Issues/PRs sorted by reactions/comments via authenticated `gh api` ($0.00)."""
    q = urllib.parse.quote(f"{query} is:issue")
    try:
        r = subprocess.run(
            ["gh", "api", f"search/issues?q={q}&sort=comments&order=desc&per_page={limit}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return []
        data = json.loads(r.stdout)
    except Exception:
        return []
    out = []
    for it in data.get("items", []):
        u = str(it.get("html_url") or "")
        if u:
            out.append(
                {
                    "lane": "hostile",
                    "source": f"github_issue(comments={it.get('comments', 0)})",
                    "url": u,
                    "title": str(it.get("title") or "")[:180],
                    "snippet": str(it.get("body") or "")[:500],
                    "published_at": str(it.get("updated_at") or "")[:20],
                }
            )
    return out


def _discover_github_repos(query: str, *, chinese: bool = False, limit: int = 5) -> list[dict[str, str]]:
    """GitHub Repos (English or Chinese deep ecosystem) via authenticated `gh api` ($0.00)."""
    q_text = expand_chinese_query(query) if chinese else query
    q = urllib.parse.quote(q_text)
    try:
        r = subprocess.run(
            ["gh", "api", f"search/repositories?q={q}&sort=stars&order=desc&per_page={limit}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return []
        data = json.loads(r.stdout)
    except Exception:
        return []
    out = []
    for repo in data.get("items", []):
        u = str(repo.get("html_url") or "")
        if u:
            out.append(
                {
                    "lane": "chinese" if chinese else "primary",
                    "source": f"{'cn_' if chinese else ''}github_repo(stars={repo.get('stargazers_count', 0)})",
                    "url": u,
                    "title": f"{repo.get('full_name','')}: {str(repo.get('description') or '')[:140]}",
                    "snippet": str(repo.get("description") or "")[:400],
                    "published_at": str(repo.get("pushed_at") or "")[:20],
                }
            )
    return out


def _discover_gitee_cn(query: str, limit: int = 4) -> list[dict[str, str]]:
    """Chinese Gitee public repository search API ($0.00)."""
    zh_q = urllib.parse.quote(expand_chinese_query(query))
    data = _http_get_json(f"https://gitee.com/api/v5/search/repositories?q={zh_q}&sort=stars_count&order=desc&per_page={limit}", timeout=8)
    if not isinstance(data, list):
        return []
    out = []
    for repo in data[:limit]:
        u = str(repo.get("html_url") or "")
        if u.startswith("http"):
            out.append(
                {
                    "lane": "chinese",
                    "source": f"gitee_cn(stars={repo.get('stargazers_count', 0)})",
                    "url": u,
                    "title": f"{repo.get('full_name','')}: {str(repo.get('description') or '')[:140]}",
                    "snippet": str(repo.get("description") or "")[:400],
                }
            )
    return out


def _discover_openalex(query: str, limit: int = 4) -> list[dict[str, str]]:
    """OpenAlex (250M+ scholarly papers, citation-ranked, free JSON API)."""
    url = f"https://api.openalex.org/works?search={urllib.parse.quote(query)}&sort=cited_by_count:desc&per-page={limit}"
    data = _http_get_json(url, timeout=8)
    if not isinstance(data, dict):
        return []
    out = []
    for w in data.get("results", []):
        loc = (w.get("primary_location") or {}).get("landing_page_url") or w.get("doi") or w.get("id") or ""
        if str(loc).startswith("http"):
            out.append(
                {
                    "lane": "academic",
                    "source": f"openalex(cites={w.get('cited_by_count', 0)})",
                    "url": str(loc),
                    "title": str(w.get("title") or "")[:180],
                    "published_at": str(w.get("publication_year") or ""),
                }
            )
    return out


def _discover_stackexchange(query: str, limit: int = 4) -> list[dict[str, str]]:
    """StackExchange API (StackOverflow high-vote technical answers)."""
    url = (
        f"https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=votes"
        f"&q={urllib.parse.quote(query)}&site=stackoverflow&pagesize={limit}"
    )
    data = _http_get_json(url, timeout=8)
    if not isinstance(data, dict):
        return []
    out = []
    for it in data.get("items", []):
        u = str(it.get("link") or "")
        if u.startswith("http"):
            out.append(
                {
                    "lane": "practitioner",
                    "source": f"stackoverflow(score={it.get('score', 0)})",
                    "url": u,
                    "title": str(it.get("title") or "")[:180],
                }
            )
    return out


def _discover_europe_pmc(query: str, limit: int = 3) -> list[dict[str, str]]:
    """Europe PMC / PubMed free JSON API (biomedical, strength, nutrition, biomechanics)."""
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(query)}&format=json&resultType=core&pageSize={limit}"
    data = _http_get_json(url, timeout=8)
    if not isinstance(data, dict):
        return []
    out = []
    for r in (data.get("resultList") or {}).get("result", []):
        pmid = r.get("pmid") or ""
        u = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        if u:
            out.append(
                {
                    "lane": "academic",
                    "source": f"pubmed_epmc(cites={r.get('citedByCount', 0)})",
                    "url": u,
                    "title": str(r.get("title") or "")[:180],
                    "snippet": str(r.get("abstractText") or r.get("title") or "")[:500],
                    "published_at": str(r.get("pubYear") or ""),
                }
            )
    return out


def _discover_ddg(query: str, limit: int = 2) -> list[dict[str, str]]:
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    data = _http_get_json(url, timeout=8)
    if not isinstance(data, dict):
        return []
    out = []
    abs_url = str(data.get("AbstractURL") or "").strip()
    if abs_url.startswith(("http://", "https://")):
        out.append(
            {
                "lane": "primary",
                "source": "ddg_instant",
                "url": abs_url,
                "title": str(data.get("Heading") or query)[:180],
                "snippet": str(data.get("AbstractText") or "")[:400],
            }
        )
    return out[:limit]


def _discover_arxiv(query: str, limit: int = 4) -> list[dict[str, str]]:
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
            summary = re.sub(r"\s+", " ", (entry.findtext("a:summary", "", ns) or "")).strip()
            pub = (entry.findtext("a:published", "", ns) or "")[:20]
            if eid.startswith(("http://", "https://")):
                out.append(
                    {
                        "lane": "academic",
                        "source": "arxiv",
                        "url": eid,
                        "title": title[:180],
                        "snippet": summary[:500],
                        "published_at": pub,
                    }
                )
        return out
    except Exception:
        return []


def live_discover_multi_index(
    query: str,
    *,
    date_sensitive: bool,
    deep_indexes: bool = False,
) -> tuple[list[dict[str, str]], list[str]]:
    """Run parallel high-signal multi-index discovery (EN + ZH + JA + RU + Hostile + Academic)."""
    anchor_q = extract_anchor_terms(query, max_terms=3)
    anchor_2 = extract_anchor_terms(query, max_terms=2)
    tasks: list[tuple[str, Any, tuple]] = [
        ("hn_stories_pts5", _discover_hn_stories, (anchor_2, date_sensitive, 5)),
        ("hn_hostile_comments", lambda q: _discover_hn_comments(q, limit=5, hostile=True), (anchor_2,)),
        ("github_repos_en", _discover_github_repos, (anchor_q,)),
        ("github_repos_cn", lambda q: _discover_github_repos(q, chinese=True, limit=4), (query,)),
        ("github_issues", _discover_github_issues, (anchor_2, 4)),
        ("arxiv", _discover_arxiv, (anchor_q, 4)),
        ("ddg_instant", _discover_ddg, (anchor_q, 2)),
        ("qiita_jp", _discover_qiita_jp, (query, 4)),
        ("lobsters", _discover_lobsters, (query, 4)),
    ]
    if deep_indexes:
        tasks += [
            ("gitee_cn", _discover_gitee_cn, (query, 4)),
            ("habr_ru", _discover_habr_ru, (query, 4)),
            ("geeknews_kr", _discover_geeknews_kr, (query, 4)),
            ("openalex", _discover_openalex, (anchor_q, 4)),
            ("stackoverflow", _discover_stackexchange, (anchor_q, 4)),
            ("europe_pmc", _discover_europe_pmc, (anchor_q, 3)),
        ]

    discovered: list[dict[str, str]] = []
    indexes_used: list[str] = []
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(tasks)))
    try:
        fut_map = {ex.submit(fn, *args): name for name, fn, args in tasks}
        try:
            for fut in concurrent.futures.as_completed(fut_map, timeout=14):
                name = fut_map[fut]
                try:
                    res = fut.result(timeout=1)
                    if res:
                        indexes_used.append(name)
                        discovered.extend(res)
                except Exception:
                    pass
        except concurrent.futures.TimeoutError:
            for fut in fut_map:
                if not fut.done():
                    fut.cancel()
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return discovered, sorted(indexes_used)


class ResearchEngine:
    def __init__(self, paths: OmegaPaths | None = None, fabric: IntelligenceFabric | None = None):
        self.paths = paths or get_paths()
        self.kf = KnowledgeFabric(self.paths)
        self.fabric = fabric or IntelligenceFabric(self.paths)
        self.tools_dir = os.path.expanduser("~/tools")

    def _find_cached_evidence(self, locator: str, freshness_ttl_s: int) -> dict[str, Any] | None:
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
        export_obsidian: bool = False,
        vault_dir: str = DEFAULT_VAULT_DIR,
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
        zh_query = expand_chinese_query(question)

        evidence_ids: list[str] = []
        positive_snippets: list[str] = []
        hostile_snippets: list[str] = []
        errors: list[str] = []
        cache_hits = 0

        # Step 2: Prior knowledge & multilingual memory retrieval BEFORE paying rediscovery cost (pass raw question!)
        prior_mems = self.kf.search_memory(question, task_family=task_family, limit=5) if question.strip() else []
        if prior_mems:
            t_first = round((time.monotonic() - t0) * 1000.0, 1)
            for pm in prior_mems:
                positive_snippets.append(f"[prior:{pm['key']}|auth={pm['authority']}] {pm['text'][:300]}")

        # In-process local SQLite FTS5 corpus query (<5ms, $0.00, 0 subprocess overhead)
        cq = (corpus_query or question).strip()
        if cq:
            try:
                from .omni import query_local_corpus

                loc = query_local_corpus(cq, top_k=6)
                hits = loc.get("top_hits") or []
                if hits:
                    if t_first is None:
                        t_first = round((time.monotonic() - t0) * 1000.0, 1)
                    summary_lines = [f"[{h['source']}|{h['url']}] {h['title']}: {h['snippet']}" for h in hits]
                    summary_blob = "\n".join(summary_lines)
                    ev = self.kf.record_evidence(
                        claim_text=f"Local FTS5 corpus match ({len(hits)} hits) for: {question[:120]}",
                        source_id="local_fts5_corpus",
                        locator=f"corpus://{cq[:80]}",
                        content_sample=summary_blob[:2000],
                        mission_id=mission_id,
                        source_type="dataset",
                        retrieval_scope="snippet",
                        support_type="contextualizes",
                        verification_method="fts5_query",
                        verification_status="verified",
                    )
                    evidence_ids.append(ev["evidence_id"])
                    for h in hits:
                        line = f"[corpus:{h['source']}|{h['url']}] {h['title']}: {h['snippet']}"
                        if h.get("lane") == "hostile" or "hostile" in str(h.get("source", "")):
                            hostile_snippets.append(line)
                        else:
                            positive_snippets.append(line)
            except Exception as e:
                errors.append(f"corpus_query:{e}")

        # Step 4: Multi-Index Parallel Discovery (EN + CN + GitHub Issues/Repos + Academic + HN Comments)
        discovered_meta: list[dict[str, str]] = []
        indexes_hit: list[str] = []
        if not offline and live_search:
            discovered_meta, indexes_hit = live_discover_multi_index(
                question, date_sensitive=date_sens, deep_indexes=cfg["deep_indexes"]
            )
            if discovered_meta and t_first is None:
                t_first = round((time.monotonic() - t0) * 1000.0, 1)
            for d in discovered_meta:
                snip = d.get("snippet") or d.get("title") or ""
                if snip:
                    line = f"[{d['source']}|{d['url']}] {d.get('title','')}: {snip[:350]}"
                    if d.get("lane") == "hostile":
                        hostile_snippets.append(line)
                    else:
                        positive_snippets.append(line)

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

        # Section 20 Anti-Loop verification cache
        urls_to_fetch: list[str] = []
        for u in dedup_urls:
            cached = self._find_cached_evidence(u, freshness_ttl_s)
            if cached:
                cache_hits += 1
                evidence_ids.append(cached["evidence_id"])
            else:
                urls_to_fetch.append(u)

        # Step 7: In-process pooled HTTP/2 + trafilatura full-text fetch (honors cfg["max_urls"] & preserves hostile lane!)
        url_lane_map = {d["url"].strip().rstrip("/"): str(d.get("lane") or "primary") for d in discovered_meta if d.get("url")}
        fetched_ok = 0
        if not offline and urls_to_fetch:
            from .omni import UA as OMNI_UA, fetch_public_page

            targets = urls_to_fetch[: cfg["max_urls"]]
            shared_cli = None
            try:
                import httpx  # type: ignore

                shared_cli = httpx.Client(
                    http2=True,
                    follow_redirects=True,
                    timeout=8,
                    headers={"User-Agent": OMNI_UA},
                    limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
                )
            except Exception:
                shared_cli = None
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
                    pages = list(ex.map(lambda u: fetch_public_page(u, timeout=8, client=shared_cli), targets))
                if pages and t_first is None:
                    t_first = round((time.monotonic() - t0) * 1000.0, 1)
                for pg in pages:
                    if pg.get("ok") and pg.get("text"):
                        fetched_ok += 1
                        lane = url_lane_map.get(pg["url"].strip().rstrip("/"), "primary")
                        ev = self.kf.record_evidence(
                            claim_text=f"Primary page [{pg.get('title', '')[:80]}] for: {question[:100]}",
                            source_id=f"omni:{pg.get('engine', 'http')}",
                            locator=pg["url"],
                            content_sample=pg["text"][:3000],
                            mission_id=mission_id,
                            source_type="primary",
                            retrieval_scope="full_text",
                            support_type="refutes" if lane == "hostile" else "supports",
                            verification_method="live_http_fetch",
                            verification_status="verified",
                        )
                        evidence_ids.append(ev["evidence_id"])
                        if lane == "hostile":
                            hostile_snippets.append(f"[hostile_page:{pg['url']}] {pg['text'][:1000]}")
                        else:
                            positive_snippets.append(f"[primary:{pg['url']}] {pg['text'][:1000]}")
                    elif pg.get("error"):
                        errors.append(f"fetch:{pg.get('url','')[:60]}:{pg['error']}")
            finally:
                if shared_cli is not None:
                    try:
                        shared_cli.close()
                    except Exception:
                        pass

        # Step 12: Optional Pure Gemini Cross-Pool Parallel Asymmetric Jury
        do_jury = cfg["use_jury"] if challenge is None else bool(challenge)
        jury_out: dict[str, Any] = {}
        if not offline and do_jury and (positive_snippets or hostile_snippets):
            jury = AsymmetricJury(self.paths, self.fabric)
            jury_out = jury.deliberate(
                question,
                positive_evidence="\n".join(positive_snippets),
                hostile_evidence="\n".join(hostile_snippets),
                export_obsidian=export_obsidian,
                vault_dir=vault_dir,
            )
        elif export_obsidian and discovered_meta:
            obs = ObsidianSync(vault_dir=vault_dir, paths=self.paths)
            body = "## Live Multi-Index Sources\n" + "\n".join(
                f"- [{d.get('title') or d['url']}]({d['url']}) (`{d['source']}`)"
                for d in discovered_meta[:15]
            )
            jury_out["dossier_path"] = obs.export_dossier(question[:80], body, tags=[m.lower(), "multi-index"])

        conflicts = self.kf.detect_claim_conflicts(mission_id) if mission_id else []
        total_verified = fetched_ok + cache_hits
        if offline:
            stop_reason = "offline_mode_prior_and_local_only"
        elif total_verified >= cfg["max_urls"]:
            stop_reason = f"mode_cap_reached ({cfg['max_urls']} sources for {m})"
        elif total_verified > 0 or discovered_meta:
            stop_reason = f"sufficient_multi_index_evidence ({len(indexes_hit)} indexes)"
        else:
            stop_reason = "no_live_sources_retrieved"

        if total_verified > 0 and not conflicts:
            readiness = "VERIFIED"
        elif discovered_meta or prior_mems or evidence_ids:
            readiness = "PARTIAL"
        else:
            readiness = "UNVERIFIED"

        total_ms = round((time.monotonic() - t0) * 1000.0, 1)
        lane_counts: dict[str, int] = {}
        for d in discovered_meta:
            ln = str(d.get("lane") or "general")
            lane_counts[ln] = lane_counts.get(ln, 0) + 1
        return {
            "mode": m,
            "date": today,
            "date_sensitive": date_sens,
            "chinese_query": zh_query,
            "japanese_query": expand_japanese_query(question),
            "russian_query": expand_russian_query(question),
            "korean_query": expand_korean_query(question),
            "indexes_hit": indexes_hit,
            "indexes_count": len(indexes_hit),
            "lane_counts": lane_counts,
            "hostile_snippets_count": len(hostile_snippets),
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
            "jury": jury_out,
            "time_to_first_ms": t_first if t_first is not None else total_ms,
            "total_ms": total_ms,
            "errors": errors,
        }
