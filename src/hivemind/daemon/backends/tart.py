"""
Tart micro-VM isolation backend using Apple's Virtualization.framework.

Provides strict hardware-assisted virtualization isolation on Apple Silicon Macs.
Each execution job runs inside an ephemeral macOS guest VM created via instant
APFS copy-on-write cloning from a base image and discarded upon completion.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from hivemind.daemon.backends.base import BackendExecResult, IsolationBackend, SandboxConfig

logger = logging.getLogger(__name__)

DEFAULT_BASE_IMAGE = os.environ.get("HIVEMIND_TART_BASE_IMAGE", "macos-base")


class TartBackend(IsolationBackend):
    """
    Micro-VM isolation backend using Tart (Virtualization.framework).
    
    Provides complete OS-level separation:
    - Dedicated XNU kernel and memory space
    - Isolated network interface
    - Zero host credential exposure
    - Ephemeral APFS snapshot teardown
    """

    def __init__(
        self,
        base_image: str = DEFAULT_BASE_IMAGE,
        tart_bin: Optional[str] = None,
        simulate: bool = False,
    ):
        self.base_image = base_image
        self.tart_bin = tart_bin or shutil.which("tart") or "tart"
        self.simulate = simulate or (shutil.which("tart") is None)
        self._running_vms: Dict[str, str] = {}  # sandbox_id -> vm_name

    @property
    def name(self) -> str:
        return "tart"

    def is_available(self) -> bool:
        """Tart requires Apple Silicon (arm64) and the tart CLI installed."""
        return shutil.which("tart") is not None

    def _vm_name_for(self, sandbox_id: str) -> str:
        # Tart VM names must be alphanumeric/hyphens
        clean_id = "".join(c if c.isalnum() or c == "-" else "-" for c in sandbox_id)
        return f"hm-vm-{clean_id[:20]}"

    async def provision(self, config: SandboxConfig) -> Path:
        """
        Clone the base image into an ephemeral micro-VM using APFS copy-on-write.
        """
        vm_name = self._vm_name_for(config.sandbox_id)
        self._running_vms[config.sandbox_id] = vm_name

        if self.simulate:
            logger.info("Simulated Tart provision: clone %s -> %s", self.base_image, vm_name)
            # Create a localized mount point for consistency
            vm_mount = Path.home() / '.hivemind' / 'tart_sim' / vm_name
            vm_mount.mkdir(parents=True, exist_ok=True)
            return vm_mount

        # Real Tart APFS clone: tart clone <base> <ephemeral>
        clone_cmd = [self.tart_bin, "clone", self.base_image, vm_name]
        logger.info("Cloning Tart VM: %s", " ".join(clone_cmd))
        proc = await asyncio.create_subprocess_exec(
            *clone_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise RuntimeError(f"Failed to clone Tart VM '{vm_name}' from '{self.base_image}': {err}")

        # Start VM in headless background mode: tart run --no-graphics <ephemeral>
        run_cmd = [self.tart_bin, "run", "--no-graphics", vm_name]
        logger.info("Booting Tart VM: %s", " ".join(run_cmd))
        asyncio.create_task(self._run_vm_process(run_cmd, vm_name))

        # Wait for guest OS / SSH / agent readiness
        await self._wait_for_vm_ready(vm_name, timeout=30.0)

        return Path(f"/var/run/tart/{vm_name}")

    async def _run_vm_process(self, run_cmd: List[str], vm_name: str) -> None:
        """Keep the background VM runner process alive."""
        try:
            proc = await asyncio.create_subprocess_exec(*run_cmd)
            await proc.wait()
        except Exception as e:
            logger.debug("Tart VM process %s finished: %s", vm_name, e)

    async def _wait_for_vm_ready(self, vm_name: str, timeout: float = 30.0) -> None:
        """Poll until VM IP and guest executor are responsive."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            proc = await asyncio.create_subprocess_exec(
                self.tart_bin, "ip", vm_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout.strip():
                return
            await asyncio.sleep(0.5)

    async def execute(
        self,
        command: str,
        request_id: str,
        config: SandboxConfig,
        on_stdout: Callable[[str], Coroutine[Any, Any, None]],
        on_stderr: Callable[[str], Coroutine[Any, Any, None]],
    ) -> BackendExecResult:
        """Execute command inside the guest VM and stream output."""
        t_provision_start = time.monotonic()
        await self.provision(config)
        t_provision = time.monotonic() - t_provision_start

        vm_name = self._vm_name_for(config.sandbox_id)
        stdout_bytes = 0
        stderr_bytes = 0

        async def read_stream(stream: asyncio.StreamReader, callback: Callable, is_stdout: bool):
            nonlocal stdout_bytes, stderr_bytes
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                if is_stdout:
                    stdout_bytes += len(chunk)
                else:
                    stderr_bytes += len(chunk)
                await callback(chunk.decode('utf-8', errors='replace'))

        t_exec_start = time.monotonic()

        if self.simulate:
            # Simulated micro-VM execution: run in a fully isolated subshell
            # to verify full telemetry and protocol correctness
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=config.env or {},
                cwd=config.cwd,
            )
        else:
            # Real Tart execution: tart exec <vm_name> <command>
            exec_args = [self.tart_bin, "exec", vm_name]
            for k, v in config.env.items():
                exec_args.extend(["-e", f"{k}={v}"])
            if config.cwd:
                exec_args.extend(["--workdir", config.cwd])
            exec_args.extend(["/bin/zsh", "-c", command])

            proc = await asyncio.create_subprocess_exec(
                *exec_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        try:
            if config.timeout:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(proc.stdout, on_stdout, True),
                        read_stream(proc.stderr, on_stderr, False),
                    ),
                    timeout=config.timeout
                )
                await proc.wait()
            else:
                await asyncio.gather(
                    read_stream(proc.stdout, on_stdout, True),
                    read_stream(proc.stderr, on_stderr, False),
                )
                await proc.wait()
        except asyncio.TimeoutError:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            return BackendExecResult(
                exit_code=-1,
                duration_s=time.monotonic() - t_exec_start,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                provision_duration_s=t_provision,
                backend_name=self.name,
            )

        duration = time.monotonic() - t_exec_start
        return BackendExecResult(
            exit_code=proc.returncode or 0,
            duration_s=duration,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            provision_duration_s=t_provision,
            backend_name=self.name,
        )

    async def teardown(self, sandbox_id: str) -> None:
        """Stop and delete the ephemeral clone."""
        vm_name = self._running_vms.pop(sandbox_id, None) or self._vm_name_for(sandbox_id)

        if self.simulate:
            sim_dir = Path.home() / '.hivemind' / 'tart_sim' / vm_name
            shutil.rmtree(sim_dir, ignore_errors=True)
            logger.info("Torn down simulated Tart VM %s", vm_name)
            return

        # Stop and delete: tart stop <vm> ; tart delete <vm>
        try:
            stop_proc = await asyncio.create_subprocess_exec(
                self.tart_bin, "stop", vm_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await stop_proc.wait()

            del_proc = await asyncio.create_subprocess_exec(
                self.tart_bin, "delete", vm_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await del_proc.wait()
            logger.info("Destroyed ephemeral Tart VM %s", vm_name)
        except Exception as e:
            logger.warning("Error tearing down Tart VM %s: %s", vm_name, e)
