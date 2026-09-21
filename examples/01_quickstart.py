#!/usr/bin/env python3
"""Hivemind Quickstart — basic execution, streaming, and sandboxes.

Prerequisites:
    1. Control plane running:  hivemind serve
    2. At least one daemon:    hivemind child start
"""
from __future__ import annotations

import hivemind


def basic_run() -> None:
    """Run a simple command and inspect the result."""
    mac = hivemind.mac()
    result = mac.run("sw_vers")

    print("=== Basic Run ===")
    print(f"stdout:      {result.stdout.strip()}")
    print(f"exit_code:   {result.exit_code}")
    print(f"duration_s:  {result.duration_s:.3f}")
    print(f"job_id:      {result.job_id}")
    print(f"machine_id:  {result.machine_id}")
    print()


def streaming_output() -> None:
    """Stream output line-by-line as it arrives."""
    mac = hivemind.mac()

    print("=== Streaming Output ===")
    for stream_name, data in mac.stream("echo line1 && sleep 1 && echo line2"):
        prefix = "[out]" if stream_name == "stdout" else "[err]"
        print(f"  {prefix} {data}", end="")
    print()


def sandboxed_execution() -> None:
    """Execute a command inside an isolated sandbox."""
    mac = hivemind.mac()
    sbx = mac.sandbox()

    print("=== Sandboxed Execution ===")
    result = sbx.exec("echo 'running in sandbox' && pwd")
    print(f"  stdout: {result.stdout.strip()}")
    print(f"  exit:   {result.exit_code}")
    print()


def run_with_env() -> None:
    """Pass custom environment variables to a command."""
    mac = hivemind.mac()

    print("=== Custom Environment ===")
    result = mac.run(
        "echo Hello $GREETING from $LOCATION",
        env={"GREETING": "World", "LOCATION": "Hivemind"},
    )
    print(f"  {result.stdout.strip()}")
    print()


if __name__ == "__main__":
    basic_run()
    streaming_output()
    sandboxed_execution()
    run_with_env()
