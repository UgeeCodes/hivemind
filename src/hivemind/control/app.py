from __future__ import annotations
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from hivemind.control.store import Store
from hivemind.control.auth import hash_token, generate_api_key, generate_device_token
from hivemind.control.ws_registry import WSRegistry
from hivemind.protocol.messages import (
    parse_message, serialize_message,
    AuthRequest, AuthResponse, ExecRequest, ExecStdout, ExecStderr, ExecExit,
    ErrorMessage, Ping, Pong,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store()
    await app.state.store.initialize()
    app.state.registry = WSRegistry()
    yield
    await app.state.store.close()

app = FastAPI(title="Hivemind Control Plane", lifespan=lifespan)

class ExecRequestModel(BaseModel):
    command: str
    machine_id: str | None = None
    env: dict[str, str] = {}
    cwd: str | None = None
    sandbox_id: str | None = None
    timeout: float | None = None
    inherit_home: bool = False

class TokenCreateModel(BaseModel):
    name: str | None = None
    scopes: list[str] = ["admin"]

async def get_owner_id(authorization: str = Header(..., description="Bearer token")) -> tuple[str, list[str]]:
    """Extract and validate API key from Authorization header. Returns (owner_id, scopes)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization[7:]
    if not token.startswith("hm_sk_"):
        raise HTTPException(status_code=401, detail="Invalid token format")
        
    prefix = token.split("_")[2]
    store: Store = app.state.store
    
    key_record = await store.get_api_key(prefix)
    if not key_record or key_record.get("revoked"):
        raise HTTPException(status_code=401, detail="Invalid or revoked token")
        
    expected_hash = key_record["token_hash"]
    if hash_token(token) != expected_hash:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    return key_record["owner_id"], key_record.get("scopes", [])

def require_admin(auth_data: tuple[str, list[str]] = Depends(get_owner_id)) -> str:
    owner_id, scopes = auth_data
    if "admin" not in scopes:
        raise HTTPException(status_code=403, detail="Admin scope required")
    return owner_id

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/machines")
async def list_machines(auth_data: tuple[str, list[str]] = Depends(get_owner_id)):
    owner_id, _ = auth_data
    registry: WSRegistry = app.state.registry
    machines = registry.list_online(owner_id)
    return {"machines": [{"machine_id": m.machine_id, "hostname": m.hostname, "tags": m.tags} for m in machines]}

@app.post("/api/exec")
async def execute_command(req: ExecRequestModel, auth_data: tuple[str, list[str]] = Depends(get_owner_id)):
    owner_id, _ = auth_data
    registry: WSRegistry = app.state.registry
    store: Store = app.state.store
    
    machine_id = req.machine_id
    if not machine_id:
        machine = registry.get_idlest(owner_id)
        if not machine:
            raise HTTPException(status_code=404, detail="No online machines available")
        machine_id = machine.machine_id
    else:
        machine = registry.get(machine_id)
        if not machine or machine.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="Machine not found or offline")

    job_id = str(uuid4())
    await store.create_job(job_id=job_id, owner_id=owner_id, machine_id=machine_id, command=req.command)
    
    exec_msg = ExecRequest(
        request_id=job_id,
        command=req.command,
        env=req.env,
        cwd=req.cwd,
        sandbox_id=req.sandbox_id,
        timeout=req.timeout,
        inherit_home=req.inherit_home
    )
    
    await registry.send_to_machine(machine_id, serialize_message(exec_msg))
    
    return {"job_id": job_id, "machine_id": machine_id, "status": "submitted"}

@app.get("/api/exec/{job_id}/stream")
async def stream_exec(job_id: str, auth_data: tuple[str, list[str]] = Depends(get_owner_id)):
    owner_id, _ = auth_data
    registry: WSRegistry = app.state.registry
    
    # Normally check store to ensure job_id belongs to owner_id here
    
    async def event_generator():
        queue = registry.add_stream_listener(job_id)
        try:
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield f"{msg}\n"
        finally:
            registry.remove_stream_listener(job_id, queue)
            
    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@app.websocket("/ws/daemon")
async def daemon_ws(websocket: WebSocket):
    await websocket.accept()
    registry: WSRegistry = app.state.registry
    store: Store = app.state.store
    machine_id = None
    
    try:
        auth_msg_raw = await websocket.receive_text()
        auth_msg = parse_message(auth_msg_raw)
        
        if not isinstance(auth_msg, AuthRequest):
            await websocket.send_text(serialize_message(ErrorMessage(error="Expected AuthRequest")))
            await websocket.close(code=1008)
            return
            
        token = auth_msg.token
        device = await store.get_device_by_token(token)
        if not device:
            await websocket.send_text(serialize_message(AuthResponse(success=False, error="Invalid token")))
            await websocket.close(code=1008)
            return
            
        machine_id = auth_msg.machine_id
        owner_id = device["owner_id"]
        
        registry.register(
            machine_id=machine_id,
            owner_id=owner_id,
            hostname=auth_msg.hostname,
            ws=websocket
        )
        await websocket.send_text(serialize_message(AuthResponse(success=True)))
        
        while True:
            msg_raw = await websocket.receive_text()
            msg = parse_message(msg_raw)
            
            if isinstance(msg, Ping):
                await websocket.send_text(serialize_message(Pong(payload=msg.payload)))
            elif isinstance(msg, (ExecStdout, ExecStderr, ExecExit, ErrorMessage)):
                if hasattr(msg, "request_id"):
                    await registry.fan_out(msg.request_id, msg_raw)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Daemon WS error: {e}")
    finally:
        if machine_id:
            registry.unregister(machine_id)

@app.websocket("/ws/stream/{request_id}")
async def client_stream_ws(websocket: WebSocket, request_id: str):
    await websocket.accept()
    registry: WSRegistry = app.state.registry
    queue = registry.add_stream_listener(request_id)
    
    try:
        while True:
            msg = await queue.get()
            if msg is None:
                break
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Client stream error: {e}")
    finally:
        registry.remove_stream_listener(request_id, queue)

@app.post("/api/tokens")
async def create_token(req: TokenCreateModel, owner_id: str = Depends(require_admin)):
    store: Store = app.state.store
    prefix, token = generate_api_key()
    token_hash = hash_token(token)
    
    await store.create_api_key(
        prefix=prefix,
        token_hash=token_hash,
        owner_id=owner_id,
        name=req.name,
        scopes=req.scopes
    )
    
    return {"token": token, "prefix": prefix, "name": req.name, "scopes": req.scopes}

@app.get("/api/tokens")
async def list_tokens(owner_id: str = Depends(require_admin)):
    store: Store = app.state.store
    keys = await store.list_api_keys(owner_id)
    return {"keys": keys}

@app.delete("/api/tokens/{key_prefix}")
async def revoke_token(key_prefix: str, owner_id: str = Depends(require_admin)):
    store: Store = app.state.store
    await store.revoke_api_key(key_prefix, owner_id)
    return {"status": "revoked"}
