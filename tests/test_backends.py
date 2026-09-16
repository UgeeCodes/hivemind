"""
Test suite for pluggable isolation backends (Seatbelt and Tart micro-VMs).
"""
import asyncio
import os
import pathlib
import sys
import tempfile
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hivemind.daemon.backends import (
    BackendExecResult,
    IsolationBackend,
    SandboxConfig,
    SeatbeltBackend,
    TartBackend,
    get_backend,
)
from hivemind.daemon.executor import Executor


class BaseBackendTestCase(unittest.IsolatedAsyncioTestCase):
    """Base test case setting up a clean isolated HIVEMIND_HOME directory."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.old_home = os.environ.get("HIVEMIND_HOME")
        os.environ["HIVEMIND_HOME"] = self.tmp_dir.name

    def tearDown(self):
        if self.old_home is not None:
            os.environ["HIVEMIND_HOME"] = self.old_home
        else:
            os.environ.pop("HIVEMIND_HOME", None)
        self.tmp_dir.cleanup()


class TestBackendRegistry(unittest.TestCase):
    """Verify backend discovery and factory instantiation."""

    def test_get_seatbelt_backend(self):
        backend = get_backend("seatbelt")
        self.assertIsInstance(backend, SeatbeltBackend)
        self.assertEqual(backend.name, "seatbelt")

    def test_get_tart_backend(self):
        backend = get_backend("tart")
        self.assertIsInstance(backend, TartBackend)
        self.assertEqual(backend.name, "tart")

    def test_invalid_backend_raises(self):
        with self.assertRaises(ValueError):
            get_backend("nonexistent_isolation_mode")


class TestSeatbeltBackend(BaseBackendTestCase):
    """Verify Seatbelt backend provisioning, execution, and cleanup."""

    async def test_provision_and_teardown(self):
        base_path = pathlib.Path(self.tmp_dir.name) / "sandboxes"
        backend = SeatbeltBackend(base_dir=base_path)
        config = SandboxConfig(sandbox_id="test_sbx_001")

        workspace = await backend.provision(config)
        self.assertTrue(workspace.exists())
        self.assertTrue((base_path / "test_sbx_001" / "sandbox.sb").exists())

        # Verify credential deny rules in compiled profile
        profile = (base_path / "test_sbx_001" / "sandbox.sb").read_text()
        self.assertIn(".ssh", profile)
        self.assertIn(".aws", profile)

        # Teardown
        await backend.teardown("test_sbx_001")
        self.assertFalse((base_path / "test_sbx_001").exists())

    async def test_execute_streaming(self):
        base_path = pathlib.Path(self.tmp_dir.name) / "sandboxes"
        backend = SeatbeltBackend(base_dir=base_path)
        config = SandboxConfig(sandbox_id="test_exec_001")

        stdout_chunks = []

        async def on_stdout(data: str):
            stdout_chunks.append(data)

        async def on_stderr(data: str):
            pass

        res = await backend.execute(
            command="echo 'backend test output'",
            request_id="req_test_001",
            config=config,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )

        self.assertEqual(res.exit_code, 0)
        self.assertIn("backend test output", "".join(stdout_chunks))
        self.assertGreaterEqual(res.duration_s, 0.0)
        self.assertGreater(res.stdout_bytes, 0)

        await backend.teardown("test_exec_001")


class TestTartBackend(BaseBackendTestCase):
    """Verify Tart backend lifecycle and simulation mode."""

    async def test_tart_simulation_lifecycle(self):
        base_path = pathlib.Path(self.tmp_dir.name) / "tart_sim"
        backend = TartBackend(simulate=True, base_dir=base_path)
        self.assertEqual(backend.name, "tart")

        config = SandboxConfig(sandbox_id="test_tart_001")
        stdout_chunks = []

        async def on_stdout(data: str):
            stdout_chunks.append(data)

        async def on_stderr(data: str):
            pass

        res = await backend.execute(
            command="echo 'tart vm test'",
            request_id="req_tart_001",
            config=config,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )

        self.assertEqual(res.exit_code, 0)
        self.assertIn("tart vm test", "".join(stdout_chunks))
        self.assertEqual(res.backend_name, "tart")

        await backend.teardown("test_tart_001")


class TestExecutorDispatch(BaseBackendTestCase):
    """Verify Executor routes to selected backends."""

    async def test_executor_routes_seatbelt(self):
        executor = Executor(default_backend="seatbelt")
        chunks = []

        async def on_stdout(chunk: str):
            chunks.append(chunk)

        async def on_stderr(chunk: str):
            pass

        res = await executor.execute(
            command="echo 'routing test'",
            request_id="req_route_1",
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            backend="seatbelt",
        )

        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.backend_name, "seatbelt")
        self.assertIn("routing test", "".join(chunks))

    async def test_executor_fallback_on_invalid_backend(self):
        executor = Executor()
        chunks = []

        async def on_stdout(chunk: str):
            chunks.append(chunk)

        async def on_stderr(chunk: str):
            pass

        # Should log a warning and fall back to seatbelt without crashing
        res = await executor.execute(
            command="echo 'fallback test'",
            request_id="req_route_2",
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            backend="invalid_unknown_backend",
        )

        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.backend_name, "seatbelt")


if __name__ == "__main__":
    unittest.main()
