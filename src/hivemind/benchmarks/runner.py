"""
Phase-aware benchmark runner for profiling isolation backend performance.

Decomposes execution into discrete provision, execute, and teardown phases
with high-resolution timing via time.perf_counter(). Supports warm-up
iterations and cold vs. warm statistical separation.
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from hivemind.daemon.backends.base import IsolationBackend, SandboxConfig
from hivemind.benchmarks.workloads import DEFAULT_WORKLOADS, BenchmarkWorkload


@dataclass
class IterationMetric:
    """Timing results for a single benchmark iteration."""
    iteration: int
    provision_ms: float
    exec_ms: float
    teardown_ms: float
    total_ms: float
    exit_code: int
    is_warmup: bool


@dataclass
class WorkloadBenchmarkResult:
    """Aggregated benchmark result for a workload across all iterations."""
    workload_id: str
    workload_name: str
    category: str
    backend: str
    total_iterations: int
    warmup_iterations: int
    metrics: List[IterationMetric]
    # Cold measurement (first non-warmup iteration)
    cold_total_ms: float
    cold_provision_ms: float
    cold_exec_ms: float
    cold_teardown_ms: float
    # Warm statistics (excluding warmup and cold)
    p50_total_ms: float
    p90_total_ms: float
    p99_total_ms: float
    mean_total_ms: float
    std_dev_ms: float
    min_total_ms: float
    max_total_ms: float
    mean_provision_ms: float
    mean_exec_ms: float
    mean_teardown_ms: float


def compute_percentile(values: List[float], percentile: float) -> float:
    """Compute a given percentile using linear interpolation.

    Args:
        values: List of numeric values (will be sorted internally).
        percentile: Percentile to compute (0-100).

    Returns:
        The interpolated percentile value.
    """
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 1:
        return sorted_v[0]
    # Linear interpolation index
    k = (percentile / 100.0) * (n - 1)
    f = math.floor(k)
    c = min(f + 1, n - 1)
    if f == c:
        return sorted_v[int(f)]
    d = k - f
    return sorted_v[int(f)] * (1 - d) + sorted_v[int(c)] * d


def compute_stats(metrics: List[IterationMetric]) -> dict:
    """Compute statistical summaries from a list of iteration metrics.

    Args:
        metrics: List of IterationMetric (should exclude warm-up iterations).

    Returns:
        Dictionary with mean, std_dev, p50, p90, p95, p99, min, max for
        total, provision, exec, and teardown phases.
    """
    if not metrics:
        return {
            "mean_total_ms": 0.0, "std_dev_ms": 0.0,
            "p50_total_ms": 0.0, "p90_total_ms": 0.0,
            "p99_total_ms": 0.0, "min_total_ms": 0.0, "max_total_ms": 0.0,
            "mean_provision_ms": 0.0, "mean_exec_ms": 0.0,
            "mean_teardown_ms": 0.0,
        }

    totals = [m.total_ms for m in metrics]
    provisions = [m.provision_ms for m in metrics]
    execs = [m.exec_ms for m in metrics]
    teardowns = [m.teardown_ms for m in metrics]

    n = len(totals)
    mean_total = sum(totals) / n

    if n > 1:
        variance = sum((x - mean_total) ** 2 for x in totals) / (n - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    return {
        "mean_total_ms": round(mean_total, 3),
        "std_dev_ms": round(std_dev, 3),
        "p50_total_ms": round(compute_percentile(totals, 50), 3),
        "p90_total_ms": round(compute_percentile(totals, 90), 3),
        "p99_total_ms": round(compute_percentile(totals, 99), 3),
        "min_total_ms": round(min(totals), 3),
        "max_total_ms": round(max(totals), 3),
        "mean_provision_ms": round(sum(provisions) / n, 3),
        "mean_exec_ms": round(sum(execs) / n, 3),
        "mean_teardown_ms": round(sum(teardowns) / n, 3),
    }


class BenchmarkRunner:
    """Executes benchmark workloads with phase-aware timing against isolation backends."""

    async def run_workload(
        self,
        workload: BenchmarkWorkload,
        backend: IsolationBackend,
        iterations: int = 10,
        warmup: int = 2,
    ) -> WorkloadBenchmarkResult:
        """Execute a single workload for N iterations with W warm-up runs.

        Args:
            workload: The benchmark workload to execute.
            backend: The isolation backend to profile.
            iterations: Total iterations to run (including warm-up).
            warmup: Number of initial warm-up iterations (discarded from stats).

        Returns:
            WorkloadBenchmarkResult with phase breakdown and statistics.
        """
        all_metrics: List[IterationMetric] = []

        for i in range(iterations):
            is_warmup = i < warmup
            sandbox_id = "sbx_bench_{hex}".format(hex=uuid.uuid4().hex[:10])
            config = SandboxConfig(
                sandbox_id=sandbox_id,
                allow_network=True,
            )

            stdout_chunks: List[str] = []
            stderr_chunks: List[str] = []

            async def on_stdout(chunk: str) -> None:
                stdout_chunks.append(chunk)

            async def on_stderr(chunk: str) -> None:
                stderr_chunks.append(chunk)

            # Phase 1: Provision
            t_prov_start = time.perf_counter()
            try:
                await backend.provision(config)
            except Exception:
                pass
            t_prov_end = time.perf_counter()

            # Phase 2: Execute
            t_exec_start = time.perf_counter()
            try:
                exec_result = await backend.execute(
                    command=workload.command,
                    request_id="req_{hex}".format(hex=uuid.uuid4().hex[:8]),
                    config=config,
                    on_stdout=on_stdout,
                    on_stderr=on_stderr,
                )
                exit_code = exec_result.exit_code
            except Exception:
                exit_code = -1
            t_exec_end = time.perf_counter()

            # Phase 3: Teardown
            t_tear_start = time.perf_counter()
            try:
                await backend.teardown(sandbox_id)
            except Exception:
                pass
            t_tear_end = time.perf_counter()

            provision_ms = (t_prov_end - t_prov_start) * 1000
            exec_ms = (t_exec_end - t_exec_start) * 1000
            teardown_ms = (t_tear_end - t_tear_start) * 1000
            total_ms = provision_ms + exec_ms + teardown_ms

            metric = IterationMetric(
                iteration=i,
                provision_ms=round(provision_ms, 3),
                exec_ms=round(exec_ms, 3),
                teardown_ms=round(teardown_ms, 3),
                total_ms=round(total_ms, 3),
                exit_code=exit_code,
                is_warmup=is_warmup,
            )
            all_metrics.append(metric)

        # Separate metrics
        measured_metrics = [m for m in all_metrics if not m.is_warmup]

        # Cold = first non-warmup iteration
        cold_metric = measured_metrics[0] if measured_metrics else None

        # Warm = all non-warmup iterations after the cold one
        warm_metrics = measured_metrics[1:] if len(measured_metrics) > 1 else measured_metrics

        stats = compute_stats(warm_metrics)

        return WorkloadBenchmarkResult(
            workload_id=workload.workload_id,
            workload_name=workload.name,
            category=workload.category.value if hasattr(workload.category, "value") else str(workload.category),
            backend=backend.name,
            total_iterations=iterations,
            warmup_iterations=warmup,
            metrics=all_metrics,
            cold_total_ms=round(cold_metric.total_ms, 3) if cold_metric else 0.0,
            cold_provision_ms=round(cold_metric.provision_ms, 3) if cold_metric else 0.0,
            cold_exec_ms=round(cold_metric.exec_ms, 3) if cold_metric else 0.0,
            cold_teardown_ms=round(cold_metric.teardown_ms, 3) if cold_metric else 0.0,
            p50_total_ms=stats["p50_total_ms"],
            p90_total_ms=stats["p90_total_ms"],
            p99_total_ms=stats["p99_total_ms"],
            mean_total_ms=stats["mean_total_ms"],
            std_dev_ms=stats["std_dev_ms"],
            min_total_ms=stats["min_total_ms"],
            max_total_ms=stats["max_total_ms"],
            mean_provision_ms=stats["mean_provision_ms"],
            mean_exec_ms=stats["mean_exec_ms"],
            mean_teardown_ms=stats["mean_teardown_ms"],
        )

    async def run_suite(
        self,
        backend: IsolationBackend,
        workloads: Optional[List[BenchmarkWorkload]] = None,
        iterations: int = 10,
        warmup: int = 2,
    ) -> List[WorkloadBenchmarkResult]:
        """Execute all benchmark workloads sequentially against a backend.

        Args:
            backend: The isolation backend to profile.
            workloads: List of workloads (defaults to DEFAULT_WORKLOADS).
            iterations: Total iterations per workload.
            warmup: Warm-up iterations per workload.

        Returns:
            List of WorkloadBenchmarkResult, one per workload.
        """
        workload_list = workloads or DEFAULT_WORKLOADS
        results: List[WorkloadBenchmarkResult] = []
        for w in workload_list:
            res = await self.run_workload(w, backend, iterations, warmup)
            results.append(res)
        return results
