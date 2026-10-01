"""
Scorecard and reporting utilities for benchmark workload evaluations.

Generates publication-ready Markdown comparison tables with phase breakdowns
and structured JSON datasets for automated plotting and figure generation.
"""
from __future__ import annotations

from typing import Any, Dict, List

from hivemind.benchmarks.runner import WorkloadBenchmarkResult


def generate_markdown_report(results_by_backend: Dict[str, List[WorkloadBenchmarkResult]]) -> str:
    """Generate a publication-ready Markdown benchmark comparison table.

    Args:
        results_by_backend: Mapping of backend name to list of benchmark results.

    Returns:
        Formatted Markdown string with phase breakdown and statistics.
    """
    backends = list(results_by_backend.keys())
    if not backends:
        return "# Hivemind Performance Benchmark Report\n\nNo backends evaluated.\n"

    # Index results by workload_id
    workload_map: Dict[str, Dict[str, WorkloadBenchmarkResult]] = {}
    for b_name, res_list in results_by_backend.items():
        for r in res_list:
            if r.workload_id not in workload_map:
                workload_map[r.workload_id] = {}
            workload_map[r.workload_id][b_name] = r

    lines = [
        "# Hivemind Performance Benchmark Scorecard",
        "",
        "Empirical phase-aware latency profiling comparing Apple Seatbelt OS sandboxing vs. Tart MicroVMs.",
        "",
    ]

    # Summary table
    header_cols = ["Workload", "Category"]
    for b in backends:
        header_cols.extend([
            "{b} Cold (ms)".format(b=b.capitalize()),
            "{b} P50 (ms)".format(b=b.capitalize()),
            "{b} P90 (ms)".format(b=b.capitalize()),
            "{b} Mean (ms)".format(b=b.capitalize()),
        ])
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cols)) + " |")

    for wid, b_results in workload_map.items():
        first_r = next(iter(b_results.values()))
        row = [first_r.workload_name, first_r.category]
        for b in backends:
            r = b_results.get(b)
            if r is None:
                row.extend(["—", "—", "—", "—"])
            else:
                row.extend([
                    "{val:.1f}".format(val=r.cold_total_ms),
                    "{val:.1f}".format(val=r.p50_total_ms),
                    "{val:.1f}".format(val=r.p90_total_ms),
                    "{val:.1f}".format(val=r.mean_total_ms),
                ])
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Phase breakdown detail
    lines.append("## Phase Breakdown (Warm Averages)")
    lines.append("")

    detail_cols = ["Workload"]
    for b in backends:
        detail_cols.extend([
            "{b} Provision".format(b=b.capitalize()),
            "{b} Execute".format(b=b.capitalize()),
            "{b} Teardown".format(b=b.capitalize()),
            "{b} Std Dev".format(b=b.capitalize()),
        ])
    lines.append("| " + " | ".join(detail_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(detail_cols)) + " |")

    for wid, b_results in workload_map.items():
        first_r = next(iter(b_results.values()))
        row = [first_r.workload_name]
        for b in backends:
            r = b_results.get(b)
            if r is None:
                row.extend(["—", "—", "—", "—"])
            else:
                row.extend([
                    "{val:.2f}ms".format(val=r.mean_provision_ms),
                    "{val:.2f}ms".format(val=r.mean_exec_ms),
                    "{val:.2f}ms".format(val=r.mean_teardown_ms),
                    "±{val:.2f}ms".format(val=r.std_dev_ms),
                ])
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")

    # Configuration note
    if backends:
        sample_r = next(iter(next(iter(results_by_backend.values()))))
        lines.append("*{total} iterations, {warmup} warm-up, measured on host.*".format(
            total=sample_r.total_iterations,
            warmup=sample_r.warmup_iterations,
        ))
        lines.append("")

    return "\n".join(lines)


def generate_json_report(results_by_backend: Dict[str, List[WorkloadBenchmarkResult]]) -> Dict[str, Any]:
    """Generate a structured dictionary/JSON dataset for statistical analysis and plotting.

    Args:
        results_by_backend: Mapping of backend name to list of benchmark results.

    Returns:
        Structured dictionary suitable for JSON serialization.
    """
    data: Dict[str, Any] = {
        "benchmark": "hivemind_workload_benchmark_suite",
        "backends": {},
    }

    for b_name, res_list in results_by_backend.items():
        data["backends"][b_name] = {
            "total_workloads": len(res_list),
            "workloads": [
                {
                    "workload_id": r.workload_id,
                    "workload_name": r.workload_name,
                    "category": r.category,
                    "total_iterations": r.total_iterations,
                    "warmup_iterations": r.warmup_iterations,
                    "cold": {
                        "total_ms": r.cold_total_ms,
                        "provision_ms": r.cold_provision_ms,
                        "exec_ms": r.cold_exec_ms,
                        "teardown_ms": r.cold_teardown_ms,
                    },
                    "warm_stats": {
                        "mean_total_ms": r.mean_total_ms,
                        "p50_total_ms": r.p50_total_ms,
                        "p90_total_ms": r.p90_total_ms,
                        "p99_total_ms": r.p99_total_ms,
                        "std_dev_ms": r.std_dev_ms,
                        "min_total_ms": r.min_total_ms,
                        "max_total_ms": r.max_total_ms,
                        "mean_provision_ms": r.mean_provision_ms,
                        "mean_exec_ms": r.mean_exec_ms,
                        "mean_teardown_ms": r.mean_teardown_ms,
                    },
                    "all_iterations": [
                        {
                            "iteration": m.iteration,
                            "provision_ms": m.provision_ms,
                            "exec_ms": m.exec_ms,
                            "teardown_ms": m.teardown_ms,
                            "total_ms": m.total_ms,
                            "exit_code": m.exit_code,
                            "is_warmup": m.is_warmup,
                        }
                        for m in r.metrics
                    ],
                }
                for r in res_list
            ],
        }

    return data
