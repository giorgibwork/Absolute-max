"""OMEGA Omni-Toolkit (AntiGem Native Android Edition — $0.00, Zero LLM Tokens).

Provides high-value local scraping, 500+ page bulk SQLite FTS5 crawling,
instant YouTube transcripts, and document parsing (PDF/DOCX/XLSX/YAML):
- Clean HTML -> Markdown extraction: trafilatura -> scrapling Selector -> bs4 -> stdlib
- 500+ Page Bulk Crawler (omega_corpus.db): parallel seed discovery via ddgs (EN+CN),
  GitHub EN+CN repos & issues, HN stories (pts>=5) + comments, arXiv, OpenAlex,
  StackOverflow + threaded httpx/urllib full-page fetch & BFS link expansion.
  Strictly skips CAPTCHA/anti-bot gated pages (no bypasses) and indexes clean
  public pages into local SQLite FTS5 for <5ms BM25 search at 0 LLM tokens.
- Instant YouTube captions (<1.5s, zero video download) via youtube-transcript-api.
- Document readers for PDF, DOCX, XLSX, YAML.
"""
from __future__ import annotations

import collections
import concurrent.futures
import hashlib
import html.parser
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import warnings
from typing import Any

warnings.filterwarnings("ignore", message=".*SOCKS support in urllib3.*")

from . import OmegaPaths, ensure_dirs, get_paths, tune_sqlite
from .research import (
    _discover_arxiv,
    _discover_github_issues,
    _discover_github_repos,
    _discover_hn_comments,
    _discover_hn_stories,
    _discover_openalex,
    _discover_stackexchange,
    expand_chinese_query,
    extract_anchor_terms,
)

UA = "Mozilla/5.0 (Linux; Android 16) OmegaApexOmni/6.3 (PublicResearch)"
MAX_PAGE_BYTES = 196608
BLOCKED_SIGNATURES = (
    "cf-browser-verification",
    "just a moment...",
    "attention required! | cloudflare",
    "verify you are human",
    "g-recaptcha",
    "hcaptcha",
)


class _SimpleHTML(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "aside"}

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self._skip = 0
        self._in_title = False
        self.title = ""
        self.chunks: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in self.SKIP:
            self._skip += 1
        elif t == "title":
            self._in_title = True
        elif t == "a":
            for k, v in attrs:
                if k == "href" and v and not v.startswith(("#", "javascript:", "mailto:")):
                    u = urllib.parse.urljoin(self.base_url, v).split("#")[0]
                    if u.startswith(("http://", "https://")):
                        self.links.append(u)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self.SKIP and self._skip > 0:
            self._skip -= 1
        elif t == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip > 0:
            return
        s = data.strip()
        if not s:
            return
        if self._in_title and not self.title:
            self.title = s[:200]
        else:
            self.chunks.append(s)


def _is_gated(html_txt: str) -> bool:
    low = (html_txt or "")[:3500].lower()
    return any(sig in low for sig in BLOCKED_SIGNATURES)


