#!/usr/bin/env bash
# hyperos_re.sh — Master entry point for HyperOS Reverse Engineering & Optimization.
# Device: Poco F6 Pro (vermeer) | HyperOS 3.0.302.0.WNKRUXM.C09 | uid 2000, no root
# Runtime: Termux (on-device) + Shizuku/ladb
#
# Usage (on-device in Termux):
#   chmod +x hyperos_re.sh
#   ./hyperos_re.sh info          # device identity + read-only probe
#   ./hyperos_re.sh analyze       # battery/perf/thermal analysis -> reports/
#   ./hyperos_re.sh extract <pkg> # extract APK(s) for a package -> apks/<pkg>/
#   ./hyperos_re.sh extract-framework # probe framework readability
#   ./hyperos_re.sh optimize      # snapshot + idempotent optimization + rollback file
#   ./hyperos_re.sh rollback <snap> # rollback a snapshot
#   ./hyperos_re.sh all           # info + analyze + optimize
#
# From PC via ladb:
#   ladb shell sh /data/local/tmp/hyperos_re/hyperos_re.sh <cmd>

set -euo pipefail

RE_DIR="/data/local/tmp/hyperos_re"
CMD_PREFIX="${HYPEROS_RE_CMD_PREFIX:-shizuku -c}"
PY="${PYTHON:-python3}"

cmd="${1:-help}"
shift || true

run() {
  # run a python module inside RE_DIR
  (cd "$RE_DIR" && $PY "$@")
}

case "$cmd" in
  info)
    run device_interface.py - <<'PY'
import asyncio
from device_interface import DeviceInterface
async def main():
    d = DeviceInterface()
    who = await d.whoami()
    un = await d.uname()
    print("=== whoami ==="); print(who.stdout.strip())
    print("=== uname ==="); print(un.stdout.strip())
    for p in ["ro.product.model","ro.product.device","ro.product.board",
              "ro.build.display.id","ro.build.version.release","ro.build.version.sdk",
              "ro.build.fingerprint","ro.product.brand","ro.product.manufacturer"]:
        r = await d.prop(p)
        print(f"{p}={r.stdout.strip()}")
asyncio.run(main())
PY
    ;;
  analyze)
    run analyzer.py - <<'PY'
import asyncio
from analyzer import Analyzer
async def main():
    from device_interface import DeviceInterface
    d = DeviceInterface()
    a = Analyzer(d, "/data/local/tmp/hyperos_re/reports")
    rep = await a.analyze()
    path = await a.write_report(rep)
    print("Report written:", path)
asyncio.run(main())
PY
    ;;
  extract)
    pkg="${1:-}"
    if [ -z "$pkg" ]; then echo "Usage: $0 extract <package>"; exit 1; fi
    run extractor.py - <<PY
import asyncio
from extractor import Extractor
from device_interface import DeviceInterface
async def main():
    d = DeviceInterface()
    e = Extractor(d, "/data/local/tmp/hyperos_re/apks")
    res = await e.extract_package("$pkg")
    print(f"Package: {res.package}")
    for apk in res.apks:
        print(f"  {apk.split}: {apk.local_path} ({apk.size} bytes)")
    for err in res.errors:
        print(f"  ERROR: {err}")
asyncio.run(main())
PY
    ;;
  extract-framework)
    run extractor.py - <<'PY'
import asyncio
from extractor import Extractor
from device_interface import DeviceInterface
async def main():
    d = DeviceInterface()
    e = Extractor(d, "/data/local/tmp/hyperos_re/frameworks")
    r = await e.extract_framework()
    print(r.stdout)
asyncio.run(main())
PY
    ;;
  optimize)
    run optimizer.py - <<'PY'
import asyncio, json, yaml
from device_interface import DeviceInterface
from optimizer import Optimizer
async def main():
    with open("/data/local/tmp/hyperos_re/config.yaml") as f:
        cfg = yaml.safe_load(f)
    d = DeviceInterface(prefix=cfg.get("command",{}).get("prefix","shizuku -c"))
    opt = Optimizer(d, "/data/local/tmp/hyperos_re/snapshots", cfg)
    res = await opt.run_full(snapshot_first=True)
    path = opt.write_result(res)
    print("Snapshot:", res.snapshot)
    print("Result:", path)
    for c in res.changes:
        status = "OK" if (c.applied and c.verified) else ("APPLIED" if c.applied else "FAILED")
        print(f"  [{status}] {c.kind} {c.target}: {c.before} -> {c.after}")
    if res.errors:
        print("Errors:", res.errors)
asyncio.run(main())
PY
    ;;
  rollback)
    snap="${1:-}"
    if [ -z "$snap" ]; then echo "Usage: $0 rollback <snapshot.json>"; exit 1; fi
    run optimizer.py - <<PY
import asyncio, json
from device_interface import DeviceInterface
from optimizer import Optimizer
async def main():
    with open("/data/local/tmp/hyperos_re/config.yaml") as f:
        import yaml; cfg = yaml.safe_load(f)
    d = DeviceInterface(prefix=cfg.get("command",{}).get("prefix","shizuku -c"))
    opt = Optimizer(d, "/data/local/tmp/hyperos_re/snapshots", cfg)
    undone = await opt.rollback("$snap")
    for u in undone: print("rolled back:", u)
asyncio.run(main())
PY
    ;;
  all)
    "$0" info
    "$0" analyze
    "$0" optimize
    ;;
  help|*)
    echo "HyperOS RE Toolkit — Poco F6 Pro (vermeer), HyperOS 3.0.302.0.WNKRUXM.C09"
    echo "Commands: info | analyze | extract <pkg> | extract-framework | optimize | rollback <snap> | all"
    echo ""
    echo "No-root limits: props (runtime), appops, deviceidle, disable-user are tunable."
    echo "/data/app, /system/framework, /vendor/lib64 are NOT directly readable."
    ;;
esac
