# HyperOS Reverse Engineering & Optimization Toolkit
# Device: Poco F6 Pro (vermeer) | HyperOS 3.0.302.0.WNKRUXM.C09 (Android 16)
# Runtime: Termux + Shizuku/ladb | uid 2000 (shell) | NO ROOT

## What this is
A read-first, safety-first on-device toolkit that reverse-engineers what is
visible at uid 2000 and applies only reversible, verifiable optimizations.
It does NOT require root and will not attempt anything that needs it.

## File layout
- config.yaml          — device constants, tunable props, appops, disable list
- device_interface.py  — Shizuku/ladb async command wrapper (timeout + retry)
- extractor.py         — APK/framework extraction via pm path + cat/dd
- analyzer.py          — battery / cpu / thermal / props / deviceidle analysis
- optimizer.py         — idempotent optimization with snapshots + rollback
- hyperos_re.sh        — master entry point
- state/, apks/, frameworks/, reports/, snapshots/ — runtime dirs

## Setup on the device (Termux)
1. Install Termux + Shizuku. Pair Shizuku (ADB or wireless debugging).
2. Grant Shizuku permission; start it.
3. Copy this folder to /data/local/tmp/hyperos_re on the device.
4. In Termux: `pkg install python openssl` and `pip install pyyaml` (optional; config parsing degrades gracefully).
5. `chmod +x /data/local/tmp/hyperos_re/hyperos_re.sh`
6. Set prefix if using ladb from a PC:
   `export HYPEROS_RE_CMD_PREFIX="ladb shell"` then run via `ladb shell sh .../hyperos_re.sh <cmd>`
   On-device Shizuku: leave default `shizuku -c`.

## Commands
- info        — device identity, whoami, uname, key props
- analyze     — battery/cpu/thermal/props/deviceidle report -> reports/
- extract <pkg> — pull an app's APK(s) via pm path -> apks/<pkg>/
- extract-framework — probe whether framework jars are readable
- optimize    — snapshot -> apply props/appops/packages/sysfs -> verify -> result json
- rollback <snap> — revert props from a snapshot
- all         — info + analyze + optimize

## What CAN be tuned at uid 2000 (no root)
- System props via setprop (runtime only; reset on reboot)
- AppOps per package/op (cmd appops set)
- deviceidle queries (cmd deviceidle dump)
- pm disable-user / enable (reversible, survives reboot until re-enabled)
- CPU governor sysfs — ONLY if the node is writable at uid 2000 (probed first)

## What CANNOT be done without root
- Direct read of /data/app, /system/framework, /vendor/lib64
- Persistent build.prop changes across reboot (no resetprop)
- Writing read-only sysfs nodes / kernel tuning
- Modifying /system, /vendor, /oem partitions
- Framework decompilation requires the framework jars (not directly readable)

## Safety
- Every optimize run writes a snapshot to snapshots/ before changing anything.
- Changes are idempotent (re-running converges to desired state).
- Post-apply verification per change; failures are recorded, not silently ignored.
- Test props individually before batch apply (review config.yaml first).
- Rollback restores captured prop values from a snapshot.

## Reverse engineering (RE) scope
- App APKs: extracted via pm path + Shizuku cat/dd; decompile with jadx/apktool/baksmali in Termux.
- Framework: only what APEX / javalib exposes at uid 2000; most framework is not directly readable.
- Observation: props, dumpsys, /proc, /sys are fully readable.

## Device-specific notes (vermeer, SM8550, Android 16)
- Dynamic super partition, A/B slots — do not touch partitions.
- Russia region build — some props may be region-gated.
- schedutil is a sane governor start; verify per-cluster before batch applying.
