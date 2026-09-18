"""
Unit tests for hardware introspection and telemetry messages.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from hivemind.daemon.hardware import (
    HardwareSpecs,
    get_chip_name,
    get_cpu_cores,
    get_cpu_utilization,
    get_hardware_specs,
    get_memory_utilization,
    get_total_ram_gb,
)
from hivemind.protocol.messages import (
    AuthRequest,
    Ping,
    parse_message,
    serialize_message,
)


class TestHardwareIntrospection(unittest.TestCase):
    """Test macOS hardware introspection helpers."""

    def test_get_chip_name_returns_string(self):
        chip = get_chip_name()
        self.assertIsInstance(chip, str)
        self.assertTrue(len(chip) > 0)

    def test_get_total_ram_gb_positive_int(self):
        ram = get_total_ram_gb()
        self.assertIsInstance(ram, int)
        self.assertGreaterEqual(ram, 1)

    def test_get_cpu_cores_positive_int(self):
        cores = get_cpu_cores()
        self.assertIsInstance(cores, int)
        self.assertGreaterEqual(cores, 1)

    def test_get_cpu_utilization_range(self):
        cpu = get_cpu_utilization()
        self.assertIsInstance(cpu, float)
        self.assertGreaterEqual(cpu, 0.0)
        self.assertLessEqual(cpu, 100.0)

    def test_get_memory_utilization_range(self):
        mem = get_memory_utilization()
        self.assertIsInstance(mem, float)
        self.assertGreaterEqual(mem, 0.0)
        self.assertLessEqual(mem, 100.0)

    def test_get_hardware_specs(self):
        specs = get_hardware_specs()
        self.assertIsInstance(specs, HardwareSpecs)
        self.assertIsInstance(specs.chip, str)
        self.assertGreaterEqual(specs.cpu_cores, 1)
        self.assertGreaterEqual(specs.ram_gb, 1)
        self.assertGreaterEqual(specs.cpu_percent, 0.0)
        self.assertGreaterEqual(specs.memory_percent, 0.0)

    def test_fallback_on_subprocess_error(self):
        with patch("subprocess.check_output", side_effect=OSError("Command not found")):
            chip = get_chip_name()
            self.assertIsInstance(chip, str)
            self.assertTrue(len(chip) > 0)

            ram = get_total_ram_gb()
            self.assertEqual(ram, 16)

            mem = get_memory_utilization()
            self.assertEqual(mem, 50.0)


class TestHardwareProtocolMessages(unittest.TestCase):
    """Test serialization of hardware specs in protocol messages."""

    def test_auth_request_with_hardware_specs(self):
        auth = AuthRequest(
            device_token="dev_tok_123",
            hostname="MacBook-Pro.local",
            arch="arm64",
            os_version="15.2",
            tags=["m4", "local"],
            chip="Apple M4",
            cpu_cores=10,
            ram_gb=16,
            cpu_percent=12.5,
            memory_percent=55.0,
        )
        serialized = serialize_message(auth)
        parsed = parse_message(serialized)

        self.assertIsInstance(parsed, AuthRequest)
        self.assertEqual(parsed.chip, "Apple M4")
        self.assertEqual(parsed.cpu_cores, 10)
        self.assertEqual(parsed.ram_gb, 16)
        self.assertEqual(parsed.cpu_percent, 12.5)
        self.assertEqual(parsed.memory_percent, 55.0)

    def test_ping_with_telemetry(self):
        ping = Ping(cpu_percent=32.4, memory_percent=68.1)
        serialized = serialize_message(ping)
        parsed = parse_message(serialized)

        self.assertIsInstance(parsed, Ping)
        self.assertEqual(parsed.cpu_percent, 32.4)
        self.assertEqual(parsed.memory_percent, 68.1)


if __name__ == "__main__":
    unittest.main()
