"""Constitutional Kernel & Capability Gateway.

Enforces:
- Fail-closed PREPARE_ONLY autonomy gate (never silently allows malformed input)
- $0.00 zero-cost spend floor unless explicitly approved
- Weakest-Agent Safety Invariant (subagents strictly inherit min(caller_ring, target_ring))
- Prompt-injection & secret leakage screening on tool calls and memory writes
- Per-session SPIDES taint tracking & repeat-failure circuit breaker
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Any

from . import (
    R0_READONLY,
    R1_SANDBOX,
    R2_WORKSPACE,
    R3_EXTERNAL_APPROVED,
    REV0_NO_EFFECT,
    REV1_RESTORABLE,
    REV2_COMPENSABLE,
    REV3_HARD_TO_RECOVER,
    REV4_IRREVERSIBLE,
    RING_NAMES,
    SCHEMA_BIT_DELEGATION,
    OmegaPaths,
    ensure_dirs,
    get_paths,
    mark_schema_bit,
    schema_has_bit,
    tune_sqlite,
)

# 1. Always-DENY destructive / host-unsafe patterns (word-bounded, order-independent flags, absolute bin paths)
HARD_DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?:^|[;&|]\s*|['\"(])(?:/(?:usr/)?bin/)?rm\s+"
            r"(?:-[a-zA-Z]*(?:r[a-zA-Z]*f|f[a-zA-Z]*r)[a-zA-Z]*|--recursive\s+--force|-r\s+-f|-f\s+-r)\s+"
            r"(?:/|~|\$HOME|\$\{HOME\}|/\*)(?:\s|$|[;&|'\"])"
        ),
        "Blocked catastrophic recursive delete on root or home directory.",
    ),
    (
        re.compile(r"open\([^)]*['\"]w['\"][^)]*\)\.write\(\s*open\("),
        "Blocked destructive self-truncation open(p,'w').write(open(p).read()); use a .bak copy.",
    ),
    (
        re.compile(r"(?:^|[;&|]\s*|['\"])(?:/(?:usr/)?bin/)?sed\s+-i(?:\s|$).*\.gemini/"),
        "Blocked in-place sed -i on ~/.gemini/ config files; snapshot and copy-test first.",
    ),
    (
        re.compile(r"(?:^|[\s>=:(\"'`])/tmp(?:/|$|[\s\"'`;)&|])"),
        "Blocked /tmp path on AntiGem Android (no /tmp exists); use $TMPDIR or ~/.",
    ),
    (
        re.compile(r"\b(?:mkfs(?:\.[a-z0-9]+)?|dd\s+if=.*of=/dev/|shutdown|reboot)\b"),
        "Blocked destructive system-level disk/power operation.",
    ),
]

# 2. Spend / payment guard ($0.00 floor)
SPEND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(?:stripe\s+charges|paypal|buy[-_ ]?credits|billing[-_ ]?upgrade|purchase[-_ ]?plan|send[-_ ]?usdc|eth_sendRawTransaction)\b",
            re.IGNORECASE,
        ),
        "Blocked spend/transfer action under $0.00 cost floor without explicit approval ticket.",
    ),
]

# 3. Privilege escalation / consequential external mutations (including nested bash -c / sh -c payloads)
PRIVILEGE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?:^|[;&|]\s*|['\"(`]\s*)(?:/(?:usr/)?bin/)?(?:su|sudo)\b"),
        "Privilege escalation (su/sudo) requires explicit human approval.",
    ),
    (
        re.compile(
            r"(?:^|[;&|]\s*|['\"(`]\s*)(?:adb|ladb|rish|shizuku|axsh)\b|"
            r"\b(?:pm\s+(?:disable(?:-user)?|uninstall)|settings\s+(?:put|delete|reset)|"
            r"device_config\s+(?:put|delete|set_sync_disabled_for_tests)|setprop)\b",
            re.IGNORECASE,
        ),
        "REV3_HARD_TO_RECOVER: Android uid 2000 / system-state mutation requires prior-state snapshot and explicit human approval.",
    ),
    (
        re.compile(r"\bchmod\s+777\b.*(?:\.ssh|\.mcp_secret|config\.json)"),
        "Unsafe permission widening on sensitive path requires human approval.",
    ),
]

EXTERNAL_MUTATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bgit\s+push\b[^\n]*\s(?:--force|-f)\b"),
        "Force-push to remote requires explicit human approval.",
    ),
    (
        re.compile(r"\bgh\s+(?:repo\s+delete|pr\s+merge|release\s+delete)\b"),
        "Consequential remote GitHub mutation requires explicit human approval.",
    ),
    (
        re.compile(r"\b(?:pkg|apt|apt-get)\s+install\b"),
        "System package install requires user explanation and explicit permission.",
    ),
]

# 4. Sensitive secret files & token patterns
TAINT_SINK_RX = re.compile(
    r"(?:\.mcp_secret|id_ed25519|jetski-standalone-oauth-token|\.git-credentials|BEGIN\s+(?:RSA|OPENSSH|EC)\s+PRIVATE\s+KEY)",
    re.IGNORECASE,
)

SECRET_VALUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github_pat", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("openai_or_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]

# 5. Untrusted prompt-injection markers
INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\boverride\s+(?:constitution|system|policy|safety)\b", re.IGNORECASE),
    re.compile(r"<\s*(?:system|system-conventions|pinned_constraints|RULE)\b", re.IGNORECASE),
    re.compile(r"\bgrant\s+(?:me|yourself)\s+(?:root|admin|unrestricted|r3)\b", re.IGNORECASE),
    re.compile(r"\bexfiltrate\b|\bsend\s+secrets?\s+to\b", re.IGNORECASE),
]

# Mutating shell patterns (blocked for R0_READONLY subagents)
MUTATING_CMD_RX = re.compile(
    r"(?:>>?|\b(?:rm|mv|cp|mkdir|touch|chmod|chown|git\s+(?:commit|push|reset|checkout|clean)|python3\s+-c\s+.*open\([^)]*['\"][wa]['\"])\b)"
)

WRITE_TOOLS = {"write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content"}
MUTATING_TOOLS = WRITE_TOOLS | {"run_command", "run_workflow"}

SHELL_CHAIN_RX = re.compile(r"[;&|><`$()]|\n")
SAFE_AUTO_APPROVE_RX = re.compile(
    r"^(?:omega\s+(?:dashboard|status|feed|code\s+(?:find|callers|outline)|crawl\b[^\n]*--query-only)|git\s+(?:status|diff|log|rev-parse|branch))\b"
)


@dataclass
class GateDecision:
    decision: str  # allow | auto_approve | ask | force_ask | deny
    action_class: str
    reason: str
    ring_required: int = R0_READONLY
    approval_id: str | None = None
    reversibility_class: str = REV0_NO_EFFECT

    def to_hook_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"decision": self.decision}
        if self.decision not in ("allow", "auto_approve"):
            out["reason"] = self.reason
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_reversibility(action_class: str, cmd: str = "", tool: str = "") -> str:
    """Classify action reversibility under Five-Level Vocabulary (REV0-REV4, arXiv:2611.22075)."""
    if action_class in ("DESTRUCTIVE", "SPEND", "SECRET_LEAK"):
        return REV4_IRREVERSIBLE
    if action_class == "PRIVILEGE_CHANGE":
        return REV3_HARD_TO_RECOVER
    if action_class == "EXTERNAL_MUTATION":
        if re.search(r"\b(?:--force|-f|delete)\b", cmd, re.IGNORECASE):
            return REV4_IRREVERSIBLE
        return REV2_COMPENSABLE
    if action_class == "WORKSPACE_MUTATION" or tool in ("write_file", "edit_file"):
        return REV1_RESTORABLE
    if action_class == "READ":
        return REV0_NO_EFFECT
    return REV3_HARD_TO_RECOVER


def scan_secrets(text: str) -> list[str]:
    """Return list of secret rule names matched in text (never returns the secret value)."""
    hits: list[str] = []
    for name, rx in SECRET_VALUE_PATTERNS:
        if rx.search(text):
            hits.append(name)
    return hits


def scan_prompt_injection(text: str) -> list[str]:
    """Detect prompt-injection payloads in untrusted content."""
    hits: list[str] = []
    for rx in INJECTION_PATTERNS:
        if rx.search(text):
            hits.append(rx.pattern[:64])
    return hits


def screen_memory_write(
    text: str,
    source_class: str,
    origin_uri: str = "local://unknown",
) -> tuple[bool, str]:
    """Screen candidate memory writes before commit.

    Untrusted sources (web_source, external_tool, inferred) cannot commit
    prompt-injection instructions or raw secrets. Even trusted sources cannot
    commit raw private keys or API tokens.
    """
    secret_hits = scan_secrets(text)
    if secret_hits:
        return False, f"QUARANTINED_SECRET: matched {','.join(secret_hits)}"

    untrusted = source_class not in ("user_explicit", "verified_log")
    if untrusted:
        inj_hits = scan_prompt_injection(text)
        if inj_hits:
            return False, f"QUARANTINED_INJECTION: untrusted source={source_class} origin={origin_uri}"

    return True, "OK"


def _collect_string_leaves(obj: Any, out: list[str], *, depth: int = 0) -> None:
    """Recursively collect all string values from nested args (e.g., ReplacementChunks)."""
    if depth > 6 or len(out) > 200:
        return
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_string_leaves(v, out, depth=depth + 1)
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            _collect_string_leaves(it, out, depth=depth + 1)


def _is_within_root(target: str, root: str) -> bool:
    """Symlink-safe containment check using realpath + commonpath (blocks sibling-prefix traversal)."""
    try:
        rt = os.path.realpath(os.path.expanduser(target))
        rr = os.path.realpath(os.path.expanduser(root))
        return os.path.commonpath([rt, rr]) == rr
    except ValueError:
        return False


def _init_delegation_table(paths: OmegaPaths) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(paths.missions_db, timeout=5.0)
    if schema_has_bit(conn, SCHEMA_BIT_DELEGATION):
        tune_sqlite(conn, read_only=False)
        return conn
    tune_sqlite(conn, read_only=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS delegation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            caller_id TEXT NOT NULL,
            caller_ring INTEGER NOT NULL,
            target_id TEXT NOT NULL,
            target_ring INTEGER NOT NULL,
            effective_ring INTEGER NOT NULL,
            task_family TEXT NOT NULL,
            mission_id TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT ''
        );
        """
    )
    mark_schema_bit(conn, SCHEMA_BIT_DELEGATION)
    conn.commit()
    return conn


