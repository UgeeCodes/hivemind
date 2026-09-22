# Hivemind

**Turn any Mac — or all of them — into a cloud.**

Hivemind is a programmable runtime for Apple Silicon. Connect one Mac or an entire fleet, then execute commands, run AI agents, and manage isolated workloads — all from a Python SDK, CLI, or MCP server.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![macOS Only](https://img.shields.io/badge/platform-macOS-lightgrey)](https://apple.com/macos)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         YOUR CODE                                │
│    Python SDK  ·  CLI  ·  MCP Server  ·  REST API                │
└──────────┬───────────────────────────────────────────────────────┘
           │  HTTPS / WebSocket
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE (FastAPI)                       │
│   Auth · Job Queue · SQLite Store · WebSocket Fan-Out            │
│   Dashboard (Next.js) on :3000                                   │
└──────────┬───────────────────────────────────────────────────────┘
           │  WebSocket (persistent)
           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     MAC DAEMON (per machine)                     │
│   Heartbeat · Hardware Telemetry · Execution Engine              │
│                                                                  │
│   ┌──────────────────────┐    ┌──────────────────────┐           │
│   │   Seatbelt Backend   │    │     Tart Backend     │           │
│   │   sandbox-exec(1)    │    │ Apple Virtualization │           │
│   │   <50ms startup      │    │ Full macOS microVM   │           │
│   │   Credential deny    │    │ Ephemeral clones     │           │
│   └──────────────────────┘    └──────────────────────┘           │
└──────────────────────────────────────────────────────────────────┘
```

### How the Pieces Fit Together

Hivemind is structured as a resilient three-tier distributed runtime:

1. **Client Tier (SDK, CLI, MCP Server)**:
   - Developers interact via Python (`import hivemind`), terminal commands (`hivemind run`), or AI assistants via MCP (`hivemind mcp`).
   - Every execution request is dispatched via HTTP POST (`/api/exec`) to the control plane, returning an immediate `job_id`.
   - The client then establishes a WebSocket connection to `/ws/stream/{job_id}` to receive live stdout, stderr, and exit code streams in real-time.

2. **Control Plane (FastAPI + aiosqlite)**:
   - **Central Coordination**: Tracks all registered machines, active jobs, and scoped authentication tokens.
   - **Intelligent Routing**: Automatically schedules workloads to the idlest Mac by calculating CPU and memory pressure from live machine heartbeats, or routes to specific machines based on tags and hardware specs.
   - **Event Fan-Out (`WSRegistry`)**: Buffers live output chunks and fans them out across multiple listening clients and dashboard observers simultaneously.

3. **Daemon Node (macOS LaunchAgent)**:
   - Runs on each Mac as a background LaunchAgent daemon (`hivemind child start`).
   - Maintains an outbound persistent WebSocket connection (`/ws/daemon`) to the control plane. Because the connection is outbound, **no open inbound ports or public IP addresses are required**.
   - Periodically samples host telemetry (Apple Silicon chip name, physical core count, RAM, CPU load, memory utilization) and sends heartbeats.
   - Spawns requested commands inside isolated execution sandboxes and streams stdio chunks back across the WebSocket connection.

---

## Design Decisions

### 1. Persistent Outbound WebSockets over SSH

- **The Problem with SSH**: Traditional fleet management relies on SSH. This demands managing and rotating SSH keys on every host, configuring firewall rules, forwarding ports, and handling NAT traversal when Macs reside behind dynamic IPs or residential networks.
- **The Hivemind Solution**: The daemon establishes an outbound WebSocket connection to the central control plane upon boot. The Mac can sit behind any NAT, VPN, or firewall without inbound exposure. Real-time bi-directional streaming is handled over a single persistent multiplexed socket.

### 2. Dual Isolation Model: Seatbelt vs. Tart MicroVMs

- **Process Isolation (`seatbelt`, Default)**:
  - Leverages macOS's native `sandbox-exec(1)` kernel mechanism.
  - Near-instant startup (<50ms) with zero memory footprint.
  - Automatically isolates filesystem writes to the sandbox folder while hard-denying access to developer credential stores (`~/.ssh`, `~/.aws`, `~/.docker`, `~/.gnupg`, etc.), keeping host credentials safe even during arbitrary code execution.
- **Hardware-Assisted MicroVMs (`tart`)**:
  - Uses Apple Silicon's native Virtualization Framework via Tart.
  - Each task executes inside a freshly cloned, fully isolated macOS guest VM.
  - Complete kernel-level isolation with automatic post-execution teardown and cleanup. If Tart is unavailable on the host, Hivemind automatically falls back to Seatbelt with a stderr diagnostic notice.

### 3. Keyless Agent Proxying

- Running autonomous agents (like Claude Code or OpenAI Codex) directly on remote execution nodes typically risks exposing model API keys to the environment where code runs.
- Hivemind decouples execution from model authorization: agent commands route LLM requests through a secure proxy URL (`--proxy`), ensuring that master API keys never reside on the worker Mac.

### 4. Native macOS `launchd` Daemon

- Rather than running ad-hoc background scripts or third-party process supervisors, Hivemind integrates with macOS's native `launchd` service architecture (`~/Library/LaunchAgents/`).
- The daemon starts automatically on system boot, gracefully restarts on crash, and logs stdout/stderr to standard macOS application log directories.

---

## 60-Second Quickstart

### 1. Install

```bash
pip install hivemind
```

Or from source:

```bash
git clone https://github.com/UgeeCodes/hivemind.git
cd hivemind
pip install -e .
```

### 2. Start the control plane

```bash
hivemind serve
```

### 3. Connect a Mac (in another terminal)

```bash
hivemind child start
```

### 4. Verify your fleet

```bash
hivemind machines
```

### 5. Run your first command

**CLI:**

```bash
hivemind run "sw_vers"
```

**Python:**

```python
import hivemind

mac = hivemind.mac()
result = mac.run("sw_vers")
print(result.stdout)       # macOS 15.5 ...
print(result.exit_code)    # 0
print(result.duration_s)   # 0.12
```

---

## Execution & Isolation Backends

Hivemind supports two isolation backends for sandboxed execution:

### Seatbelt (default)

The `seatbelt` backend uses macOS `sandbox-exec(1)` profiles for process-level isolation. It starts in under 50ms with zero overhead.

**What it does:**

- Allows reads globally (system libraries, toolchains)
- Restricts file writes to the sandbox directory only
- Blocks access to credential stores:
  - `~/.ssh`, `~/.aws`, `~/.config/gcloud`, `~/.docker`
  - `~/.gnupg`, `~/.netrc`, `~/.npmrc`
- Network access is allowed by default (configurable)

```bash
hivemind run "npm test"                 # sandboxed by default
hivemind run --real "brew install jq"   # use real HOME for host tools
```

### Tart (microVMs)

The `tart` backend uses [Tart](https://tart.run) to run commands inside ephemeral Apple Virtualization microVMs on Apple Silicon. Each execution gets a fresh VM clone that is destroyed after completion.

```bash
hivemind run --backend tart "swift build"
```

**Lifecycle:** clone base image → boot headless → exec command → stop → delete

If Tart is not installed, Hivemind automatically falls back to Seatbelt with a notice on stderr.

### The `--real` flag

By default, commands run with an isolated `HOME` directory. Pass `--real` (CLI) or `inherit_home=True` (SDK) to use the real user home, giving access to installed tools, dotfiles, and shell configuration.

---

## Agent Integration & MCP

### MCP Server (Claude Desktop, Cursor, etc.)

Hivemind ships an MCP server that gives AI assistants direct access to your Mac fleet. Available tools: `run`, `read_file`, `write_file`, `list_dir`, `screenshot`, `machines`.

**Start the server:**

```bash
hivemind mcp
```

**Configure in Claude Desktop or Cursor** (`mcpServers`):

```jsonc
"hivemind": {
  "command": "hivemind",
  "args": ["mcp"],
  "env": {
    "HIVEMIND_CONTROL_PLANE": "http://your-server:8000",
    "HIVEMIND_API_KEY": "hm_sk_..."
  }
}
```

### SKILL.md for Claude Code

Generate or install a SKILL.md that teaches Claude Code how to use Hivemind:

```bash
hivemind skill              # generate to ~/.hivemind/SKILL.md
hivemind skill --install    # install into ~/.claude/skills/
```

### Keyless Agent Dispatch

Run AI agents on remote Macs without exposing API keys. Model calls route through a proxy so credentials never touch the Mac:

```bash
hivemind agent "Refactor the auth module" --proxy https://proxy.example.com
hivemind agent "Run all tests" --harness codex --all   # run on every Mac
```

### Scoped API Tokens

Mint least-privilege tokens for agents and CI:

```bash
hivemind token new ci-runner --scope run     # can execute, can't mint keys
hivemind token new reader --scope read       # read-only fleet access
hivemind token ls                            # list all tokens
hivemind token revoke hm_sk_ab              # revoke by prefix
```

---

## Environment Variables

| Variable                 | Description                | Default                               |
| ------------------------ | -------------------------- | ------------------------------------- |
| `HIVEMIND_CONTROL_PLANE` | Control plane URL          | `http://localhost:8000`               |
| `HIVEMIND_API_KEY`       | API key for authentication | `hm_sk_default_admin_key` (local dev) |

Both the Python SDK and MCP server read these automatically.

---

## CLI Reference

### Top-Level Commands

| Command                     | Description                               | Key Flags                                                             |
| --------------------------- | ----------------------------------------- | --------------------------------------------------------------------- |
| `hivemind run "<cmd>"`      | Execute a command on a remote Mac         | `--machine`, `--timeout`, `--sandbox`, `--real`, `--backend`          |
| `hivemind machines`         | List online machines in your fleet        | —                                                                     |
| `hivemind shell`            | Interactive remote REPL (Ctrl+D to exit)  | `--machine`                                                           |
| `hivemind status`           | Show control plane URL and API key config | —                                                                     |
| `hivemind serve`            | Start the control plane server            | `--host`, `--port`                                                    |
| `hivemind mcp`              | Start the MCP server for AI assistants    | —                                                                     |
| `hivemind agent "<prompt>"` | Run an AI agent on a remote Mac           | `--proxy`, `--secret`, `--harness`, `--sandbox`, `--machine`, `--all` |
| `hivemind skill`            | Generate or install SKILL.md              | `--install`, `--output`                                               |

### Daemon Management (`hivemind child`)

| Command                 | Description                                  | Key Flags                                             |
| ----------------------- | -------------------------------------------- | ----------------------------------------------------- |
| `hivemind child start`  | Start daemon (connects Mac to control plane) | `--control-plane`, `--token`, `--tag`, `--foreground` |
| `hivemind child stop`   | Stop and uninstall the daemon                | —                                                     |
| `hivemind child status` | Check daemon running state and PID           | —                                                     |
| `hivemind child logs`   | View daemon logs                             | `-f` (follow)                                         |

The daemon installs as a macOS LaunchAgent for automatic restart on reboot. Use `--foreground` to run in the current terminal for debugging.

### Token Management (`hivemind token`)

| Command                          | Description                                         |
| -------------------------------- | --------------------------------------------------- |
| `hivemind token new <name>`      | Create a new API token (`--scope admin\|run\|read`) |
| `hivemind token ls`              | List all API tokens                                 |
| `hivemind token revoke <prefix>` | Revoke a token by its prefix                        |

### Volume Management (`hivemind volume`)

| Command                         | Description                   |
| ------------------------------- | ----------------------------- |
| `hivemind volume ls`            | List volumes (coming soon)    |
| `hivemind volume create <name>` | Create a volume (coming soon) |
| `hivemind volume rm <name>`     | Remove a volume (coming soon) |

---

## Python SDK Reference

### Getting a Mac

```python
import hivemind

# Auto-select the idlest machine
mac = hivemind.mac()

# Target a specific machine
mac = hivemind.mac(machine_id="mac_0276ffc3")

# Custom control plane
mac = hivemind.mac(url="http://remote:8000", token="hm_sk_...")
```

### Running Commands

```python
result = mac.run("uname -a")
print(result.stdout)       # Darwin ...
print(result.stderr)       # (empty on success)
print(result.exit_code)    # 0
print(result.duration_s)   # 0.08
print(result.job_id)       # uuid
print(result.machine_id)   # mac_0276ffc3
```

**Full parameter list:**

```python
result = mac.run(
    "swift build",
    env={"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
    cwd="/project",
    sandbox_id="build-sandbox",
    timeout=300.0,
    inherit_home=True,     # use real HOME (--real)
    stream=True,           # print output as it arrives
    backend="seatbelt",    # or "tart"
)
```

### Streaming Output

```python
for stream_name, data in mac.stream("long-running-build"):
    if stream_name == "stdout":
        print(data, end="")
    elif stream_name == "stderr":
        print(f"[err] {data}", end="")
```

### Sandboxed Execution

```python
sbx = mac.sandbox()
result = sbx.exec("npm test", check=True)  # raises on non-zero exit
```

### Fleet Operations

```python
macs = hivemind.fleet()
for m in macs:
    print(f"{m.hostname}: {m.chip}, {m.ram_gb}GB, "
          f"{m.cpu_percent:.0f}% CPU, {m.memory_percent:.0f}% RAM")
```

### Configuration

```python
hivemind.configure(
    url="http://remote:8000",
    token="hm_sk_...",
)
```

---

## Dashboard

Hivemind includes a Next.js web dashboard (default: `http://localhost:3000`).

**Overview Page:**

- Live fleet status with hardware telemetry (chip, cores, RAM, CPU/memory load)
- Quick Run terminal for executing commands from the browser
- Run Inspector showing recent job history with stdout/stderr and exit codes

**Tokens Page (`/tokens`):**

- Create, list, and revoke API tokens from the browser

---

## Development

```bash
# Clone and install
git clone https://github.com/UgeeCodes/hivemind.git
cd hivemind
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
python3 -m unittest discover tests -v

# Start control plane + daemon locally
hivemind serve &
hivemind child start --foreground
```

---

## License

Apache-2.0
