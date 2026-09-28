"""
Tests for security threat model definitions, probe runner, and scorecard generation.
"""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from hivemind.daemon.backends.base import BackendExecResult, IsolationBackend, SandboxConfig
from hivemind.security.probes import DEFAULT_PROBES, ProbeCategory, SecurityProbe
from hivemind.security.runner import ProbeResult, SecurityProbeRunner
from hivemind.security.report import generate_json_report, generate_markdown_report


class DummyMockBackend(IsolationBackend):
    """Test backend with configurable containment responses."""

    def __init__(self, name: str = "mock_backend", simulate_contained: bool = True):
        self._name = name
        self.simulate_contained = simulate_contained
        self.provision_called = False
        self.teardown_called = False

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    async def provision(self, config: SandboxConfig):
        self.provision_called = True
        return None

    async def execute(self, command: str, request_id: str, config: SandboxConfig, on_stdout, on_stderr):
        exit_code = 1 if self.simulate_contained else 0
        if exit_code == 0:
            await on_stdout("sensitive data leaked")
        else:
            await on_stderr("Operation not permitted")
        return BackendExecResult(exit_code=exit_code, duration_s=0.01, backend_name=self._name)

    async def teardown(self, sandbox_id: str):
        self.teardown_called = True


class TestSecurityProbeCatalog(unittest.TestCase):
    """Verify standard probe catalog integrity."""

    def test_default_probes_structure(self):
        self.assertGreater(len(DEFAULT_PROBES), 0)
        probe_ids = set()

        categories_found = set()
        for p in DEFAULT_PROBES:
            self.assertIsInstance(p, SecurityProbe)
            self.assertNotIn(p.probe_id, probe_ids, f"Duplicate probe_id {p.probe_id}")
            probe_ids.add(p.probe_id)
            categories_found.add(p.category)
            self.assertTrue(len(p.command) > 0)
            self.assertTrue(len(p.name) > 0)

        # Verify all 5 categories are tested
        expected_categories = {
            ProbeCategory.CREDENTIAL_ISOLATION,
            ProbeCategory.FILESYSTEM_CONFINEMENT,
            ProbeCategory.PERSISTENCE_PREVENTION,
            ProbeCategory.NETWORK_CONFINEMENT,
            ProbeCategory.PROCESS_ISOLATION,
        }
        self.assertEqual(categories_found, expected_categories)


class TestSecurityRunnerAndReports(unittest.IsolatedAsyncioTestCase):
    """Verify probe execution, containment grading, and report generation."""

    async def test_runner_evaluates_contained(self):
        backend = DummyMockBackend(name="safe_backend", simulate_contained=True)
        runner = SecurityProbeRunner()

        test_probe = SecurityProbe(
            probe_id="PROBE-TEST-01",
            category=ProbeCategory.CREDENTIAL_ISOLATION,
            name="Test Probe",
            description="Testing containment evaluation",
            command="echo test",
        )

        result = await runner.run_probe(test_probe, backend)
        self.assertTrue(result.contained)
        self.assertEqual(result.exit_code, 1)
        self.assertTrue(backend.provision_called)
        self.assertTrue(backend.teardown_called)

    async def test_runner_evaluates_leaked(self):
        backend = DummyMockBackend(name="insecure_backend", simulate_contained=False)
        runner = SecurityProbeRunner()

        test_probe = SecurityProbe(
            probe_id="PROBE-TEST-02",
            category=ProbeCategory.FILESYSTEM_CONFINEMENT,
            name="Leak Test",
            description="Testing leak detection",
            command="echo leak",
        )

        result = await runner.run_probe(test_probe, backend)
        self.assertFalse(result.contained)
        self.assertEqual(result.exit_code, 0)

    async def test_report_generation(self):
        res1 = ProbeResult(
            probe_id="PROBE-1",
            probe_name="SSH Key Read",
            category="credential_isolation",
            backend="seatbelt",
            contained=True,
            exit_code=1,
            duration_ms=12.5,
            output="denied",
            description="SSH key read denied",
        )
        res2 = ProbeResult(
            probe_id="PROBE-1",
            probe_name="SSH Key Read",
            category="credential_isolation",
            backend="tart",
            contained=True,
            exit_code=1,
            duration_ms=850.0,
            output="file not found",
            description="SSH key read in VM",
        )

        results_by_backend = {
            "seatbelt": [res1],
            "tart": [res2],
        }

        # Test Markdown generation
        md = generate_markdown_report(results_by_backend)
        self.assertIn("Hivemind Security Isolation Benchmark Scorecard", md)
        self.assertIn("PROBE-1", md)
        self.assertIn("CONTAINED", md)

        # Test JSON generation
        json_data = generate_json_report(results_by_backend)
        self.assertIn("backends", json_data)
        self.assertIn("seatbelt", json_data["backends"])
        self.assertEqual(json_data["backends"]["seatbelt"]["contained"], 1)


class TestSecurityBackendGuards(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_unavailable_and_simulated_before_provision(self):
        for available, simulated in [(False, False), (False, True), (True, True)]:
            for entry_point in ('run_probe', 'run_suite'):
                with self.subTest(available=available, simulated=simulated, entry_point=entry_point):
                    backend = DummyMockBackend()
                    backend.is_available = lambda: available
                    backend.simulate = simulated
                    backend.provision = AsyncMock()
                    backend.execute = AsyncMock()
                    runner = SecurityProbeRunner()
                    with self.assertRaises(ValueError):
                        if entry_point == 'run_probe':
                            await runner.run_probe(DEFAULT_PROBES[0], backend)
                        else:
                            await runner.run_suite(backend)
                    backend.provision.assert_not_called()
                    backend.execute.assert_not_called()


class TestSecuritySkipCLI(unittest.TestCase):
    def test_all_skips_simulation_and_keeps_json_parseable(self):
        import json
        from unittest.mock import patch
        from typer.testing import CliRunner
        from hivemind.cli.main import app

        import inspect
        runner_options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
        seatbelt = DummyMockBackend('seatbelt')
        tart = DummyMockBackend('tart')
        tart.simulate = True
        tart.provision = AsyncMock()
        with patch('hivemind.daemon.backends.get_backend', side_effect=[seatbelt, tart]):
            result = CliRunner(**runner_options).invoke(app, ['security', 'run', '--backend', 'all', '--json'])
        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(result.stdout)
        self.assertEqual(list(report['backends']), ['seatbelt'])
        self.assertEqual(report['skipped_backends']['tart']['status'], 'skipped')
        self.assertIn('Skipping backend tart', result.stderr)
        tart.provision.assert_not_called()

    def test_unavailable_backend_saved_as_not_tested(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from typer.testing import CliRunner
        from hivemind.cli.main import app

        backend = DummyMockBackend('tart')
        backend.is_available = lambda: False
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.md'
            with patch('hivemind.daemon.backends.get_backend', return_value=backend):
                result = CliRunner().invoke(app, ['security', 'run', '--backend', 'tart', '-o', str(output)])
            self.assertEqual(result.exit_code, 0, result.output)
            report = output.read_text()
            self.assertIn('No backends evaluated', report)
            self.assertIn('Tart**: SKIPPED / NOT TESTED', report)
            self.assertNotIn('0.0%', report)
        self.assertFalse(backend.provision_called)


if __name__ == "__main__":
    unittest.main()
