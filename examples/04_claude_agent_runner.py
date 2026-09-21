#!/usr/bin/env python3
"""Claude Agent Runner — dispatch AI agents to remote Macs via proxy.

This example shows how to run an AI coding agent (Claude or Codex)
on a remote Mac without exposing API keys. Model API calls route
through a proxy so credentials never touch the Mac.

Prerequisites:
    1. Control plane running:  hivemind serve
    2. At least one daemon:    hivemind child start
    3. Agent CLI installed on the target Mac (e.g. `claude` or `codex`)
    4. A proxy URL for model API calls
"""
from __future__ import annotations

from hivemind.agent import run_agent, run_agent_on_fleet


def single_agent() -> None:
    """Run a Claude agent on a single Mac."""
    print("=== Single Agent Dispatch ===\n")

    result = run_agent(
        prompt="List all Python files in the current directory and summarize them",
        harness="claude",
        proxy="https://proxy.example.com",  # replace with your proxy
        stream=True,
    )

    print(f"\n  exit_code: {result.exit_code}")
    print(f"  duration:  {result.duration_s:.1f}s")
    print()


def fleet_agent() -> None:
    """Run an agent on every Mac in the fleet."""
    print("=== Fleet-Wide Agent Dispatch ===\n")

    results = run_agent_on_fleet(
        prompt="Report the macOS version and available disk space",
        harness="claude",
        proxy="https://proxy.example.com",  # replace with your proxy
    )

    for machine_id, result in results.items():
        status = "ok" if result.exit_code == 0 else "FAILED"
        print(f"  [{machine_id}] {status} — exit {result.exit_code}")
    print()


def scoped_agent() -> None:
    """Run an agent with a direct API token (no proxy)."""
    print("=== Agent with Direct Token ===\n")

    result = run_agent(
        prompt="echo hello from agent",
        harness="claude",
        token="sk-ant-...",  # replace with your Anthropic key
        sandbox=True,        # run inside an isolated sandbox
        stream=True,
    )

    print(f"\n  exit_code: {result.exit_code}")
    print()


if __name__ == "__main__":
    # Uncomment the example you want to run:
    # single_agent()
    # fleet_agent()
    # scoped_agent()
    print("Uncomment one of the functions in __main__ to run an example.")
    print("Make sure to replace proxy URLs and tokens with real values.")
