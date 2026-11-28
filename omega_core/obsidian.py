"""Unified Single-Galaxy Obsidian Knowledge Graph Engine (/sdcard/Documents/OmegaVault).

Projects the entire OMEGA APEX / Absolute Max OS into ONE massive, zero-orphan,
8-color neon Knowledge Graph (no separate Canvas files, no 10-folder sprawl):
- Root hub: OMEGA-APEX.md
- Nodes/: All 13 OS Subsystems, Core Modules, Pure Gemini + Antigravity Base Models & Quota Pools,
  all active omega_vault.db Memories, Verified Evidence, Active Missions,
  Concept Bridges, and Top Curated Chinese/GitHub/Trading/Strategy Corpus Nodes
- Inbox/: The single drop folder for user notes/rules (two-way ingested into SQLite)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import time
from typing import Any

from . import R1_SANDBOX, VERSION, OmegaPaths, get_paths, tune_sqlite
from .fabric import IntelligenceFabric
from .memory import KnowledgeFabric, connect_vault
from .mission import MissionKernel

DEFAULT_VAULT_DIR = "/sdcard/Documents/OmegaVault"

# Exclusive domain routing: prefix -> (hub_name, exclusive_tag)
DOMAIN_MAP: dict[str, tuple[str, str]] = {
    "os": ("Hub-OMEGA-OS", "os"),
    "runtime": ("Hub-OMEGA-OS", "os"),
    "bridge": ("Hub-OMEGA-OS", "os"),
    "protocol": ("Hub-OMEGA-OS", "os"),
    "prefs": ("Hub-Config", "config"),
    "user": ("Hub-Config", "config"),
    "profile": ("Hub-Life-Training", "life"),
    "life": ("Hub-Life-Training", "life"),
    "training": ("Hub-Life-Training", "life"),
    "device": ("Hub-POCO-Vermeer", "vermeer"),
    "gaming": ("Hub-POCO-Vermeer", "vermeer"),
    "finance": ("Hub-Finance-Markets", "finance"),
    "work": ("Hub-Finance-Markets", "finance"),
}

# 8 mutually exclusive neon color groups (first match wins, showTags=False so every dot is a real note)
GRAPH_CONFIG: dict[str, Any] = {
    "collapse-filter": False,
    "search": "",
    "showTags": False,
    "showAttachments": False,
    "hideUnresolved": True,
    "showOrphans": False,
    "collapse-color-groups": False,
    "colorGroups": [
        {"query": "tag:#center", "color": {"a": 1, "rgb": 16777215}},       # Pure White Star #FFFFFF
        {"query": "tag:#mission", "color": {"a": 1, "rgb": 16723555}},      # Neon Pink #FF2E63
        {"query": "tag:#vermeer", "color": {"a": 1, "rgb": 10182117}},      # Electric Violet #9B5DE5
        {"query": "tag:#finance", "color": {"a": 1, "rgb": 3835647}},       # Electric Blue #3A86FF
        {"query": "tag:#life", "color": {"a": 1, "rgb": 16752412}},         # Bright Amber #FF9F1C
        {"query": "tag:#research", "color": {"a": 1, "rgb": 16765286}},     # Gold #FFD166
        {"query": "tag:#models", "color": {"a": 1, "rgb": 448160}},         # Emerald #06D6A0
        {"query": "tag:#os", "color": {"a": 1, "rgb": 62932}},              # Neon Cyan #00F5D4
        {"query": "tag:#concept", "color": {"a": 1, "rgb": 16744319}},      # Magenta Glow #FF7FBF
        {"query": "tag:#config", "color": {"a": 1, "rgb": 11066076}},       # Ice #A8DADC
    ],
    "collapse-display": False,
    "showArrow": False,
    "textFadeMultiplier": 0.4,
    "nodeSizeMultiplier": 1.35,
    "lineSizeMultiplier": 0.9,
    "collapse-forces": False,
    "centerStrength": 0.38,
    "repelStrength": 13.5,
    "linkStrength": 0.9,
    "linkDistance": 140,
    "scale": 0.65,
    "close": False,
}

APP_CONFIG: dict[str, Any] = {
    "alwaysUpdateLinks": True,
    "newFileLocation": "folder",
    "newFileFolderPath": "Inbox",
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
    "canvas": False,
    "outline": True,
    "properties": True,
    "bookmarks": True,
}


def _slug(s: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]+", "-", s.strip())
    return re.sub(r"-{2,}", "-", clean).strip("-")[:68] or "note"


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    for attempt in range(3):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
            return
        except OSError:
            if attempt == 2:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return
            time.sleep(0.05 * (attempt + 1))


def _write_json(path: str, data: dict[str, Any], force: bool = False) -> None:
    if not force and os.path.exists(path):
        return
    _write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


class ObsidianSync:
    """Two-way single-galaxy projection between OMEGA APEX SQLite core and Obsidian."""

    def __init__(self, vault_dir: str = DEFAULT_VAULT_DIR, paths: OmegaPaths | None = None):
        self.vault_dir = os.path.abspath(os.path.expanduser(vault_dir))
        self.paths = paths or get_paths()
        self.kf = KnowledgeFabric(self.paths)
        self.mk = MissionKernel(self.paths)
        self.fab = IntelligenceFabric(self.paths)

    def _ensure_layout(self, force_config: bool = False) -> None:
        for sub in (".obsidian", "Nodes", "Inbox"):
            os.makedirs(os.path.join(self.vault_dir, sub), exist_ok=True)

        obs = os.path.join(self.vault_dir, ".obsidian")
        _write_json(os.path.join(obs, "graph.json"), GRAPH_CONFIG, force=force_config)
        _write_json(os.path.join(obs, "app.json"), APP_CONFIG, force=force_config)
        _write_json(os.path.join(obs, "appearance.json"), APPEARANCE_CONFIG, force=force_config)
        _write_json(os.path.join(obs, "core-plugins.json"), CORE_PLUGINS_CONFIG, force=force_config)

    def _cleanup_legacy_folders(self) -> None:
        """Migrate any user notes out of old numbered folders and remove multi-folder/canvas clutter."""
        inbox_dir = os.path.join(self.vault_dir, "Inbox")
        os.makedirs(inbox_dir, exist_ok=True)
        for old_inbox in ("08-Inbox", "09-Config"):
            od = os.path.join(self.vault_dir, old_inbox)
            if os.path.isdir(od):
                for fn in os.listdir(od):
                    if fn.endswith(".md") and not fn.startswith("README"):
                        fp = os.path.join(od, fn)
                        with open(fp, "r", encoding="utf-8", errors="replace") as f:
                            head = f.read(300)
                        if "omega_exported: true" not in head:
                            shutil.copy2(fp, os.path.join(inbox_dir, fn))
        for legacy in (
            "00-Hubs", "01-Missions", "02-Research", "03-Knowledge",
            "04-Device", "05-Finance", "06-Life", "07-Models", "08-Inbox", "09-Config",
        ):
            lp = os.path.join(self.vault_dir, legacy)
            if os.path.isdir(lp):
                shutil.rmtree(lp, ignore_errors=True)
        for f in os.listdir(self.vault_dir):
            if f.endswith(".canvas"):
                try:
                    os.remove(os.path.join(self.vault_dir, f))
                except OSError:
                    pass

    def ingest_user_notes(self) -> dict[str, Any]:
        """Ingest user-authored Markdown files from Inbox/ into omega_vault.db."""
        ingested: list[str] = []
        skipped = 0
        inbox_dir = os.path.join(self.vault_dir, "Inbox")
        if not os.path.isdir(inbox_dir):
            return {"ingested_count": 0, "ingested_keys": [], "skipped_exported": 0}

        for fn in sorted(os.listdir(inbox_dir)):
            if not fn.endswith(".md") or fn.startswith("_") or fn.startswith("README"):
                continue
            fp = os.path.join(inbox_dir, fn)
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read().strip()
            if "omega_exported: true" in raw[:300]:
                skipped += 1
                continue
            if len(raw) < 10:
                continue
            is_rule = fn.lower().startswith(("rule-", "config-"))
            fam = "global" if is_rule else "general"
            key = f"obsidian/inbox/{_slug(fn[:-3])}"
            clean_body = re.sub(r"^---.*?---\s*", "", raw, count=1, flags=re.DOTALL).strip()
            res = self.kf.add_memory(
                key,
                clean_body[:2000],
                tags="obsidian,inbox",
                authority="user_explicit",
                task_family=fam,
                capability_ring=R1_SANDBOX,
                origin_uri=f"obsidian://Inbox/{fn}",
                global_override=is_rule,
            )
            if res.get("status") == "COMMITTED":
                ingested.append(key)
        return {"ingested_count": len(ingested), "ingested_keys": ingested, "skipped_exported": skipped}

    def export_dossier(self, title: str, markdown_body: str, *, tags: list[str] | None = None, links: list[str] | None = None) -> str:
        """Write a linked research dossier node directly into Nodes/."""
        self._ensure_layout(force_config=False)
        today = time.strftime("%Y-%m-%d")
        fname = f"Dossier-{today}-{_slug(title)}.md"
        fp = os.path.join(self.vault_dir, "Nodes", fname)
        link_str = " · ".join(f"[[{x}]]" for x in (["Hub-Research-Alpha", "OMEGA-APEX"] + list(links or [])))
        doc = (
            "---\n"
            f"title: \"{title.replace(chr(34), '')}\"\n"
            f"date: {today}\n"
            "omega_exported: true\n"
            "tags: [research]\n"
            "---\n\n"
            f"# {title}\n\n"
            f"Links: {link_str}\n\n"
            f"{markdown_body.strip()}\n"
        )
        _write_text(fp, doc)
        return fp

    def sync_all(self, *, force_config: bool = False, include_corpus_highlights: bool = True) -> dict[str, Any]:
        """Build ONE unified, 8-color, zero-orphan Knowledge Graph (no canvas, no folder clutter)."""
        self._cleanup_legacy_folders()
        self._ensure_layout(force_config=force_config)
        ingest_res = self.ingest_user_notes()
        now_str = time.strftime("%Y-%m-%d %H:%M")

        nodes_dir = os.path.join(self.vault_dir, "Nodes")
        preserved_dossiers: list[str] = []
        # Clear previously exported Nodes EXCEPT Dossier-* research reports (preserve & link them!)
        for fn in sorted(os.listdir(nodes_dir)):
            fp = os.path.join(nodes_dir, fn)
            if not (os.path.isfile(fp) and fn.endswith(".md")):
                continue
            if fn.startswith("Dossier-"):
                preserved_dossiers.append(fn[:-3])
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(300)
                if "omega_exported: true" in head:
                    os.remove(fp)
            except OSError:
                # Transient Android FUSE lock while Obsidian is open; safe to overwrite in place
                continue

        nodes_written = 0
        hubs: dict[str, tuple[str, list[str]]] = {
            "Hub-OMEGA-OS": ("os", []),
            "Hub-Models-Workforce": ("models", []),
            "Hub-Research-Alpha": ("research", list(preserved_dossiers)),
            "Hub-POCO-Vermeer": ("vermeer", []),
            "Hub-Finance-Markets": ("finance", []),
            "Hub-Life-Training": ("life", []),
            "Hub-Missions": ("mission", []),
            "Hub-Config": ("config", []),
        }
        concept_links: dict[str, list[str]] = {}

        def write_node(name: str, tag: str, body: str) -> None:
            nonlocal nodes_written
            _write_text(
                os.path.join(nodes_dir, f"{name}.md"),
                f"---\nomega_exported: true\ntags: [{tag}]\n---\n\n{body.strip()}\n",
            )
            nodes_written += 1

        # 1. All 13 Canonical Subsystems from ledger/status.json
        ledger_path = os.path.join(self.paths.repo_root, "ledger", "status.json")
        if os.path.exists(ledger_path):
            with open(ledger_path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
            plane_hubs: dict[str, list[str]] = {}
            for s in ledger.get("subsystems", []):
                sname = f"Sys-{_slug(s['id'])}-{_slug(s['name'])[:28]}"
                pname = f"Plane-{_slug(s['plane'])}"
                plane_hubs.setdefault(pname, []).append(sname)
                hubs["Hub-OMEGA-OS"][1].append(pname)
                write_node(
                    sname,
                    "os",
                    f"# {s['id']} — {s['name']}\n\n"
                    f"- **Plane:** [[{pname}]] · [[Hub-OMEGA-OS]]\n"
                    f"- **Status:** `{s['status']}`\n"
                    f"- **Owner:** `{s['owner']}`\n"
                    f"- **Tests:** `{', '.join(s.get('test_refs', []))}`\n",
                )
            for pname, slist in plane_hubs.items():
                write_node(
                    pname,
                    "os",
                    f"# {pname}\n\nHub: [[Hub-OMEGA-OS]] · [[OMEGA-APEX]]\n\n"
                    + "\n".join(f"- [[{x}]]" for x in slist),
                )

        # 2. All Core Modules (omega_core/*.py)
        core_dir = os.path.join(self.paths.repo_root, "omega_core")
        if os.path.isdir(core_dir):
            for fn in sorted(os.listdir(core_dir)):
                if fn.endswith(".py") and not fn.startswith("__"):
                    mname = f"Core-{_slug(fn[:-3])}"
                    hubs["Hub-OMEGA-OS"][1].append(mname)
                    write_node(
                        mname,
                        "os",
                        f"# omega_core/{fn}\n\nHub: [[Hub-OMEGA-OS]] · [[OMEGA-APEX]]\n",
                    )

        # 3. All active omega_vault.db memories (color-coded by true domain!)
        conn = connect_vault(self.paths)
        try:
            mems = conn.execute(
                "SELECT key, tags, text, authority, task_family, capability_ring FROM memories WHERE status='active' ORDER BY key ASC"
            ).fetchall()
            ev_rows = conn.execute(
                "SELECT evidence_id, claim_text, source_id, locator, support_type, verification_status FROM evidence ORDER BY retrieved_at DESC LIMIT 30"
            ).fetchall()
        finally:
            conn.close()

        # Pre-compute shared concepts (>=2 notes) so we NEVER emit unresolved grey ghost links!
        mem_records = []
        for m in mems:
            prefix = m["key"].split("/", 1)[0].lower()
            hub_name, dom_tag = DOMAIN_MAP.get(prefix, ("Hub-OMEGA-OS", "os"))
            nname = f"Mem-{_slug(m['key'].replace('/', '-'))}"
            tags = [t.strip() for t in m["tags"].split(",") if t.strip()][:4]
            tag_slugs = [_slug(t) for t in tags]
            for ts in tag_slugs:
                concept_links.setdefault(ts, []).append(nname)
            mem_records.append((m, hub_name, dom_tag, nname, tag_slugs))

        valid_concepts = {ts for ts, linked in concept_links.items() if len(set(linked)) >= 2}

        for m, hub_name, dom_tag, nname, tag_slugs in mem_records:
            hubs[hub_name][1].append(nname)
            c_refs = [f"[[Concept-{ts}]]" for ts in tag_slugs if ts in valid_concepts]
            write_node(
                nname,
                dom_tag,
                f"# {m['key']}\n\n"
                f"- **Hub:** [[{hub_name}]]\n"
                f"- **Authority:** `{m['authority']}` | **Scope:** `{m['task_family']}` | **Ring:** `R{m['capability_ring']}`\n"
                + (f"- **Links:** {' · '.join(c_refs)}\n" if c_refs else "")
                + f"\n{m['text']}\n",
            )

        # 4. Pure Gemini + Antigravity Base Models + Quota Pools (Emerald Constellation)
        base_models = self.fab.list_base_models()
        pools: dict[str, list[str]] = {}
        for bm in base_models:
            pname = f"Pool-{_slug(bm['quota_pool'])}"
            mname = f"Model-{_slug(bm['base_model'])}"
            pools.setdefault(pname, []).append(mname)
            hubs["Hub-Models-Workforce"][1].append(pname)
            lat = f"{bm['best_latency_ms']:.0f} ms" if bm["best_latency_ms"] else "untested"
            write_node(
                mname,
                "models",
                f"# {bm['base_model']}\n\n"
                f"- **Quota Pool:** [[{pname}]] · [[Hub-Models-Workforce]]\n"
                f"- **Status:** `{bm['qualification_state']}` (`{lat}`)\n"
                f"- **Tiers:** `{', '.join(bm['effort_tiers'])}`\n",
            )
        for pname, mlist in pools.items():
            write_node(
                pname,
                "models",
                f"# {pname}\n\nHub: [[Hub-Models-Workforce]] · [[OMEGA-APEX]]\n\n"
                + "\n".join(f"- [[{x}]]" for x in sorted(mlist)),
            )

        # 5. Active Missions & Pro² Blockers (Neon Pink Constellation)
        missions = self.mk.list_missions(limit=20)
        for ms in missions:
            full = self.mk.get_mission(ms["mission_id"])
            mnode = f"Mission-{_slug(ms['mission_id'])}"
            hubs["Hub-Missions"][1].append(mnode)
            probs = "\n".join(f"- [{p['status']}|sev {p['severity']}] {p['blocker']}" for p in full.get("problems", []))
            write_node(
                mnode,
                "mission",
                f"# {ms['mission_id']}: {full['objective']}\n\n"
                f"- **Hub:** [[Hub-Missions]] · [[OMEGA-APEX]]\n"
                f"- **State:** `{full['state']}` | **Family:** `{full['task_family']}`\n\n"
                f"## Blockers\n{probs or '- None'}\n",
            )

        # 6. Verified Evidence Nodes (Gold Constellation)
        for ev in ev_rows:
            enode = f"Ev-{_slug(ev['evidence_id'])}"
            hubs["Hub-Research-Alpha"][1].append(enode)
            write_node(
                enode,
                "research",
                f"# {ev['evidence_id']}\n\n"
                f"- **Hub:** [[Hub-Research-Alpha]]\n"
                f"- **Claim:** {ev['claim_text']}\n"
                f"- **Source:** {ev['locator']} (`{ev['support_type']}` / `{ev['verification_status']}`)\n",
            )

        # 7. High-Signal Curated Nodes from Local Corpora + Full Host Knowledge (Tools, Skills, Bounties, Contracts, Reports)
        corpus_total = 0
        if include_corpus_highlights:
            home = os.path.expanduser("~")
            mem_dir = os.path.join(home, ".antigem", "memory")

            # 7a. All executable ~/tools/*.py utilities
            tools_dir = os.path.join(home, "tools")
            tool_nodes: list[str] = []
            if os.path.isdir(tools_dir):
                for fn in sorted(os.listdir(tools_dir)):
                    if not fn.endswith(".py") or ".bak" in fn:
                        continue
                    fp = os.path.join(tools_dir, fn)
                    doc = ""
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as tf:
                            head = tf.read(500)
                        dm = re.search(r'"""(.*?)"""', head, re.DOTALL)
                        doc = dm.group(1).strip()[:280] if dm else "On-device executable Python tool."
                    except Exception:
                        doc = "On-device executable Python tool."
                    tname = f"Tool-{_slug(fn[:-3])}"
                    tool_nodes.append(tname)
                    write_node(tname, "os", f"# ~/tools/{fn}\n\n- **Cluster:** [[Cluster-Tools-Suite]] · [[Hub-OMEGA-OS]]\n\n{doc}\n")
                if tool_nodes:
                    hubs["Hub-OMEGA-OS"][1].append("Cluster-Tools-Suite")
                    write_node(
                        "Cluster-Tools-Suite",
                        "os",
                        f"# On-Device Tools Suite ({len(tool_nodes)} Scripts)\n\nHub: [[Hub-OMEGA-OS]] · [[OMEGA-APEX]]\n\n"
                        + "\n".join(f"- [[{x}]]" for x in tool_nodes),
                    )

            # 7b. All installed ~/.gemini/config/skills/*/SKILL.md skills
            skills_root = os.path.join(home, ".gemini", "config", "skills")
            skill_nodes: list[str] = []
            if os.path.isdir(skills_root):
                for sd in sorted(os.listdir(skills_root)):
                    sf = os.path.join(skills_root, sd, "SKILL.md")
                    if not os.path.isfile(sf):
                        continue
                    try:
                        with open(sf, "r", encoding="utf-8", errors="replace") as f:
                            stxt = f.read(1200)
                    except Exception:
                        continue
                    sname = f"Skill-{_slug(sd)}"
                    skill_nodes.append(sname)
                    write_node(sname, "os", f"# Skill: {sd}\n\n- **Cluster:** [[Cluster-Skills]] · [[Hub-OMEGA-OS]]\n\n{stxt[:650]}\n")
                if skill_nodes:
                    hubs["Hub-OMEGA-OS"][1].append("Cluster-Skills")
                    write_node(
                        "Cluster-Skills",
                        "os",
                        f"# Installed Skills ({len(skill_nodes)})\n\nHub: [[Hub-OMEGA-OS]] · [[OMEGA-APEX]]\n\n"
                        + "\n".join(f"- [[{x}]]" for x in skill_nodes),
                    )

            # 7c. All live GitHub Bounties from bounties.db
            bounties_db = os.path.join(mem_dir, "bounties.db")
            bounty_nodes: list[str] = []
            if os.path.isfile(bounties_db):
                try:
                    bc = sqlite3.connect(bounties_db, timeout=3.0)
                    tune_sqlite(bc)
                    brows = bc.execute(
                        "SELECT url, repo, number, title, payout_raw, comments, labels, score, substr(body_snippet, 1, 400) FROM bounties ORDER BY score DESC LIMIT 50"
                    ).fetchall()
                    bc.close()
                    for url, repo, num, title, pay, cmts, labels, score, snip in brows:
                        bname = f"Bounty-{_slug(repo.split('/')[-1])}-{num}"
                        bounty_nodes.append(bname)
                        write_node(
                            bname,
                            "finance",
                            f"# {repo}#{num}: {title[:110]}\n\n"
                            f"- **Cluster:** [[Cluster-GitHub-Bounties]] · [[Hub-Finance-Markets]]\n"
                            f"- **Score:** `{score:.1f}` | **Payout:** `{pay}` | **Comments:** `{cmts}`\n"
                            f"- **Labels:** `{labels}`\n"
                            f"- **URL:** {url}\n\n"
                            f"{snip}\n",
                        )
                    if bounty_nodes:
                        hubs["Hub-Finance-Markets"][1].append("Cluster-GitHub-Bounties")
                        write_node(
                            "Cluster-GitHub-Bounties",
                            "finance",
                            f"# GitHub Bounty Leads ({len(bounty_nodes)} Tracked)\n\nHub: [[Hub-Finance-Markets]] · [[OMEGA-APEX]]\n\n"
                            + "\n".join(f"- [[{x}]]" for x in bounty_nodes),
                        )
                except Exception:
                    pass

            # 7d. All v5.14 Contracts & Plugins (archived architectural specs)
            v514_root = os.path.join(self.paths.repo_root, "docs", "v5.14", "absolute-max-os-v5.14")
            contract_nodes: list[str] = []
            for sub_dir in ("02-contracts", "03-plugins"):
                cd = os.path.join(v514_root, sub_dir)
                if not os.path.isdir(cd):
                    continue
                for fn in sorted(os.listdir(cd)):
                    if not fn.endswith(".md"):
                        continue
                    try:
                        with open(os.path.join(cd, fn), "r", encoding="utf-8", errors="replace") as f:
                            ctxt = f.read(700)
                    except Exception:
                        continue
                    cname = f"Spec-{_slug(fn[:-3])}"
                    contract_nodes.append(cname)
                    write_node(cname, "research", f"# {fn[:-3]}\n\n- **Cluster:** [[Cluster-V514-Contracts]] · [[Hub-Research-Alpha]]\n\n{ctxt}\n")
            if contract_nodes:
                hubs["Hub-Research-Alpha"][1].append("Cluster-V514-Contracts")
                hubs["Hub-OMEGA-OS"][1].append("Cluster-V514-Contracts")
                write_node(
                    "Cluster-V514-Contracts",
                    "research",
                    f"# Archived v5.14 Contracts & Plugins ({len(contract_nodes)})\n\nHubs: [[Hub-Research-Alpha]] · [[Hub-OMEGA-OS]]\n\n"
                    + "\n".join(f"- [[{x}]]" for x in contract_nodes),
                )

            # 7e. Saved local Markdown research reports (~/tools/*.md + TSB audit)
            report_files = []
            if os.path.isdir(tools_dir):
                report_files += [os.path.join(tools_dir, f) for f in sorted(os.listdir(tools_dir)) if f.endswith(".md")]
            tsb_audit = os.path.join(mem_dir, "user_audit_tsb_thread_2026-11-16.md")
            if os.path.isfile(tsb_audit):
                report_files.append(tsb_audit)
            for rf in report_files:
                try:
                    with open(rf, "r", encoding="utf-8", errors="replace") as f:
                        rtxt = f.read(1400).strip()
                except Exception:
                    continue
                if len(rtxt) < 30:
                    continue
                base = os.path.basename(rf)[:-3]
                is_tsb = "tsb" in base.lower()
                rtag = "vermeer" if is_tsb else "research"
                rhub = "Hub-POCO-Vermeer" if is_tsb else "Hub-Research-Alpha"
                rname = f"Report-{_slug(base)}"
                hubs[rhub][1].append(rname)
                write_node(rname, rtag, f"# Report: {base}\n\n- **Hub:** [[{rhub}]] · [[OMEGA-APEX]]\n\n{rtxt}\n")

            # 7f. Curated High-Signal Local Corpus Clusters (SQLite FTS5 corpora, 0 pts=0 noise)
            corpora = [
                ("omega_corpus.db", "Cluster-Omega-Omni-Corpus", "Hub-Research-Alpha", "research", 45),
                ("cn_vermeer_corpus.db", "Cluster-CN-Vermeer-GitHub", "Hub-POCO-Vermeer", "vermeer", 45),
                ("trading_research_corpus.db", "Cluster-Trading-Alpha", "Hub-Finance-Markets", "finance", 40),
                ("strategy_research_corpus.db", "Cluster-Quant-Strategy", "Hub-Finance-Markets", "finance", 40),
                ("research_corpus.db", "Cluster-AI-Harness-Papers", "Hub-Research-Alpha", "research", 35),
            ]
            for db_name, cluster_name, domain_hub, dom_tag, limit_n in corpora:
                db_path = os.path.join(mem_dir, db_name)
                if not os.path.exists(db_path):
                    continue
                try:
                    cc = sqlite3.connect(db_path, timeout=3.0)
                    tune_sqlite(cc)
                    cnt = cc.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
                    # Pick diverse high-signal docs (skip 0-point HN noise!)
                    rows = cc.execute(
                        """
                        SELECT id, title, url, source, substr(text, 1, 500)
                        FROM docs
                        WHERE length(text) > 220 AND source != 'hn(pts=0)'
                        GROUP BY source
                        ORDER BY length(text) DESC
                        LIMIT ?
                        """,
                        (limit_n,),
                    ).fetchall()
                    if len(rows) < limit_n:
                        extra = cc.execute(
                            """
                            SELECT id, title, url, source, substr(text, 1, 500)
                            FROM docs
                            WHERE length(text) > 260 AND source != 'hn(pts=0)'
                            ORDER BY id DESC
                            LIMIT ?
                            """,
                            (limit_n - len(rows),),
                        ).fetchall()
                        seen_ids = {r[0] for r in rows}
                        rows.extend(r for r in extra if r[0] not in seen_ids)
                    cc.close()
                except Exception:
                    continue

                corpus_total += cnt
                hubs[domain_hub][1].append(cluster_name)
                hubs["Hub-Research-Alpha"][1].append(cluster_name)
                child_nodes = []
                for rid, title, url, src, snippet in rows[:limit_n]:
                    nname = f"Src-{_slug(db_name[:6])}-{rid}-{_slug(title)[:30]}"
                    child_nodes.append(nname)
                    write_node(
                        nname,
                        dom_tag,
                        f"# {title[:120]}\n\n"
                        f"- **Cluster:** [[{cluster_name}]] · [[{domain_hub}]]\n"
                        f"- **Source:** `{src}`\n"
                        f"- **URL:** {url}\n\n"
                        f"{snippet}\n",
                    )
                write_node(
                    cluster_name,
                    dom_tag,
                    f"# {cluster_name} ({cnt} Indexed Docs)\n\n"
                    f"Hubs: [[{domain_hub}]] · [[Hub-Research-Alpha]]\n\n"
                    + "\n".join(f"- [[{x}]]" for x in child_nodes),
                )

        # 8. Concept Bridges (connect shared cross-domain ideas cleanly)
        for tag_slug, linked in sorted(concept_links.items()):
            uniq = sorted(set(linked))
            if len(uniq) < 2:
                continue
            cname = f"Concept-{tag_slug}"
            write_node(
                cname,
                "concept",
                f"# Concept: {tag_slug}\n\nCenter: [[OMEGA-APEX]]\n\n"
                + "\n".join(f"- [[{x}]]" for x in uniq),
            )

        # 9. Domain Hubs (each glows in its own cluster color & links to OMEGA-APEX star!)
        for hub_name, (tag, children) in hubs.items():
            uniq = sorted(set(children))
            write_node(
                hub_name,
                tag,
                f"# {hub_name}\n\nCenter: [[OMEGA-APEX]]\n\n"
                + (f"## Cluster Nodes ({len(uniq)})\n\n" + "\n".join(f"- [[{x}]]" for x in uniq) if uniq else "- Ready for incoming nodes."),
            )

        # 10. Link any user Inbox notes into OMEGA-APEX so ZERO orphans ever exist!
        inbox_dir = os.path.join(self.vault_dir, "Inbox")
        inbox_readme = (
            "---\nomega_exported: true\ntags: [config]\n---\n\n"
            "# Inbox (Drop Your Notes Here)\n\n"
            "Hub: [[Hub-Config]] · [[OMEGA-APEX]]\n\n"
            "Write any note here in Obsidian and say **\"sync my obsidian notes\"** to ingest it into OMEGA.\n"
        )
        _write_text(os.path.join(inbox_dir, "README-Inbox.md"), inbox_readme)
        hubs["Hub-Config"][1].append("README-Inbox")

        # 11. Central Star Node at Vault Root: OMEGA-APEX.md
        res = self.fab.host_resources()
        center_doc = (
            "---\n"
            f"version: {VERSION}\n"
            f"synced_at: \"{now_str}\"\n"
            "omega_exported: true\n"
            "tags: [center]\n"
            "---\n\n"
            f"# OMEGA APEX / Absolute Max OS ({VERSION})\n\n"
            "## Constellation Hubs\n"
            "- [[Hub-OMEGA-OS]] (Cyan) — 13 Subsystems & Core Engine\n"
            f"- [[Hub-Models-Workforce]] (Emerald) — {len(base_models)} Qualified Gemini Base Models & {len(pools)} Gemini Quota Pools\n"
            "- [[Hub-Research-Alpha]] (Gold) — Tri-Lingual Chinese + GitHub Research & Evidence\n"
            "- [[Hub-POCO-Vermeer]] (Violet) — POCO F6 Pro (`vermeer`) + Chinese GitHub Corpus + TSB\n"
            "- [[Hub-Finance-Markets]] (Blue) — Polymarket, Quant Strategy & GitHub Bounties\n"
            "- [[Hub-Life-Training]] (Amber) — Armwrestling, Indoor Gym, Weight Loss & UK 2027\n"
            "- [[Hub-Missions]] (Neon Pink) — Active Missions & Pro² Blockers\n"
            "- [[Hub-Config]] (Ice) — Operator Rules & [[README-Inbox]]\n\n"
            "## Live Snapshot\n"
            f"- **RAM Free:** `{res.get('ram_avail_mb', 0)} / {res.get('ram_total_mb', 0)} MB`\n"
            f"- **Disk Free:** `{res.get('disk_free_mb', 0)} MB` | **Cost:** `$0.00`\n"
            f"- **Local Corpus Indexed:** `{corpus_total}` docs\n"
        )
        _write_text(os.path.join(self.vault_dir, "OMEGA-APEX.md"), center_doc)
        nodes_written += 2

        return {
            "vault_dir": self.vault_dir,
            "nodes_written": nodes_written,
            "memories_exported": len(mems),
            "models_exported": len(base_models),
            "missions_exported": len(missions),
            "evidence_exported": len(ev_rows),
            "corpus_docs_linked": corpus_total,
            "ingest": ingest_res,
        }
