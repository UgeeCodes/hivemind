"""
Comprehensive test suite verifying logic, schemas, and cross-module consistency across Hivemind.
Runs using standard library unittest (no external dependencies required).
"""
import ast
import os
import pathlib
import sys
import unittest

# Ensure src is in sys.path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class TestASTAndSyntax(unittest.TestCase):
    """Verify that all Python files parse into valid AST without syntax errors."""

    def test_all_python_files_compile(self):
        py_files = list(SRC_DIR.rglob("*.py"))
        self.assertGreater(len(py_files), 10, "Should have found project Python files")

        for py_file in py_files:
            with self.subTest(file=str(py_file.relative_to(PROJECT_ROOT))):
                content = py_file.read_text(encoding="utf-8")
                try:
                    tree = ast.parse(content, filename=str(py_file))
                    self.assertIsInstance(tree, ast.Module)
                except SyntaxError as e:
                    self.fail(f"Syntax error in {py_file}: {e}")

    def test_example_scripts_compile(self):
        examples_dir = PROJECT_ROOT / "examples"
        py_files = list(examples_dir.rglob("*.py"))
        self.assertGreaterEqual(len(py_files), 4, "Should have found example scripts")

        for py_file in py_files:
            with self.subTest(file=str(py_file.relative_to(PROJECT_ROOT))):
                content = py_file.read_text(encoding="utf-8")
                try:
                    tree = ast.parse(content, filename=str(py_file))
                    self.assertIsInstance(tree, ast.Module)
                except SyntaxError as e:
                    self.fail(f"Syntax error in {py_file}: {e}")


class TestAuthModule(unittest.TestCase):
    """Verify auth functions and scope hierarchy."""

    def setUp(self):
        from hivemind.control.auth import (
            generate_api_key,
            generate_device_token,
            hash_token,
            verify_scope,
            SCOPE_HIERARCHY,
            TOKEN_PREFIX,
            DEVICE_TOKEN_PREFIX,
        )
        self.generate_api_key = generate_api_key
        self.generate_device_token = generate_device_token
        self.hash_token = hash_token
        self.verify_scope = verify_scope
        self.SCOPE_HIERARCHY = SCOPE_HIERARCHY
        self.TOKEN_PREFIX = TOKEN_PREFIX
        self.DEVICE_TOKEN_PREFIX = DEVICE_TOKEN_PREFIX

    def test_generate_api_key(self):
        full_key, key_hash, key_prefix = self.generate_api_key(name="test")
        self.assertTrue(full_key.startswith(self.TOKEN_PREFIX))
        self.assertEqual(len(key_hash), 64)
        self.assertEqual(key_prefix, full_key[:16])
        self.assertEqual(self.hash_token(full_key), key_hash)

    def test_generate_device_token(self):
        full_token, token_hash = self.generate_device_token()
        self.assertTrue(full_token.startswith(self.DEVICE_TOKEN_PREFIX))
        self.assertEqual(len(token_hash), 64)
        self.assertEqual(self.hash_token(full_token), token_hash)

    def test_scope_verification(self):
        # admin scope has full access
        self.assertTrue(self.verify_scope(["admin"], "admin"))
        self.assertTrue(self.verify_scope(["admin"], "run"))
        self.assertTrue(self.verify_scope(["admin"], "read"))

        # run scope can read and run, but not admin
        self.assertTrue(self.verify_scope(["run"], "run"))
        self.assertTrue(self.verify_scope(["run"], "read"))
        self.assertFalse(self.verify_scope(["run"], "admin"))

        # read scope can only read
        self.assertTrue(self.verify_scope(["read"], "read"))
        self.assertFalse(self.verify_scope(["read"], "run"))
        self.assertFalse(self.verify_scope(["read"], "admin"))


