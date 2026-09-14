from __future__ import annotations
import asyncio
import logging
import os
import pty
import signal
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SANDBOX_BASE = Path.home() / '.hivemind' / 'sandboxes'

@dataclass
class ExecResult:
    exit_code: int
    duration_s: float

class Executor:
    """Manages command execution in isolated sandbox environments."""
    
    def __init__(self):
        self._active_processes: dict[str, asyncio.subprocess.Process] = {}  # request_id -> Process
        self._sessions: dict[str, asyncio.subprocess.Process] = {}  # session_id -> Process
    
    def _create_sandbox_dirs(self, sandbox_id: str) -> dict[str, Path]:
        """Create the sandbox directory tree: {workspace, tmp, home}."""
        base = SANDBOX_BASE / sandbox_id
        dirs = {
            'workspace': base / 'workspace',
            'tmp': base / 'tmp',
            'home': base / 'home',
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs
    
    def _build_sandbox_env(self, sandbox_dirs: dict[str, Path], extra_env: dict[str, str] | None = None, inherit_home: bool = False) -> dict[str, str]:
        """Build a clean environment for sandbox execution.
        
        Redirects HOME, TMPDIR, and common toolchain caches into the sandbox.
        Starts from a minimal allowlist (env -i style) and adds standard PATH.
        """
        home = str(Path.home()) if inherit_home else str(sandbox_dirs['home'])
        env = {
            'HOME': home,
            'TMPDIR': str(sandbox_dirs['tmp']),
            'PATH': '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
            'SHELL': '/bin/zsh',
            'TERM': 'xterm-256color',
            'LANG': 'en_US.UTF-8',
            # Redirect toolchain caches into sandbox
            'PIP_CACHE_DIR': str(sandbox_dirs['home'] / '.cache' / 'pip'),
            'npm_config_cache': str(sandbox_dirs['home'] / '.cache' / 'npm'),
            'CARGO_HOME': str(sandbox_dirs['home'] / '.cargo'),
            'XDG_CACHE_HOME': str(sandbox_dirs['home'] / '.cache'),
            'XDG_CONFIG_HOME': str(sandbox_dirs['home'] / '.config'),
            'XDG_DATA_HOME': str(sandbox_dirs['home'] / '.local' / 'share'),
        }
        # Add Homebrew and Xcode paths if they exist
        for extra_path in ['/opt/homebrew/bin', '/opt/homebrew/sbin']:
            if Path(extra_path).exists():
                env['PATH'] = f"{extra_path}:{env['PATH']}"
        # Add user-supplied env
        if extra_env:
            env.update(extra_env)
        return env
    
    async def execute(
        self,
        command: str,
        request_id: str,
        on_stdout: callable,  # async callback(data: str)
        on_stderr: callable,  # async callback(data: str)
        sandbox_id: str | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float | None = None,
        inherit_home: bool = False,
    ) -> ExecResult:
        """Execute a command in a sandbox and stream output via callbacks.
        
        Uses asyncio subprocess with a PTY for full interactive support.
        Manages the process in its own session (start_new_session=True) for clean teardown.
        """
        # Generate sandbox_id if not provided
        if sandbox_id is None:
            from uuid import uuid4
            sandbox_id = f'sbx_eph_{uuid4().hex[:12]}'
        
        sandbox_dirs = self._create_sandbox_dirs(sandbox_id)
        exec_env = self._build_sandbox_env(sandbox_dirs, env, inherit_home)
        work_dir = cwd or str(sandbox_dirs['workspace'])
        
        start = time.monotonic()
        
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=exec_env,
            cwd=work_dir,
            start_new_session=True,  # Own process group for clean killpg
        )
        self._active_processes[request_id] = proc
        
        async def read_stream(stream, callback):
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                await callback(chunk.decode('utf-8', errors='replace'))
        
        try:
            if timeout:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(proc.stdout, on_stdout),
                        read_stream(proc.stderr, on_stderr),
                    ),
                    timeout=timeout
                )
                await proc.wait()
            else:
                await asyncio.gather(
                    read_stream(proc.stdout, on_stdout),
                    read_stream(proc.stderr, on_stderr),
                )
                await proc.wait()
        except asyncio.TimeoutError:
            # Kill the entire process group
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                await asyncio.sleep(0.5)
                if proc.returncode is None:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            return ExecResult(exit_code=-1, duration_s=time.monotonic() - start)
        finally:
            self._active_processes.pop(request_id, None)
        
        return ExecResult(
            exit_code=proc.returncode or 0,
            duration_s=time.monotonic() - start,
        )
    
    async def cancel(self, request_id: str) -> bool:
        """Cancel a running execution by request_id."""
        proc = self._active_processes.get(request_id)
        if not proc:
            return False
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        return True
