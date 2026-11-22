"""Two-Way Obsidian Knowledge Graph & Canvas Engine (/sdcard/Documents/OmegaVault).

Projects OMEGA APEX SQLite state (omega_vault.db, missions.db, models.db,
evidence, and curated highlights from local FTS5 corpora) into a pre-configured
Obsidian vault with:
- Tuned viral-style Graph View (.obsidian/graph.json) with 8 neon color clusters
- Interactive Architecture Canvas (00-Hubs/OMEGA-OS-Architecture.canvas)
- Hub MOCs (Maps of Content) + Atomic [[wikilinked]] notes + Concept Bridges
- Two-way sync: ingests user notes/rules from 08-Inbox/ and 09-Config/ back into
  omega_vault.db with authority='user_explicit'
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from typing import Any

from . import R1_SANDBOX, VERSION, OmegaPaths, get_paths
from .fabric import IntelligenceFabric
from .memory import KnowledgeFabric, connect_vault
from .mission import MissionKernel

DEFAULT_VAULT_DIR = "/sdcard/Documents/OmegaVault"

DOMAIN_MAP: dict[str, tuple[str, str, str]] = {
    "os": ("00-Hubs", "MOC-OMEGA-OS", "#os"),
    "runtime": ("00-Hubs", "MOC-OMEGA-OS", "#os"),
    "bridge": ("00-Hubs", "MOC-OMEGA-OS", "#os"),
    "protocol": ("00-Hubs", "MOC-OMEGA-OS", "#os"),
    "prefs": ("09-Config", "MOC-OMEGA-OS", "#config"),
    "user": ("09-Config", "MOC-OMEGA-OS", "#config"),
    "profile": ("06-Life", "MOC-Training-Life", "#life"),
    "life": ("06-Life", "MOC-Training-Life", "#life"),
    "training": ("06-Life", "MOC-Training-Life", "#training"),
    "device": ("04-Device", "MOC-Device-Vermeer", "#vermeer"),
    "gaming": ("04-Device", "MOC-Device-Vermeer", "#gaming"),
    "finance": ("05-Finance", "MOC-Finance-Markets", "#finance"),
    "work": ("05-Finance", "MOC-Finance-Markets", "#finance"),
}

GRAPH_CONFIG: dict[str, Any] = {
    "collapse-filter": False,
    "search": "",
    "showTags": True,
    "showAttachments": False,
    "hideUnresolved": False,
    "showOrphans": True,
    "collapse-color-groups": False,
    "colorGroups": [
        {"query": "path:00-Hubs OR tag:#os", "color": {"a": 1, "rgb": 62932}},         # Cyan #00F5D4
        {"query": "path:01-Missions OR tag:#mission", "color": {"a": 1, "rgb": 16723555}},  # Neon Pink #FF2E63
        {"query": "path:02-Research OR tag:#research", "color": {"a": 1, "rgb": 16765286}}, # Gold #FFD166
        {"query": "path:03-Knowledge OR tag:#knowledge", "color": {"a": 1, "rgb": 448160}}, # Emerald #06D6A0
        {"query": "path:04-Device OR tag:#vermeer OR tag:#gaming", "color": {"a": 1, "rgb": 10182117}}, # Violet #9B5DE5
        {"query": "path:05-Finance OR tag:#finance", "color": {"a": 1, "rgb": 3835647}},    # Electric Blue #3A86FF
        {"query": "path:06-Life OR tag:#training OR tag:#life", "color": {"a": 1, "rgb": 16752412}}, # Amber #FF9F1C
        {"query": "path:07-Models OR path:08-Inbox OR path:09-Config", "color": {"a": 1, "rgb": 11066076}}, # Ice #A8DADC
    ],
    "collapse-display": False,
    "showArrow": True,
    "textFadeMultiplier": -0.3,
    "nodeSizeMultiplier": 1.25,
    "lineSizeMultiplier": 1.15,
    "collapse-forces": False,
    "centerStrength": 0.42,
    "repelStrength": 11.5,
    "linkStrength": 0.88,
    "linkDistance": 160,
    "scale": 0.85,
    "close": False,
}

APP_CONFIG: dict[str, Any] = {
    "alwaysUpdateLinks": True,
    "newFileLocation": "folder",
    "newFileFolderPath": "08-Inbox",
    "useMarkdownLinks": False,
    "showLineNumber": False,
    "readableLineLength": True,
    "strictLineBreaks": False,
}

APPEARANCE_CONFIG: dict[str, Any] = {
    "baseFontSize": 15,
    "theme": "obsidian",
    "accentColor": "#00F5D4",
}

CORE_PLUGINS_CONFIG: dict[str, bool] = {
    "file-explorer": True,
    "global-search": True,
    "switcher": True,
    "graph": True,
    "backlink": True,
    "outgoing-link": True,
    "tag-pane": True,
    "page-preview": True,
    "canvas": True,
    "outline": True,
    "properties": True,
    "bookmarks": True,
}


def _slug(s: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]+", "-", s.strip())
    return re.sub(r"-{2,}", "-", clean).strip("-")[:72] or "note"


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def _write_json_if_missing_or_force(path: str, data: dict[str, Any], force: bool = False) -> None:
    if not force and os.path.exists(path):
        return
    _write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


class ObsidianSync:
    """Two-way projection between OMEGA APEX SQLite core and an Obsidian Vault."""

    def __init__(self, vault_dir: str = DEFAULT_VAULT_DIR, paths: OmegaPaths | None = None):
        self.vault_dir = os.path.abspath(os.path.expanduser(vault_dir))
        self.paths = paths or get_paths()
        self.kf = KnowledgeFabric(self.paths)
        self.mk = MissionKernel(self.paths)
        self.fab = IntelligenceFabric(self.paths)

    def _ensure_layout(self, force_config: bool = False) -> None:
        folders = [
            ".obsidian",
            "00-Hubs",
            "01-Missions",
            "02-Research/Dossiers",
            "02-Research/Corpus",
            "02-Research/Evidence",
            "03-Knowledge/Concepts",
            "04-Device",
            "05-Finance",
            "06-Life",
            "07-Models",
            "08-Inbox",
            "09-Config",
        ]
        for sub in folders:
            os.makedirs(os.path.join(self.vault_dir, sub), exist_ok=True)

        obs = os.path.join(self.vault_dir, ".obsidian")
        _write_json_if_missing_or_force(os.path.join(obs, "graph.json"), GRAPH_CONFIG, force=force_config)
        _write_json_if_missing_or_force(os.path.join(obs, "app.json"), APP_CONFIG, force=force_config)
        _write_json_if_missing_or_force(os.path.join(obs, "appearance.json"), APPEARANCE_CONFIG, force=force_config)
        _write_json_if_missing_or_force(os.path.join(obs, "core-plugins.json"), CORE_PLUGINS_CONFIG, force=force_config)

    def _build_canvas(self) -> str:
        """Build an interactive Obsidian Canvas visualizing the OMEGA APEX architecture & flows."""
        nodes = [
            {"id": "hub", "type": "file", "file": "00-Hubs/00-OMEGA-COMMAND-CENTER.md", "x": 0, "y": 0, "width": 340, "height": 200, "color": "5"},
            {"id": "os", "type": "file", "file": "00-Hubs/MOC-OMEGA-OS.md", "x": -460, "y": -260, "width": 300, "height": 170, "color": "5"},
            {"id": "models", "type": "file", "file": "00-Hubs/MOC-Models-Workforce.md", "x": 460, "y": -260, "width": 300, "height": 170, "color": "4"},
            {"id": "research", "type": "file", "file": "00-Hubs/MOC-Research-Corpus.md", "x": 0, "y": -340, "width": 340, "height": 170, "color": "3"},
            {"id": "device", "type": "file", "file": "00-Hubs/MOC-Device-Vermeer.md", "x": -460, "y": 240, "width": 300, "height": 170, "color": "6"},
            {"id": "finance", "type": "file", "file": "00-Hubs/MOC-Finance-Markets.md", "x": 0, "y": 320, "width": 320, "height": 170, "color": "5"},
            {"id": "life", "type": "file", "file": "00-Hubs/MOC-Training-Life.md", "x": 460, "y": 240, "width": 300, "height": 170, "color": "2"},
            {"id": "inbox", "type": "text", "text": "## 08-Inbox & 09-Config (Two-Way Sync)\nDrop notes, ideas, or custom rules here in Obsidian.\nSay \"sync my obsidian notes\" and OMEGA ingests them into SQLite as `user_explicit` truth.", "x": -460, "y": 0, "width": 320, "height": 160, "color": "1"},
            {"id": "jury", "type": "text", "text": "## 3-Family Asymmetric Jury\n- Builder: Gemini 4 Neon XHigh\n- Hostile Prosecutor: Claude Opus/Sonnet 5.5\n- Judge: GPT-OSS 120B / Argon\n- Grounding: CN + GitHub + HN Comments + Papers", "x": 460, "y": 0, "width": 340, "height": 170, "color": "3"},
        ]
        edges = [
            {"id": "e1", "fromNode": "hub", "fromSide": "top", "toNode": "research", "toSide": "bottom", "label": "Tri-Lingual Research"},
            {"id": "e2", "fromNode": "hub", "fromSide": "left", "toNode": "os", "toSide": "right", "label": "Constitutional Core"},
            {"id": "e3", "fromNode": "hub", "fromSide": "right", "toNode": "models", "toSide": "left", "label": "3 Quota Pools"},
            {"id": "e4", "fromNode": "hub", "fromSide": "bottom", "toNode": "finance", "toSide": "top", "label": "Alpha & Bounties"},
            {"id": "e5", "fromNode": "hub", "fromSide": "bottom", "toNode": "device", "toSide": "top", "label": "Vermeer UID 2000"},
            {"id": "e6", "fromNode": "hub", "fromSide": "bottom", "toNode": "life", "toSide": "top", "label": "Gym & UK 2027"},
            {"id": "e7", "fromNode": "inbox", "fromSide": "right", "toNode": "hub", "toSide": "left", "label": "2-Way Ingest"},
            {"id": "e8", "fromNode": "research", "fromSide": "right", "toNode": "jury", "toSide": "top", "label": "Adversarial Verify"},
            {"id": "e9", "fromNode": "models", "fromSide": "bottom", "toNode": "jury", "toSide": "top", "label": "Cross-Family"},
        ]
        return json.dumps({"nodes": nodes, "edges": edges}, indent=2) + "\n"

    def ingest_user_notes(self) -> dict[str, Any]:
        """Ingest user-authored Markdown files from 08-Inbox/ and 09-Config/ into omega_vault.db."""
        ingested: list[str] = []
        skipped = 0
        for folder, fam in (("08-Inbox", "general"), ("09-Config", "global")):
            d = os.path.join(self.vault_dir, folder)
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not fn.endswith(".md") or fn.startswith("_") or fn.startswith("README"):
                    continue
                fp = os.path.join(d, fn)
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read().strip()
                # Skip OMEGA auto-exported notes so we never create a feedback loop
                if "omega_exported: true" in raw[:300]:
                    skipped += 1
                    continue
                if len(raw) < 10:
                    continue
                key = f"obsidian/{_slug(folder)}/{_slug(fn[:-3])}"
                clean_body = re.sub(r"^---.*?---\s*", "", raw, count=1, flags=re.DOTALL).strip()
                res = self.kf.add_memory(
                    key,
                    clean_body[:2000],
                    tags=f"obsidian,{folder.lower()}",
                    authority="user_explicit",
                    task_family=fam,
                    capability_ring=R1_SANDBOX,
                    origin_uri=f"obsidian://{folder}/{fn}",
                    global_override=(fam == "global"),
                )
                if res.get("status") == "COMMITTED":
                    ingested.append(key)
        return {"ingested_count": len(ingested), "ingested_keys": ingested, "skipped_exported": skipped}

    def export_dossier(self, title: str, markdown_body: str, *, tags: list[str] | None = None, links: list[str] | None = None) -> str:
        """Write a research dossier into 02-Research/Dossiers/ linked into the Graph View."""
        self._ensure_layout(force_config=False)
        today = time.strftime("%Y-%m-%d")
        fname = f"{today}-{_slug(title)}.md"
        fp = os.path.join(self.vault_dir, "02-Research", "Dossiers", fname)
        tag_list = sorted(set(["research", "dossier"] + [t.lstrip("#") for t in (tags or [])]))
        link_str = " · ".join(f"[[{x}]]" for x in (["00-OMEGA-COMMAND-CENTER", "MOC-Research-Corpus"] + list(links or [])))
        doc = (
            "---\n"
            f"title: \"{title.replace(chr(34), '')}\"\n"
            f"date: {today}\n"
            "omega_exported: true\n"
            f"tags: [{', '.join(tag_list)}]\n"
            "---\n\n"
            f"# {title}\n\n"
            f"Links: {link_str}\n\n"
            f"{markdown_body.strip()}\n"
        )
        _write_text(fp, doc)
        return fp

    def sync_all(self, *, force_config: bool = False, include_corpus_highlights: bool = True) -> dict[str, Any]:
        """Run full two-way sync: ingest user notes, then project full Knowledge Graph + Canvas."""
        self._ensure_layout(force_config=force_config)
        ingest_res = self.ingest_user_notes()
        now_str = time.strftime("%Y-%m-%d %H:%M")

        nodes_written = 0
        moc_buckets: dict[str, list[str]] = {
            "MOC-OMEGA-OS": [],
            "MOC-Device-Vermeer": [],
            "MOC-Finance-Markets": [],
            "MOC-Training-Life": [],
            "MOC-Models-Workforce": [],
            "MOC-Research-Corpus": [],
        }
        tag_to_notes: dict[str, list[str]] = {}

        # 1. Export all active omega_vault.db memories as linked atomic nodes
        conn = connect_vault(self.paths)
        try:
            mems = conn.execute(
                "SELECT key, tags, text, authority, task_family, capability_ring, origin_uri, updated_at FROM memories WHERE status='active' ORDER BY key ASC"
            ).fetchall()
            ev_rows = conn.execute(
                "SELECT evidence_id, claim_text, source_id, source_type, locator, support_type, verification_status, retrieved_at FROM evidence ORDER BY retrieved_at DESC LIMIT 40"
            ).fetchall()
        finally:
            conn.close()

        for m in mems:
            prefix = m["key"].split("/", 1)[0].lower()
            folder, moc, dom_tag = DOMAIN_MAP.get(prefix, ("03-Knowledge", "MOC-OMEGA-OS", "#knowledge"))
            note_name = _slug(m["key"].replace("/", "-"))
            tags = [t.strip() for t in m["tags"].split(",") if t.strip()]
            all_tags = sorted(set([dom_tag.lstrip("#"), "knowledge", m["task_family"]] + tags[:6]))
            for t in tags[:4]:
                tag_to_notes.setdefault(_slug(t), []).append(note_name)
            moc_buckets[moc].append(note_name)

            concept_links = [f"[[Concept-{_slug(t)}]]" for t in tags[:4]]
            content = (
                "---\n"
                f"key: \"{m['key']}\"\n"
                f"authority: {m['authority']}\n"
                f"task_family: {m['task_family']}\n"
                f"capability_ring: R{m['capability_ring']}\n"
                "omega_exported: true\n"
                f"tags: [{', '.join(all_tags)}]\n"
                "---\n\n"
                f"# {m['key']}\n\n"
                f"- **Hub:** [[{moc}]] · [[00-OMEGA-COMMAND-CENTER]]\n"
                f"- **Authority:** `{m['authority']}` | **Scope:** `{m['task_family']}` | **Ring:** `R{m['capability_ring']}`\n"
                + (f"- **Concepts:** {' · '.join(concept_links)}\n" if concept_links else "")
                + "\n## Verified Record\n\n"
                f"{m['text']}\n"
            )
            _write_text(os.path.join(self.vault_dir, folder, f"{note_name}.md"), content)
            nodes_written += 1

        # 2. Export Concept Bridge Nodes (connects shared concepts across domains for clean circular clusters)
        for tag_slug, linked_notes in sorted(tag_to_notes.items()):
            if len(linked_notes) < 2:
                continue
            cname = f"Concept-{tag_slug}"
            bullets = "\n".join(f"- [[{n}]]" for n in sorted(set(linked_notes)))
            content = (
                "---\n"
                "omega_exported: true\n"
                f"tags: [knowledge, concept, {tag_slug}]\n"
                "---\n\n"
                f"# Concept: {tag_slug}\n\n"
                "Hub: [[00-OMEGA-COMMAND-CENTER]]\n\n"
                f"## Connected Notes ({len(set(linked_notes))})\n\n{bullets}\n"
            )
            _write_text(os.path.join(self.vault_dir, "03-Knowledge", "Concepts", f"{cname}.md"), content)
            nodes_written += 1

        # 3. Export 9 Base Models + 3 Quota Pool Constellation Nodes
        base_models = self.fab.list_base_models()
        pools: dict[str, list[str]] = {}
        for bm in base_models:
            pool = bm["quota_pool"]
            mname = f"Model-{_slug(bm['base_model'])}"
            pname = f"Pool-{_slug(pool)}"
            pools.setdefault(pname, []).append(mname)
            moc_buckets["MOC-Models-Workforce"].append(mname)
            lat = f"{bm['best_latency_ms']:.0f} ms" if bm["best_latency_ms"] else "untested"
            content = (
                "---\n"
                f"base_model: {bm['base_model']}\n"
                f"quota_pool: {pool}\n"
                f"status: {bm['qualification_state']}\n"
                "omega_exported: true\n"
                f"tags: [models, {pool}]\n"
                "---\n\n"
                f"# {bm['base_model']}\n\n"
                f"- **Quota Pool:** [[{pname}]] · **Hub:** [[MOC-Models-Workforce]]\n"
                f"- **Status:** `{bm['qualification_state']}`\n"
                f"- **Best Measured Latency:** `{lat}`\n"
                f"- **Effort Tiers:** `{', '.join(bm['effort_tiers'])}`\n"
                f"- **Qualified Tiers:** `{', '.join(bm['qualified_tiers']) or 'none'}`\n"
            )
            _write_text(os.path.join(self.vault_dir, "07-Models", f"{mname}.md"), content)
            nodes_written += 1

        for pname, mlist in pools.items():
            moc_buckets["MOC-Models-Workforce"].append(pname)
            bullets = "\n".join(f"- [[{x}]]" for x in sorted(mlist))
            content = (
                "---\nomega_exported: true\ntags: [models, quota-pool]\n---\n\n"
                f"# {pname}\n\nHub: [[MOC-Models-Workforce]] · [[00-OMEGA-COMMAND-CENTER]]\n\n"
                f"## Models in This Quota Pool\n\n{bullets}\n"
            )
            _write_text(os.path.join(self.vault_dir, "07-Models", f"{pname}.md"), content)
            nodes_written += 1

        # 4. Export Active Missions & Pro² Problem State
        missions = self.mk.list_missions(limit=20)
        mission_links: list[str] = []
        for ms in missions:
            full = self.mk.get_mission(ms["mission_id"])
            mnode = f"Mission-{_slug(ms['mission_id'])}"
            mission_links.append(mnode)
            probs = "\n".join(
                f"- **[{p['status']}|sev {p['severity']}]** {p['blocker']}"
                for p in full.get("problems", [])
            ) or "- No open blockers logged yet."
            content = (
                "---\n"
                f"mission_id: {ms['mission_id']}\n"
                f"state: {full['state']}\n"
                f"family: {full['task_family']}\n"
                "omega_exported: true\n"
                f"tags: [mission, {full['task_family']}]\n"
                "---\n\n"
                f"# {ms['mission_id']}: {full['objective']}\n\n"
                "- **Hub:** [[00-OMEGA-COMMAND-CENTER]] · [[MOC-OMEGA-OS]]\n"
                f"- **State:** `{full['state']}` | **Autonomy:** `{full['autonomy_mode']}`\n\n"
                f"## Pro² Problem State (Blockers)\n\n{probs}\n"
            )
            _write_text(os.path.join(self.vault_dir, "01-Missions", f"{mnode}.md"), content)
            nodes_written += 1

        # 5. Export Verified Evidence Records
        for ev in ev_rows:
            enode = f"Evidence-{_slug(ev['evidence_id'])}"
            moc_buckets["MOC-Research-Corpus"].append(enode)
            content = (
                "---\n"
                f"evidence_id: {ev['evidence_id']}\n"
                f"source_type: {ev['source_type']}\n"
                f"verification_status: {ev['verification_status']}\n"
                "omega_exported: true\n"
                "tags: [research, evidence]\n"
                "---\n\n"
                f"# {ev['evidence_id']}\n\n"
                "- **Hub:** [[MOC-Research-Corpus]] · [[00-OMEGA-COMMAND-CENTER]]\n"
                f"- **Claim:** {ev['claim_text']}\n"
                f"- **Locator:** {ev['locator']}\n"
                f"- **Support:** `{ev['support_type']}` | **Status:** `{ev['verification_status']}`\n"
            )
            _write_text(os.path.join(self.vault_dir, "02-Research", "Evidence", f"{enode}.md"), content)
            nodes_written += 1

        # 6. Export Curated Top Sources from Local FTS5 Corpora (Chinese/GitHub/Trading/Strategy)
        corpus_count = 0
        if include_corpus_highlights:
            mem_dir = os.path.expanduser("~/.antigem/memory")
            corpora = [
                ("cn_vermeer_corpus.db", "Corpus-CN-Vermeer-GitHub", "MOC-Device-Vermeer", "vermeer"),
                ("trading_research_corpus.db", "Corpus-Trading-Polymarket", "MOC-Finance-Markets", "finance"),
                ("strategy_research_corpus.db", "Corpus-Strategy-Quant", "MOC-Finance-Markets", "finance"),
                ("research_corpus.db", "Corpus-AI-Harness", "MOC-OMEGA-OS", "os"),
            ]
            for db_name, hub_name, domain_moc, dom_tag in corpora:
                db_path = os.path.join(mem_dir, db_name)
                if not os.path.exists(db_path):
                    continue
                try:
                    cc = sqlite3.connect(db_path, timeout=3.0)
                    total_docs = cc.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
                    top_srcs = cc.execute(
                        "SELECT source, COUNT(*) AS c FROM docs GROUP BY source ORDER BY c DESC LIMIT 12"
                    ).fetchall()
                    sample_rows = cc.execute(
                        "SELECT title, url, source FROM docs WHERE length(text) > 200 ORDER BY id DESC LIMIT 12"
                    ).fetchall()
                    cc.close()
                except Exception:
                    continue

                corpus_count += total_docs
                moc_buckets["MOC-Research-Corpus"].append(hub_name)
                moc_buckets[domain_moc].append(hub_name)
                src_bullets = "\n".join(f"- `{s}`: {c} docs" for s, c in top_srcs)
                doc_bullets = "\n".join(f"- [{t[:90]}]({u}) (`{s}`)" for t, u, s in sample_rows)
                content = (
                    "---\n"
                    f"db: {db_name}\n"
                    f"total_docs: {total_docs}\n"
                    "omega_exported: true\n"
                    f"tags: [research, corpus, {dom_tag}]\n"
                    "---\n\n"
                    f"# {hub_name} ({total_docs} Indexed Docs)\n\n"
                    f"- **Hubs:** [[MOC-Research-Corpus]] · [[{domain_moc}]] · [[00-OMEGA-COMMAND-CENTER]]\n\n"
                    f"## Top Sources\n\n{src_bullets}\n\n"
                    f"## Recent High-Signal Entries\n\n{doc_bullets}\n"
                )
                _write_text(os.path.join(self.vault_dir, "02-Research", "Corpus", f"{hub_name}.md"), content)
                nodes_written += 1

        # 7. Export Hub MOCs + Central Star Command Center + Canvas + Inbox/Config READMEs
        moc_titles = {
            "MOC-OMEGA-OS": ("OMEGA APEX Core OS Architecture", "os"),
            "MOC-Device-Vermeer": ("POCO F6 Pro (vermeer) & Gaming Hub", "vermeer"),
            "MOC-Finance-Markets": ("Polymarket, Bounties & Finance Hub", "finance"),
            "MOC-Training-Life": ("Armwrestling, Gym, Fitness & UK 2027 Hub", "life"),
            "MOC-Models-Workforce": ("9 Base Models & 3 Quota Pools Hub", "models"),
            "MOC-Research-Corpus": ("Tri-Lingual Research, Evidence & Local Corpora", "research"),
        }
        for moc_name, (title, tag) in moc_titles.items():
            items = sorted(set(moc_buckets.get(moc_name, [])))
            links_md = "\n".join(f"- [[{x}]]" for x in items) or "- (No linked nodes yet)"
            content = (
                "---\nomega_exported: true\n"
                f"tags: [hub, {tag}]\n---\n\n"
                f"# {title}\n\n"
                "Parent: [[00-OMEGA-COMMAND-CENTER]] · Visual Map: [[OMEGA-OS-Architecture.canvas]]\n\n"
                f"## Connected Cluster ({len(items)} nodes)\n\n{links_md}\n"
            )
            _write_text(os.path.join(self.vault_dir, "00-Hubs", f"{moc_name}.md"), content)
            nodes_written += 1

        res = self.fab.host_resources()
        cmd_center = (
            "---\n"
            f"version: {VERSION}\n"
            f"synced_at: \"{now_str}\"\n"
            "omega_exported: true\n"
            "tags: [hub, os, command-center]\n"
            "---\n\n"
            f"# OMEGA APEX / Absolute Max OS — Command Center ({VERSION})\n\n"
            "> Open **Graph View** (top-right menu) or [[OMEGA-OS-Architecture.canvas]] to explore the full constellation.\n\n"
            "## Domain Hubs (Constellation Centers)\n"
            "- [[MOC-OMEGA-OS]] — Core Kernel, Hooks, Safety & Ledger\n"
            "- [[MOC-Research-Corpus]] — Tri-Lingual Chinese + GitHub Research & Evidence\n"
            "- [[MOC-Models-Workforce]] — 9 Qualified Base Models across 3 Quota Pools\n"
            "- [[MOC-Device-Vermeer]] — POCO F6 Pro (`vermeer` HyperOS 3 UID 2000) & TSB\n"
            "- [[MOC-Finance-Markets]] — Polymarket, GitHub Bounties & Cashout Rails\n"
            "- [[MOC-Training-Life]] — Armwrestling, Indoor Gym, Weight Loss & UK 2027\n\n"
            "## Live System Snapshot\n"
            f"- **Synced:** `{now_str}`\n"
            f"- **Host RAM Free:** `{res.get('ram_avail_mb', 0)} / {res.get('ram_total_mb', 0)} MB`\n"
            f"- **Disk Free:** `{res.get('disk_free_mb', 0)} MB` | **Cost Floor:** `$0.00`\n"
            f"- **Active Missions:** `{len(mission_links)}` | **Local Corpus Indexed:** `{corpus_count}` docs\n"
            + ("\n## Active Missions\n" + "\n".join(f"- [[{x}]]" for x in mission_links) + "\n" if mission_links else "")
            + "\n## Two-Way Workflow\n"
            "- Drop any personal note or idea into `08-Inbox/` or rule into `09-Config/`.\n"
            "- Tell OMEGA *\"sync my obsidian notes\"* and it ingests your notes into SQLite and rebuilds the graph.\n"
        )
        _write_text(os.path.join(self.vault_dir, "00-Hubs", "00-OMEGA-COMMAND-CENTER.md"), cmd_center)
        _write_text(os.path.join(self.vault_dir, "00-Hubs", "OMEGA-OS-Architecture.canvas"), self._build_canvas())

        inbox_readme = (
            "# 08-Inbox — Drop Your Notes & Ideas Here\n\n"
            "Write any note in this folder inside Obsidian. Next time you say **\"sync my obsidian notes\"**, "
            "OMEGA ingests it directly into `omega_vault.db` as a verified `user_explicit` fact and links it into the Knowledge Graph.\n"
        )
        cfg_readme = (
            "# 09-Config — Your Personal OS Rules & Overrides\n\n"
            "Any Markdown rule file you create here is ingested as a `global` `user_explicit` rule during Obsidian sync.\n"
        )
        _write_text(os.path.join(self.vault_dir, "08-Inbox", "README-Inbox.md"), inbox_readme)
        _write_text(os.path.join(self.vault_dir, "09-Config", "README-Config.md"), cfg_readme)
        nodes_written += 4

        return {
            "vault_dir": self.vault_dir,
            "nodes_written": nodes_written,
            "memories_exported": len(mems),
            "models_exported": len(base_models),
            "missions_exported": len(missions),
            "evidence_exported": len(ev_rows),
            "corpus_docs_linked": corpus_count,
            "canvas": os.path.join(self.vault_dir, "00-Hubs", "OMEGA-OS-Architecture.canvas"),
            "ingest": ingest_res,
        }
