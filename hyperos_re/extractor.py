#!/usr/bin/env python3
"""
extractor.py — APK / framework extraction for HyperOS RE (on-device, uid 2000).

Strategy (no root, cannot read /data/app or /system/framework directly):
  1. pm path <pkg>  -> package code path (base + split config.* APKs)
  2. Shizuku cat    -> stream the APK bytes to /data/local/tmp/hyperos_re/apks/
  3. For framework: read /apex/com.android.runtime/javalib/ or use
     dalvikvm -cp trick to load framework classes.

Output: per-package directory under apks/<pkg>/ with base.apk + splits.
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from device_interface import DeviceInterface, CmdResult


@dataclass
class ExtractedApk:
    package: str
    split: str            # "base" or "config.xx" etc.
    remote_path: str
    local_path: str
    size: int = 0


@dataclass
class ExtractionResult:
    package: str
    apks: list[ExtractedApk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Extractor:
    def __init__(self, iface: DeviceInterface, apks_dir: str):
        self.iface = iface
        self.apks_dir = apks_dir
        os.makedirs(self.apks_dir, exist_ok=True)

    async def extract_package(self, package: str) -> ExtractionResult:
        res = ExtractionResult(package=package)
        path_res = await self.iface.pm_path(package)
        if path_res.rc != 0 or not path_res.stdout.strip():
            res.errors.append(f"pm path failed: {path_res.stderr.strip()}")
            return res

        # pm path may return multiple lines (base + splits)
        for line in path_res.stdout.strip().splitlines():
            line = line.strip()
            if not line or ": " not in line:
                continue
            _, apk_path = line.split(": ", 1)
            apk_path = apk_path.strip()
            split = self._split_name(apk_path)
            local = os.path.join(self.apks_dir, package, split + ".apk")
            os.makedirs(os.path.dirname(local), exist_ok=True)

            # stream bytes via Shizuku cat
            cat_res = await self.iface.cat(apk_path)
            if cat_res.rc != 0:
                res.errors.append(f"cat {apk_path}: {cat_res.stderr.strip()}")
                continue
            # cat returns text; APKs are binary. Shizuku cat of binary may corrupt.
            # Prefer `dd` if available, otherwise cat and warn.
            dd_res = await self.iface.run(f"dd if={shlex_q(apk_path)} of={local} bs=1M")
            if dd_res.rc == 0:
                size = os.path.getsize(local) if os.path.exists(local) else 0
                res.apks.append(
                    ExtractedApk(
                        package=package,
                        split=split,
                        remote_path=apk_path,
                        local_path=local,
                        size=size,
                    )
                )
            else:
                res.errors.append(f"dd {apk_path}->{local}: {dd_res.stderr.strip()}")
        return res

    async def extract_framework(self) -> CmdResult:
        """Attempt to read framework jars from APEX (readable, uid 2000)."""
        return await self.iface.run(
            "ls /apex/com.android.runtime/javalib/ 2>/dev/null || "
            "ls /system/framework 2>/dev/null || echo 'framework not directly readable'"
        )

    def _split_name(self, apk_path: str) -> str:
        base = os.path.basename(apk_path)
        if base == "base.apk":
            return "base"
        m = re.search(r"config\.(.+?)\.apk$", base)
        if m:
            return "config_" + m.group(1).replace(".", "_")
        return base.replace(".apk", "")


def shlex_q(s: str) -> str:
    import shlex
    return shlex.quote(s)


__all__ = ["Extractor", "ExtractionResult", "ExtractedApk"]