def extract_clean_text(html_txt: str, url: str = "") -> tuple[str, str, list[str]]:
    """Extract (title, clean_markdown_or_text, links) using best installed parser."""
    if not html_txt:
        return "", "", []
    # Always extract links + title cleanly via lightweight stdlib parser
    p = _SimpleHTML(url)
    try:
        p.feed(html_txt)
    except Exception:
        pass
    title = p.title
    links = list(dict.fromkeys(p.links))[:40]

    # 1. Trafilatura (highest quality article -> Markdown)
    try:
        import trafilatura  # type: ignore

        md = trafilatura.extract(html_txt, url=url or None, output_format="markdown", include_links=False)
        if md and len(md.strip()) > 80:
            return title, md.strip(), links
    except Exception:
        pass

    # 2. Scrapling Selector (adaptive CSS/DOM extraction if installed)
    try:
        from scrapling.parser import Selector  # type: ignore

        sel = Selector(html_txt)
        body_txt = " ".join(t.strip() for t in sel.css("article ::text, main ::text, p ::text").getall() if t.strip())
        if len(body_txt) > 120:
            return title, re.sub(r"\s+", " ", body_txt), links
    except Exception:
        pass

    # 3. BeautifulSoup4 + html2text (clean Crawl4AI-style Markdown, zero C/Rust deps)
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html_txt, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "aside"]):
            tag.decompose()
        if not title and soup.title and soup.title.string:
            title = soup.title.string.strip()[:200]
        main_el = soup.find("article") or soup.find("main") or soup.body or soup
        try:
            import html2text  # type: ignore

            h2t = html2text.HTML2Text()
            h2t.ignore_links = True
            h2t.ignore_images = True
            h2t.body_width = 0
            md = re.sub(r"\n{3,}", "\n\n", h2t.handle(str(main_el))).strip()
            if len(md) > 80:
                return title, md, links
        except Exception:
            pass
        txt = "\n".join(ln.strip() for ln in main_el.get_text("\n").splitlines() if ln.strip())
        if len(txt) > 60:
            return title, txt, links
    except Exception:
        pass

    return title, re.sub(r"\s+", " ", " ".join(p.chunks)).strip(), links


def fetch_public_page(url: str, timeout: int = 7, client: Any | None = None) -> dict[str, Any]:
    """Fetch a public HTTP(S) page via pooled httpx[http2] -> urllib; skips anti-bot/CAPTCHA gates honestly."""
    t0 = time.monotonic()
    try:
        if client is not None:
            r = client.get(url, timeout=timeout)
            if r.status_code >= 400:
                return {"ok": False, "url": url, "status": r.status_code, "error": f"HTTP {r.status_code}"}
            raw = r.content[:MAX_PAGE_BYTES]
            html_txt = raw.decode("utf-8", errors="replace")
            if _is_gated(html_txt):
                return {"ok": False, "url": url, "status": r.status_code, "error": "gated_antibot_skipped"}
            title, text, links = extract_clean_text(html_txt, url=str(r.url))
            return {
                "ok": bool(len(text) > 80),
                "engine": "httpx_http2_pool",
                "url": str(r.url),
                "status": r.status_code,
                "title": title or str(r.url),
                "text": text[:10000],
                "links": links,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "ms": round((time.monotonic() - t0) * 1000.0, 1),
            }
        import httpx  # type: ignore

        with httpx.Client(http2=True, follow_redirects=True, timeout=timeout, headers={"User-Agent": UA}) as cli:
            r = cli.get(url)
            if r.status_code >= 400:
                return {"ok": False, "url": url, "status": r.status_code, "error": f"HTTP {r.status_code}"}
            raw = r.content[:MAX_PAGE_BYTES]
            html_txt = raw.decode("utf-8", errors="replace")
            if _is_gated(html_txt):
                return {"ok": False, "url": url, "status": r.status_code, "error": "gated_antibot_skipped"}
            title, text, links = extract_clean_text(html_txt, url=str(r.url))
            return {
                "ok": bool(len(text) > 80),
                "engine": "httpx_http2",
                "url": str(r.url),
                "status": r.status_code,
                "title": title or str(r.url),
                "text": text[:10000],
                "links": links,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "ms": round((time.monotonic() - t0) * 1000.0, 1),
            }
    except ImportError:
        pass
    except Exception as e:
        return {"ok": False, "url": url, "status": 0, "error": f"{type(e).__name__}: {e}"}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_PAGE_BYTES)
            html_txt = raw.decode("utf-8", errors="replace")
            if _is_gated(html_txt):
                return {"ok": False, "url": url, "status": resp.status, "error": "gated_antibot_skipped"}
            title, text, links = extract_clean_text(html_txt, url=url)
            return {
                "ok": bool(len(text) > 80),
                "engine": "urllib",
                "url": url,
                "status": getattr(resp, "status", 200),
                "title": title or url,
                "text": text[:10000],
                "links": links,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "ms": round((time.monotonic() - t0) * 1000.0, 1),
            }
    except Exception as e:
        return {"ok": False, "url": url, "status": 0, "error": f"{type(e).__name__}: {e}"}


