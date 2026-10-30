#!/usr/bin/env python3
"""
analyzer.py — Battery / performance / thermal analysis for HyperOS (on-device).

Reads only what uid 2000 can access: props, /proc, /sys, dumpsys, pm, appops.
Produces a machine-readable report under reports/.
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from device_interface import DeviceInterface, CmdResult


@dataclass
class CpuInfo:
    governor: str = ""
    min_freq: str = ""
    max_freq: str = ""
    cur_freq: str = ""
    online: str = ""


@dataclass
class BatteryInfo:
    level: str = ""
    status: str = ""
    health: str = ""
    temp: str = ""
    voltage: str = ""
    technology: str = ""


@dataclass
class AnalysisReport:
    device: str = ""
    android: str = ""
    build: str = ""
    cpu: dict[str, CpuInfo] = field(default_factory=dict)
    battery: BatteryInfo = field(default_factory=BatteryInfo)
    thermal: dict[str, str] = field(default_factory=dict)
    props: dict[str, str] = field(default_factory=dict)
    idle: dict[str, str] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class Analyzer:
    def __init__(self, iface: DeviceInterface, reports_dir: str):
        self.iface = iface
        self.reports_dir = reports_dir
        os.makedirs(self.reports_dir, exist_ok=True)

    async def _first(self, text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    async def analyze(self) -> AnalysisReport:
        report = AnalysisReport()

        # identity
        r_build = await self.iface.prop("ro.build.display.id")
        r_android = await self.iface.prop("ro.build.version.release")
        report.build = r_build.stdout.strip() or "unknown"
        report.android = r_android.stdout.strip() or "unknown"

        # battery
        bat = await self.iface.dumpsys("battery")
        report.battery.level = self._first(bat.stdout, r"level:\s*(\d+)")
        report.battery.status = self._first(bat.stdout, r"status:\s*(\d+)")
        report.battery.health = self._first(bat.stdout, r"health:\s*(\d+)")
        report.battery.temp = self._first(bat.stdout, r"temperature:\s*(\d+)")
        report.battery.voltage = self._first(bat.stdout, r"voltage:\s*(\d+)")
        report.battery.technology = self._first(bat.stdout, r"technology:\s*(\S+)")

        # cpu governors / freqs (read-only at uid 2000 usually)
        cpu = await self.iface.run(
            "for d in /sys/devices/system/cpu/cpu[0-9]*; do "
            "echo \"$d gov=$(cat $d/cpufreq/scaling_governor 2>/dev/null) "
            "min=$(cat $d/cpufreq/scaling_min_freq 2>/dev/null) "
            "max=$(cat $d/cpufreq/scaling_max_freq 2>/dev/null) "
            "cur=$(cat $d/cpufreq/scaling_cur_freq 2>/dev/null) "
            "online=$(cat $d/online 2>/dev/null)\"; done"
        )
        for line in cpu.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split()
            dev = parts[0] if parts else ""
            info = CpuInfo()
            for tok in parts[1:]:
                if tok.startswith("gov="):
                    info.governor = tok[4:]
                elif tok.startswith("min="):
                    info.min_freq = tok[4:]
                elif tok.startswith("max="):
                    info.max_freq = tok[4:]
                elif tok.startswith("cur="):
                    info.cur_freq = tok[4:]
                elif tok.startswith("online="):
                    info.online = tok[7:]
            if dev:
                report.cpu[dev] = info

        # thermal zone temps
        therm = await self.iface.run(
            "for z in /sys/class/thermal/thermal_zone*; do "
            "echo \"$(basename $z)=$(cat $z/temp 2>/dev/null)\"; done"
        )
        for line in therm.stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                report.thermal[k.strip()] = v.strip() + "mC"

        # key props
        for p in [
            "ro.build.display.id",
            "ro.build.version.sdk",
            "ro.product.model",
            "ro.product.device",
            "ro.product.board",
            "ro.build.fingerprint",
            "persist.sys.usb.config",
            "debug.performance.tuning",
        ]:
            pr = await self.iface.prop(p)
            if pr.rc == 0 and pr.stdout.strip():
                report.props[p] = pr.stdout.strip()

        # deviceidle
        idle = await self.iface.cmd("deviceidle", "dump")
        report.idle["raw"] = idle.stdout[:2000]

        # findings / recommendations
        report.findings.append(
            f"Build {report.build} on Android {report.android}; uid 2000, no root."
        )
        if report.battery.temp:
            try:
                t = int(report.battery.temp) / 10.0
                if t > 45:
                    report.findings.append(f"Battery temperature {t}°C — thermal throttling likely.")
                    report.recommendations.append("Reduce performance governor to powersave until cool.")
            except ValueError:
                pass

        sched = [c for c in report.cpu.values() if c.governor]
        if sched:
            report.findings.append(
                f"CPU governors observed: {sorted({c.governor for c in sched})}"
            )
            report.recommendations.append(
                "Test schedutil on performance-critical cores; powersave on little cores."
            )

        report.recommendations.append(
            "Review disabled-package and appops changes in optimizer.py before batch apply."
        )
        report.recommendations.append(
            "Props set via setprop are runtime-only; they reset on reboot without root."
        )

        return report

    async def write_report(self, report: AnalysisReport) -> str:
        import json
        path = os.path.join(self.reports_dir, "analysis.json")
        data = {
            "device": report.device,
            "android": report.android,
            "build": report.build,
            "cpu": {k: v.__dict__ for k, v in report.cpu.items()},
            "battery": report.battery.__dict__,
            "thermal": report.thermal,
            "props": report.props,
            "idle": report.idle,
            "findings": report.findings,
            "recommendations": report.recommendations,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        # human-readable
        txt = os.path.join(self.reports_dir, "analysis.txt")
        with open(txt, "w") as f:
            f.write(f"HyperOS Analysis — {report.build} (Android {report.android})\n")
            f.write("=" * 60 + "\n\n")
            f.write("Battery:\n")
            for k, v in report.battery.__dict__.items():
                f.write(f"  {k}: {v}\n")
            f.write("\nCPU:\n")
            for k, v in report.cpu.items():
                f.write(f"  {k}: gov={v.governor} min={v.min_freq} max={v.max_freq} "
                        f"cur={v.cur_freq} online={v.online}\n")
            f.write("\nThermal:\n")
            for k, v in report.thermal.items():
                f.write(f"  {k}: {v}\n")
            f.write("\nProps:\n")
            for k, v in report.props.items():
                f.write(f"  {k}: {v}\n")
            f.write("\nFindings:\n")
            for fnd in report.findings:
                f.write(f"  - {fnd}\n")
            f.write("\nRecommendations:\n")
            for rec in report.recommendations:
                f.write(f"  - {rec}\n")
        return path


__all__ = ["Analyzer", "AnalysisReport", "CpuInfo", "BatteryInfo"]
