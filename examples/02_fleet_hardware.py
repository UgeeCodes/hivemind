#!/usr/bin/env python3
"""Fleet Hardware Inspection — query machines and route by load.

Prerequisites:
    1. Control plane running:  hivemind serve
    2. At least one daemon:    hivemind child start
"""
from __future__ import annotations

import hivemind


def inspect_fleet() -> None:
    """List every online Mac with hardware telemetry."""
    macs = hivemind.fleet()

    print(f"=== Fleet: {len(macs)} machine(s) online ===\n")
    for m in macs:
        print(f"  {m.hostname} ({m.machine_id})")
        print(f"    Chip:   {m.chip or 'unknown'}")
        print(f"    Cores:  {m.cpu_cores or '?'}")
        print(f"    RAM:    {m.ram_gb or '?'} GB")
        print(f"    CPU:    {m.cpu_percent:.0f}%" if m.cpu_percent is not None else "    CPU:    —")
        print(f"    Memory: {m.memory_percent:.0f}%" if m.memory_percent is not None else "    Memory: —")
        print(f"    Tags:   {', '.join(m.tags) if m.tags else '—'}")
        print()


def route_to_idlest() -> None:
    """Pick the machine with the lowest CPU load and run a task on it."""
    macs = hivemind.fleet()
    if not macs:
        print("No machines online.")
        return

    idlest = min(macs, key=lambda m: m.cpu_percent or 0.0)
    print(f"=== Routing to idlest: {idlest.hostname} ({idlest.cpu_percent:.0f}% CPU) ===\n")

    mac = hivemind.mac(machine_id=idlest.machine_id)
    result = mac.run("sysctl -n hw.ncpu && sysctl -n hw.memsize")
    print(f"  {result.stdout.strip()}")
    print()


if __name__ == "__main__":
    inspect_fleet()
    route_to_idlest()
