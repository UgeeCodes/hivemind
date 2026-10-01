"""
Tests for benchmark workload definitions, statistical functions, runner, and report generation.
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from hivemind.daemon.backends.base import BackendExecResult, IsolationBackend, SandboxConfig
from hivemind.benchmarks.workloads import DEFAULT_WORKLOADS, BenchmarkWorkload, WorkloadCategory
from hivemind.benchmarks.runner import (
    BenchmarkRunner,
    IterationMetric,
    WorkloadBenchmarkResult,
    compute_percentile,
    compute_stats,
)
from hivemind.benchmarks.report import generate_json_report, generate_markdown_report


class DummyBenchBackend(IsolationBackend):
    """Test backend with controllable execution results."""

    def __init__(self, name: str = "mock_bench", exit_code: int = 0):
        self._name = name
        self._exit_code = exit_code

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    async def provision(self, config: SandboxConfig):
        return None

    async def execute(self, command: str, request_id: str, config: SandboxConfig, on_stdout, on_stderr):
        await on_stdout("benchmark output")
        return BackendExecResult(exit_code=self._exit_code, duration_s=0.01, backend_name=self._name)

    async def teardown(self, sandbox_id: str):
        pass


class TestBenchmarkWorkloadCatalog(unittest.TestCase):
    """Verify standard benchmark workload catalog integrity."""

    def test_default_workloads_structure(self):
        self.assertGreater(len(DEFAULT_WORKLOADS), 0)
        workload_ids = set()
        categories_found = set()

        for w in DEFAULT_WORKLOADS:
            self.assertIsInstance(w, BenchmarkWorkload)
            self.assertNotIn(w.workload_id, workload_ids, "Duplicate workload_id: {}".format(w.workload_id))
            workload_ids.add(w.workload_id)
            categories_found.add(w.category)
            self.assertTrue(len(w.command) > 0)
            self.assertTrue(len(w.name) > 0)
            self.assertTrue(len(w.description) > 0)

        # Verify all 3 categories are represented
        expected_categories = {
            WorkloadCategory.MICRO,
            WorkloadCategory.IO,
            WorkloadCategory.COMPUTE,
        }
        self.assertEqual(categories_found, expected_categories)

    def test_workload_ids_have_bench_prefix(self):
        for w in DEFAULT_WORKLOADS:
            self.assertTrue(
                w.workload_id.startswith("BENCH-"),
                "Workload ID '{}' should start with 'BENCH-'".format(w.workload_id),
            )


class TestStatisticalFunctions(unittest.TestCase):
    """Verify percentile and stats calculations with known datasets."""

    def test_compute_percentile_single_value(self):
        self.assertAlmostEqual(compute_percentile([5.0], 50), 5.0)
        self.assertAlmostEqual(compute_percentile([5.0], 99), 5.0)

    def test_compute_percentile_known_dataset(self):
        # 10 values: 1..10
        values = [float(i) for i in range(1, 11)]
        p50 = compute_percentile(values, 50)
        # Median of 1..10 with linear interpolation = 5.5
        self.assertAlmostEqual(p50, 5.5, places=1)

        p90 = compute_percentile(values, 90)
        # P90 of 1..10 should be ~9.1
        self.assertGreater(p90, 8.0)
        self.assertLessEqual(p90, 10.0)

    def test_compute_percentile_empty(self):
        self.assertEqual(compute_percentile([], 50), 0.0)

    def test_compute_stats_known_values(self):
        metrics = [
            IterationMetric(iteration=i, provision_ms=1.0, exec_ms=float(i + 1),
                           teardown_ms=0.5, total_ms=float(i + 2.5),
                           exit_code=0, is_warmup=False)
            for i in range(5)
        ]
        stats = compute_stats(metrics)

        # Mean total: (2.5, 3.5, 4.5, 5.5, 6.5) => mean = 4.5
        self.assertAlmostEqual(stats["mean_total_ms"], 4.5, places=1)
        self.assertGreater(stats["std_dev_ms"], 0)
        self.assertAlmostEqual(stats["mean_provision_ms"], 1.0, places=1)
        self.assertAlmostEqual(stats["mean_teardown_ms"], 0.5, places=1)

    def test_compute_stats_empty(self):
        stats = compute_stats([])
        self.assertEqual(stats["mean_total_ms"], 0.0)
        self.assertEqual(stats["std_dev_ms"], 0.0)


class TestBenchmarkRunner(unittest.IsolatedAsyncioTestCase):
    """Verify benchmark runner execution and phase timing."""

    async def test_runner_collects_metrics(self):
        backend = DummyBenchBackend(name="test_backend")
        runner = BenchmarkRunner()

        workload = BenchmarkWorkload(
            workload_id="BENCH-TEST-01",
            category=WorkloadCategory.MICRO,
            name="Test Workload",
            description="Testing benchmark runner",
            command="/usr/bin/true",
        )

        result = await runner.run_workload(workload, backend, iterations=5, warmup=1)

        self.assertEqual(result.workload_id, "BENCH-TEST-01")
        self.assertEqual(result.backend, "test_backend")
        self.assertEqual(result.total_iterations, 5)
        self.assertEqual(result.warmup_iterations, 1)
        self.assertEqual(len(result.metrics), 5)

        # First metric should be warmup
        self.assertTrue(result.metrics[0].is_warmup)
        # Second metric onwards should not be warmup
        self.assertFalse(result.metrics[1].is_warmup)

        # Cold measurement should be > 0
        self.assertGreaterEqual(result.cold_total_ms, 0)

        # All timing values should be non-negative
        self.assertGreaterEqual(result.mean_total_ms, 0)
        self.assertGreaterEqual(result.p50_total_ms, 0)
        self.assertGreaterEqual(result.p90_total_ms, 0)

    async def test_runner_suite_runs_all_workloads(self):
        backend = DummyBenchBackend(name="suite_backend")
        runner = BenchmarkRunner()

        results = await runner.run_suite(backend, iterations=4, warmup=1)
        self.assertEqual(len(results), len(DEFAULT_WORKLOADS))

        for r in results:
            self.assertEqual(r.backend, "suite_backend")
            self.assertEqual(r.total_iterations, 4)


class TestBenchmarkReports(unittest.TestCase):
    """Verify Markdown and JSON report generation."""

    def _make_sample_result(self, backend: str) -> WorkloadBenchmarkResult:
        return WorkloadBenchmarkResult(
            workload_id="BENCH-NOOP",
            workload_name="No-Op Floor",
            category="micro",
            backend=backend,
            total_iterations=10,
            warmup_iterations=2,
            metrics=[],
            cold_total_ms=5.2,
            cold_provision_ms=1.0,
            cold_exec_ms=3.8,
            cold_teardown_ms=0.4,
            p50_total_ms=3.1,
            p90_total_ms=4.5,
            p99_total_ms=5.0,
            mean_total_ms=3.3,
            std_dev_ms=0.7,
            min_total_ms=2.8,
            max_total_ms=5.2,
            mean_provision_ms=0.8,
            mean_exec_ms=2.1,
            mean_teardown_ms=0.4,
        )

    def test_markdown_report_structure(self):
        results_by_backend = {
            "seatbelt": [self._make_sample_result("seatbelt")],
        }
        md = generate_markdown_report(results_by_backend)

        self.assertIn("Hivemind Performance Benchmark Scorecard", md)
        self.assertIn("No-Op Floor", md)
        self.assertIn("Phase Breakdown", md)
        self.assertIn("Seatbelt", md)

    def test_markdown_report_multi_backend(self):
        results_by_backend = {
            "seatbelt": [self._make_sample_result("seatbelt")],
            "tart": [self._make_sample_result("tart")],
        }
        md = generate_markdown_report(results_by_backend)

        self.assertIn("Seatbelt", md)
        self.assertIn("Tart", md)

    def test_json_report_structure(self):
        results_by_backend = {
            "seatbelt": [self._make_sample_result("seatbelt")],
        }
        json_data = generate_json_report(results_by_backend)

        self.assertIn("backends", json_data)
        self.assertIn("seatbelt", json_data["backends"])
        seatbelt = json_data["backends"]["seatbelt"]
        self.assertEqual(seatbelt["total_workloads"], 1)
        self.assertEqual(len(seatbelt["workloads"]), 1)

        workload = seatbelt["workloads"][0]
        self.assertEqual(workload["workload_id"], "BENCH-NOOP")
        self.assertIn("cold", workload)
        self.assertIn("warm_stats", workload)
        self.assertAlmostEqual(workload["cold"]["total_ms"], 5.2)
        self.assertAlmostEqual(workload["warm_stats"]["p50_total_ms"], 3.1)

    def test_empty_report(self):
        md = generate_markdown_report({})
        self.assertIn("No backends evaluated", md)


if __name__ == "__main__":
    unittest.main()