class TestSandboxModule(unittest.TestCase):
    """Verify Seatbelt sandbox profile generation and deny-lists."""

    def setUp(self):
        from hivemind.daemon.sandbox import (
            generate_seatbelt_profile,
            wrap_command_with_seatbelt,
            DENIED_PATHS,
        )
        self.generate_profile = generate_seatbelt_profile
        self.wrap_command = wrap_command_with_seatbelt
        self.DENIED_PATHS = DENIED_PATHS

    def test_seatbelt_profile_contains_rules(self):
        profile = self.generate_profile("sbx_test_123", allow_network=True)
        self.assertIn("(version 1)", profile)
        self.assertIn("sbx_test_123", profile)
        self.assertIn("(allow network*)", profile)

        # Check deny rules for credentials
        self.assertIn(".ssh", profile)
        self.assertIn(".aws", profile)

    def test_seatbelt_profile_deny_network(self):
        profile = self.generate_profile("sbx_test_isolated", allow_network=False)
        self.assertIn("(deny network*)", profile)


class TestLaunchdModule(unittest.TestCase):
    """Verify LaunchAgent plist structure."""

    def test_generate_plist(self):
        from hivemind.daemon.launchd import generate_plist, LABEL

        plist = generate_plist(
            control_plane_url="http://localhost:8000",
            device_token="hm_dt_test123",
            tags=["m2", "studio"],
        )

        self.assertEqual(plist["Label"], LABEL)
        self.assertTrue(plist["RunAtLoad"])
        self.assertIn("--control-plane", plist["ProgramArguments"])
        self.assertIn("http://localhost:8000", plist["ProgramArguments"])
        self.assertIn("--device-token", plist["ProgramArguments"])
        self.assertIn("hm_dt_test123", plist["ProgramArguments"])
        self.assertIn("--tag", plist["ProgramArguments"])
        self.assertIn("m2", plist["ProgramArguments"])


class TestAgentModule(unittest.TestCase):
    """Verify AI agent harness and command formatting."""

    def test_build_claude_command(self):
        from hivemind.agent import _build_agent_command, AgentConfig

        config = AgentConfig(
            prompt="Run tests",
            proxy="https://proxy.example.com",
            token="token_abc",
            harness="claude",
        )
        cmd, env = _build_agent_command(config)
        self.assertIn("claude --print", cmd)
        self.assertEqual(env.get("ANTHROPIC_BASE_URL"), "https://proxy.example.com")
        self.assertEqual(env.get("ANTHROPIC_API_KEY"), "token_abc")

    def test_build_codex_command(self):
        from hivemind.agent import _build_agent_command, AgentConfig

        config = AgentConfig(
            prompt="Fix bugs",
            proxy="https://proxy.example.com",
            token="token_xyz",
            harness="codex",
        )
        cmd, env = _build_agent_command(config)
        self.assertIn("codex --quiet", cmd)
        self.assertEqual(env.get("OPENAI_BASE_URL"), "https://proxy.example.com")
        self.assertEqual(env.get("OPENAI_API_KEY"), "token_xyz")


class TestSkillModule(unittest.TestCase):
    """Verify SKILL.md template content."""

    def test_skill_template(self):
        from hivemind.skill import SKILL_TEMPLATE
        self.assertIn("name: hivemind", SKILL_TEMPLATE)
        self.assertIn("hivemind.mac()", SKILL_TEMPLATE)
        self.assertIn("HIVEMIND_CONTROL_PLANE", SKILL_TEMPLATE)


class TestWSRegistryBuffering(unittest.IsolatedAsyncioTestCase):
    """Verify WSRegistry buffering and fan_out logic."""

    async def test_buffering_replay_and_completion(self):
        from hivemind.control.ws_registry import WSRegistry
        import json

        registry = WSRegistry()
        req_id = "req_buffering_test"

        # Daemon sends output before client connects
        await registry.fan_out(req_id, json.dumps({"type": "exec_stdout", "data": "hello world"}))
        await registry.fan_out(req_id, json.dumps({"type": "exec_exit", "exit_code": 0}))

        # Client connects later
        queue = registry.add_stream_listener(req_id)

        # Should immediately receive buffered stdout
        msg1 = await queue.get()
        self.assertIn("hello world", msg1)

        # Should receive exec_exit
        msg2 = await queue.get()
        self.assertIn("exec_exit", msg2)

        # Should receive None sentinel
        sentinel = await queue.get()
        self.assertIsNone(sentinel)


