"""
Abstract base interface for isolation backends in Hivemind.

Defines the contract that all execution isolation strategies (Seatbelt, Tart VMs, etc.)
must implement to allow uniform benchmarking and runtime isolation swapping.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional


@dataclass
class SandboxConfig:
    """Configuration for an isolated sandbox environment."""
    sandbox_id: str
    env: Dict[str, str] = field(default_factory=dict)
    cwd: Optional[str] = None
    timeout: Optional[float] = None
    inherit_home: bool = False
    allow_network: bool = True
    cpu_limit: Optional[int] = None
    memory_limit_mb: Optional[int] = None


@dataclass
class BackendExecResult:
    """Execution output and performance metrics from an isolation backend."""
    exit_code: int
    duration_s: float
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    provision_duration_s: float = 0.0
    teardown_duration_s: float = 0.0
    backend_name: str = "base"


class IsolationBackend(ABC):
    """
    Abstract contract for isolation backends.
    
    Implementations must manage the lifecycle (provision -> execute -> teardown)
    of commands inside an isolated environment.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this isolation backend (e.g. 'seatbelt', 'tart')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend's prerequisites are installed on the current host."""
        ...

    @abstractmethod
    async def provision(self, config: SandboxConfig) -> Path:
        """
        Prepare/provision the sandbox environment (directory tree, VM clone, profile compilation).
        Returns the root path of the provisioned workspace.
        """
        ...

    @abstractmethod
    async def execute(
        self,
        command: str,
        request_id: str,
        config: SandboxConfig,
        on_stdout: Callable[[str], Coroutine[Any, Any, None]],
        on_stderr: Callable[[str], Coroutine[Any, Any, None]],
    ) -> BackendExecResult:
        """
        Execute a command within the isolated environment and stream output chunks via callbacks.
        """
        ...

    @abstractmethod
    async def teardown(self, sandbox_id: str) -> None:
        """Clean up the sandbox environment (delete directory tree, destroy VM snapshot)."""
        ...
