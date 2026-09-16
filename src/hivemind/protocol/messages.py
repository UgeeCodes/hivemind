"""
WebSocket protocol message definitions for the hivemind project.

This module defines all message types exchanged over WebSocket between
the control plane, daemon, and SDK clients using a discriminated union pattern.
"""
from __future__ import annotations

import time
from typing import Annotated, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter


# Base
class Message(BaseModel):
    """Base class for all WebSocket messages."""
    type: str
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: float = Field(default_factory=time.time)


# Auth
class AuthRequest(Message):
    """Sent from daemon to control plane to authenticate."""
    type: Literal['auth_request'] = 'auth_request'
    device_token: str
    hostname: str
    arch: str
    os_version: str
    tags: list[str] = []


class AuthResponse(Message):
    """Sent from control plane to daemon as a response to AuthRequest."""
    type: Literal['auth_response'] = 'auth_response'
    success: bool
    machine_id: Optional[str] = None
    error: Optional[str] = None


# Execution
class ExecRequest(Message):
    """Sent from control plane to daemon to request command execution."""
    type: Literal['exec_request'] = 'exec_request'
    command: str
    env: dict[str, str] = {}
    cwd: Optional[str] = None
    sandbox_id: Optional[str] = None
    timeout: Optional[float] = None
    inherit_home: bool = False


class ExecStdout(Message):
    """Sent from daemon (via control plane) to SDK containing stdout data."""
    type: Literal['exec_stdout'] = 'exec_stdout'
    data: str


class ExecStderr(Message):
    """Sent from daemon (via control plane) to SDK containing stderr data."""
    type: Literal['exec_stderr'] = 'exec_stderr'
    data: str


class ExecExit(Message):
    """Sent from daemon to indicate a command has finished."""
    type: Literal['exec_exit'] = 'exec_exit'
    exit_code: int
    duration_s: float


# Sessions (persistent processes)
class SessionStart(Message):
    """Sent to start a persistent session process."""
    type: Literal['session_start'] = 'session_start'
    command: str
    env: dict[str, str] = {}
    sandbox_id: Optional[str] = None


class SessionInput(Message):
    """Sent to provide stdin input to a running session."""
    type: Literal['session_input'] = 'session_input'
    session_id: str
    data: str


class SessionOutput(Message):
    """Sent from daemon containing output from a running session."""
    type: Literal['session_output'] = 'session_output'
    session_id: str
    stream: Literal['stdout', 'stderr']
    data: str


class SessionClosed(Message):
    """Sent when a session process has closed."""
    type: Literal['session_closed'] = 'session_closed'
    session_id: str
    exit_code: int


# File transfer
class FilePush(Message):
    """Sent to push a file to the remote system."""
    type: Literal['file_push'] = 'file_push'
    path: str
    content_b64: str
    mode: int = 0o644


class FilePull(Message):
    """Sent to request a file from the remote system."""
    type: Literal['file_pull'] = 'file_pull'
    path: str


class FileData(Message):
    """Sent as a response to FilePull, containing file content."""
    type: Literal['file_data'] = 'file_data'
    path: str
    content_b64: str
    size: int


# Heartbeat
class Ping(Message):
    """Ping message for keep-alive."""
    type: Literal['ping'] = 'ping'


class Pong(Message):
    """Pong response for keep-alive."""
    type: Literal['pong'] = 'pong'


# Error
class ErrorMessage(Message):
    """Sent when an error occurs."""
    type: Literal['error'] = 'error'
    error: str
    code: Optional[str] = None


# Discriminated union of all possible messages
AnyMessage = Annotated[
    Union[
        AuthRequest,
        AuthResponse,
        ExecRequest,
        ExecStdout,
        ExecStderr,
        ExecExit,
        SessionStart,
        SessionInput,
        SessionOutput,
        SessionClosed,
        FilePush,
        FilePull,
        FileData,
        Ping,
        Pong,
        ErrorMessage,
    ],
    Field(discriminator='type')
]

_message_adapter = TypeAdapter(AnyMessage)


def parse_message(raw: Union[str, bytes]) -> AnyMessage:
    """Parse a raw JSON string into the appropriate Message subclass."""
    return _message_adapter.validate_json(raw)


def serialize_message(msg: Message) -> str:
    """Serialize a Message to JSON string."""
    return msg.model_dump_json()
