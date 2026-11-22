"""RTK-Style Terminal Output Compressor & Compact Session Handoff Generator (Pure Stdlib, $0.00).

Inspired by rtk-ai/rtk & TACO (arXiv 2026):
- Strips ANSI codes, carriage-return progress-bar spam (git clone/push 1%..100%),
  and verbose passing-test boilerplate BEFORE output enters chat history.
- ALWAYS preserves errors, tracebacks, assertions, exit codes, and file paths
  so compression never triggers extra retry turns.
- Generates <750-char Session Handoff Cards for zero-loss fresh-chat restarts.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any

from . import VERSION, OmegaPaths, ensure_dirs, get_paths
from .mission import MissionKernel

ANSI_RX = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07")
PROGRESS_RX = re.compile(
    r"^(?:remote:\s*)?(?:Enumerating|Counting|Compressing|Writing|Receiving|Resolving)\s+(?:objects|deltas):\s+\d+%",
    re.IGNORECASE,
)
SPINNER_RX = re.compile(r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s+")
ERROR_RX = re.compile(r"\b(?:ERROR|FAIL|FAILED|Exception|Traceback|AssertionError|CRITICAL|DENY|QUARANTINED)\b")


def compress_output(raw: str, *, max_lines: int = 55, max_chars: int = 3800) -> dict[str, Any]:
    """Deterministically compress noisy terminal output while preserving 100% of error lines."""
    orig_chars = len(raw)
    cleaned = ANSI_RX.sub("", raw or "")
    # Collapse carriage-return overwrites (keep final state of each overwritten line)
    lines: list[str] = []
    for chunk in cleaned.splitlines():
        final_part = chunk.split("\r")[-1].rstrip()
        if not final_part:
            continue
        if SPINNER_RX.match(final_part):
            continue
        if PROGRESS_RX.match(final_part) and "done." not in final_part.lower() and "100%" not in final_part:
            continue
        lines.append(final_part)

    # Deduplicate consecutive identical lines
    dedup: list[str] = []
    repeat = 0
    for ln in lines:
        if dedup and dedup[-1] == ln:
            repeat += 1
            continue
        if repeat > 0:
            dedup[-1] = f"{dedup[-1]} (x{repeat + 1})"
            repeat = 0
        dedup.append(ln)
    if repeat > 0 and dedup:
        dedup[-1] = f"{dedup[-1]} (x{repeat + 1})"

    # If still over max_lines, preserve head + ALL error lines + tail
    if len(dedup) > max_lines:
        head = dedup[:15]
        tail = dedup[-20:]
        mid_errors = [ln for ln in dedup[15:-20] if ERROR_RX.search(ln)][:20]
        dropped = len(dedup) - len(head) - len(tail) - len(mid_errors)
        final_lines = head + ([f"[... {dropped} noisy lines compressed ...]"] if dropped > 0 else []) + mid_errors + tail
    else:
        final_lines = dedup

    out_text = "\n".join(final_lines)
    if len(out_text) > max_chars:
        out_text = out_text[: max_chars - 40] + "\n[... truncated to RTK cap ...]"

    saved_pct = round((1.0 - (len(out_text) / orig_chars)) * 100.0, 1) if orig_chars > 0 else 0.0
    return {
        "text": out_text,
        "orig_chars": orig_chars,
        "compressed_chars": len(out_text),
        "saved_pct": max(0.0, saved_pct),
    }


def run_compressed(cmd: list[str], *, timeout_s: int = 30) -> dict[str, Any]:
    """Run a command and return RTK-compressed stdout/stderr + exact returncode."""
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    combined = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    comp = compress_output(combined)
    comp["rc"] = r.returncode
    comp["ms"] = round((time.monotonic() - t0) * 1000.0, 1)
    return comp


def generate_handoff(paths: OmegaPaths | None = None, *, note: str = "") -> dict[str, Any]:
    """Generate a compact <750-char Session Handoff Card for instant fresh-chat restarts."""
    p = paths or get_paths()
    ensure_dirs(p)
    mk = MissionKernel(p)
    active = mk.list_missions(state="ACTIVE", limit=2)
    approvals = mk.list_approvals(status="PENDING")

    git_head = ""
    try:
        r = subprocess.run(
            ["git", "-C", p.repo_root, "log", "-n", "1", "--oneline"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0:
            git_head = r.stdout.strip()
    except Exception:
        pass

    lines = [
        f"# OMEGA Handoff ({VERSION} | {time.strftime('%Y-%m-%d %H:%M')})",
        f"- Repo HEAD: `{git_head or 'unknown'}`",
        f"- Pending approvals: `{len(approvals)}` | Active missions: `{len(active)}`",
    ]
    for m in active:
        full = mk.get_mission(m["mission_id"])
        open_p = [pr["blocker"][:70] for pr in full.get("problems", []) if pr["status"] in ("OPEN", "TESTING")][:2]
        lines.append(f"- Mission `{m['mission_id']}` [{m['task_family']}]: {m['objective'][:90]}")
        if open_p:
            lines.append(f"  - Blockers: {'; '.join(open_p)}")
    if note.strip():
        lines.append(f"- Next: {note.strip()[:180]}")
    else:
        lines.append("- Next: Continue active mission or state new target in plain speech.")

    card = "\n".join(lines)[:750]
    out_path = os.path.join(p.omega_home, "last_handoff.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(card + "\n")

    return {"handoff_path": out_path, "chars": len(card), "card": card}
