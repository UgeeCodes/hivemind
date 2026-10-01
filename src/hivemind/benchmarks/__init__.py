"""
Workload benchmark definitions for empirical performance profiling.

Provides standardized benchmark workloads, phase-aware timing harnesses,
and statistical scorecard generators to compare execution performance
between Seatbelt (OS sandboxing) and Tart (Apple Virtualization microVMs).
"""
from __future__ import annotations

from hivemind.benchmarks.workloads import (
    BenchmarkWorkload,
    DEFAULT_WORKLOADS,
    WorkloadCategory,
)
from hivemind.benchmarks.runner import (
    BenchmarkRunner,
    IterationMetric,
    WorkloadBenchmarkResult,
)
from hivemind.benchmarks.report import (
    generate_json_report,
    generate_markdown_report,
)

__all__ = [
    "BenchmarkWorkload",
    "BenchmarkRunner",
    "DEFAULT_WORKLOADS",
    "IterationMetric",
    "WorkloadBenchmarkResult",
    "WorkloadCategory",
    "generate_json_report",
    "generate_markdown_report",
]
