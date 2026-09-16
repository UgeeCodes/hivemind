"""
Seatbelt (sandbox-exec) isolation backend for macOS.

Provides lightweight process and filesystem isolation by compiling Apple Seatbelt
profiles to block sensitive credential stores, redirect toolchain caches, and isolate
directory trees without the overhead of full virtualization.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import shlex
import signal
import textwrap
import time
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from hivemind.daemon.backends.base import BackendExecResult, IsolationBackend, SandboxConfig

logger = logging.getLogger(__name__)

SANDBOX_BASE = Path.home() / '.hivemind' / 'sandboxes'

DENIED_PATHS = [
    '~/.ssh',
    '~/.aws',
    '~/.azure',
    '~/.config/gcloud',
    '~/Library/Keychains',
    '~/.gnupg',
    '~/.netrc',
    '~/Library/Application Support/1Password',
]


class SeatbeltBackend(IsolationBackend):
    """
    Lightweight isolation using macOS Seatbelt (`sandbox-exec`) profiles
    and clean process-group teardown.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or SANDBOX_BASE

    @property
    def name(self) -> str:
        return "seatbelt"

    def is_available(self) -> bool:
        """Seatbelt is available on macOS if sandbox-exec binary is present."""
        return platform.system() == "Darwin" and os.path.exists("/usr/bin/sandbox-exec")

    def _generate_profile(self, sandbox_dir: Path, allow_network: bool = True) -> str:
        """Compile a Seatbelt policy denying credential stores and write-locking host directories."""
        home_dir = str(Path.home())
        deny_rules = "\n".join(
            f'    (deny file-read* (subpath "{p.replace("~", home_dir)}"))'
            for p in DENIED_PATHS
        )
        network_rule = "(allow network*)" if allow_network else "(deny network*)"

        return textwrap.dedent(f"""\
            (version 1)
            (allow default)

            ;; Deny reads of personal credential stores
            {deny_rules}

            ;; Restrict file writes strictly to sandbox directory tree & temp
            (deny file-write*
                (require-not
                    (require-any
                        (subpath "{sandbox_dir}")
                        (subpath "/private/tmp")
                        (subpath "/private/var/folders")
                    )
                )
            )

            ;; Network policy
            ({network_rule})
        """)

    async def provision(self, config: SandboxConfig) -> Path:
        """Create sandbox directory tree and write the compiled Seatbelt profile."""
        sbx_dir = self.base_dir / config.sandbox_id
        dirs = {
            'workspace': sbx_dir / 'workspace',
            'tmp': sbx_dir / 'tmp',
            'home': sbx_dir / 'home',
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)

        profile_content = self._generate_profile(sbx_dir, config.allow_network)
        profile_path = sbx_dir / 'sandbox.sb'
        profile_path.write_text(profile_content)

        return dirs['workspace']

    def _build_env(self, config: SandboxConfig, sbx_dir: Path) -> Dict[str, str]:
        """Build isolated environment variables redirecting caches into the sandbox."""
        home = str(Path.home()) if config.inherit_home else str(sbx_dir / 'home')
        env = {
            'HOME': home,
            'TMPDIR': str(sbx_dir / 'tmp'),
            'PATH': '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'SHELL': '/bin/zsh',
            'TERM': 'xterm-256color',
            'LANG': 'en_US.UTF-8',
            'PIP_CACHE_DIR': str(sbx_dir / 'home' / '.cache' / 'pip'),
            'npm_config_cache': str(sbx_dir / 'home' / '.cache' / 'npm'),
            'CARGO_HOME': str(sbx_dir / 'home' / '.cargo'),
            'XDG_CACHE_HOME': str(sbx_dir / 'home' / '.cache'),
            'XDG_CONFIG_HOME': str(sbx_dir / 'home' / '.config'),
            'XDG_DATA_HOME': str(sbx_dir / 'home' / '.local' / 'share'),
        }

        # Add Homebrew paths if available
        for extra_path in ['/opt/homebrew/bin', '/opt/homebrew/sbin']:
            if Path(extra_path).exists():
                env['PATH'] = f"{extra_path}:{env['PATH']}"

        if config.env:
            env.update(config.env)

        return env

    async def execute(
        self,
        command: str,
        request_id: str,
        config: SandboxConfig,
        on_stdout: Callable[[str], Coroutine[Any, Any, None]],
        on_stderr: Callable[[str], Coroutine[Any, Any, None]],
    ) -> BackendExecResult:
        """Run command under Seatbelt sandbox-exec with streaming callbacks."""
        t_provision_start = time.monotonic()
        workspace = await self.provision(config)
        t_provision = time.monotonic() - t_provision_start

        sbx_dir = self.base_dir / config.sandbox_id
        profile_path = sbx_dir / 'sandbox.sb'
        exec_env = self._build_env(config, sbx_dir)
        work_dir = config.cwd or str(workspace)

        # Wrap command with sandbox-exec
        wrapped_cmd = f"sandbox-exec -f {shlex.quote(str(profile_path))} /bin/zsh -c {shlex.quote(command)}"

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
        proc = await asyncio.create_subprocess_shell(
            wrapped_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=exec_env,
            cwd=work_dir,
            start_new_session=True,  # Process group isolation for clean killpg
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
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                await asyncio.sleep(0.5)
                if proc.returncode is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
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
        """Remove the sandbox directory tree."""
        import shutil
        sbx_dir = self.base_dir / sandbox_id
        if sbx_dir.exists():
            shutil.rmtree(sbx_dir, ignore_errors=True)
            logger.info("Torn down Seatbelt sandbox %s", sandbox_id)
