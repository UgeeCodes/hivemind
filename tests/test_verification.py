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


if __name__ == "__main__":
    unittest.main()

