from __future__ import annotations
import asyncio
import logging
import os
import platform
import shutil
import socket
import time
from pathlib import Path
from uuid import uuid4

import websockets
from websockets.asyncio.client import connect

from hivemind.protocol.messages import (
    parse_message, serialize_message,
    AuthRequest, AuthResponse, ExecRequest, ExecStdout, ExecStderr, ExecExit,
    SessionStart, SessionInput, SessionOutput, SessionClosed,
    FilePush, FilePull, FileData,
    Ping, Pong, ErrorMessage, SandboxDestroy,
)
from hivemind.daemon.executor import Executor
from hivemind.daemon.hardware import get_hardware_specs, get_cpu_utilization, get_memory_utilization

logger = logging.getLogger(__name__)

class DaemonAgent:
    """The daemon agent that maintains a persistent WebSocket to the control plane.
    
    This is the core of the 'herds child' equivalent. It:
    1. Connects to the control plane via outbound WebSocket (NAT traversal)
    2. Authenticates with a device token
    3. Receives exec requests and dispatches them to the Executor
    4. Streams results (stdout/stderr/exit) back up the WebSocket
    5. Handles reconnection with exponential backoff
    """
    
    def __init__(
        self,
        control_plane_url: str,
        device_token: str,
        tags: list[str] | None = None,
    ):
        self.control_plane_url = control_plane_url.rstrip('/')
        self.device_token = device_token
        self.tags = tags or []
        self.executor = Executor()
        self._ws = None
        self._running = False
        self._reconnect_delay = 1.0  # Start at 1s, max 60s
        self._max_reconnect_delay = 60.0
    
    @property
    def ws_url(self) -> str:
        base = self.control_plane_url.replace('http://', 'ws://').replace('https://', 'wss://')
        return f'{base}/ws/daemon'
    
    async def _authenticate(self, ws) -> bool:
        """Send auth request with hardware specs and wait for response."""
        hw = get_hardware_specs()
        auth_msg = AuthRequest(
            device_token=self.device_token,
            hostname=socket.gethostname(),
            arch=platform.machine(),
            os_version=platform.mac_ver()[0] or platform.release(),
            tags=self.tags,
            chip=hw.chip,
            cpu_cores=hw.cpu_cores,
            ram_gb=hw.ram_gb,
            cpu_percent=hw.cpu_percent,
            memory_percent=hw.memory_percent,
        )
        await ws.send(serialize_message(auth_msg))
        
        raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        response = parse_message(raw)
        
        if isinstance(response, AuthResponse) and response.success:
            logger.info(f'Authenticated as machine {response.machine_id} ({hw.chip}, {hw.ram_gb}GB RAM, {hw.cpu_cores} cores)')
            return True
        else:
            error = getattr(response, 'error', 'Unknown auth error')
            logger.error(f'Authentication failed: {error}')
            return False
    
    async def _handle_exec_request(self, ws, msg: ExecRequest) -> None:
        """Handle an exec request by running the command and streaming output."""
        async def on_stdout(data: str):
            out_msg = ExecStdout(request_id=msg.request_id, data=data)
            await ws.send(serialize_message(out_msg))
        
        async def on_stderr(data: str):
            err_msg = ExecStderr(request_id=msg.request_id, data=data)
            await ws.send(serialize_message(err_msg))
        
        result = await self.executor.execute(
            command=msg.command,
            request_id=msg.request_id,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            sandbox_id=msg.sandbox_id,
            env=msg.env,
            cwd=msg.cwd,
            timeout=msg.timeout,
            inherit_home=msg.inherit_home,
            backend=getattr(msg, "backend", "seatbelt"),
        )
        
        exit_msg = ExecExit(
            request_id=msg.request_id,
            exit_code=result.exit_code,
            duration_s=result.duration_s,
        )
        await ws.send(serialize_message(exit_msg))
    
    async def _message_loop(self, ws) -> None:
        """Main loop: receive messages and dispatch."""
        async for raw in ws:
            try:
                msg = parse_message(raw)
            except Exception as e:
                logger.warning(f'Failed to parse message: {e}')
                continue
            
            if isinstance(msg, ExecRequest):
                # Run in background so we can handle multiple concurrent requests
                asyncio.create_task(self._handle_exec_request(ws, msg))
            elif isinstance(msg, SandboxDestroy):
                asyncio.create_task(self._handle_sandbox_destroy(msg))
            elif isinstance(msg, Ping):
                pong = Pong(request_id=msg.request_id)
                await ws.send(serialize_message(pong))
            else:
                logger.debug(f'Unhandled message type: {msg.type}')

    async def _handle_sandbox_destroy(self, msg: SandboxDestroy) -> None:
        """Physically delete a sandbox directory from disk."""
        sandbox_base = Path(os.environ.get("HIVEMIND_HOME", str(Path.home() / ".hivemind"))) / "sandboxes"
        sandbox_dir = sandbox_base / msg.sandbox_id

        # Path traversal protection: ensure resolved path is inside sandbox_base
        try:
            resolved = sandbox_dir.resolve()
            base_resolved = sandbox_base.resolve()
            if not str(resolved).startswith(str(base_resolved) + os.sep):
                logger.error(f'Sandbox destroy rejected: path traversal detected for {msg.sandbox_id!r}')
                return
        except Exception as e:
            logger.error(f'Sandbox destroy path resolution error: {e}')
            return

        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
            logger.info(f'Sandbox {msg.sandbox_id!r} physically destroyed at {sandbox_dir}')
        else:
            logger.warning(f'Sandbox directory does not exist: {sandbox_dir}')

    
    async def _heartbeat_loop(self, ws) -> None:
        """Periodically stream resource telemetry (CPU/Memory %) to the control plane."""
        try:
            while self._running:
                await asyncio.sleep(5.0)
                ping = Ping(
                    cpu_percent=get_cpu_utilization(),
                    memory_percent=get_memory_utilization(),
                )
                await ws.send(serialize_message(ping))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f'Heartbeat error: {e}')

    async def run(self) -> None:
        """Main run loop with reconnection logic."""
        self._running = True
        
        while self._running:
            try:
                logger.info(f'Connecting to {self.ws_url}...')
                async with connect(self.ws_url) as ws:
                    self._ws = ws
                    self._reconnect_delay = 1.0  # Reset on successful connect
                    
                    if not await self._authenticate(ws):
                        logger.error('Auth failed, retrying...')
                        await asyncio.sleep(self._reconnect_delay)
                        continue
                    
                    logger.info('Connected and authenticated. Listening for commands...')
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                    try:
                        await self._message_loop(ws)
                    finally:
                        heartbeat_task.cancel()
                        
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                logger.warning(f'Connection lost: {e}. Reconnecting in {self._reconnect_delay:.1f}s...')
            except Exception as e:
                logger.error(f'Unexpected error: {e}. Reconnecting in {self._reconnect_delay:.1f}s...')
            finally:
                self._ws = None
            
            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
    
    async def stop(self) -> None:
        """Gracefully stop the daemon."""
        self._running = False
        if self._ws:
            await self._ws.close()
