from __future__ import annotations
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
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

# Default dev key for seamless local usage
DEFAULT_DEV_KEY = "hm_sk_default_admin_key"
DEFAULT_DEV_KEY_HASH = hash_token(DEFAULT_DEV_KEY)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store()
    await app.state.store.initialize()
    app.state.registry = WSRegistry()
    
    # Ensure default dev key exists in the store
    existing = await app.state.store.get_api_key(DEFAULT_DEV_KEY_HASH)
    if not existing:
        await app.state.store.create_api_key(
            key_hash=DEFAULT_DEV_KEY_HASH,
            key_prefix="hm_sk_default",
            name="Default Local Admin",
            owner_id="default_owner",
            scopes=["admin", "run", "read"]
        )
        logger.info("Initialized default admin key: %s", DEFAULT_DEV_KEY)
    
    yield
    await app.state.store.close()

app = FastAPI(title="Hivemind Control Plane", lifespan=lifespan)

# Allow CORS for Next.js dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from typing import Any, Optional, Union

class ExecRequestModel(BaseModel):
    command: str
    machine_id: Optional[str] = None
    env: dict[str, str] = {}
    cwd: Optional[str] = None
    sandbox_id: Optional[str] = None
    timeout: Optional[float] = None
    inherit_home: bool = False

class TokenCreateModel(BaseModel):
    name: Optional[str] = None
    scopes: list[str] = ["admin"]

async def get_owner_id(authorization: Optional[str] = Header(None, description="Bearer token")) -> tuple[str, list[str]]:
    """Extract and validate API key from Authorization header. Returns (owner_id, scopes)."""
    store: Store = app.state.store
    
    # If no auth header provided, allow default local dev owner
    if not authorization or not authorization.strip():
        return "default_owner", ["admin", "run", "read"]
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization[7:].strip()
    if not token:
        return "default_owner", ["admin", "run", "read"]
        
    if not token.startswith("hm_sk_"):
        raise HTTPException(status_code=401, detail="Invalid token format (must start with hm_sk_)")
        
    key_hash = hash_token(token)
    key_record = await store.get_api_key(key_hash)
    if not key_record or key_record.get("revoked_at") is not None:
        raise HTTPException(status_code=401, detail="Invalid or revoked token")
        
    if key_record.get("expires_at") and key_record["expires_at"] < time.time():
        raise HTTPException(status_code=401, detail="Token has expired")
        
    return key_record["owner_id"], key_record.get("scopes", ["admin"])

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
    store: Store = app.state.store
    
    # Combine online live registry machines and stored machines
    stored = await store.list_machines(owner_id)
    online_map = {m.machine_id: m for m in registry.list_online(owner_id)}
    
    machines = []
    seen_ids = set()
    for m in stored:
        mid = m["id"]
        seen_ids.add(mid)
        is_online = mid in online_map
        machines.append({
            "id": mid,
            "machine_id": mid,
            "hostname": m["hostname"],
            "arch": m["arch"],
            "os_version": m.get("os_version", "macOS"),
            "status": "online" if is_online else "offline",
            "tags": m.get("tags", []),
            "chip": m.get("chip") or "Apple Silicon",
            "cpu_cores": m.get("cpu_cores") or 8,
            "ram_gb": m.get("ram_gb") or 16,
            "cpu_percent": m.get("cpu_percent") or 0.0,
            "memory_percent": m.get("memory_percent") or 0.0,
        })
    
    # Include any in registry not yet persisted in store
    for mid, m in online_map.items():
        if mid not in seen_ids:
            machines.append({
                "id": mid,
                "machine_id": mid,
                "hostname": m.hostname,
                "arch": "arm64",
                "os_version": "macOS",
                "status": "online",
                "tags": m.tags,
                "chip": "Apple Silicon",
                "cpu_cores": 8,
                "ram_gb": 16,
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
            })
            
    return machines

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
    await store.create_job(
        job_id=job_id,
        machine_id=machine_id,
        command=req.command,
        sandbox_id=req.sandbox_id
    )
    
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

@app.get("/api/jobs")
async def list_jobs(auth_data: tuple[str, list[str]] = Depends(get_owner_id)):
    store: Store = app.state.store
    jobs = await store.list_jobs(limit=50)
    result = []
    for j in jobs:
        duration_ms = 0
        if j.get("completed_at") and j.get("started_at"):
            duration_ms = int((j["completed_at"] - j["started_at"]) * 1000)
        result.append({
            "id": j["id"],
            "command": j["command"],
            "status": j.get("status", "pending"),
            "machine_id": j.get("machine_id", ""),
            "duration_ms": duration_ms,
            "created_at": j.get("created_at")
        })
    return result