class TestSQLiteSchema(unittest.TestCase):
    """Verify that all SQL schemas in store.py execute cleanly on a standard sqlite3 database."""

    def test_schema_creates_tables(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()

        # Read SQL directly from store.py AST string literal
        store_path = SRC_DIR / "hivemind" / "control" / "store.py"
        store_tree = ast.parse(store_path.read_text(encoding="utf-8"))

        sql_script = None
        for node in ast.walk(store_tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "executescript":
                if node.args and isinstance(node.args[0], ast.Constant):
                    sql_script = node.args[0].value
                    break

        self.assertIsNotNone(sql_script, "Should find CREATE TABLE SQL script in store.py")
        cursor.executescript(sql_script)

        # Verify all 5 expected tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        expected = {"machines", "api_keys", "jobs", "sandboxes", "volumes"}
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")
        conn.close()


class TestWebDashboardFiles(unittest.TestCase):
    """Verify configuration files for Next.js web dashboard."""

    def test_package_json_is_valid(self):
        import json
        pkg_file = PROJECT_ROOT / "web" / "package.json"
        self.assertTrue(pkg_file.exists())
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "hivemind-dashboard")
        self.assertIn("next", data["dependencies"])

    def test_tsconfig_json_is_valid(self):
        import json
        ts_file = PROJECT_ROOT / "web" / "tsconfig.json"
        self.assertTrue(ts_file.exists())
        data = json.loads(ts_file.read_text(encoding="utf-8"))
        self.assertIn("compilerOptions", data)


class TestJobOutputAndPruning(unittest.IsolatedAsyncioTestCase):
    """Verify job output persistence and 25-run retention pruning."""

    async def test_job_output_and_pruning(self):
        import tempfile
        from pathlib import Path
        from hivemind.control.store import Store

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_store.db"
            store = Store(db_path=str(db_path))
            await store.initialize()

            # Register a test machine
            await store.register_machine(
                machine_id="mac_test_prune",
                hostname="test-mac",
                arch="arm64",
                os_version="15.0",
                device_token_hash="hash123",
                owner_id="owner_test",
            )

            # Test appending stdout and stderr
            job_id = "job_test_output"
            await store.create_job(
                job_id=job_id,
                machine_id="mac_test_prune",
                command="echo 'hello world'",
            )
            await store.append_job_output(job_id, stdout="hello ")
            await store.append_job_output(job_id, stdout="world\n")
            await store.append_job_output(job_id, stderr="warning: test\n")
            await store.update_job_status(job_id, "completed", exit_code=0)

            job = await store.get_job(job_id)
            self.assertIsNotNone(job)
            self.assertEqual(job["stdout"], "hello world\n")
            self.assertEqual(job["stderr"], "warning: test\n")
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["exit_code"], 0)

            # Test 25-run retention pruning
            for i in range(30):
                jid = f"job_retention_{i}"
                await store.create_job(
                    job_id=jid,
                    machine_id="mac_test_prune",
                    command=f"cmd_{i}",
                )
                await store.update_job_status(jid, "completed", exit_code=0)

            jobs = await store.list_jobs(limit=50)
            self.assertEqual(len(jobs), 25)

            await store.close()


