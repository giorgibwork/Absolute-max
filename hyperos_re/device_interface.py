#!/usr/bin/env python3
"""
device_interface.py — Shizuku / ladb command wrapper for HyperOS RE toolkit.
Runs on-device (Termux). Every shell call is prefixed with the configured
command prefix (ladb shell from PC, or shizuku -c on-device).

uid 2000 (shell), NO ROOT. Elevated only via Shizuku app-ops elevation.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CmdResult:
    rc: int
    stdout: str
    stderr: str
    duration_ms: float
    cmd: str


class DeviceInterface:
    def __init__(
        self,
        prefix: Optional[str] = None,
        timeout_s: int = 30,
        retries: int = 3,
        workdir: str = "/data/local/tmp/hyperos_re",
    ):
        self.prefix = prefix or os.environ.get(
            "HYPEROS_RE_CMD_PREFIX", "shizuku -c"
        )
        self.timeout_s = timeout_s
        self.retries = retries
        self.workdir = workdir
        os.makedirs(self.workdir, exist_ok=True)

    async def run(
        self,
        command: str,
        *,
        timeout_s: Optional[int] = None,
        retries: Optional[int] = None,
        check: bool = False,
    ) -> CmdResult:
        """Run one shell command through the Shizuku/ladb prefix."""
        full = f"{self.prefix} {command}"
        timeout = timeout_s or self.timeout_s
        tries = retries if retries is not None else self.retries
        last: Optional[CmdResult] = None

        for attempt in range(1, tries + 1):
            start = time.monotonic()
            try:
                proc = await asyncio.create_subprocess_shell(
                    full,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                rc = proc.returncode if proc.returncode is not None else -1
                result = CmdResult(
                    rc=rc,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    duration_ms=(time.monotonic() - start) * 1000,
                    cmd=full,
                )
            except asyncio.TimeoutError:
                result = CmdResult(
                    rc=-1,
                    stdout="",
                    stderr=f"timeout after {timeout}s",
                    duration_ms=(time.monotonic() - start) * 1000,
                    cmd=full,
                )
            last = result
            if result.rc == 0:
                return result
            if attempt < tries:
                await asyncio.sleep(0.5 * attempt)
        if check and last is not None and last.rc != 0:
            raise RuntimeError(
                f"command failed after {tries} tries: {last.cmd}\n"
                f"rc={last.rc}\nstderr={last.stderr}"
            )
        return last  # type: ignore[return-value]

    async def run_many(self, commands: list[str], concurrency: int = 4) -> list[CmdResult]:
        sem = asyncio.Semaphore(concurrency)

        async def one(cmd: str) -> CmdResult:
            async with sem:
                return await self.run(cmd)

        return await asyncio.gather(*(one(c) for c in commands))

    def run_sync(self, command: str, **kwargs) -> CmdResult:
        return asyncio.get_event_loop().run_until_complete(self.run(command, **kwargs))

    # ---------------- device info helpers ----------------

    async def prop(self, name: str) -> CmdResult:
        return await self.run(f"getprop {name}")

    async def setprop(self, name: str, value: str) -> CmdResult:
        return await self.run(f"setprop {name} {value}")

    async def shell(self, command: str, **kwargs) -> CmdResult:
        return await self.run(command, **kwargs)

    async def pm_path(self, package: str) -> CmdResult:
        return await self.run(f"pm path {package}")

    async def dumpsys(self, service: str) -> CmdResult:
        return await self.run(f"dumpsys {service}")

    async def cmd(self, service: str, *args: str) -> CmdResult:
        return await self.run(f"cmd {service} {' '.join(args)}")

    async def cat(self, path: str) -> CmdResult:
        return await self.run(f"cat {shlex.quote(path)}")

    async def ls(self, path: str) -> CmdResult:
        return await self.run(f"ls -la {shlex.quote(path)}")

    async def whoami(self) -> CmdResult:
        return await self.run("id")

    async def uname(self) -> CmdResult:
        return await self.run("uname -a")


__all__ = ["DeviceInterface", "CmdResult"]
