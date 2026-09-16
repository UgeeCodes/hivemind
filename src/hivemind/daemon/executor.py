"""
Executor service for Hivemind.

Dispatches execution jobs to pluggable isolation backends (Seatbelt, Tart micro-VMs)
while streaming real-time stdout and stderr output via asynchronous callbacks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, Optional
from uuid import uuid4

from hivemind.daemon.backends import (
    BackendExecResult,
    IsolationBackend,
    SandboxConfig,
    get_backend,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    """Standardized result of a command execution."""
    exit_code: int
    duration_s: float
    backend_name: str = "seatbelt"
    provision_duration_s: float = 0.0


class Executor:
    """
    Manages command execution across pluggable isolation backends.
    
    Supports:
    - 'seatbelt': Fast, lightweight directory & credential isolation (<50ms startup)
    - 'tart': Strict hardware-assisted micro-VM isolation
    """

    def __init__(self, default_backend: str = "seatbelt"):
        self.default_backend = default_backend
        self._active_processes: Dict[str, Any] = {}
        self._sessions: Dict[str, Any] = {}

    async def execute(
        self,
        command: str,
        request_id: str,
        on_stdout: Callable[[str], Coroutine[Any, Any, None]],
        on_stderr: Callable[[str], Coroutine[Any, Any, None]],
        sandbox_id: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        inherit_home: bool = False,
        backend: Optional[str] = None,
    ) -> ExecResult:
        """
        Execute a command in an isolated sandbox backend and stream output via callbacks.
        """
        sbx_id = sandbox_id or f"sbx_eph_{uuid4().hex[:12]}"
        backend_name = backend or self.default_backend

        try:
            backend_instance = get_backend(backend_name)
        except ValueError as e:
            logger.warning("%s. Falling back to 'seatbelt'.", e)
            backend_name = "seatbelt"
            backend_instance = get_backend("seatbelt")

        config = SandboxConfig(
            sandbox_id=sbx_id,
            env=env or {},
            cwd=cwd,
            timeout=timeout,
            inherit_home=inherit_home,
        )

        res = await backend_instance.execute(
            command=command,
            request_id=request_id,
            config=config,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )

        return ExecResult(
            exit_code=res.exit_code,
            duration_s=res.duration_s,
            backend_name=res.backend_name,
            provision_duration_s=res.provision_duration_s,
        )

    async def cancel(self, request_id: str) -> bool:
        """Cancel a running execution by request_id."""
        proc = self._active_processes.get(request_id)
        if not proc:
            return False
        try:
            import os
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, AttributeError):
            pass
        return True