class TestExecRequestBackendPlumbing(unittest.TestCase):
    """Verify ExecRequestModel and SDK serialization of isolation backend."""

    def test_exec_request_model_defaults_and_custom(self):
        from hivemind.control.app import ExecRequestModel

        # Default is seatbelt
        req_default = ExecRequestModel(command="echo hi")
        self.assertEqual(req_default.backend, "seatbelt")

        # Custom tart backend
        req_tart = ExecRequestModel(command="echo tart", backend="tart")
        self.assertEqual(req_tart.backend, "tart")

    def test_app_exec_endpoint_receives_backend(self):
        from unittest.mock import AsyncMock
        from fastapi.testclient import TestClient
        from hivemind.control.app import app
        from hivemind.protocol.messages import parse_message

        sent_messages = []
        async def mock_send(machine_id, serialized_msg):
            sent_messages.append((machine_id, parse_message(serialized_msg)))

        with TestClient(app) as client:
            app.state.registry.send_to_machine = mock_send
            app.state.registry.register(
                machine_id="mac_test_backend",
                owner_id="default_owner",
                hostname="test-host",
                ws=AsyncMock(),
            )

            resp = client.post("/api/exec", json={"command": "echo test", "backend": "tart"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(sent_messages), 1)
            mid, exec_msg = sent_messages[0]
            self.assertEqual(mid, "mac_test_backend")
            self.assertEqual(exec_msg.backend, "tart")
            self.assertEqual(exec_msg.command, "echo test")


class TestSandboxStoreOperations(unittest.IsolatedAsyncioTestCase):
    """Verify sandbox registration, listing, destroy, and counting."""

    async def test_sandbox_lifecycle_and_counts(self):
        import tempfile
        from pathlib import Path
        from hivemind.control.store import Store

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = Store(db_path=db_path)
            await store.initialize()

            # Empty initially
            sandboxes = await store.list_sandboxes()
            self.assertEqual(len(sandboxes), 0)
            counts = await store.count_all_sandboxes()
            self.assertEqual(counts["active"], 0)
            self.assertEqual(counts["total"], 0)

            # Register two sandboxes
            await store.register_sandbox("sbx_1", "mac_1", name="dev-sandbox", dir_path="/tmp/sbx_1")
            await store.register_sandbox("sbx_2", "mac_1", name="prod-sandbox", dir_path="/tmp/sbx_2")

            sandboxes = await store.list_sandboxes()
            self.assertEqual(len(sandboxes), 2)
            counts = await store.count_all_sandboxes()
            self.assertEqual(counts["active"], 2)
            self.assertEqual(counts["total"], 2)

            # Destroy one
            destroyed = await store.destroy_sandbox("sbx_1")
            self.assertTrue(destroyed)

            # Idempotent / already destroyed
            destroyed_again = await store.destroy_sandbox("sbx_1")
            self.assertFalse(destroyed_again)

            # Active list should only have sbx_2 now
            active_sandboxes = await store.list_sandboxes()
            self.assertEqual(len(active_sandboxes), 1)
            self.assertEqual(active_sandboxes[0]["id"], "sbx_2")

            # Counts should reflect 1 active and 2 total
            counts = await store.count_all_sandboxes()
            self.assertEqual(counts["active"], 1)
            self.assertEqual(counts["total"], 2)

            await store.close()


class TestVolumeStoreOperations(unittest.IsolatedAsyncioTestCase):
    """Verify volume creation, listing, retrieval, and deletion."""

    async def test_volume_crud(self):
        import tempfile
        from pathlib import Path
        from hivemind.control.store import Store

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            store = Store(db_path=db_path)
            await store.initialize()

            # Initially empty
            volumes = await store.list_volumes("owner_1")
            self.assertEqual(len(volumes), 0)

            # Create volumes
            await store.create_volume("build-cache", "owner_1")
            await store.create_volume("data-lake", "owner_1")

            volumes = await store.list_volumes("owner_1")
            self.assertEqual(len(volumes), 2)
            names = {v["name"] for v in volumes}
            self.assertEqual(names, {"build-cache", "data-lake"})

            # Get single volume
            vol = await store.get_volume("build-cache")
            self.assertIsNotNone(vol)
            self.assertEqual(vol["name"], "build-cache")
            self.assertEqual(vol["owner_id"], "owner_1")

            # Delete volume
            await store.delete_volume("build-cache")
            volumes_after = await store.list_volumes("owner_1")
            self.assertEqual(len(volumes_after), 1)
            self.assertEqual(volumes_after[0]["name"], "data-lake")

            # Get deleted volume
            self.assertIsNone(await store.get_volume("build-cache"))

            await store.close()


if __name__ == "__main__":
    unittest.main()

