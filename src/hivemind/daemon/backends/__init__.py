"""
Isolation backends package for Hivemind.
"""
from __future__ import annotations

from typing import Dict, Type

from hivemind.daemon.backends.base import BackendExecResult, IsolationBackend, SandboxConfig
from hivemind.daemon.backends.seatbelt import SeatbeltBackend
from hivemind.daemon.backends.tart import TartBackend

_REGISTRY: Dict[str, Type[IsolationBackend]] = {
    "seatbelt": SeatbeltBackend,
    "tart": TartBackend,
}


def get_backend(name: str = "seatbelt", **kwargs) -> IsolationBackend:
    """Instantiate an isolation backend by name ('seatbelt' or 'tart')."""
    backend_cls = _REGISTRY.get(name.lower())
    if not backend_cls:
        raise ValueError(f"Unknown isolation backend: '{name}'. Available: {list(_REGISTRY.keys())}")
    return backend_cls(**kwargs)


__all__ = [
    "IsolationBackend",
    "SandboxConfig",
    "BackendExecResult",
    "SeatbeltBackend",
    "TartBackend",
    "get_backend",
]
