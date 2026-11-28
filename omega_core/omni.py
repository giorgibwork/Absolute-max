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
import xml.etree.ElementTree as ET
from typing import Any

warnings.filterwarnings("ignore", message=".*SOCKS support in urllib3.*")

from . import (
    SCHEMA_BIT_CORPUS,
    OmegaPaths,
    ensure_dirs,
    get_paths,
    mark_schema_bit,
    safe_fts_query,
    schema_has_bit,
    tokenize_multilingual,
    tune_sqlite,
)
from .research import (
    _discover_arxiv,
    _discover_europe_pmc,
    _discover_geeknews_kr,
    _discover_gitee_cn,
    _discover_github_issues,
    _discover_github_repos,
    _discover_habr_ru,
    _discover_hn_comments,
    _discover_hn_stories,
    _discover_lobsters,
    _discover_openalex,
    _discover_qiita_jp,
    _discover_stackexchange,
    expand_chinese_query,
    expand_japanese_query,
    expand_korean_query,
    expand_russian_query,
    extract_anchor_terms,
)

UA = "Mozilla/5.0 (Linux; Android 16) OmegaApexOmni/8.0 (PublicResearch)"
MD_MIRROR_HOSTS = ("antigravity.google/docs/", "aistudio.google.com/docs/")
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


def _extract_response_content(raw: bytes, final_url: str, content_type: str = "") -> tuple[str, str, list[str], str]:
    """Decode HTML or PDF bytes cleanly; reject binary noise and anti-bot gates."""
    ct = (content_type or "").lower()
    if raw.startswith(b"%PDF-") or "application/pdf" in ct:
        try:
            import io
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(raw))
            chunks = []
            for page in reader.pages[:12]:
                txt = (page.extract_text() or "").strip()
                if txt:
                    chunks.append(txt)
                if sum(len(c) for c in chunks) >= 12000:
                    break
            text = "\n\n".join(chunks).strip()
            meta_title = ""
            try:
                meta_title = str((reader.metadata or {}).get("/Title") or "").strip()
            except Exception:
                pass
            return (meta_title or final_url, text, [], "")
        except Exception:
            return ("", "", [], "pdf_parse_failed")
    if b"\x00" in raw[:1024]:
        return ("", "", [], "binary_skipped")
    html_txt = raw.decode("utf-8", errors="replace")
    if _is_gated(html_txt):
        return ("", "", [], "gated_antibot_skipped")
    title, text, links = extract_clean_text(html_txt, url=final_url)
    return (title or final_url, text, links, "")


def maybe_markdown_mirror_url(url: str) -> str | None:
    """Return raw .md mirror URL for llms.txt-enabled Google docs (5-10x smaller than HTML)."""
    u = (url or "").strip().split("#")[0].split("?")[0].rstrip("/")
    low = u.lower()
    if any(h in low for h in MD_MIRROR_HOSTS) and not low.endswith(".md"):
        return u + ".md"
    return None


