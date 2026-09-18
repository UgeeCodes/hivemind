from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Iterator

import httpx
import websockets
from websockets.sync.client import connect as ws_connect

logger = logging.getLogger(__name__)

DEFAULT_URL = 'http://localhost:8000'

# Global configuration
_config = {
    'url': os.environ.get('HIVEMIND_CONTROL_PLANE', DEFAULT_URL),
    'token': os.environ.get('HIVEMIND_API_KEY', ''),
}

def configure(url: str | None = None, token: str | None = None) -> None:
    """Set global SDK configuration."""
    if url:
        _config['url'] = url
    if token:
        _config['token'] = token

def _headers() -> dict[str, str]:
    tok = _config['token'] or 'hm_sk_default_admin_key'
    return {'Authorization': f'Bearer {tok}'}

def _base_url() -> str:
    return _config['url'].rstrip('/')

@dataclass
class Result:
    """Result of a command execution."""
    stdout: str = ''
    stderr: str = ''
    exit_code: int = 0
    duration_s: float = 0.0
    job_id: str = ''
    machine_id: str = ''

@dataclass
class Mac:
    """Represents a connection to a Mac in your fleet.
    
    Usage:
        mac = hivemind.mac()  # auto-selects idlest machine
        mac = hivemind.mac(machine_id='my-mac')
        result = mac.run('uname -a')
        print(result.stdout)
    """
    machine_id: str | None = None
    url: str | None = None
    token: str | None = None
    
    def _get_url(self) -> str:
        return (self.url or _base_url()).rstrip('/')
    
    def _get_headers(self) -> dict[str, str]:
        token = self.token or _config['token'] or 'hm_sk_default_admin_key'
        return {'Authorization': f'Bearer {token}'}
    
    def run(
        self,
        command: str,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        sandbox_id: str | None = None,
        timeout: float | None = None,
        inherit_home: bool = False,
        stream: bool = False,
    ) -> Result:
        """Execute a command on this Mac.
        
        Args:
            command: Shell command to run
            env: Additional environment variables
            cwd: Working directory
            sandbox_id: Run in a specific sandbox
            timeout: Timeout in seconds
            inherit_home: If True, use the real HOME directory
            stream: If True, print output as it arrives
        
        Returns:
            Result with stdout, stderr, exit_code, duration_s
        """
        url = self._get_url()
        headers = self._get_headers()
        
        # Submit the exec request
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f'{url}/api/exec',
                json={
                    'command': command,
                    'machine_id': self.machine_id,
                    'env': env or {},
                    'cwd': cwd,
                    'sandbox_id': sandbox_id,
                    'timeout': timeout,
                    'inherit_home': inherit_home,
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        
        job_id = data['job_id']
        machine_id = data['machine_id']
        
        # Stream results via WebSocket
        ws_url = url.replace('http://', 'ws://').replace('https://', 'wss://')
        
        stdout_parts = []
        stderr_parts = []
        exit_code = 0
        duration_s = 0.0
        
        with ws_connect(f'{ws_url}/ws/stream/{job_id}') as ws:
            for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                    
                msg_type = msg.get('type')
                if msg_type == 'exec_stdout':
                    stdout_parts.append(msg['data'])
                    if stream:
                        print(msg['data'], end='', flush=True)
                elif msg_type == 'exec_stderr':
                    stderr_parts.append(msg['data'])
                    if stream:
                        import sys
                        print(msg['data'], end='', file=sys.stderr, flush=True)
                elif msg_type == 'exec_exit':
                    exit_code = msg['exit_code']
                    duration_s = msg.get('duration_s', 0.0)
                    break
        
        return Result(
            stdout=''.join(stdout_parts),
            stderr=''.join(stderr_parts),
            exit_code=exit_code,
            duration_s=duration_s,
            job_id=job_id,
            machine_id=machine_id,
        )
    
    def stream(self, command: str, **kwargs) -> Iterator[tuple[str, str]]:
        """Execute a command and yield (stream_name, data) tuples.
        
        Yields:
            ('stdout', data) or ('stderr', data) tuples
        """
        url = self._get_url()
        headers = self._get_headers()
        
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f'{url}/api/exec',
                json={'command': command, 'machine_id': self.machine_id, **kwargs},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        
        job_id = data['job_id']
        ws_url = url.replace('http://', 'ws://').replace('https://', 'wss://')
        
        with ws_connect(f'{ws_url}/ws/stream/{job_id}') as ws:
            for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get('type')
                if msg_type == 'exec_stdout':
                    yield ('stdout', msg['data'])
                elif msg_type == 'exec_stderr':
                    yield ('stderr', msg['data'])
                elif msg_type == 'exec_exit':
                    return
    
    def sandbox(self, name: str | None = None) -> Sandbox:
        """Get or create a sandbox on this Mac."""
        return Sandbox(mac=self, name=name)
    
    def shell(self) -> None:
        """Open an interactive shell session to this Mac."""
        # This is implemented in the CLI, not the SDK
        raise NotImplementedError('Use `hivemind shell` CLI command for interactive shells')


@dataclass
class Sandbox:
    """An isolated execution environment on a Mac."""
    mac: Mac
    name: str | None = None
    sandbox_id: str | None = None
    
    def exec(self, command: str, check: bool = False, **kwargs) -> Result:
        """Execute a command in this sandbox."""
        result = self.mac.run(command, sandbox_id=self.sandbox_id, **kwargs)
        if check and result.exit_code != 0:
            raise RuntimeError(f'Command failed with exit code {result.exit_code}: {result.stderr}')
        return result
    
    def put(self, local_path: str, remote_path: str | None = None) -> None:
        """Upload a file to the sandbox. (Stub for now)"""
        raise NotImplementedError('File upload coming in Phase 5')
    
    def get(self, remote_path: str, local_path: str) -> None:
        """Download a file from the sandbox. (Stub for now)"""
        raise NotImplementedError('File download coming in Phase 5')
    
    def expose(self, port: int) -> str:
        """Expose a sandbox port as a public URL. (Stub for now)"""
        raise NotImplementedError('Port exposure coming in Phase 6')


@dataclass  
class Volume:
    """Persistent named storage across runs."""
    name: str
    
    @classmethod
    def from_name(cls, name: str) -> Volume:
        """Get or create a volume by name."""
        return cls(name=name)
    
    def get(self, remote_path: str, local_path: str) -> None:
        """Download a file from the volume. (Stub)"""
        raise NotImplementedError('Volume download coming soon')
    
    def put(self, local_path: str, remote_path: str | None = None) -> None:
        """Upload a file to the volume. (Stub)"""
        raise NotImplementedError('Volume upload coming soon')


def mac(
    machine_id: str | None = None,
    url: str | None = None,
    token: str | None = None,
) -> Mac:
    """Get a Mac from your fleet.
    
    Args:
        machine_id: Target a specific machine. If None, picks the idlest.
        url: Control plane URL. Defaults to HIVEMIND_CONTROL_PLANE env or localhost.
        token: API key. Defaults to HIVEMIND_API_KEY env.
    
    Returns:
        Mac instance ready for commands.
    """
    return Mac(machine_id=machine_id, url=url, token=token)


def fleet(url: str | None = None, token: str | None = None) -> list[Mac]:
    """Get all online Macs in your fleet."""
    base = (url or _base_url()).rstrip('/')
    tok = token or _config['token'] or 'hm_sk_default_admin_key'
    headers = {'Authorization': f'Bearer {tok}'}
    
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f'{base}/api/machines', headers=headers)
        resp.raise_for_status()
        data = resp.json()
        machines = data if isinstance(data, list) else data.get('machines', [])
    
    return [Mac(machine_id=m['machine_id'], url=url, token=token) for m in machines]