def discover_ddgs(query: str, max_results: int = 25) -> list[dict[str, str]]:
    """Live multi-engine web search via `ddgs`, falling back to clean httpx DuckDuckGo HTML + Wikipedia API ($0.00)."""
    try:
        from ddgs import DDGS  # type: ignore

        out = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                u = str(r.get("href") or r.get("link") or "").strip()
                if u.startswith(("http://", "https://")):
                    out.append(
                        {
                            "url": u,
                            "source": "ddgs",
                            "title": str(r.get("title") or "")[:180],
                            "snippet": str(r.get("body") or "")[:600],
                        }
                    )
        if out:
            return out
    except Exception:
        pass

    # Pure-Python fallback: Wikipedia OpenSearch/Query API + DuckDuckGo HTML public endpoint (skips any gate)
    out: list[dict[str, str]] = []
    try:
        import httpx  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore

        with httpx.Client(http2=True, follow_redirects=True, timeout=8, headers={"User-Agent": UA}) as cli:
            # 1) DuckDuckGo public HTML results (honestly skipped if anti-bot gated)
            try:
                r = cli.get("https://html.duckduckgo.com/html/", params={"q": query})
                if r.status_code == 200 and not _is_gated(r.text):
                    soup = BeautifulSoup(r.text, "html.parser")
                    for res in soup.select(".result")[:max_results]:
                        a = res.select_one("a.result__a")
                        sn = res.select_one(".result__snippet")
                        if not a:
                            continue
                        href = str(a.get("href") or "")
                        if "uddg=" in href:
                            href = urllib.parse.unquote(href.split("uddg=", 1)[1].split("&", 1)[0])
                        if href.startswith(("http://", "https://")):
                            out.append(
                                {
                                    "url": href,
                                    "source": "ddg_html",
                                    "title": a.get_text(" ", strip=True)[:180],
                                    "snippet": (sn.get_text(" ", strip=True) if sn else "")[:600],
                                }
                            )
            except Exception:
                pass

            # 2) Wikipedia public REST search API (high-signal encyclopedia & citation hub)
            try:
                wr = cli.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "srlimit": min(25, max_results),
                        "format": "json",
                    },
                )
                if wr.status_code == 200:
                    for item in wr.json().get("query", {}).get("search", []):
                        ttl = str(item.get("title") or "").strip()
                        if not ttl:
                            continue
                        snip = re.sub(r"<[^>]+>", "", str(item.get("snippet") or ""))
                        out.append(
                            {
                                "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(ttl.replace(" ", "_")),
                                "source": "wikipedia",
                                "title": ttl[:180],
                                "snippet": snip[:600],
                            }
                        )
            except Exception:
                pass
    except Exception:
        pass
    return out[:max_results]


