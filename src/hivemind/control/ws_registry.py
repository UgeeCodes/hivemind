from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class ConnectedMachine:
    machine_id: str
    owner_id: str
    hostname: str
    ws: Any  # Can be websockets ServerConnection or FastAPI WebSocket
    tags: list[str] = field(default_factory=list)

class WSRegistry:
    """In-memory registry of connected daemon WebSocket connections."""
    
    def __init__(self):
        self._machines: dict[str, ConnectedMachine] = {}  # machine_id -> ConnectedMachine
        self._pending_responses: dict[str, asyncio.Future] = {}  # request_id -> Future for exec results
        self._stream_listeners: dict[str, list[asyncio.Queue]] = {}  # request_id -> list of queues for streaming
        self._message_buffers: dict[str, list[str]] = {}  # request_id -> list of buffered messages
        self._completed_requests: set[str] = set()  # request_id that reached exec_exit
    
    def register(self, machine_id: str, owner_id: str, hostname: str, ws: Any, tags: list[str] = None) -> None:
        """Register a daemon connection."""
        if tags is None:
            tags = []
        self._machines[machine_id] = ConnectedMachine(
            machine_id=machine_id,
            owner_id=owner_id,
            hostname=hostname,
            ws=ws,
            tags=tags
        )
        logger.info(f"Registered machine {machine_id} for owner {owner_id}")
    
    def unregister(self, machine_id: str) -> None:
        """Unregister a daemon connection."""
        if machine_id in self._machines:
            del self._machines[machine_id]
            logger.info(f"Unregistered machine {machine_id}")
    
    def get(self, machine_id: str) -> ConnectedMachine | None:
        """Get a connected machine by ID."""
        return self._machines.get(machine_id)
    
    def get_idlest(self, owner_id: str) -> ConnectedMachine | None:
        """Get the 'idlest' available machine for an owner (for now, just first online)."""
        machines = self.list_online(owner_id)
        if not machines:
            return None
        return machines[0]
    
    def list_online(self, owner_id: str) -> list[ConnectedMachine]:
        """List all online machines for an owner."""
        return [m for m in self._machines.values() if m.owner_id == owner_id]
    
    async def send_to_machine(self, machine_id: str, message: str) -> None:
        """Send a WebSocket message to a specific daemon."""
        machine = self.get(machine_id)
        if not machine:
            logger.warning(f"Machine {machine_id} not found, cannot send message")
            return
        
        try:
            # Handle both FastAPI WebSocket and websockets ServerConnection
            if hasattr(machine.ws, 'send_text'):
                await machine.ws.send_text(message)
            else:
                await machine.ws.send(message)
        except Exception as e:
            logger.error(f"Error sending to machine {machine_id}: {e}")
            self.unregister(machine_id)
    
    def add_stream_listener(self, request_id: str) -> asyncio.Queue:
        """Add a streaming listener for a request_id. Returns a queue that will receive messages."""
        queue = asyncio.Queue()
        
        # Replay buffered messages if any already arrived
        if request_id in self._message_buffers:
            for msg in self._message_buffers[request_id]:
                queue.put_nowait(msg)
            if request_id in self._completed_requests:
                queue.put_nowait(None)
                
        if request_id not in self._stream_listeners:
            self._stream_listeners[request_id] = []
        self._stream_listeners[request_id].append(queue)
        return queue
    
    def remove_stream_listener(self, request_id: str, queue: asyncio.Queue) -> None:
        """Remove a streaming listener."""
        if request_id in self._stream_listeners:
            try:
                self._stream_listeners[request_id].remove(queue)
            except ValueError:
                pass
            if not self._stream_listeners[request_id]:
                del self._stream_listeners[request_id]
    
    async def fan_out(self, request_id: str, message: str) -> None:
        """Push a message to all listeners for a given request_id, buffering for late listeners."""
        if request_id not in self._message_buffers:
            self._message_buffers[request_id] = []
        self._message_buffers[request_id].append(message)
        
        is_exit = False
        try:
            msg_data = json.loads(message)
            if msg_data.get("type") == "exec_exit":
                is_exit = True
                self._completed_requests.add(request_id)
        except json.JSONDecodeError:
            pass

        listeners = self._stream_listeners.get(request_id, [])
        for queue in list(listeners):
            try:
                queue.put_nowait(message)
                if is_exit:
                    queue.put_nowait(None)
            except Exception as e:
                logger.error(f"Error putting message in stream queue for {request_id}: {e}")