@app.get("/api/sandboxes")
async def list_sandboxes(auth_data: tuple[str, list[str]] = Depends(get_owner_id)):
    store: Store = app.state.store
    sandboxes = await store.list_sandboxes()
    return sandboxes

@app.get("/api/exec/{job_id}/stream")
async def stream_exec(job_id: str, auth_data: tuple[str, list[str]] = Depends(get_owner_id)):
    registry: WSRegistry = app.state.registry
    
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
            
        token_hash = hash_token(auth_msg.device_token)
        machine = await store.get_machine_by_token_hash(token_hash)
        
        if not machine:
            machine_id = f"mac_{uuid4().hex[:8]}"
            owner_id = "default_owner"
            await store.register_machine(
                machine_id=machine_id,
                hostname=auth_msg.hostname,
                arch=auth_msg.arch,
                os_version=auth_msg.os_version,
                device_token_hash=token_hash,
                owner_id=owner_id,
                tags=auth_msg.tags,
                chip=auth_msg.chip,
                cpu_cores=auth_msg.cpu_cores,
                ram_gb=auth_msg.ram_gb,
                cpu_percent=auth_msg.cpu_percent,
                memory_percent=auth_msg.memory_percent,
            )
        else:
            machine_id = machine["id"]
            owner_id = machine["owner_id"]
            await store.register_machine(
                machine_id=machine_id,
                hostname=auth_msg.hostname,
                arch=auth_msg.arch,
                os_version=auth_msg.os_version,
                device_token_hash=token_hash,
                owner_id=owner_id,
                tags=auth_msg.tags,
                chip=auth_msg.chip,
                cpu_cores=auth_msg.cpu_cores,
                ram_gb=auth_msg.ram_gb,
                cpu_percent=auth_msg.cpu_percent,
                memory_percent=auth_msg.memory_percent,
            )
            await store.update_machine_status(machine_id, "online")
            await store.update_machine_last_seen(machine_id)
            
        registry.register(
            machine_id=machine_id,
            owner_id=owner_id,
            hostname=auth_msg.hostname,
            ws=websocket,
            tags=auth_msg.tags
        )
        await websocket.send_text(serialize_message(AuthResponse(success=True, machine_id=machine_id)))
        
        while True:
            msg_raw = await websocket.receive_text()
            msg = parse_message(msg_raw)
            
            if isinstance(msg, Ping):
                if getattr(msg, "cpu_percent", None) is not None or getattr(msg, "memory_percent", None) is not None:
                    await store.update_machine_telemetry(machine_id, msg.cpu_percent, msg.memory_percent)
                await websocket.send_text(serialize_message(Pong(request_id=msg.request_id)))
            elif isinstance(msg, (ExecStdout, ExecStderr, ExecExit, ErrorMessage)):
                if hasattr(msg, "request_id"):
                    if isinstance(msg, ExecExit):
                        status = "completed" if msg.exit_code == 0 else "failed"
                        await store.update_job_status(msg.request_id, status, exit_code=msg.exit_code)
                    await registry.fan_out(msg.request_id, msg_raw)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Daemon WS error: %s", e)
    finally:
        if machine_id:
            registry.unregister(machine_id)
            try:
                await store.update_machine_status(machine_id, "offline")
            except Exception:
                pass

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
        logger.error("Client stream error: %s", e)
    finally:
        registry.remove_stream_listener(request_id, queue)

@app.post("/api/tokens")
async def create_token(req: TokenCreateModel, owner_id: str = Depends(require_admin)):
    store: Store = app.state.store
    full_key, key_hash, key_prefix = generate_api_key(name=req.name)
    
    await store.create_api_key(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=req.name,
        owner_id=owner_id,
        scopes=req.scopes
    )
    
    return {
        "id": key_prefix,
        "token": full_key,
        "prefix": key_prefix,
        "name": req.name,
        "scopes": req.scopes,
        "status": "active"
    }

@app.get("/api/tokens")
async def list_tokens(owner_id: str = Depends(require_admin)):
    store: Store = app.state.store
    keys = await store.list_api_keys(owner_id)
    tokens = []
    for k in keys:
        tokens.append({
            "id": k.get("key_prefix", ""),
            "prefix": k.get("key_prefix", ""),
            "name": k.get("name") or "Unnamed Token",
            "scopes": k.get("scopes", []),
            "created_at": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(k.get("created_at", time.time()))),
            "status": "revoked" if k.get("revoked_at") else "active"
        })
    return tokens

@app.delete("/api/tokens/{key_prefix}")
@app.post("/api/tokens/{key_prefix}/revoke")
async def revoke_token(key_prefix: str, owner_id: str = Depends(require_admin)):
    store: Store = app.state.store
    revoked = await store.revoke_api_key_by_prefix(key_prefix, owner_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Token not found or already revoked")
    return {"status": "revoked"}
