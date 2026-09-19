from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite


class Store:
    """
    Manages all persistent state for the control plane using SQLite.
    """
    def __init__(self, db_path: str = 'hivemind.db'):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        conn = await self._get_conn()
        await conn.executescript('''
            CREATE TABLE IF NOT EXISTS machines (
                id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                arch TEXT NOT NULL,
                os_version TEXT NOT NULL,
                tags TEXT DEFAULT '[]',  -- JSON array
                chip TEXT,
                cpu_cores INTEGER,
                ram_gb INTEGER,
                cpu_percent REAL,
                memory_percent REAL,
                device_token_hash TEXT NOT NULL UNIQUE,
                owner_id TEXT NOT NULL,
                status TEXT DEFAULT 'offline',  -- online | offline | busy
                last_seen_at REAL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY,
                key_prefix TEXT NOT NULL,  -- first 8 chars for display
                name TEXT,
                owner_id TEXT NOT NULL,
                scopes TEXT DEFAULT '["admin"]',  -- JSON array: admin | run | read
                expires_at REAL,  -- NULL = never
                revoked_at REAL,  -- NULL = active
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                machine_id TEXT NOT NULL,
                api_key_prefix TEXT,
                command TEXT NOT NULL,
                status TEXT DEFAULT 'pending',  -- pending | running | completed | failed | timeout
                exit_code INTEGER,
                sandbox_id TEXT,
                stdout TEXT DEFAULT '',
                stderr TEXT DEFAULT '',
                started_at REAL,
                completed_at REAL,
                created_at REAL NOT NULL,
                FOREIGN KEY (machine_id) REFERENCES machines(id)
            );

            CREATE TABLE IF NOT EXISTS sandboxes (
                id TEXT PRIMARY KEY,
                machine_id TEXT NOT NULL,
                name TEXT,
                dir_path TEXT NOT NULL,
                status TEXT DEFAULT 'active',  -- active | destroyed
                created_at REAL NOT NULL,
                last_used_at REAL,
                FOREIGN KEY (machine_id) REFERENCES machines(id)
            );

            CREATE TABLE IF NOT EXISTS volumes (
                name TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                machine_id TEXT,
                path TEXT,
                size_bytes INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
        ''')
        # Migrate existing tables to ensure hardware columns exist
        for col_def in ['chip TEXT', 'cpu_cores INTEGER', 'ram_gb INTEGER', 'cpu_percent REAL', 'memory_percent REAL']:
            try:
                await conn.execute(f'ALTER TABLE machines ADD COLUMN {col_def}')
            except Exception:
                pass
        # Migrate existing jobs table to ensure output columns exist
        for col_def in ['stdout TEXT DEFAULT ""', 'stderr TEXT DEFAULT ""']:
            try:
                await conn.execute(f'ALTER TABLE jobs ADD COLUMN {col_def}')
            except Exception:
                pass
        await conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _row_to_dict(self, row: aiosqlite.Row | None, json_cols: list[str] = []) -> dict[str, Any] | None:
        if row is None:
            return None
        d = dict(row)
        for col in json_cols:
            if col in d and d[col] is not None:
                try:
                    d[col] = json.loads(d[col])
                except json.JSONDecodeError:
                    d[col] = []
        return d

    # Machine methods
    async def register_machine(
        self,
        machine_id: str,
        hostname: str,
        arch: str,
        os_version: str,
        device_token_hash: str,
        owner_id: str,
        tags: list[str] | None = None,
        chip: str | None = None,
        cpu_cores: int | None = None,
        ram_gb: int | None = None,
        cpu_percent: float | None = None,
        memory_percent: float | None = None,
    ) -> None:
        """Register a new machine or update existing one."""
        conn = await self._get_conn()
        tags_json = json.dumps(tags or [])
        now = time.time()
        
        await conn.execute('''
            INSERT INTO machines (
                id, hostname, arch, os_version, tags, chip, cpu_cores, ram_gb, cpu_percent, memory_percent, device_token_hash, owner_id, status, last_seen_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'online', ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                hostname=excluded.hostname,
                arch=excluded.arch,
                os_version=excluded.os_version,
                tags=excluded.tags,
                chip=coalesce(excluded.chip, machines.chip),
                cpu_cores=coalesce(excluded.cpu_cores, machines.cpu_cores),
                ram_gb=coalesce(excluded.ram_gb, machines.ram_gb),
                cpu_percent=coalesce(excluded.cpu_percent, machines.cpu_percent),
                memory_percent=coalesce(excluded.memory_percent, machines.memory_percent),
                device_token_hash=excluded.device_token_hash,
                owner_id=excluded.owner_id,
                status='online',
                last_seen_at=excluded.last_seen_at
        ''', (machine_id, hostname, arch, os_version, tags_json, chip, cpu_cores, ram_gb, cpu_percent, memory_percent, device_token_hash, owner_id, now, now))
        await conn.commit()

    async def update_machine_telemetry(self, machine_id: str, cpu_percent: float | None, memory_percent: float | None) -> None:
        """Update live CPU and memory utilization for an online machine."""
        conn = await self._get_conn()
        await conn.execute(
            'UPDATE machines SET cpu_percent = ?, memory_percent = ?, last_seen_at = ? WHERE id = ?',
            (cpu_percent, memory_percent, time.time(), machine_id)
        )
        await conn.commit()

    async def get_machine(self, machine_id: str) -> dict[str, Any] | None:
        """Retrieve a machine by its ID."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM machines WHERE id = ?', (machine_id,)) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row, json_cols=['tags'])

    async def get_machine_by_token_hash(self, device_token_hash: str) -> dict[str, Any] | None:
        """Retrieve a machine by its device token hash."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM machines WHERE device_token_hash = ?', (device_token_hash,)) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row, json_cols=['tags'])

    async def get_machine_by_hostname(self, hostname: str, owner_id: str) -> dict[str, Any] | None:
        """Retrieve a machine by its hostname and owner."""
        conn = await self._get_conn()
        async with conn.execute(
            'SELECT * FROM machines WHERE hostname = ? AND owner_id = ? ORDER BY last_seen_at DESC LIMIT 1',
            (hostname, owner_id)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row, json_cols=['tags'])

    async def list_machines(self, owner_id: str) -> list[dict[str, Any]]:
        """List all machines for a specific owner."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM machines WHERE owner_id = ? ORDER BY created_at DESC', (owner_id,)) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(r, json_cols=['tags']) for r in rows if r is not None]  # type: ignore

    async def update_machine_status(self, machine_id: str, status: str) -> None:
        """Update the status of a machine."""
        conn = await self._get_conn()
        await conn.execute('UPDATE machines SET status = ? WHERE id = ?', (status, machine_id))
        await conn.commit()

    async def update_machine_last_seen(self, machine_id: str) -> None:
        """Update the last_seen_at timestamp for a machine."""
        conn = await self._get_conn()
        await conn.execute('UPDATE machines SET last_seen_at = ? WHERE id = ?', (time.time(), machine_id))
        await conn.commit()

    # API key methods
    async def create_api_key(
        self,
        key_hash: str,
        key_prefix: str,
        name: str | None,
        owner_id: str,
        scopes: list[str],
        expires_at: float | None = None
    ) -> None:
        """Create a new API key."""
        conn = await self._get_conn()
        scopes_json = json.dumps(scopes)
        now = time.time()
        await conn.execute('''
            INSERT INTO api_keys (key_hash, key_prefix, name, owner_id, scopes, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (key_hash, key_prefix, name, owner_id, scopes_json, expires_at, now))
        await conn.commit()

    async def get_api_key(self, key_hash: str) -> dict[str, Any] | None:
        """Retrieve an API key by its hash."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM api_keys WHERE key_hash = ?', (key_hash,)) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row, json_cols=['scopes'])

    async def list_api_keys(self, owner_id: str) -> list[dict[str, Any]]:
        """List all API keys for an owner."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM api_keys WHERE owner_id = ? ORDER BY created_at DESC', (owner_id,)) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(r, json_cols=['scopes']) for r in rows if r is not None]  # type: ignore

    async def revoke_api_key(self, key_hash: str) -> None:
        """Revoke an API key by hash."""
        conn = await self._get_conn()
        await conn.execute('UPDATE api_keys SET revoked_at = ? WHERE key_hash = ?', (time.time(), key_hash))
        await conn.commit()

    async def revoke_api_key_by_prefix(self, key_prefix: str, owner_id: str | None = None) -> bool:
        """Revoke an API key by prefix."""
        conn = await self._get_conn()
        query = 'UPDATE api_keys SET revoked_at = ? WHERE key_prefix = ?'
        params: list[Any] = [time.time(), key_prefix]
        if owner_id:
            query += ' AND owner_id = ?'
            params.append(owner_id)
        cursor = await conn.execute(query, tuple(params))
        await conn.commit()
        return cursor.rowcount > 0

    async def validate_api_key(self, key_hash: str, required_scope: str) -> bool:
        """Validate if an API key is active and has the required scope."""
        key = await self.get_api_key(key_hash)
        if not key:
            return False
        
        if key['revoked_at'] is not None:
            return False
            
        if key['expires_at'] is not None and key['expires_at'] < time.time():
            return False
            
        scopes = key.get('scopes', [])
        if 'admin' in scopes:
            return True
        return required_scope in scopes

    # Job methods
    async def create_job(
        self,
        job_id: str,
        machine_id: str,
        command: str,
        api_key_prefix: str | None = None,
        sandbox_id: str | None = None
    ) -> None:
        """Create a new job."""
        conn = await self._get_conn()
        now = time.time()
        await conn.execute('''
            INSERT INTO jobs (id, machine_id, api_key_prefix, command, sandbox_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (job_id, machine_id, api_key_prefix, command, sandbox_id, now))
        await conn.commit()

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        exit_code: int | None = None
    ) -> None:
        """Update the status of a job."""
        conn = await self._get_conn()
        now = time.time()
        
        updates = ['status = ?']
        params: list[Any] = [status]
        
        if status == 'running':
            updates.append('started_at = ?')
            params.append(now)
        elif status in ('completed', 'failed', 'timeout'):
            updates.append('completed_at = ?')
            params.append(now)
            if exit_code is not None:
                updates.append('exit_code = ?')
                params.append(exit_code)
                
        params.append(job_id)
        
        query = f'UPDATE jobs SET {", ".join(updates)} WHERE id = ?'
        await conn.execute(query, tuple(params))
        await conn.commit()

        if status in ('completed', 'failed', 'timeout'):
            await self.prune_jobs(keep=25)

    async def append_job_output(
        self,
        job_id: str,
        stdout: str = '',
        stderr: str = '',
        max_chars: int = 65536,
    ) -> None:
        """Append stdout and/or stderr to a job, capped at max_chars."""
        if not stdout and not stderr:
            return
        conn = await self._get_conn()
        if stdout:
            await conn.execute(
                '''
                UPDATE jobs 
                SET stdout = substr(COALESCE(stdout, '') || ?, -?)
                WHERE id = ?
                ''',
                (stdout, max_chars, job_id)
            )
        if stderr:
            await conn.execute(
                '''
                UPDATE jobs 
                SET stderr = substr(COALESCE(stderr, '') || ?, -?)
                WHERE id = ?
                ''',
                (stderr, max_chars, job_id)
            )
        await conn.commit()

    async def prune_jobs(self, keep: int = 25) -> int:
        """Prune old jobs to retain only the most recent `keep` runs."""
        conn = await self._get_conn()
        cursor = await conn.execute(
            '''
            DELETE FROM jobs 
            WHERE id NOT IN (
                SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?
            )
            ''',
            (keep,)
        )
        deleted = cursor.rowcount
        await conn.commit()
        return deleted

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve a job by its ID."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row)

    async def list_jobs(self, machine_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        """List recent jobs, optionally filtered by machine."""
        conn = await self._get_conn()
        query = 'SELECT * FROM jobs'
        params: tuple[Any, ...] = ()
        
        if machine_id:
            query += ' WHERE machine_id = ?'
            params = (machine_id,)
            
        query += ' ORDER BY created_at DESC LIMIT ?'
        params = params + (limit,)
        
        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows if r is not None]  # type: ignore

    # Sandbox methods
    async def register_sandbox(self, sandbox_id: str, machine_id: str, name: str | None = None, dir_path: str = "") -> None:
        """Register or update a sandbox."""
        conn = await self._get_conn()
        now = time.time()
        await conn.execute('''
            INSERT INTO sandboxes (id, machine_id, name, dir_path, created_at, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET last_used_at = excluded.last_used_at
        ''', (sandbox_id, machine_id, name, dir_path, now, now))
        await conn.commit()

    async def list_sandboxes(self, machine_id: str | None = None) -> list[dict[str, Any]]:
        """List sandboxes, optionally filtered by machine."""
        conn = await self._get_conn()
        query = 'SELECT * FROM sandboxes WHERE status = "active"'
        params: tuple[Any, ...] = ()
        if machine_id:
            query += ' AND machine_id = ?'
            params = (machine_id,)
        query += ' ORDER BY created_at DESC'
        async with conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows if r is not None]  # type: ignore

    # Volume methods
    async def create_volume(self, name: str, owner_id: str) -> None:
        """Create a new volume."""
        conn = await self._get_conn()
        now = time.time()
        await conn.execute('''
            INSERT INTO volumes (name, owner_id, created_at)
            VALUES (?, ?, ?)
        ''', (name, owner_id, now))
        await conn.commit()

    async def get_volume(self, name: str) -> dict[str, Any] | None:
        """Retrieve a volume by its name."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM volumes WHERE name = ?', (name,)) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row)

    async def list_volumes(self, owner_id: str) -> list[dict[str, Any]]:
        """List all volumes for a specific owner."""
        conn = await self._get_conn()
        async with conn.execute('SELECT * FROM volumes WHERE owner_id = ? ORDER BY created_at DESC', (owner_id,)) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows if r is not None]  # type: ignore

    async def delete_volume(self, name: str) -> None:
        """Delete a volume."""
        conn = await self._get_conn()
        await conn.execute('DELETE FROM volumes WHERE name = ?', (name,))
        await conn.commit()
