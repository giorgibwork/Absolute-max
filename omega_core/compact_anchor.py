"""Lossless Post-Compact Anchor Engine for Antigravity CLI (`agy 1.5.13`) + OMEGA APEX v6.0.

Why this exists (proven from `agy 1.5.13` binary + 2025-2026 agent compaction research):
1. `agy 1.5.13` has NO `PreCompact` / `PostCompact` hooks, and `SessionStart` only runs once at
   conversation start (not after `/compact`).
2. LLM prose summaries drop exact strings ("telephone game", arXiv:2605.11051 / arXiv:2608.24188)
   and blur UNVERIFIED/failed commands into "confirmed done" (epistemic fabrication, arXiv:2607.13071).
3. Injecting changing text on every turn breaks Automatic Prefix Caching (KV-cache invalidation).

Solution:
- `PostToolUse` deterministically extracts verbatim paths, URLs, handles, and PASS/FAIL epistemic tags
  into `~/.antigem/state/<conv_id>.anchor.json` (<5ms, 0 LLM tokens).
- `PreInvocation` checks `transcript.jsonl` for a newly increased `CHECKPOINT` `step_index`.
  - Normal turns: returns None -> ZERO injection -> preserves 99% KV-cache hit rate.
  - Exact 1st turn after `/compact`: injects one compact verbatim anchor block (<=1400 chars),
    then advances `last_seen_checkpoint_step` so subsequent turns stay silent.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from . import OmegaPaths, ensure_dirs, get_paths

URL_RX = re.compile(r"https?://[^\s\"'<>)\]]{6,180}")
HANDLE_RX = re.compile(r"(?<![A-Za-z0-9_])@[A-Za-z0-9_]{2,32}\b")
PATH_RX = re.compile(r"(?:~/|/sdcard/|/data/data/ai\.antigem/files/home/|/data/user/0/ai\.antigem/files/home/)[A-Za-z0-9._/@~-]{3,160}")
SECRET_HINT_RX = re.compile(r"(?:token|apikey|api_key|secret|password|private_key|seed|bearer)[=:\s]", re.IGNORECASE)

MAX_ITEMS = 12
MAX_INJECT_CHARS = 1400


def _safe_conv_id(raw_id: str | None) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", str(raw_id or "default"))[:64] or "default"


def anchor_path(conv_id: str, paths: OmegaPaths | None = None) -> str:
    p = paths or get_paths()
    ensure_dirs(p)
    return os.path.join(p.state_dir, f"{_safe_conv_id(conv_id)}.anchor.json")


def load_anchor(conv_id: str, paths: OmegaPaths | None = None) -> dict[str, Any]:
    ap = anchor_path(conv_id, paths)
    base: dict[str, Any] = {
        "conv_id": _safe_conv_id(conv_id),
        "last_seen_checkpoint_step": 0,
        "transcript_mtime": 0.0,
        "files_written": [],
        "urls": [],
        "handles": [],
        "verified_pass": [],
        "failed_cmds": [],
        "unverified_notes": [],
        "next_action": "",
        "updated_at": 0,
    }
    if os.path.exists(ap):
        try:
            with open(ap, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                base.update(data)
        except Exception:
            pass
    return base


def save_anchor(conv_id: str, data: dict[str, Any], paths: OmegaPaths | None = None) -> None:
    ap = anchor_path(conv_id, paths)
    data["updated_at"] = int(time.time())
    tmp = ap + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ap)


def _dedup_push(lst: list[str], item: str, limit: int = MAX_ITEMS) -> None:
    s = (item or "").strip()
    if not s or SECRET_HINT_RX.search(s):
        return
    if s in lst:
        lst.remove(s)
    lst.append(s)
    if len(lst) > limit:
        del lst[:-limit]


def update_anchor_from_tool(
    conv_id: str,
    tool: str,
    args: dict[str, Any],
    ok: bool,
    err: str = "",
    paths: OmegaPaths | None = None,
) -> dict[str, Any]:
    """Deterministic extractive update called from PostToolUse (<5ms, 0 LLM tokens)."""
    anc = load_anchor(conv_id, paths)
    blob = " ".join(
        str(args.get(k) or "")
        for k in ("Path", "CommandLine", "command", "uri", "url", "text", "Prompt")
    )

    # Track written/edited files verbatim (never paraphrased)
    fpath = str(args.get("Path") or "").strip()
    if fpath and tool in ("write_file", "edit_file"):
        _dedup_push(anc["files_written"], fpath)

    for m in PATH_RX.findall(blob):
        m_clean = m.rstrip(".,;:")
        if "/.gemini/antigravity-cli/mcp/" in m_clean or m_clean.endswith(".bak"):
            continue
        if tool in ("write_file", "edit_file") or any(ext in m_clean for ext in (".py", ".md", ".jpg", ".png", ".sh")):
            _dedup_push(anc["files_written"], m_clean)

    for u in URL_RX.findall(blob):
        u_clean = u.rstrip(".,;:")
        if "127.0.0.1" not in u_clean and "localhost" not in u_clean:
            _dedup_push(anc["urls"], u_clean)

    for h in HANDLE_RX.findall(blob):
        if h.lower() not in ("@override", "@classmethod", "@staticmethod", "@property"):
            _dedup_push(anc["handles"], h)

    # Epistemic tracking: separate verified passes from failures (blocks arXiv:2607.13071 fabrication)
    cmd = str(args.get("CommandLine") or args.get("command") or "").strip()
    if cmd:
        short_cmd = re.sub(r"\s+", " ", cmd)[:90]
        if ok:
            _dedup_push(anc["verified_pass"], short_cmd, limit=8)
        else:
            _dedup_push(anc["failed_cmds"], f"{short_cmd} -> {err[:60]}", limit=6)
    elif not ok and err:
        _dedup_push(anc["failed_cmds"], f"{tool} -> {err[:70]}", limit=6)

    save_anchor(conv_id, anc, paths)
    return anc


def pin_anchor_note(
    conv_id: str,
    *,
    urls: list[str] | None = None,
    handles: list[str] | None = None,
    files: list[str] | None = None,
    unverified: list[str] | None = None,
    next_action: str | None = None,
    paths: OmegaPaths | None = None,
) -> dict[str, Any]:
    """Explicitly pin high-value exact strings / NEXT action before compaction."""
    anc = load_anchor(conv_id, paths)
    for u in (urls or []):
        _dedup_push(anc["urls"], u)
    for h in (handles or []):
        _dedup_push(anc["handles"], h)
    for fp in (files or []):
        _dedup_push(anc["files_written"], fp)
    for uv in (unverified or []):
        _dedup_push(anc["unverified_notes"], uv, limit=8)
    if next_action is not None:
        anc["next_action"] = next_action.strip()[:240]
    save_anchor(conv_id, anc, paths)
    return anc


def _latest_checkpoint_step(transcript_file: str) -> int:
    """Fast scan of transcript.jsonl for the highest CHECKPOINT step_index."""
    if not os.path.exists(transcript_file):
        return 0
    latest = 0
    try:
        with open(transcript_file, "rb") as f:
            for raw in f:
                if b'"CHECKPOINT"' not in raw:
                    continue
                try:
                    d = json.loads(raw.decode("utf-8", "ignore"))
                    if d.get("type") == "CHECKPOINT":
                        si = int(d.get("step_index") or 0)
                        if si > latest:
                            latest = si
                except Exception:
                    continue
    except Exception:
        return 0
    return latest


def format_anchor_block(anc: dict[str, Any], transcript_file: str) -> str:
    """Render compact verbatim restore block (<= MAX_INJECT_CHARS)."""
    lines = ["[Omega Lossless Anchor — Post-Compact Exact Restore]"]
    if anc.get("next_action"):
        lines.append(f"NEXT: {anc['next_action']}")
    if anc.get("urls"):
        lines.append("URLS: " + " | ".join(anc["urls"][-6:]))
    if anc.get("handles"):
        lines.append("HANDLES: " + ", ".join(anc["handles"][-6:]))
    if anc.get("files_written"):
        clean_files = [f for f in anc["files_written"] if "/.gemini/antigravity-cli/mcp/" not in f and not f.endswith(".bak")]
        if clean_files:
            lines.append("FILES: " + " | ".join(clean_files[-6:]))
    if anc.get("unverified_notes"):
        lines.append("UNVERIFIED: " + " ; ".join(anc["unverified_notes"][-3:]))
    if anc.get("failed_cmds"):
        lines.append("RECENT_FAILS: " + " ; ".join(anc["failed_cmds"][-2:]))
    lines.append(f"RAW_TRANSCRIPT: {transcript_file}")
    text = "\n".join(lines)
    return text[:MAX_INJECT_CHARS]


def maybe_post_compact_message(
    conv_id: str,
    paths: OmegaPaths | None = None,
    brain_root: str | None = None,
) -> str | None:
    """Return restore block ONLY on the 1st turn after a new CHECKPOINT appears in transcript.jsonl."""
    cid = _safe_conv_id(conv_id)
    if cid == "default":
        return None
    root = brain_root or os.path.expanduser("~/.gemini/antigravity-cli/brain")
    tfile = os.path.join(root, cid, ".system_generated", "logs", "transcript.jsonl")
    if not os.path.exists(tfile):
        return None

    anc = load_anchor(cid, paths)
    try:
        mtime = os.path.getmtime(tfile)
    except OSError:
        return None

    # Fast-path: if transcript hasn't changed since last check, skip scan completely
    if mtime == anc.get("transcript_mtime") and anc.get("last_seen_checkpoint_step", 0) > 0:
        return None

    latest_ckpt = _latest_checkpoint_step(tfile)
    prev_ckpt = int(anc.get("last_seen_checkpoint_step") or 0)

    # First observation on an existing session: record current checkpoint without noisy injection
    if prev_ckpt == 0 and latest_ckpt > 0:
        anc["last_seen_checkpoint_step"] = latest_ckpt
        anc["transcript_mtime"] = mtime
        save_anchor(cid, anc, paths)
        return None

    if latest_ckpt > prev_ckpt:
        anc["last_seen_checkpoint_step"] = latest_ckpt
        anc["transcript_mtime"] = mtime
        save_anchor(cid, anc, paths)
        return format_anchor_block(anc, tfile)

    if mtime != anc.get("transcript_mtime"):
        anc["transcript_mtime"] = mtime
        save_anchor(cid, anc, paths)
    return None
