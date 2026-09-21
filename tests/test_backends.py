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

    async def test_find_tart_binary_and_arch_check(self):
        from unittest.mock import patch
        from hivemind.daemon.backends.tart import find_tart_binary, is_apple_silicon

        # Test with mocked which
        with patch("shutil.which", return_value="/opt/homebrew/bin/tart"), \
             patch("os.path.isfile", return_value=True), \
             patch("os.access", return_value=True):
            self.assertEqual(find_tart_binary(), "/opt/homebrew/bin/tart")

        # Test apple silicon check returns boolean
        arch_res = is_apple_silicon()
        self.assertIsInstance(arch_res, bool)

    async def test_list_images_simulation(self):
        base_path = pathlib.Path(self.tmp_dir.name) / "tart_sim"
        backend = TartBackend(simulate=True, base_dir=base_path, base_image="macos-test")
        images = await backend.list_images()
        self.assertIn("macos-test", images)
        self.assertTrue(await backend.has_image("macos-test"))
        self.assertFalse(await backend.has_image("nonexistent-image"))

    async def test_list_images_parsing(self):
        from unittest.mock import AsyncMock, patch

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"macos-base\nmacos-sonoma\n", b"")
        mock_proc.returncode = 0

        backend = TartBackend(simulate=False, tart_bin="/usr/local/bin/tart")
        backend._host_available = True

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            images = await backend.list_images()
            self.assertEqual(images, ["macos-base", "macos-sonoma"])
            self.assertTrue(await backend.has_image("macos-base"))
            self.assertFalse(await backend.has_image("linux-ubuntu"))

    async def test_tart_provision_missing_base_image_raises(self):
        from unittest.mock import patch

        backend = TartBackend(simulate=False, tart_bin="/usr/local/bin/tart", base_image="nonexistent-base")
        backend._host_available = True

        with patch.object(backend, "has_image", return_value=False):
            config = SandboxConfig(sandbox_id="test_missing_img")
            with self.assertRaises(RuntimeError) as ctx:
                await backend.provision(config)
            self.assertIn("not found on host", str(ctx.exception))

    async def test_tart_real_lifecycle_mocked(self):
        from unittest.mock import AsyncMock, patch, MagicMock

        backend = TartBackend(simulate=False, tart_bin="/usr/local/bin/tart", base_image="macos-base")
        backend._host_available = True

        # Mock clone process
        mock_clone_proc = AsyncMock()
        mock_clone_proc.communicate.return_value = (b"", b"")
        mock_clone_proc.returncode = 0

        # Mock vm runner process
        mock_vm_proc = AsyncMock()
        mock_vm_proc.returncode = None
        mock_vm_proc.terminate = MagicMock()
        mock_vm_proc.kill = MagicMock()
        mock_vm_proc.wait = AsyncMock(return_value=0)

        # Mock ip readiness check process
        mock_ip_proc = AsyncMock()
        mock_ip_proc.communicate.return_value = (b"192.168.64.2\n", b"")
        mock_ip_proc.returncode = 0

        # Mock exec process
        mock_exec_proc = AsyncMock()
        mock_exec_proc.returncode = 0
        mock_exec_proc.stdout = AsyncMock()
        mock_exec_proc.stdout.read = AsyncMock(side_effect=[b"real vm stdout", b""])
        mock_exec_proc.stderr = AsyncMock()
        mock_exec_proc.stderr.read = AsyncMock(side_effect=[b""])
        mock_exec_proc.wait = AsyncMock(return_value=0)

        # Mock stop & delete processes
        mock_stop_proc = AsyncMock()
        mock_stop_proc.wait = AsyncMock(return_value=0)
        mock_del_proc = AsyncMock()
        mock_del_proc.wait = AsyncMock(return_value=0)

        def mock_exec_dispatcher(*args, **kwargs):
            cmd = args[1] if len(args) > 1 else ""
            if cmd == "clone":
                return mock_clone_proc
            elif cmd == "run":
                return mock_vm_proc
            elif cmd == "ip":
                return mock_ip_proc
            elif cmd == "exec":
                return mock_exec_proc
            elif cmd == "stop":
                return mock_stop_proc
            elif cmd == "delete":
                return mock_del_proc
            return AsyncMock()

        config = SandboxConfig(sandbox_id="test_real_001")
        stdout_chunks = []

        async def on_stdout(data: str):
            stdout_chunks.append(data)

        async def on_stderr(data: str):
            pass

        with patch.object(backend, "has_image", return_value=True), \
             patch("asyncio.create_subprocess_exec", side_effect=mock_exec_dispatcher):
            res = await backend.execute(
                command="echo 'real vm stdout'",
                request_id="req_real_001",
                config=config,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )
            self.assertEqual(res.exit_code, 0)
            self.assertIn("real vm stdout", "".join(stdout_chunks))

            # Verify VM process tracking
            self.assertIn("test_real_001", backend._vm_processes)

            # Teardown
            await backend.teardown("test_real_001")
            self.assertNotIn("test_real_001", backend._vm_processes)
            mock_del_proc.wait.assert_awaited()

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

    async def test_executor_fallback_on_unavailable_tart(self):
        from unittest.mock import patch

        executor = Executor()
        stdout_chunks = []
        stderr_chunks = []

        async def on_stdout(chunk: str):
            stdout_chunks.append(chunk)

        async def on_stderr(chunk: str):
            stderr_chunks.append(chunk)

        # Mock TartBackend.is_available returning False
        with patch("hivemind.daemon.backends.tart.TartBackend.is_available", return_value=False):
            res = await executor.execute(
                command="echo 'tart fallback test'",
                request_id="req_fallback_tart",
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                backend="tart",
            )

        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.backend_name, "seatbelt")
        self.assertIn("tart fallback test", "".join(stdout_chunks))
        self.assertTrue(any("Notice: 'tart' microVM driver not available" in err for err in stderr_chunks))

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
