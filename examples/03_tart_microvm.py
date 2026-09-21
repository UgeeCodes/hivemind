#!/usr/bin/env python3
"""Tart MicroVM Execution — run commands in ephemeral Apple Virtualization VMs.

Prerequisites:
    1. Control plane running:  hivemind serve
    2. At least one daemon:    hivemind child start
    3. Tart installed:         brew install cirruslabs/cli/tart
    4. A base image pulled:    tart clone ghcr.io/cirruslabs/macos-sequoia-base:latest sequoia-base

If Tart is not installed, Hivemind falls back to Seatbelt isolation
automatically with a notice on stderr.
"""
from __future__ import annotations

import sys

import hivemind


def run_in_tart() -> None:
    """Execute a command inside a Tart microVM."""
    mac = hivemind.mac()

    print("=== Tart MicroVM Execution ===\n")
    result = mac.run("sw_vers && echo 'Hello from microVM'", backend="tart")

    print(f"  stdout:    {result.stdout.strip()}")
    if result.stderr:
        # Fallback notice appears here if Tart is unavailable
        print(f"  stderr:    {result.stderr.strip()}", file=sys.stderr)
    print(f"  exit_code: {result.exit_code}")
    print(f"  duration:  {result.duration_s:.3f}s")
    print()


def tart_vs_seatbelt() -> None:
    """Compare execution in Tart vs Seatbelt backends."""
    mac = hivemind.mac()

    print("=== Backend Comparison ===\n")
    for backend in ("seatbelt", "tart"):
        result = mac.run("echo 'running' && uname -m", backend=backend)
        status = "ok" if result.exit_code == 0 else "failed"
        print(f"  [{backend:>8}] {status} in {result.duration_s:.3f}s")
    print()


if __name__ == "__main__":
    run_in_tart()
    tart_vs_seatbelt()
