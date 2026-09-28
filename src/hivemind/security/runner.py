"""
Security probe runner for evaluating isolation boundaries across backends.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

from hivemind.daemon.backends.base import IsolationBackend, SandboxConfig
from hivemind.security.probes import DEFAULT_PROBES, SecurityProbe


@dataclass
class ProbeResult:
    """Empirical outcome of running a SecurityProbe against an IsolationBackend."""
    probe_id: str
    probe_name: str
    category: str
    backend: str
    contained: bool
    exit_code: int
    duration_ms: float
    output: str
    description: str


class SecurityProbeRunner:
    """Executes a battery of security containment probes against an IsolationBackend."""

    @staticmethod
    def validate_backend(backend: IsolationBackend) -> None:
        """Refuse to execute security probes without real isolation."""
        if not backend.is_available():
            raise ValueError("real isolation unavailable: host requirements or backend binary missing")
        if getattr(backend, "simulate", False):
            raise ValueError("simulation mode is not permitted for security probes")

    async def run_probe(
        self,
        probe: SecurityProbe,
        backend: IsolationBackend,
    ) -> ProbeResult:
        """Execute a single probe in an ephemeral sandbox and grade containment."""
        self.validate_backend(backend)
        sandbox_id = f"sbx_sec_{uuid.uuid4().hex[:10]}"
        config = SandboxConfig(
            sandbox_id=sandbox_id,
            allow_network=probe.allow_network,
        )

        stdout_chunks: List[str] = []
        stderr_chunks: List[str] = []

        async def on_stdout(chunk: str) -> None:
            stdout_chunks.append(chunk)

        async def on_stderr(chunk: str) -> None:
            stderr_chunks.append(chunk)

        start_time = time.monotonic()
        try:
            await backend.provision(config)
            exec_result = await backend.execute(
                command=probe.command,
                request_id=f"req_{uuid.uuid4().hex[:8]}",
                config=config,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )
            exit_code = exec_result.exit_code
        except Exception as e:
            # An execution error triggered by the security boundary also counts as containment
            stderr_chunks.append(str(e))
            exit_code = -1
        finally:
            try:
                await backend.teardown(sandbox_id)
            except Exception:
                pass

        duration_ms = (time.monotonic() - start_time) * 1000

        # Containment is achieved when the unauthorized action is blocked (exit code != 0)
        contained = exit_code != 0

        combined_output = "".join(stdout_chunks + stderr_chunks).strip()

        return ProbeResult(
            probe_id=probe.probe_id,
            probe_name=probe.name,
            category=probe.category.value if hasattr(probe.category, "value") else str(probe.category),
            backend=backend.name,
            contained=contained,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 2),
            output=combined_output,
            description=probe.description,
        )

    async def run_suite(
        self,
        backend: IsolationBackend,
        probes: Optional[List[SecurityProbe]] = None,
    ) -> List[ProbeResult]:
        """Execute all probes sequentially against an IsolationBackend."""
        self.validate_backend(backend)
        probe_list = probes or DEFAULT_PROBES
        results: List[ProbeResult] = []
        for p in probe_list:
            res = await self.run_probe(p, backend)
            results.append(res)
        return results
