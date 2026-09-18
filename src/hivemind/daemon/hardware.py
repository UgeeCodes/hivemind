"""
Hardware and resource introspection for macOS.

Extracts Apple Silicon chip specifications, core counts, RAM capacity,
and live CPU and memory utilization without external dependencies.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HardwareSpecs:
    """Hardware profile and live resource usage for a Mac machine."""
    chip: str
    cpu_cores: int
    ram_gb: int
    cpu_percent: float
    memory_percent: float


def get_chip_name() -> str:
    """Retrieve the Apple Silicon or CPU model name (e.g. 'Apple M4 Pro', 'Apple M3')."""
    if platform.system() == "Darwin":
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            if out:
                return out
        except Exception:
            pass
    return platform.processor() or "Apple Silicon"


def get_total_ram_gb() -> int:
    """Get total unified memory/RAM in GB rounded to the nearest integer."""
    if platform.system() == "Darwin":
        try:
            mem_bytes = int(
                subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    stderr=subprocess.DEVNULL
                ).decode().strip()
            )
            return round(mem_bytes / (1024 ** 3))
        except Exception:
            pass
    return 16


def get_cpu_cores() -> int:
    """Get logical CPU core count."""
    return os.cpu_count() or 8


def get_cpu_utilization() -> float:
    """Estimate live CPU utilization percent using 1-minute system load average."""
    cores = get_cpu_cores()
    try:
        load1 = os.getloadavg()[0]
        return min(100.0, round((load1 / cores) * 100.0, 1))
    except Exception:
        return 0.0


def get_memory_utilization() -> float:
    """
    Calculate accurate macOS memory usage percentage:
    (wired + active + compressed) / total_memory
    matching macOS Activity Monitor.
    """
    if platform.system() != "Darwin":
        return 50.0

    try:
        mem_bytes = int(
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
        out = subprocess.check_output(["vm_stat"], stderr=subprocess.DEVNULL).decode()
        page_size = 4096
        stats = {}
        for line in out.splitlines():
            if "page size of" in line:
                try:
                    page_size = int(line.split("page size of")[1].split("bytes")[0].strip())
                except Exception:
                    page_size = 4096
            elif ":" in line:
                k, v = line.split(":", 1)
                num = v.strip().rstrip(".")
                if num.isdigit():
                    stats[k.strip()] = int(num) * page_size

        wired = stats.get("Pages wired down", 0)
        active = stats.get("Pages active", 0)
        compressed = stats.get("Pages occupied by compressor", 0)
        used = wired + active + compressed

        if mem_bytes > 0:
            return round((used / mem_bytes) * 100.0, 1)
    except Exception as e:
        logger.debug("Failed to calculate macOS memory utilization: %s", e)

    return 50.0


def get_hardware_specs() -> HardwareSpecs:
    """Retrieve complete hardware profile and live resource usage."""
    return HardwareSpecs(
        chip=get_chip_name(),
        cpu_cores=get_cpu_cores(),
        ram_gb=get_total_ram_gb(),
        cpu_percent=get_cpu_utilization(),
        memory_percent=get_memory_utilization(),
    )