def _corpus_conn(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    tune_sqlite(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            published TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
            title, text, url, source, content='docs', content_rowid='id'
        );
        CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs BEGIN
            INSERT INTO docs_fts(rowid, title, text, url, source)
            VALUES (new.id, new.title, new.text, new.url, new.source);
        END;
        CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs BEGIN
            INSERT INTO docs_fts(docs_fts, rowid, title, text, url, source)
            VALUES ('delete', old.id, old.title, old.text, old.url, old.source);
        END;
        CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON docs BEGIN
            INSERT INTO docs_fts(docs_fts, rowid, title, text, url, source)
            VALUES ('delete', old.id, old.title, old.text, old.url, old.source);
            INSERT INTO docs_fts(rowid, title, text, url, source)
            VALUES (new.id, new.title, new.text, new.url, new.source);
        END;
        """
    )
    conn.commit()
    return conn


TIER1_DOMAINS = (
    "arxiv.org", "github.com", "aclanthology.org", "openreview.net", "neurips.cc",
    "icml.cc", "iclr.cc", "sqlite.org", "docs.python.org", "developer.android.com",
    "antigravity.google", "research.google", "microsoft.com/en-us/research", "proceedings.mlr.press",
)
TIER2_DOMAINS = ("news.ycombinator.com", "openalex.org", "huggingface.co", "ietf.org", "rfc-editor.org")
LOW_SIGNAL_DOMAINS = ("medium.com", "dev.to", "geeksforgeeks.org", "w3schools.com", "quora.com")


def score_source_authority(url: str, source: str = "") -> float:
    """Doctrine Part V §19 deterministic source quality hierarchy (1.0=primary paper/code -> 0.3=low-signal)."""
    u = (url or "").lower()
    s = (source or "").lower()
    if any(d in u for d in TIER1_DOMAINS) or s.startswith(("arxiv", "github_repo", "github_issue")):
        return 1.0
    if any(d in u for d in TIER2_DOMAINS) or s.startswith(("hn_", "openalex")):
        return 0.85
    if "wikipedia.org" in u or "stackoverflow.com" in u or s.startswith("wikipedia"):
        return 0.70
    if any(d in u for d in LOW_SIGNAL_DOMAINS):
        return 0.35
    return 0.60


def _bm25_top_hits(conn: sqlite3.Connection, anchor: str, top_k: int) -> list[tuple]:
    """AND-first BM25 FTS5 retrieval re-ranked by Doctrine §19 Source Authority."""
    tokens = list(dict.fromkeys(re.findall(r"[A-Za-z0-9_]{3,}", anchor)))
    if not tokens:
        return conn.execute(
            "SELECT url, source, title, published, substr(text, 1, 180) FROM docs ORDER BY fetched_at DESC LIMIT ?",
            (top_k,),
        ).fetchall()

    seen: set[str] = set()
    raw_hits: list[tuple[float, tuple]] = []
    queries = []
    if len(tokens) >= 2:
        queries.append((" AND ".join(tokens[:3]), 1.35))
    queries.append((" OR ".join(tokens[:5]), 1.0))

    for q, boost in queries:
        try:
            batch = conn.execute(
                """
                SELECT d.url, d.source, d.title, d.published, substr(d.text, 1, 180)
                FROM docs_fts f JOIN docs d ON d.id = f.rowid
                WHERE docs_fts MATCH ?
                ORDER BY bm25(docs_fts) LIMIT ?
                """,
                (q, top_k * 3),
            ).fetchall()
            for rank, r in enumerate(batch, 1):
                if r[0] not in seen:
                    seen.add(r[0])
                    auth = score_source_authority(r[0], r[1])
                    score = (boost / (10.0 + rank)) * auth
                    raw_hits.append((score, r))
        except sqlite3.OperationalError:
            continue

    if not raw_hits:
        return conn.execute(
            "SELECT url, source, title, published, substr(text, 1, 180) FROM docs ORDER BY fetched_at DESC LIMIT ?",
            (top_k,),
        ).fetchall()
    raw_hits.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in raw_hits[:top_k]]


def query_local_corpus(topic: str, *, db_path: str | None = None, top_k: int = 8) -> dict[str, Any]:
    """<5ms local SQLite FTS5 BM25 query against already-crawled bulk pages (0 network, 0 LLM tokens)."""
    t0 = time.monotonic()
    db = db_path or os.path.expanduser("~/.antigem/memory/omega_corpus.db")
    if not os.path.isfile(db):
        return {"topic": topic, "db_path": db, "total_docs_in_db": 0, "elapsed_ms": 0.0, "top_hits": []}
    anchor = extract_anchor_terms(topic, max_terms=4)
    conn = _corpus_conn(db)
    try:
        total = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        rows = _bm25_top_hits(conn, anchor, top_k)
    finally:
        conn.close()
    return {
        "topic": topic,
        "db_path": db,
        "total_docs_in_db": total,
        "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 2),
        "llm_tokens_used": 0,
        "top_hits": [{"url": r[0], "source": r[1], "title": r[2][:120], "published": r[3], "snippet": r[4]} for r in rows],
    }


def canonical_url_key(url: str) -> str:
    """Epistemic Guard mirror normalization (arXiv:2611.27095): collapse arXiv abs/html & regional URL mirrors."""
    u = (url or "").strip().split("#")[0]
    m = re.search(r"arxiv\.org/(?:abs|html|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", u, re.IGNORECASE)
    if m:
        return f"arxiv:{m.group(1)}"
    u = re.sub(r"/loc/[a-z0-9_-]+/", "/", u, flags=re.IGNORECASE)
    return u.rstrip("/").lower()


def content_shingles(text: str, n: int = 5) -> set[str]:
    """Deterministic normalized 5-word shingle set for lightly-edited syndicated mirror collapse."""
    words = re.findall(r"[a-z0-9\u4e00-\u9fff]{3,}", (text or "").lower())
    if len(words) < n + 3:
        return set()
    return {" ".join(words[i : i + n]) for i in range(min(120, len(words) - n + 1))}


def collapse_syndicated_mirrors(rows: list[dict[str, str]], jaccard_threshold: float = 0.65) -> tuple[list[dict[str, str]], int]:
    """Collapse URL mirrors & verbatim/lightly-edited syndicated copies (Epistemic Guard, arXiv:2611.27095)."""
    by_canon: dict[str, dict[str, str]] = {}
    collapsed = 0
    for r in rows:
        ck = canonical_url_key(r["url"])
        if ck in by_canon:
            collapsed += 1
            if len(r["text"]) > len(by_canon[ck]["text"]):
                by_canon[ck] = r
        else:
            by_canon[ck] = r

    # Process longer texts first so richest canonical source always wins
    candidates = sorted(by_canon.values(), key=lambda x: len(x["text"]), reverse=True)
    kept: list[dict[str, str]] = []
    kept_shingles: list[set[str]] = []
    for r in candidates:
        sh = content_shingles(r["text"])
        if not sh:
            kept.append(r)
            continue
        is_mirror = False
        for existing in kept_shingles:
            inter = len(sh & existing)
            if inter:
                union = len(sh | existing)
                if union and (inter / union) >= jaccard_threshold:
                    is_mirror = True
                    break
        if is_mirror:
            collapsed += 1
        else:
            kept.append(r)
            kept_shingles.append(sh)
    return kept, collapsed


def bulk_crawl(
    topic: str,
    *,
    target_pages: int = 500,
    db_path: str | None = None,
    max_workers: int = 16,
    follow_bfs_pages: int = 80,
    top_k: int = 8,
) -> dict[str, Any]:
    """Pull up to 500+ public docs into local SQLite FTS5 at $0.00 and 0 LLM tokens, then return compact top BM25 hits."""
    t0 = time.monotonic()
    db = db_path or os.path.expanduser("~/.antigem/memory/omega_corpus.db")
    anchor = extract_anchor_terms(topic, max_terms=3)
    zh_q = expand_chinese_query(topic)

    # 1. High-yield parallel multi-index seed discovery (EN + CN + Academic + GitHub + HN + DDG/Wiki)
    rows: list[dict[str, str]] = []
    seed_urls: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futs = [
            ex.submit(discover_ddgs, topic, 40),
            ex.submit(discover_ddgs, zh_q, 30),
            ex.submit(_discover_arxiv, topic, min(200, max(60, target_pages // 2))),
            ex.submit(_discover_openalex, topic, min(80, max(30, target_pages // 5))),
            ex.submit(_discover_hn_stories, anchor, False, 80),
            ex.submit(_discover_hn_comments, anchor, 80),
            ex.submit(_discover_github_repos, anchor, False, 50),
            ex.submit(_discover_github_repos, topic, True, 35),
            ex.submit(_discover_github_issues, anchor, 40),
            ex.submit(_discover_stackexchange, anchor, 35),
        ]
        for f in futs:
            try:
                items = f.result(timeout=18)
                for it in items:
                    u = it.get("url", "").strip()
                    if not u:
                        continue
                    seed_urls.append(u)
                    txt = (it.get("snippet") or it.get("title") or "").strip()
                    if len(txt) >= 30:
                        rows.append(
                            {
                                "url": u,
                                "source": it.get("source", "seed"),
                                "title": it.get("title", u)[:180],
                                "published": it.get("published_at", ""),
                                "text": txt[:10000],
                            }
                        )
            except Exception:
                pass

    # 2. Threaded full-page fetch with shared HTTP/2 connection pool + 1-hop BFS expansion
    seen_urls: set[str] = set()
    queue = collections.deque(dict.fromkeys(seed_urls))
    fetched_full = 0
    gated_skipped = 0
    crawl_cap = min(follow_bfs_pages, max(20, target_pages - len(rows) + 40))

    shared_cli = None
    try:
        import httpx  # type: ignore

        shared_cli = httpx.Client(
            http2=True,
            follow_redirects=True,
            timeout=6,
            headers={"User-Agent": UA},
            limits=httpx.Limits(max_connections=max_workers * 2, max_keepalive_connections=max_workers),
        )
    except Exception:
        shared_cli = None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            while queue and fetched_full < crawl_cap:
                batch: list[str] = []
                while queue and len(batch) < max_workers and (fetched_full + len(batch)) < crawl_cap:
                    u = queue.popleft()
                    if u not in seen_urls and not u.endswith((".pdf", ".zip", ".png", ".jpg", ".mp4")):
                        seen_urls.add(u)
                        batch.append(u)
                if not batch:
                    break
                for res in ex.map(lambda u: fetch_public_page(u, timeout=6, client=shared_cli), batch):
                    if res.get("ok"):
                        fetched_full += 1
                        rows.append(
                            {
                                "url": res["url"],
                                "source": f"full:{res.get('engine', 'http')}",
                                "title": res.get("title", res["url"])[:180],
                                "published": "",
                                "text": res["text"][:10000],
                            }
                        )
                        for lk in res.get("links", [])[:4]:
                            if lk not in seen_urls and len(queue) < crawl_cap * 3:
                                queue.append(lk)
                    elif res.get("error") == "gated_antibot_skipped":
                        gated_skipped += 1
    finally:
        if shared_cli is not None:
            try:
                shared_cli.close()
            except Exception:
                pass

    # Filter off-topic StackOverflow hits (require >=2 topic terms in title+text)
    topic_terms = [w for w in re.findall(r"[a-z0-9]{4,}", topic.lower()) if w not in {"2025", "2026", "with", "from", "that", "this"}]
    if len(topic_terms) >= 2:
        filtered_rows = []
        for r in rows:
            if r.get("source", "").startswith("stackoverflow"):
                blob = (r.get("title", "") + " " + r.get("text", "")).lower()
                if sum(1 for w in topic_terms if w in blob) < 2:
                    continue
            filtered_rows.append(r)
        rows = filtered_rows

    # 3. Epistemic Guard mirror collapse + deduplicate & save batch into SQLite FTS5
    unique_rows, mirrors_collapsed = collapse_syndicated_mirrors(rows)
    dedup_map: dict[str, dict[str, str]] = {r["url"]: r for r in unique_rows}

    now = int(time.time())
    conn = _corpus_conn(db)
    try:
        conn.executemany(
            """
            INSERT INTO docs (url, source, title, published, text, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                source=excluded.source,
                title=excluded.title,
                text=CASE WHEN length(excluded.text) > length(docs.text) THEN excluded.text ELSE docs.text END,
                fetched_at=excluded.fetched_at
            """,
            [(r["url"], r["source"], r["title"], r.get("published", ""), r["text"], now) for r in dedup_map.values()],
        )
        conn.commit()
        total_in_db = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]

        # Return ultra-compact top_k AND-first BM25 hits (<2.5KB) at 0 LLM tokens!
        top = _bm25_top_hits(conn, anchor, top_k)
    finally:
        conn.close()

    return {
        "topic": topic,
        "chinese_query": zh_q,
        "db_path": db,
        "unique_docs_saved": len(dedup_map),
        "mirrors_collapsed": mirrors_collapsed,
        "full_pages_fetched": fetched_full,
        "gated_antibot_skipped": gated_skipped,
        "total_docs_in_db": total_in_db,
        "elapsed_s": round(time.monotonic() - t0, 2),
        "llm_tokens_used": 0,
        "top_hits": [{"url": r[0], "source": r[1], "title": r[2][:120], "published": r[3], "snippet": r[4]} for r in top],
    }


def fetch_youtube_transcript(url_or_id: str) -> dict[str, Any]:
    """<1.5s zero-download timestamped YouTube transcript via youtube-transcript-api."""
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url_or_id)
    vid = m.group(1) if m else url_or_id.strip()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

        api = YouTubeTranscriptApi()
        fetched = api.fetch(vid) if hasattr(api, "fetch") else YouTubeTranscriptApi.get_transcript(vid)
        segs = []
        for s in fetched:
            start = getattr(s, "start", None) if not isinstance(s, dict) else s.get("start", 0)
            dur = getattr(s, "duration", 0) if not isinstance(s, dict) else s.get("duration", 0)
            txt = getattr(s, "text", "") if not isinstance(s, dict) else s.get("text", "")
            segs.append({"start": round(float(start or 0), 2), "end": round(float(start or 0) + float(dur or 0), 2), "text": str(txt).strip()})
        return {"ok": True, "video_id": vid, "segments_count": len(segs), "segments": segs}
    except Exception as e:
        return {"ok": False, "video_id": vid, "error": f"{type(e).__name__}: {e}"}


def read_document(path: str, max_chars: int = 12000) -> dict[str, Any]:
    """Read PDF, DOCX, XLSX, or YAML cleanly into text."""
    fp = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(fp):
        return {"ok": False, "error": f"not_found:{fp}"}
    ext = os.path.splitext(fp)[1].lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(fp)
            text = "\n\n".join((pg.extract_text() or "") for pg in reader.pages)
            return {"ok": True, "type": "pdf", "pages": len(reader.pages), "text": text[:max_chars]}
        if ext == ".docx":
            try:
                import docx  # type: ignore

                d = docx.Document(fp)
                text = "\n".join(p.text for p in d.paragraphs if p.text.strip())
                return {"ok": True, "type": "docx", "paragraphs": len(d.paragraphs), "text": text[:max_chars]}
            except ImportError:
                import xml.etree.ElementTree as ET
                import zipfile

                with zipfile.ZipFile(fp) as zf:
                    root = ET.fromstring(zf.read("word/document.xml"))
                paras = []
                for p in root.iter():
                    if p.tag.endswith("}p"):
                        txt = "".join(t.text for t in p.iter() if t.tag.endswith("}t") and t.text).strip()
                        if txt:
                            paras.append(txt)
                return {"ok": True, "type": "docx_stdlib", "paragraphs": len(paras), "text": "\n".join(paras)[:max_chars]}
        if ext == ".xlsx":
            import openpyxl  # type: ignore

            wb = openpyxl.load_workbook(fp, read_only=True, data_only=True)
            lines = []
            for name in wb.sheetnames[:5]:
                ws = wb[name]
                lines.append(f"## Sheet: {name}")
                for row in list(ws.iter_rows(values_only=True))[:60]:
                    if any(v is not None for v in row):
                        lines.append(" | ".join("" if v is None else str(v) for v in row))
            return {"ok": True, "type": "xlsx", "sheets": wb.sheetnames, "text": "\n".join(lines)[:max_chars]}
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            return {"ok": True, "type": ext or "text", "text": f.read(max_chars)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