def fetch_public_page(url: str, timeout: int = 7, client: Any | None = None) -> dict[str, Any]:
    """Fetch a public HTTP(S) page, .md mirror, or PDF via pooled httpx[http2] -> urllib; skips anti-bot/binary gates."""
    t0 = time.monotonic()
    md_url = maybe_markdown_mirror_url(url)

    def _finish(raw: bytes, final_url: str, status: int, engine: str, content_type: str = "") -> dict[str, Any]:
        # Fast-path clean raw Markdown from .md mirrors without HTML parsing overhead
        if final_url.lower().endswith(".md") and b"\x00" not in raw[:1024]:
            md_txt = raw.decode("utf-8", errors="replace").strip()
            if len(md_txt) > 80 and not md_txt.lstrip().startswith("<!DOCTYPE") and not md_txt.lstrip().startswith("<html"):
                first_h = next((ln.lstrip("# ").strip() for ln in md_txt.splitlines() if ln.strip().startswith("#")), final_url)
                return {
                    "ok": True,
                    "engine": f"{engine}_md_mirror",
                    "url": final_url,
                    "status": status,
                    "title": first_h[:180],
                    "text": md_txt[:10000],
                    "links": [],
                    "sha256": hashlib.sha256(md_txt.encode("utf-8")).hexdigest()[:16],
                    "ms": round((time.monotonic() - t0) * 1000.0, 1),
                }
        title, text, links, err = _extract_response_content(raw, final_url, content_type)
        if err:
            return {"ok": False, "url": final_url, "status": status, "error": err}
        return {
            "ok": bool(len(text) > 80),
            "engine": engine,
            "url": final_url,
            "status": status,
            "title": title or final_url,
            "text": text[:10000],
            "links": links,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
            "ms": round((time.monotonic() - t0) * 1000.0, 1),
        }

    try:
        if client is not None:
            if md_url:
                try:
                    rm = client.get(md_url, timeout=timeout)
                    if rm.status_code == 200 and len(rm.content) > 80:
                        out_m = _finish(rm.content[:MAX_PAGE_BYTES], str(rm.url), rm.status_code, "httpx_http2_pool", rm.headers.get("content-type", ""))
                        if out_m.get("ok"):
                            return out_m
                except Exception:
                    pass
            r = client.get(url, timeout=timeout)
            if r.status_code >= 400:
                return {"ok": False, "url": url, "status": r.status_code, "error": f"HTTP {r.status_code}"}
            return _finish(r.content[:MAX_PAGE_BYTES], str(r.url), r.status_code, "httpx_http2_pool", r.headers.get("content-type", ""))
        import httpx  # type: ignore

        with httpx.Client(http2=True, follow_redirects=True, timeout=timeout, headers={"User-Agent": UA}) as cli:
            if md_url:
                try:
                    rm = cli.get(md_url)
                    if rm.status_code == 200 and len(rm.content) > 80:
                        out_m = _finish(rm.content[:MAX_PAGE_BYTES], str(rm.url), rm.status_code, "httpx_http2", rm.headers.get("content-type", ""))
                        if out_m.get("ok"):
                            return out_m
                except Exception:
                    pass
            r = cli.get(url)
            if r.status_code >= 400:
                return {"ok": False, "url": url, "status": r.status_code, "error": f"HTTP {r.status_code}"}
            return _finish(r.content[:MAX_PAGE_BYTES], str(r.url), r.status_code, "httpx_http2", r.headers.get("content-type", ""))
    except ImportError:
        pass
    except Exception as e:
        return {"ok": False, "url": url, "status": 0, "error": f"{type(e).__name__}: {e}"}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_PAGE_BYTES)
            ct = resp.headers.get("Content-Type", "") if getattr(resp, "headers", None) else ""
            return _finish(raw, url, getattr(resp, "status", 200), "urllib", ct)
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


def _corpus_conn(db_path: str, *, read_only: bool = False) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    if schema_has_bit(conn, SCHEMA_BIT_CORPUS):
        tune_sqlite(conn, read_only=read_only)
        return conn
    tune_sqlite(conn, read_only=False)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            published TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            fetched_at INTEGER NOT NULL,
            lane TEXT NOT NULL DEFAULT 'general'
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
    cols = {r[1] for r in conn.execute("PRAGMA table_info(docs)").fetchall()}
    if "lane" not in cols:
        conn.execute("ALTER TABLE docs ADD COLUMN lane TEXT NOT NULL DEFAULT 'general'")
    mark_schema_bit(conn, SCHEMA_BIT_CORPUS)
    conn.commit()
    return conn


TIER1_DOMAINS = (
    "arxiv.org", "github.com", "aclanthology.org", "openreview.net", "neurips.cc",
    "icml.cc", "iclr.cc", "sqlite.org", "docs.python.org", "developer.android.com",
    "antigravity.google", "aistudio.google.com", "research.google", "blog.google",
    "proceedings.mlr.press", "europepmc.org", "pubmed.ncbi.nlm.nih.gov", "gov.uk",
)
TIER2_DOMAINS = (
    "news.ycombinator.com", "lobste.rs", "news.smol.ai", "simonwillison.net",
    "openalex.org", "huggingface.co", "qiita.com", "habr.com", "ietf.org", "rfc-editor.org",
    "news.hada.io", "gitee.com",
)
LOW_SIGNAL_DOMAINS = ("medium.com", "dev.to", "geeksforgeeks.org", "w3schools.com", "quora.com")


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def score_source_authority(url: str, source: str = "") -> float:
    """Doctrine Part V §19 strict-host source quality hierarchy (immune to URL query-param spoofing)."""
    host = _url_domain(url)
    s = (source or "").lower()
    if (host and any(_host_matches(host, d) for d in TIER1_DOMAINS)) or s.startswith(("arxiv", "github_repo", "github_issue", "europe_pmc")):
        return 1.0
    if (host and any(_host_matches(host, d) for d in TIER2_DOMAINS)) or s.startswith(("hn_", "openalex", "lobsters", "smol_ai", "hf_daily", "qiita", "habr", "geeknews", "gitee")):
        return 0.88
    if (host and (_host_matches(host, "wikipedia.org") or _host_matches(host, "stackoverflow.com"))) or s.startswith("wikipedia"):
        return 0.70
    if host and any(_host_matches(host, d) for d in LOW_SIGNAL_DOMAINS):
        return 0.35
    return 0.60


