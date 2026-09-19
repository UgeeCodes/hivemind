# Hivemind Roadmap Issues

This document breaks down the upcoming features into individual, self-contained issues. You can pick and execute them one at a time.

---

## Issue #1: Sandboxes & Persistent Volumes UI Pages

### Goal
Provide dedicated dashboard views for inspecting and managing sandboxes and persistent storage volumes across the Mac fleet.

### Scope
1. **Sandboxes Page (`web/src/app/sandboxes/page.tsx`)**:
   * Table/card view listing all active and destroyed sandboxes across machines.
   * Details: Sandbox ID, target machine ID, path, creation time, status (`active` / `destroyed`).
   * Action: "Destroy" button calling `DELETE /api/sandboxes/{id}` to clean up sandbox directories.
2. **Volumes Page (`web/src/app/volumes/page.tsx`)**:
   * Table listing mounted volumes, owner ID, machine assignment, size in KB/MB, and path.
   * Action: "Create Volume" modal allowing users to provision a named volume for shared workloads.
3. **Navigation Integration**:
   * Add active links in top sub-nav (`Overview`, `Sandboxes`, `Volumes`, `API Tokens`).
   * Clicking the `LIVE SANDBOXES` and `VOLUMES` counter cards on the Overview page navigates directly to these routes.

### Acceptance Criteria
* Navigating to `/sandboxes` and `/volumes` displays live data from `/api/sandboxes` and `/api/volumes`.
* Users can destroy a sandbox from the web UI.
* Sub-navigation highlights the active tab accurately across all pages.

---

## Issue #2: Browser-Based Interactive Web Terminal (`xterm.js`)

### Goal
Allow developers to open a full interactive shell (PTY session) directly inside the browser to access any connected Mac.

### Scope
1. **Interactive PTY WebSocket Endpoint**:
   * Control plane `/ws/session` endpoint forwarding bidirectional stdin/stdout between browser and daemon PTY session (`SessionStart`, `SessionInput`, `SessionOutput`, `SessionClosed`).
2. **Frontend Terminal Component**:
   * Integrate `@xterm/xterm` (and `@xterm/addon-fit`) into a clean slide-out drawer or full-screen terminal modal.
   * Machine selector dropdown to pick which online Mac to drop into.
   * Support keyboard shortcuts, ANSI colors, tab completion, and window resizing (`SIGWINCH`).
3. **Clean Teardown**:
   * Closing the terminal modal cleanly closes the background PTY session on the remote Mac.

### Acceptance Criteria
* Running interactive commands (e.g. `top`, `htop`, `zsh`, `python3`) works with live typing and cursor control.
* Session terminates gracefully when typing `exit` or closing the drawer.

---

## Issue #3: Tag-Based & Fleet-Wide Run Dispatching

### Goal
Enable targeting specific Mac hardware profiles (e.g. M4 Max, 64GB RAM) via tags, or running commands across the entire cluster simultaneously.

### Scope
1. **CLI Flag Extensions**:
   * `hivemind run --tag <tag> "<cmd>"`: Routes execution to a machine matching the tag.
   * `hivemind run --all "<cmd>"`: Fans out the command in parallel to all connected Macs, streaming prefixed output (`[mac_1] ...`, `[mac_2] ...`).
2. **SDK Support**:
   * `mac.fleet().filter(tag='m4').run('<cmd>')`
   * `mac.fleet().broadcast('<cmd>')`
3. **Dashboard Quick Run Targeting**:
   * Add a machine selector dropdown next to the Quick Run input:
     * `Auto (Idlest)` (default)
     * Specific machine (e.g. `Ugees-MacBook-Pro (mac_0276ffc3)`)
     * `All Online Macs (Broadcast)`

### Acceptance Criteria
* `hivemind run --all "sw_vers"` executes concurrently on all online machines and returns individual exit codes.
* Quick Run dropdown correctly targets the selected machine ID.

---

## Issue #4: Real Tart MicroVM Virtualization Driver

### Goal
Wire up the pluggable isolation driver architecture to support real lightweight macOS microVMs on Apple Silicon using `tart`.

### Scope
1. **Host Tart Detection**:
   * Check for `/usr/local/bin/tart` or `which tart` on the daemon host Mac.
   * Detect available local VM base images (e.g. `tart list`).
2. **Full Lifecycle Execution in `TartBackend`**:
   * Clone ephemeral VM: `tart clone <base_img> <clone_name>`.
   * Run command inside VM via `tart run --net-bridged` or SSH runner.
   * Stop & delete ephemeral VM upon execution completion: `tart delete <clone_name>`.
3. **CLI / SDK Selection**:
   * `hivemind run --backend tart "..."` vs `hivemind run --backend seatbelt "..."`.
   * Fallback to Seatbelt with a warning if Tart is not installed.

### Acceptance Criteria
* When Tart is installed, running with `--backend tart` executes inside an isolated Apple Virtualization VM.
* If Tart is missing, gracefully falls back to Seatbelt isolation without failing the run.

---

## Issue #5: Comprehensive Documentation & Quickstart Guide

### Goal
Create top-tier developer documentation, quickstart guides, and architecture references for developers and PyPI release.

### Scope
1. **README.md Overhaul**:
   * Clear value proposition: *"Modal, for your Macs."*
   * ASCII / SVG architecture diagrams.
   * 60-second Quickstart guide:
     1. Install: `pip install hivemind`
     2. Start local control plane & daemon: `hivemind serve` & `hivemind child start`
     3. Run first command via CLI & Python SDK.
2. **CLI Reference & Cheatsheet**:
   * Complete table of all commands (`child`, `machines`, `run`, `token`, `volume`, `agent`).
3. **Python SDK Recipes**:
   * Code snippets for running background batch jobs, mounting persistent volumes, and integrating with AI agents (MCP / LangChain).

### Acceptance Criteria
* A new developer can clone the repo and get a command executing on a Mac in under 3 minutes following the README.
