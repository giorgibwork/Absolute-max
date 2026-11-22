#!/usr/bin/env python3
"""
02-PYTHON-STDLIB-PRIMITIVES.py: Zero-Dependency Portable OS Primitives (v5.1.0)
Runs on any Python 3.9+ host (macOS, Linux, Windows, Cloud VMs) without ARM64 ELF binaries.
Usage:
  python3 02-PYTHON-STDLIB-PRIMITIVES.py toc <path>
  python3 02-PYTHON-STDLIB-PRIMITIVES.py compact < <logfile>
  python3 02-PYTHON-STDLIB-PRIMITIVES.py mem-store <key> <val> [source_class] [origin_uri]
  python3 02-PYTHON-STDLIB-PRIMITIVES.py mem-recall <key>
  python3 02-PYTHON-STDLIB-PRIMITIVES.py verify <workspace_dir>
"""
import sys, os, re, json, time, sqlite3, hashlib, subprocess
from pathlib import Path

STORE_DB = Path.home() / ".abs_max_os_v5_1_portable.db"

def cmd_toc(target: str):
    p = Path(target)
    if not p.exists():
        sys.exit(1)
    if p.is_file():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                print(f"{'  ' * (len(m.group(1))-1)}• [L{i}] {m.group(2)}")
    else:
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            print(f"📂 {root}")
            for f in sorted(files):
                if not f.startswith("."):
                    print(f"  📄 {f}")

def cmd_compact():
    raw = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", sys.stdin.read())
    lines = raw.splitlines()
    if len(lines) <= 60:
        print("\n".join(lines))
    else:
        print("\n".join(lines[:20]) + f"\n\n[... {len(lines)-55} lines compacted ...]\n\n" + "\n".join(lines[-35:]))

def cmd_mem_store(key: str, val: str, src: str = "tool_stdout", origin: str = "local://portable"):
    if re.search(r"(?i)(ignore\s+previous|system\s*:\s*override|<system-conventions>)", val) and src != "user_verified":
        print(json.dumps({"status": "QUARANTINED", "key": key, "source": src}))
        sys.exit(10)
    with sqlite3.connect(STORE_DB) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, src TEXT, origin TEXT, ts REAL)")
        conn.execute("INSERT OR REPLACE INTO kv VALUES (?, ?, ?, ?, ?)", (key, val, src, origin, time.time()))
    print(json.dumps({"status": "COMMITTED", "key": key}))

def cmd_mem_recall(key: str):
    if not STORE_DB.exists():
        sys.exit(1)
    with sqlite3.connect(STORE_DB) as conn:
        row = conn.execute("SELECT k, v, src, origin, ts FROM kv WHERE k = ?", (key,)).fetchone()
    if not row:
        sys.exit(1)
    print(json.dumps({"key": row[0], "value": row[1], "source": row[2], "origin": row[3], "ts": row[4]}, indent=2))

def cmd_verify(root_dir: str):
    errs = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]
        for f in files:
            if f.endswith(".py"):
                fp = os.path.join(root, f)
                r = subprocess.run([sys.executable, "-m", "py_compile", fp], capture_output=True, text=True)
                if r.returncode != 0:
                    errs.append(r.stderr.strip())
    ok = len(errs) == 0
    print(json.dumps({"terminal_gate_S": 1 if ok else 0, "errors": errs}, indent=2))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    c = sys.argv[1]
    if c == "toc" and len(sys.argv) >= 3:
        cmd_toc(sys.argv[2])
    elif c == "compact":
        cmd_compact()
    elif c == "mem-store" and len(sys.argv) >= 4:
        cmd_mem_store(sys.argv[2], sys.argv[3], *(sys.argv[4:6]))
    elif c == "mem-recall" and len(sys.argv) >= 3:
        cmd_mem_recall(sys.argv[2])
    elif c == "verify":
        cmd_verify(sys.argv[2] if len(sys.argv) >= 3 else ".")
    else:
        sys.exit(1)