def _url_domain(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _infer_lane(source: str, lane: str = "") -> str:
    if lane and lane != "general":
        return lane
    s = (source or "").lower()
    if "hostile" in s or "issue" in s or "lobsters" in s or "hn_comment" in s:
        return "hostile"
    if any(k in s for k in ("cn_", "gitee", "v2ex", "qiita", "habr", "geeknews", "ddg_zh")):
        return "multilingual"
    if any(k in s for k in ("smol_ai", "hf_daily", "simonwillison", "google_ai_blog")):
        return "ai_pulse"
    if any(k in s for k in ("arxiv", "openalex", "pubmed")):
        return "academic"
    return "general"


def _bm25_top_hits(conn: sqlite3.Connection, anchor: str, top_k: int) -> list[tuple]:
    """Multilingual AND-first BM25 FTS5 retrieval with §19 authority, per-domain cap (<=2), and lane diversity."""
    tokens = tokenize_multilingual(anchor, min_latin=2, min_cjk=2, max_tokens=8)
    if not tokens:
        return conn.execute(
            "SELECT url, source, title, published, substr(text, 1, 180), lane FROM docs ORDER BY fetched_at DESC LIMIT ?",
            (top_k,),
        ).fetchall()

    seen: set[str] = set()
    raw_hits: list[tuple[float, tuple]] = []
    queries: list[tuple[str, float]] = []
    if len(tokens) >= 2:
        q_and = safe_fts_query(" ".join(tokens[:3]), mode="AND", max_terms=3)
        if q_and:
            queries.append((q_and, 1.35))
    q_or = safe_fts_query(" ".join(tokens[:6]), mode="OR", max_terms=6)
    if q_or:
        queries.append((q_or, 1.0))

    for q, boost in queries:
        try:
            batch = conn.execute(
                """
                SELECT d.url, d.source, d.title, d.published, substr(d.text, 1, 180), d.lane
                FROM docs_fts f JOIN docs d ON d.id = f.rowid
                WHERE docs_fts MATCH ?
                ORDER BY bm25(docs_fts) LIMIT ?
                """,
                (q, max(top_k * 5, 30)),
            ).fetchall()
            for rank, r in enumerate(batch, 1):
                if r[0] not in seen:
                    seen.add(r[0])
                    auth = score_source_authority(r[0], r[1])
                    score = (boost / (10.0 + rank)) * auth
                    raw_hits.append((score, r))
        except sqlite3.OperationalError:
            continue

    # CJK / substring fallback when SQLite unicode61 misses unspaced CJK phrases
    has_non_ascii = any(ord(ch) > 127 for ch in anchor)
    if len(raw_hits) < top_k and (has_non_ascii or not raw_hits):
        for tok in tokens[:4]:
            like = f"%{tok}%"
            sub_rows = conn.execute(
                """
                SELECT url, source, title, published, substr(text, 1, 180), lane
                FROM docs
                WHERE title LIKE ? OR text LIKE ?
                ORDER BY fetched_at DESC LIMIT ?
                """,
                (like, like, top_k * 3),
            ).fetchall()
            for rank, r in enumerate(sub_rows, 1):
                if r[0] not in seen:
                    seen.add(r[0])
                    auth = score_source_authority(r[0], r[1])
                    raw_hits.append(((0.85 / (10.0 + rank)) * auth, r))

    if not raw_hits:
        # NEVER poison novel domain queries with unrelated recent AI docs! Return empty so caller knows corpus is cold.
        return []

    raw_hits.sort(key=lambda x: x[0], reverse=True)

    # Anti-consensus selection: cap any single domain at 2 hits and guarantee hostile/multilingual slots when available
    picked: list[tuple] = []
    picked_urls: set[str] = set()
    domain_counts: dict[str, int] = {}

    def _try_add(r: tuple) -> bool:
        u = r[0]
        if u in picked_urls:
            return False
        dom = _url_domain(u)
        if dom and domain_counts.get(dom, 0) >= 2:
            return False
        picked.append(r)
        picked_urls.add(u)
        if dom:
            domain_counts[dom] = domain_counts.get(dom, 0) + 1
        return True

    # 1. Guarantee top hostile/contrarian + top multilingual hit when top_k >= 4
    if top_k >= 4:
        for _, r in raw_hits:
            if _infer_lane(r[1], r[5]) == "hostile" and _try_add(r):
                break
        for _, r in raw_hits:
            if _infer_lane(r[1], r[5]) == "multilingual" and _try_add(r):
                break

    # 2. Fill remaining slots by authority-weighted BM25 respecting domain cap <= 2
    for _, r in raw_hits:
        if len(picked) >= top_k:
            break
        _try_add(r)

    # 3. Backfill if domain cap left fewer than top_k
    if len(picked) < top_k:
        for _, r in raw_hits:
            if len(picked) >= top_k:
                break
            if r[0] not in picked_urls:
                picked.append(r)
                picked_urls.add(r[0])

    return picked[:top_k]


def query_local_corpus(topic: str, *, db_path: str | None = None, top_k: int = 8) -> dict[str, Any]:
    """<5ms multilingual local SQLite FTS5 BM25 query against already-crawled bulk pages (0 network, 0 LLM tokens)."""
    t0 = time.monotonic()
    db = db_path or os.path.expanduser("~/.antigem/memory/omega_corpus.db")
    if not os.path.isfile(db):
        return {"topic": topic, "db_path": db, "total_docs_in_db": 0, "elapsed_ms": 0.0, "top_hits": []}
    anchor = extract_anchor_terms(topic, max_terms=5)
    conn = _corpus_conn(db, read_only=True)
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
        "top_hits": [
            {
                "url": r[0],
                "source": r[1],
                "lane": _infer_lane(r[1], r[5]),
                "title": r[2][:120],
                "published": r[3],
                "snippet": r[4],
            }
            for r in rows
        ],
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
    """Deterministic multilingual 5-token shingle set for syndicated mirror collapse (EN/CJK/RU/GE)."""
    words = [w.lower() for w in tokenize_multilingual(text or "", min_latin=2, min_cjk=2, max_tokens=160)]
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
    anchor = extract_anchor_terms(topic, max_terms=4)
    anchor_2 = extract_anchor_terms(topic, max_terms=2)
    zh_q = expand_chinese_query(topic)
    ja_q = expand_japanese_query(topic)
    ru_q = expand_russian_query(topic)
    ko_q = expand_korean_query(topic)
    hostile_q = f"{anchor_2} broken OR regression OR myth OR overrated"

    # 1. High-yield parallel multilingual (EN/ZH/JA/RU/KO) + hostile + science/biomechanics seed discovery
    rows: list[dict[str, str]] = []
    seed_urls: list[str] = []
    engines_ok: list[str] = []
    engines_empty: list[str] = []
    engine_errors: dict[str, str] = {}
    seed_jobs: list[tuple[str, str, Any, tuple]] = [
        ("ddg_en", "general", discover_ddgs, (topic, 35)),
        ("ddg_hostile", "hostile", discover_ddgs, (hostile_q, 25)),
        ("ddg_zh", "multilingual", discover_ddgs, (zh_q, 25)),
        ("ddg_ko", "multilingual", discover_ddgs, (ko_q, 15)),
        ("arxiv", "academic", _discover_arxiv, (anchor, min(140, max(35, target_pages // 4)))),
        ("openalex", "academic", _discover_openalex, (anchor, min(60, max(25, target_pages // 6)))),
        ("europe_pmc", "academic", _discover_europe_pmc, (anchor, 20)),
        ("hn_stories", "general", _discover_hn_stories, (anchor_2, False, 50)),
        ("hn_hostile", "hostile", lambda q, n: _discover_hn_comments(q, limit=n, hostile=True), (anchor_2, 45)),
        ("github_en", "primary", lambda q, n: _discover_github_repos(q, chinese=False, limit=n), (anchor_2, 35)),
        ("github_cn", "multilingual", lambda q, n: _discover_github_repos(q, chinese=True, limit=n), (topic, 25)),
        ("gitee_cn", "multilingual", _discover_gitee_cn, (topic, 15)),
        ("github_issues", "hostile", _discover_github_issues, (anchor_2, 30)),
        ("qiita_jp", "multilingual", _discover_qiita_jp, (topic, 15)),
        ("habr_ru", "multilingual", _discover_habr_ru, (topic, 12)),
        ("geeknews_kr", "multilingual", _discover_geeknews_kr, (topic, 10)),
        ("lobsters", "hostile", _discover_lobsters, (topic, 15)),
        ("stackoverflow", "general", _discover_stackexchange, (anchor, 20)),
    ]
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=12)
    try:
        fut_map = {ex.submit(fn, *args): (ename, dlane) for ename, dlane, fn, args in seed_jobs}
        try:
            for f in concurrent.futures.as_completed(fut_map, timeout=22):
                ename, dlane = fut_map[f]
                try:
                    items = f.result(timeout=2)
                    if items:
                        engines_ok.append(ename)
                    else:
                        engines_empty.append(ename)
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
                                    "source": it.get("source") or ename,
                                    "lane": it.get("lane") or dlane,
                                    "title": it.get("title", u)[:180],
                                    "published": it.get("published_at", ""),
                                    "text": txt[:10000],
                                }
                            )
                except Exception as e:
                    engines_empty.append(ename)
                    engine_errors[ename] = f"{type(e).__name__}: {str(e)[:80]}"
        except concurrent.futures.TimeoutError:
            for f, (ename, _) in fut_map.items():
                if not f.done():
                    f.cancel()
                    engines_empty.append(ename)
                    engine_errors[ename] = "TimeoutError: exceeded 22s seed budget"
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

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
                    if u not in seen_urls and not u.lower().endswith((".zip", ".tar", ".gz", ".png", ".jpg", ".jpeg", ".mp4", ".apk", ".dmg")):
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
                                "lane": "primary",
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

    # Filter off-topic StackOverflow hits (multilingual-safe)
    topic_terms = [w.lower() for w in tokenize_multilingual(topic, min_latin=3, min_cjk=2, max_tokens=10) if w.lower() not in {"2025", "2026", "with", "from", "that", "this"}]
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
    lane_counts: dict[str, int] = {}
    for r in dedup_map.values():
        ln = _infer_lane(r.get("source", ""), r.get("lane", ""))
        r["lane"] = ln
        lane_counts[ln] = lane_counts.get(ln, 0) + 1

    now = int(time.time())
    conn = _corpus_conn(db)
    try:
        conn.executemany(
            """
            INSERT INTO docs (url, source, title, published, text, fetched_at, lane)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                source=excluded.source,
                title=excluded.title,
                lane=CASE WHEN excluded.lane != 'general' THEN excluded.lane ELSE docs.lane END,
                text=CASE WHEN length(excluded.text) > length(docs.text) THEN excluded.text ELSE docs.text END,
                fetched_at=excluded.fetched_at
            """,
            [(r["url"], r["source"], r["title"], r.get("published", ""), r["text"], now, r.get("lane", "general")) for r in dedup_map.values()],
        )
        conn.commit()
        total_in_db = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]

        # Return ultra-compact top_k lane-diverse & authority-ranked BM25 hits at 0 LLM tokens!
        top = _bm25_top_hits(conn, anchor, top_k)
    finally:
        conn.close()

    return {
        "topic": topic,
        "chinese_query": zh_q,
        "japanese_query": ja_q,
        "russian_query": ru_q,
        "korean_query": ko_q,
        "db_path": db,
        "engines_ok": sorted(engines_ok),
        "engines_empty": sorted(engines_empty),
        "engine_errors": engine_errors,
        "lane_counts": lane_counts,
        "unique_docs_saved": len(dedup_map),
        "mirrors_collapsed": mirrors_collapsed,
        "full_pages_fetched": fetched_full,
        "gated_antibot_skipped": gated_skipped,
        "total_docs_in_db": total_in_db,
        "elapsed_s": round(time.monotonic() - t0, 2),
        "llm_tokens_used": 0,
        "top_hits": [
            {"url": r[0], "source": r[1], "lane": _infer_lane(r[1], r[5]), "title": r[2][:120], "published": r[3], "snippet": r[4]}
            for r in top
        ],
    }


def ingest_ai_pulse(
    *,
    query: str = "",
    limit: int = 12,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Ingest live AI X/Twitter digest (news.smol.ai) + HF Daily Papers + Lobsters + Simon Willison + Google AI + V2EX + Habr + GeekNews at 0 LLM tokens."""
    t0 = time.monotonic()
    db = db_path or os.path.expanduser("~/.antigem/memory/omega_corpus.db")
    import httpx  # type: ignore

    rows: list[dict[str, str]] = []
    sources_ok: list[str] = []
    sources_failed: list[str] = []

    def _strip_html(s: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()

    def _pull_rss(cli: Any, name: str, url: str, lane: str, max_items: int = 12) -> list[dict[str, str]]:
        r = cli.get(url)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content[:2621440])
        out = []
        # Handle RSS <item> and Atom <entry>
        ns = {"a": "http://www.w3.org/2005/Atom", "c": "http://purl.org/rss/1.0/modules/content/"}
        items = root.findall(".//item")
        if items:
            for it in items:
                title = (it.findtext("title") or "").strip()
                if title.lower() in ("not much happened today", "quiet day"):
                    continue
                link = (it.findtext("link") or "").strip()
                body = it.findtext("c:encoded", default="", namespaces=ns) or it.findtext("description") or ""
                pub = (it.findtext("pubDate") or "")[:25]
                txt = _strip_html(body) or title
                if link.startswith("http") and len(txt) >= 20:
                    out.append({"url": link, "source": name, "lane": lane, "title": title[:180], "published": pub, "text": txt[:10000]})
                    if len(out) >= max_items:
                        break
        else:
            for ent in root.findall("a:entry", ns)[:max_items]:
                title = (ent.findtext("a:title", "", ns) or "").strip()
                lk_el = ent.find("a:link", ns)
                link = str(lk_el.get("href") or "") if lk_el is not None else ""
                body = ent.findtext("a:content", "", ns) or ent.findtext("a:summary", "", ns) or ""
                pub = (ent.findtext("a:updated", "", ns) or ent.findtext("a:published", "", ns) or "")[:25]
                txt = _strip_html(body) or title
                if link.startswith("http") and len(txt) >= 20:
                    out.append({"url": link, "source": name, "lane": lane, "title": title[:180], "published": pub, "text": txt[:10000]})
        return out

    def _pull_hf_papers(cli: Any) -> list[dict[str, str]]:
        r = cli.get("https://huggingface.co/api/daily_papers?limit=15")
        if r.status_code != 200:
            return []
        out = []
        for it in r.json()[:15]:
            p = it.get("paper") or {}
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            title = str(p.get("title") or it.get("title") or pid)
            summary = str(p.get("summary") or it.get("summary") or title)
            up = p.get("upvotes", 0)
            out.append({
                "url": f"https://huggingface.co/papers/{pid}",
                "source": f"hf_daily(up={up})",
                "lane": "academic",
                "title": title[:180],
                "published": str(it.get("publishedAt") or "")[:20],
                "text": summary[:6000],
            })
        return out

    def _pull_lobsters(cli: Any) -> list[dict[str, str]]:
        r = cli.get("https://lobste.rs/t/ai.json")
        if r.status_code != 200:
            return []
        out = []
        for it in r.json()[:15]:
            u = str(it.get("url") or it.get("comments_url") or "")
            if u.startswith("http"):
                out.append({
                    "url": u,
                    "source": f"lobsters(score={it.get('score', 0)})",
                    "lane": "hostile",
                    "title": str(it.get("title") or "")[:180],
                    "published": str(it.get("created_at") or "")[:20],
                    "text": (str(it.get("description") or "") or str(it.get("title") or ""))[:4000],
                })
        return out

    def _pull_v2ex(cli: Any) -> list[dict[str, str]]:
        r = cli.get("https://www.v2ex.com/api/topics/hot.json")
        if r.status_code != 200:
            return []
        out = []
        for it in r.json()[:12]:
            u = str(it.get("url") or "")
            if u.startswith("http"):
                out.append({
                    "url": u,
                    "source": f"v2ex_cn(replies={it.get('replies', 0)})",
                    "lane": "multilingual",
                    "title": str(it.get("title") or "")[:180],
                    "published": "",
                    "text": (str(it.get("content") or "") or str(it.get("title") or ""))[:4000],
                })
        return out

    with httpx.Client(http2=True, follow_redirects=True, timeout=12, headers={"User-Agent": UA}) as cli:
        jobs: list[tuple[str, Any]] = [
            ("smol_ai_x_digest", lambda: _pull_rss(cli, "smol_ai_x_digest", "https://news.smol.ai/rss.xml", "ai_pulse", 8)),
            ("hf_daily_papers", lambda: _pull_hf_papers(cli)),
            ("lobsters_ai", lambda: _pull_lobsters(cli)),
            ("simon_willison", lambda: _pull_rss(cli, "simonwillison", "https://simonwillison.net/atom/everything/", "ai_pulse", 10)),
            ("google_ai_blog", lambda: _pull_rss(cli, "google_ai_blog", "https://blog.google/technology/ai/rss/", "primary", 10)),
            ("habr_ru_ai", lambda: _pull_rss(cli, "habr_ru", "https://habr.com/ru/rss/hubs/artificial_intelligence/articles/?fl=ru", "multilingual", 10)),
            ("geeknews_kr", lambda: _pull_rss(cli, "geeknews_kr", "https://news.hada.io/rss/news", "multilingual", 10)),
            ("v2ex_cn_hot", lambda: _pull_v2ex(cli)),
        ]
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        try:
            fmap = {ex.submit(fn): name for name, fn in jobs}
            try:
                for f in concurrent.futures.as_completed(fmap, timeout=20):
                    name = fmap[f]
                    try:
                        items = f.result(timeout=2)
                        if items:
                            sources_ok.append(name)
                            rows.extend(items)
                        else:
                            sources_failed.append(name)
                    except Exception:
                        sources_failed.append(name)
            except concurrent.futures.TimeoutError:
                for f, name in fmap.items():
                    if not f.done():
                        f.cancel()
                        sources_failed.append(name)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    unique_rows, collapsed = collapse_syndicated_mirrors(rows)
    now = int(time.time())
    conn = _corpus_conn(db)
    try:
        conn.executemany(
            """
            INSERT INTO docs (url, source, title, published, text, fetched_at, lane)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                source=excluded.source,
                title=excluded.title,
                lane=excluded.lane,
                text=CASE WHEN length(excluded.text) > length(docs.text) THEN excluded.text ELSE docs.text END,
                fetched_at=excluded.fetched_at
            """,
            [(r["url"], r["source"], r["title"], r.get("published", ""), r["text"], now, r.get("lane", "ai_pulse")) for r in unique_rows],
        )
        conn.commit()
        total_in_db = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        if query.strip():
            hits = _bm25_top_hits(conn, extract_anchor_terms(query, max_terms=5), limit)
            out_items = [{"url": r[0], "source": r[1], "lane": _infer_lane(r[1], r[5]), "title": r[2][:120], "published": r[3], "snippet": r[4]} for r in hits]
        else:
            # Diverse top highlights across sources
            seen_src: dict[str, int] = {}
            out_items = []
            for r in unique_rows:
                base_s = r["source"].split("(")[0]
                if seen_src.get(base_s, 0) >= 2:
                    continue
                seen_src[base_s] = seen_src.get(base_s, 0) + 1
                out_items.append({
                    "url": r["url"],
                    "source": r["source"],
                    "lane": r["lane"],
                    "title": r["title"][:120],
                    "published": r.get("published", ""),
                    "snippet": r["text"][:200],
                })
                if len(out_items) >= limit:
                    break
    finally:
        conn.close()

    return {
        "ok": len(sources_ok) > 0,
        "sources_ok": sorted(sources_ok),
        "sources_failed": sorted(sources_failed),
        "items_ingested": len(unique_rows),
        "mirrors_collapsed": collapsed,
        "total_docs_in_db": total_in_db,
        "elapsed_s": round(time.monotonic() - t0, 2),
        "llm_tokens_used": 0,
        "highlights": out_items,
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