def delegate_ring(
    caller_id: str,
    caller_ring: int,
    target_id: str,
    target_ring: int,
    task_family: str = "general",
    mission_id: str = "",
    reason: str = "",
    paths: OmegaPaths | None = None,
) -> int:
    """Weakest-Agent Safety Invariant (#10).

    A delegated subagent or tool class strictly inherits min(caller_ring, target_ring)
    and every boundary crossing is logged persistently.
    """
    p = paths or get_paths()
    c_ring = max(R0_READONLY, min(R3_EXTERNAL_APPROVED, int(caller_ring)))
    t_ring = max(R0_READONLY, min(R3_EXTERNAL_APPROVED, int(target_ring)))
    eff = min(c_ring, t_ring)

    conn = _init_delegation_table(p)
    try:
        conn.execute(
            """
            INSERT INTO delegation_log
                (ts, caller_id, caller_ring, target_id, target_ring, effective_ring, task_family, mission_id, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (int(time.time()), caller_id, c_ring, target_id, t_ring, eff, task_family, mission_id, reason[:240]),
        )
        conn.commit()
    finally:
        conn.close()
    return eff


def _check_approved_ticket(paths: OmegaPaths, action_sig: str, *, ttl_s: int = 3600) -> str | None:
    """Single-use TTL-bounded approval ticket lookup (atomically marks CONSUMED to block replay)."""
    if not os.path.exists(paths.missions_db):
        return None
    try:
        conn = sqlite3.connect(paths.missions_db, timeout=2.0)
        tune_sqlite(conn, read_only=False)
        now = int(time.time())
        ahash = hashlib.sha256(action_sig.encode("utf-8")).hexdigest()[:16]
        row = conn.execute(
            """
            SELECT approval_id, resolved_at FROM approvals
            WHERE status = 'APPROVED'
              AND (command_or_payload = ? OR action_hash = ?)
              AND (resolved_at = 0 OR resolved_at >= ?)
            ORDER BY resolved_at DESC LIMIT 1
            """,
            (action_sig, ahash, now - ttl_s),
        ).fetchone()
        if not row:
            conn.close()
            return None
        aid = row[0]
        cur = conn.execute(
            "UPDATE approvals SET status = 'CONSUMED' WHERE approval_id = ? AND status = 'APPROVED'",
            (aid,),
        )
        conn.commit()
        conn.close()
        return aid if cur.rowcount == 1 else None
    except Exception:
        return None


def classify_command(cmd: str) -> tuple[str, int, str]:
    """Return (action_class, required_ring, reason)."""
    for rx, reason in HARD_DENY_PATTERNS:
        if rx.search(cmd):
            return "DESTRUCTIVE", R3_EXTERNAL_APPROVED + 1, reason
    for rx, reason in SPEND_PATTERNS:
        if rx.search(cmd):
            return "SPEND", R3_EXTERNAL_APPROVED, reason
    for rx, reason in PRIVILEGE_PATTERNS:
        if rx.search(cmd):
            return "PRIVILEGE_CHANGE", R3_EXTERNAL_APPROVED, reason
    for rx, reason in EXTERNAL_MUTATION_PATTERNS:
        if rx.search(cmd):
            return "EXTERNAL_MUTATION", R3_EXTERNAL_APPROVED, reason
    if MUTATING_CMD_RX.search(cmd):
        return "WORKSPACE_MUTATION", R2_WORKSPACE, "Workspace write/mutation command."
    return "READ", R0_READONLY, "Read-only or local inspection command."


def evaluate_tool_call(
    payload: dict[str, Any] | None,
    *,
    caller_ring: int = R2_WORKSPACE,
    autonomy_mode: str = "PREPARE_ONLY",
    paths: OmegaPaths | None = None,
    raw_parse_error: bool = False,
) -> GateDecision:
    """Evaluate a tool invocation against Constitutional laws (fail-closed)."""
    p = paths or get_paths()

    # Fail-closed on malformed/unparseable hook payloads
    if raw_parse_error or payload is None or not isinstance(payload, dict):
        return GateDecision(
            decision="deny",
            action_class="MALFORMED_INPUT",
            reason="Fail-closed constitutional gate: malformed or empty hook payload.",
            ring_required=R3_EXTERNAL_APPROVED,
        )

    tc = payload.get("toolCall") or {}
    if not isinstance(tc, dict):
        return GateDecision(
            decision="deny",
            action_class="MALFORMED_INPUT",
            reason="Fail-closed constitutional gate: invalid toolCall structure.",
            ring_required=R3_EXTERNAL_APPROVED,
        )

    tool = str(tc.get("name") or "").strip()
    args = tc.get("args") or {}
    if not isinstance(args, dict):
        return GateDecision(
            decision="deny",
            action_class="MALFORMED_INPUT",
            reason="Fail-closed constitutional gate: invalid tool args.",
            ring_required=R3_EXTERNAL_APPROVED,
        )

    cmd = str(args.get("CommandLine") or args.get("command") or args.get("cmd") or "")
    target_path = str(
        args.get("Path")
        or args.get("TargetFile")
        or args.get("AbsolutePath")
        or args.get("file_path")
        or args.get("path")
        or ""
    )
    target_url = str(args.get("Url") or args.get("url") or "")

    conv_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("conversationId") or "default"))[:48] or "default"
    st_path = os.path.join(p.state_dir, f"{conv_id}.json")

    def _load_session_state() -> tuple[dict[str, Any] | None, bool]:
        if not os.path.exists(st_path):
            return None, False
        try:
            with open(st_path, "r", encoding="utf-8") as sf:
                st = json.load(sf)
            return (st if isinstance(st, dict) else {}), False
        except Exception:
            return None, True

    # 1. File write/edit capability ring + recursive secret scan + symlink-safe sandbox checks
    if tool in WRITE_TOOLS:
        if caller_ring < R1_SANDBOX:
            return GateDecision(
                decision="deny",
                action_class="WORKSPACE_MUTATION",
                reason=f"Weakest-Agent gate: caller ring {RING_NAMES.get(caller_ring, caller_ring)} cannot invoke {tool}.",
                ring_required=R2_WORKSPACE,
            )
        if caller_ring == R1_SANDBOX:
            if not (_is_within_root(target_path, p.tmpdir) or _is_within_root(target_path, p.omega_home)):
                return GateDecision(
                    decision="deny",
                    action_class="WORKSPACE_MUTATION",
                    reason=f"Sandbox ring R1_SANDBOX blocked write outside sandbox/tmpdir: {target_path}",
                    ring_required=R2_WORKSPACE,
                )
        leaves: list[str] = []
        _collect_string_leaves(args, leaves)
        full_payload_text = "\n".join(leaves)
        if TAINT_SINK_RX.search(target_path):
            return GateDecision(
                decision="force_ask",
                action_class="PRIVILEGE_CHANGE",
                reason=f"REV3 write to sensitive credential path requires explicit un-cached approval: {target_path}",
                ring_required=R3_EXTERNAL_APPROVED,
                reversibility_class=REV3_HARD_TO_RECOVER,
            )
        sec_hits = scan_secrets(full_payload_text)
        if sec_hits:
            return GateDecision(
                decision="deny",
                action_class="SECRET_LEAK",
                reason=f"Blocked writing raw secret material ({','.join(sec_hits)}) to {target_path}.",
                ring_required=R3_EXTERNAL_APPROVED,
                reversibility_class=REV4_IRREVERSIBLE,
            )
        return GateDecision("allow", "WORKSPACE_MUTATION", "Permitted workspace file edit.", R2_WORKSPACE, reversibility_class=REV1_RESTORABLE)

    # 1b. SPIDES taint gate on read_file / view_file / read_url_content (blocks credential exfil after web taint)
    if tool in ("read_file", "view_file", "read_url_content"):
        probe_txt = f"{target_path} {target_url}"
        if TAINT_SINK_RX.search(probe_txt):
            st, corrupt = _load_session_state()
            if corrupt or (st and st.get("tainted_web")):
                return GateDecision(
                    decision="force_ask",
                    action_class="SPIDES_TAINT",
                    reason=f"SPIDES taint gate: session touched untrusted web content and {tool} accesses sensitive path/URL.",
                    ring_required=R3_EXTERNAL_APPROVED,
                    reversibility_class=REV3_HARD_TO_RECOVER,
                )

    # 2. Shell command classification & enforcement
    if tool in ("run_command", "bash", "sh") or cmd:
        action_class, req_ring, reason = classify_command(cmd)
        rev_cls = classify_reversibility(action_class, cmd=cmd, tool=tool)
        if action_class == "DESTRUCTIVE":
            return GateDecision("deny", action_class, reason, req_ring, reversibility_class=rev_cls)

        if action_class in ("SPEND", "PRIVILEGE_CHANGE", "EXTERNAL_MUTATION"):
            approved = _check_approved_ticket(p, cmd)
            if approved:
                return GateDecision("allow", action_class, f"Approved via single-use ticket {approved}.", req_ring, approved, rev_cls)
            if action_class == "SPEND":
                return GateDecision("deny", action_class, reason, req_ring, reversibility_class=rev_cls)
            # REV3 privilege / Android uid 2000 mutations ALWAYS force_ask unconditionally without a single-use ticket!
            if action_class == "PRIVILEGE_CHANGE":
                return GateDecision("force_ask", action_class, reason, req_ring, reversibility_class=rev_cls)
            if autonomy_mode == "PREPARE_ONLY" or caller_ring < R3_EXTERNAL_APPROVED:
                return GateDecision("ask", action_class, reason, req_ring, reversibility_class=rev_cls)

        if req_ring > caller_ring:
            return GateDecision(
                decision="deny",
                action_class=action_class,
                reason=f"Weakest-Agent gate: action requires {RING_NAMES.get(req_ring, req_ring)}, caller has {RING_NAMES.get(caller_ring, caller_ring)}.",
                ring_required=req_ring,
                reversibility_class=rev_cls,
            )

        # 3. Per-session circuit breaker + SPIDES taint gate
        state, corrupt = _load_session_state()
        if corrupt:
            if TAINT_SINK_RX.search(cmd):
                return GateDecision(
                    decision="ask",
                    action_class="SPIDES_TAINT",
                    reason="Session taint state unreadable while accessing sensitive path.",
                    ring_required=R3_EXTERNAL_APPROVED,
                )
        elif state:
            cmd_hash = hashlib.sha256(f"{tool}:{cmd}".encode("utf-8")).hexdigest()[:16]
            if state.get("last_fail_hash") == cmd_hash and int(state.get("fail_streak", 0)) >= 2:
                return GateDecision(
                    decision="deny",
                    action_class="CIRCUIT_BREAKER",
                    reason="Circuit breaker tripped: identical command failed twice in a row. Inspect root cause first.",
                    ring_required=caller_ring,
                )
            if state.get("tainted_web") and TAINT_SINK_RX.search(cmd):
                return GateDecision(
                    decision="ask",
                    action_class="SPIDES_TAINT",
                    reason="SPIDES taint gate: session read untrusted web content and command touches sensitive credentials.",
                    ring_required=R3_EXTERNAL_APPROVED,
                )

        # Strictly safe single-command REV0 read-only diagnostics auto-approve cleanly (zero shell chaining!)
        stripped_cmd = cmd.strip()
        if (
            action_class == "READ"
            and caller_ring >= R2_WORKSPACE
            and stripped_cmd
            and not SHELL_CHAIN_RX.search(stripped_cmd)
            and SAFE_AUTO_APPROVE_RX.match(stripped_cmd)
        ):
            return GateDecision("auto_approve", action_class, "REV0 read-only diagnostic auto-approved.", req_ring, reversibility_class=REV0_NO_EFFECT)

        return GateDecision("allow", action_class, reason, req_ring, reversibility_class=rev_cls)

    # 3. Generic tool ring enforcement
    if tool in MUTATING_TOOLS and caller_ring < R1_SANDBOX:
        return GateDecision(
            decision="deny",
            action_class="WORKSPACE_MUTATION",
            reason=f"Weakest-Agent gate: {RING_NAMES.get(caller_ring, caller_ring)} cannot invoke {tool}.",
            ring_required=R1_SANDBOX,
        )

    return GateDecision("allow", "READ", "Permitted tool call.", R0_READONLY)
