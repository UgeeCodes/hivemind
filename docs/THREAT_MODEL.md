# Threat Model: Isolation Boundaries for BYO‑Mac Cloud Runtimes

**Document Version:** 1.0  
**Date:** October 5, 2026  
**Author:** Ugonna Nwaka  
**Status:** Active  

---

## 1. System Model

### 1.1 Deployment Scenario

Hivemind operates as a **Bring-Your-Own-Mac (BYO-Mac)** cloud runtime: personally owned Apple Silicon Macs serve as shared execution nodes, receiving and running arbitrary shell commands dispatched by remote clients (developers, CI pipelines, or autonomous AI coding agents).

```
┌──────────────────────────────────────────────────────────────┐
│                     TRUST BOUNDARY 1                          │
│                  Control Plane (Operator)                      │
│          Authenticated API · Job Dispatch · Telemetry          │
└────────────────────────────┬─────────────────────────────────┘
                             │ WebSocket (TLS)
┌────────────────────────────▼─────────────────────────────────┐
│                     TRUST BOUNDARY 2                          │
│                 Host Mac (Machine Owner)                       │
│    Credential Stores · LaunchAgents · System Preferences      │
│    ┌───────────────────────────────────────────────────────┐  │
│    │              TRUST BOUNDARY 3                          │  │
│    │         Isolation Sandbox (Untrusted Code)             │  │
│    │   Sandboxed HOME · Restricted Writes · Denied Reads   │  │
│    └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Trust Boundaries

| Boundary | Inner Entity | Outer Entity | Enforcement Mechanism |
|---|---|---|---|
| **TB-1** | Control Plane | External Network | SHA-256 hashed API keys with scope hierarchy (`admin ⊃ run ⊃ read`) |
| **TB-2** | Host macOS | Control Plane | Device token authentication; daemon runs as unprivileged user |
| **TB-3** | Sandbox Environment | Host macOS | **Seatbelt:** Apple `sandbox-exec(1)` kernel profiles; **Tart:** Apple Virtualization.framework hardware guest boundary |

### 1.3 Assets Under Protection

The following host-resident assets must be protected from unauthorized access by sandboxed workloads:

| Asset Class | Examples | Sensitivity |
|---|---|---|
| **Authentication Credentials** | `~/.ssh/id_rsa`, `~/.ssh/id_ed25519`, `~/.aws/credentials`, `~/.config/gcloud/`, `~/.docker/config.json`, `~/.netrc`, `~/.npmrc` | **Critical** — Compromise enables lateral movement to cloud accounts and remote systems |
| **Cryptographic Material** | `~/.gnupg/`, `~/Library/Keychains/login.keychain-db` | **Critical** — Enables identity impersonation and code signing forgery |
| **Persistence Mechanisms** | `~/Library/LaunchAgents/`, `~/Library/LaunchDaemons/`, user crontab | **High** — Enables attacker persistence surviving sandbox teardown and system reboots |
| **Host Shell Configuration** | `~/.zshrc`, `~/.bashrc`, `~/.zprofile` | **High** — Enables code injection into future interactive sessions |
| **System Integrity** | `/Library/Preferences/`, `/System/`, `/etc/` | **High** — Enables host-wide configuration tampering |
| **Host Process State** | PID 1 (`launchd`), kernel task, other user processes | **Medium** — Signal injection can disrupt host services |

---

## 2. Attacker Model

### 2.1 Attacker Identity and Access

The attacker is an **authenticated but untrusted workload submitter** — a user or autonomous agent holding a valid API key with `run` scope who submits arbitrary shell commands for execution on a host Mac.

This models real-world scenarios including:
- A developer running untrusted third-party build scripts (`curl | sh` install patterns)
- An AI coding agent autonomously executing shell commands with insufficient oversight
- A compromised CI pipeline injecting malicious commands into the job queue
- A malicious insider with valid credentials but hostile intent

### 2.2 Attacker Capabilities

| Capability | Description |
|---|---|
| **C1: Arbitrary Command Execution** | The attacker can submit any shell command string for execution inside the sandbox. This includes shell builtins, system binaries, scripting interpreters (Python, Ruby, Perl), and compiled executables. |
| **C2: Environment Manipulation** | The attacker can specify environment variables (`env` parameter) and request the real host HOME directory (`inherit_home=True`). |
| **C3: Network Access** | By default, sandboxed processes have outbound network access (configurable). The attacker can attempt DNS exfiltration, reverse shells, or data uploads. |
| **C4: Filesystem Probing** | The attacker can attempt to read, write, list, and stat arbitrary filesystem paths, including paths outside the designated sandbox directory. |
| **C5: Process Interaction** | The attacker can attempt to signal, inspect, or communicate with processes outside the sandbox via `kill()`, `/proc` (not available on macOS), or Mach ports. |

### 2.3 Attacker Goals

| Goal | MITRE ATT&CK Mapping | Description |
|---|---|---|
| **G1: Credential Theft** | T1552 (Unsecured Credentials) | Read SSH keys, cloud tokens, API secrets, or Keychain data from the host filesystem. |
| **G2: Persistence** | T1543 (Create or Modify System Process) | Install a LaunchAgent, crontab entry, or login hook that survives sandbox teardown and executes on next system boot. |
| **G3: Lateral Movement** | T1021 (Remote Services) | Use stolen credentials to SSH into other machines, authenticate to cloud APIs, or pivot through the network. |
| **G4: Host Disruption** | T1489 (Service Stop) | Signal or kill critical host processes (e.g., PID 1, WindowServer) to deny service. |
| **G5: Data Exfiltration** | T1041 (Exfiltration Over C2 Channel) | Transmit collected host data to an external server via network sockets. |

### 2.4 Attacker Constraints (Out of Scope)

The following attack vectors are **explicitly out of scope** for this threat model:

| Exclusion | Rationale |
|---|---|
| **Kernel exploits** | Seatbelt and Tart both depend on kernel integrity. A kernel-level zero-day bypasses all userspace isolation. This is a platform-level concern addressed by Apple's security updates, not by the runtime. |
| **Physical access attacks** | The attacker does not have physical access to the Mac. Cold boot attacks, DMA attacks, and hardware implants are excluded. |
| **Side-channel attacks** | Speculative execution (Spectre/Meltdown variants), cache timing, and electromagnetic emanation attacks are excluded. These require specialized measurement apparatus and are not mitigated by process-level or VM-level isolation alone. |
| **Supply chain compromise** | Compromise of the Hivemind daemon binary, Python interpreter, or system libraries is excluded. The attacker operates within the provided execution environment. |
| **Control plane compromise** | The attacker does not have `admin` scope and cannot modify the control plane, daemon configuration, or authentication system. |

---

## 3. Containment Criteria

### 3.1 Definition of "Contained"

A security probe is classified as **🛡️ CONTAINED** if and only if:

> The adversarial command exits with a **non-zero exit code** AND the targeted host asset remains **unmodified and unread** after execution.

Specifically:
- **For read probes** (credential theft): The command attempting to read the protected file must fail. The sandbox must deny the `open()` / `read()` syscall, causing the process to receive `EPERM` or `EACCES` and exit with a non-zero status.
- **For write probes** (persistence, filesystem escape): The command attempting to create or modify a file outside the sandbox must fail. The target file must not exist or must remain unchanged after execution.
- **For signal probes** (process isolation): The command attempting to send a signal to a host process must fail with `EPERM`.
- **For network probes** (when network is denied): The command attempting to open a socket must fail.

### 3.2 Definition of "Leaked"

A security probe is classified as **⚠️ LEAKED** if:

> The adversarial command exits with **exit code 0** OR the targeted host asset is **observably accessed or modified** after execution.

### 3.3 Measurement Methodology

Each probe is executed as follows:

1. **Provision** a fresh, ephemeral sandbox instance (unique `sandbox_id`).
2. **Execute** the adversarial command inside the sandbox via `backend.execute()`.
3. **Capture** the process exit code, stdout, and stderr.
4. **Evaluate** containment: `exit_code != 0` → CONTAINED; `exit_code == 0` → LEAKED.
5. **Teardown** the sandbox, removing all temporary files.
6. **Record** the wall-clock latency of the entire probe lifecycle.

This methodology ensures:
- **Reproducibility**: Each probe runs in an isolated, freshly provisioned sandbox with no state leakage between probes.
- **Ground truth**: The exit code is the authoritative containment signal. The sandbox kernel enforcement (not application-level checks) determines the outcome.
- **No simulation**: Probes execute real adversarial commands against real isolation boundaries. There is no mocking or simulation of the sandbox mechanism itself.

---

## 4. Threat Vector ↔ Probe Mapping

Each probe in the Security Probe Suite maps to a specific attacker goal, asset, and attack technique:

| Probe ID | Attacker Goal | Target Asset | Attack Technique | Containment Mechanism |
|---|---|---|---|---|
| `PROBE-CRED-01` | G1: Credential Theft | `~/.ssh/id_rsa` | `cat ~/.ssh/id_rsa` | Seatbelt `(deny file-read*)` on `~/.ssh` subpath |
| `PROBE-CRED-02` | G1: Credential Theft | `~/Library/Keychains/login.keychain-db` | `cat` keychain DB | Seatbelt `(deny file-read*)` on Keychains subpath |
| `PROBE-CRED-03` | G1: Credential Theft | `~/.aws/credentials` | `cat ~/.aws/credentials` | Seatbelt `(deny file-read*)` on `~/.aws` subpath |
| `PROBE-CRED-04` | G1: Credential Theft | `~/.netrc` | `cat ~/.netrc` | Seatbelt `(deny file-read*)` on `~/.netrc` |
| `PROBE-FS-01` | G2: Persistence (indirect) | `~/.zshrc` | `echo 'malicious' >> ~/.zshrc` | Seatbelt `(deny file-write*)` outside sandbox dir |
| `PROBE-FS-02` | G4: Host Disruption | `/usr/local/lib/` | `touch /usr/local/lib/probe` | Seatbelt `(deny file-write*)` on system paths |
| `PROBE-PERSIST-01` | G2: Persistence | `~/Library/LaunchAgents/` | `touch ~/Library/LaunchAgents/com.probe.canary.plist` | Seatbelt `(deny file-write*)` outside sandbox dir |
| `PROBE-NET-01` | G5: Data Exfiltration | Outbound network socket | `python3 -c "socket.create_connection(('1.1.1.1', 443))"` | Seatbelt `(deny network*)` when network disabled |
| `PROBE-PROC-01` | G4: Host Disruption | PID 1 (`launchd`) | `kill -9 1` | macOS kernel `EPERM` for unprivileged signal to PID 1 |

---

## 5. Isolation Mechanism Comparison

### 5.1 Apple Seatbelt (OS Sandbox)

| Property | Value |
|---|---|
| **Isolation boundary** | Process-level: XNU Seatbelt kernel extension (`sandbox-exec(1)`) |
| **Kernel sharing** | Shared — sandbox and host share the same XNU kernel instance |
| **Filesystem isolation** | Policy-enforced: dynamic `.sb` profile denies reads/writes to specified paths |
| **Network isolation** | Policy-enforced: `(deny network*)` or `(allow network*)` per profile |
| **Process isolation** | Partial — sandboxed process can see host process list; signal delivery restricted by Unix permissions |
| **Startup latency** | < 50ms (profile compilation + `fork()/exec()`) |
| **Memory overhead** | Negligible (no guest OS) |
| **Escape risk** | Moderate — kernel exploits or Seatbelt profile bypass could breach containment |

### 5.2 Tart MicroVM (Hardware Virtualization)

| Property | Value |
|---|---|
| **Isolation boundary** | Hardware-level: Apple Virtualization.framework (Hypervisor.framework) |
| **Kernel sharing** | Separate — guest runs its own XNU kernel instance |
| **Filesystem isolation** | Complete — guest has its own APFS volume (CoW clone of base image) |
| **Network isolation** | Configurable: NAT, bridged, or no networking |
| **Process isolation** | Complete — guest processes are invisible to the host |
| **Startup latency** | ~2,000–5,000ms (APFS clone + VM boot + guest init) |
| **Memory overhead** | Significant — full guest macOS memory footprint (~2–4 GB minimum) |
| **Escape risk** | Low — requires hypervisor escape (hardware-enforced boundary) |

### 5.3 Comparative Summary

| Dimension | Seatbelt | Tart | Winner |
|---|---|---|---|
| Startup latency | ~15ms | ~2,500ms | **Seatbelt** (167× faster) |
| Memory efficiency | Negligible | ~2–4 GB per VM | **Seatbelt** |
| Credential containment | Policy-enforced deny rules | Hardware boundary | **Tart** (stronger guarantee) |
| Kernel isolation | None (shared kernel) | Full (separate kernel) | **Tart** |
| Escape difficulty | Seatbelt profile bypass | Hypervisor escape | **Tart** (significantly harder) |
| Developer ergonomics | Near-native responsiveness | Multi-second boot penalty | **Seatbelt** |

---

## 6. Limitations and Transparency

### 6.1 Hardware Availability

Tart microVM benchmarks were **not executed on the test hardware** used in this study. The test machine did not have the `tart` binary installed, and full macOS guest VM deployment was not available during the experimental period.

**Implications:**
- All Seatbelt results (security probes and performance benchmarks) represent **measured empirical data** from real `sandbox-exec` execution.
- All Tart latency figures (2,500ms startup estimate) are **projected values** derived from published Tart documentation and community benchmarks, not from direct measurement on the test hardware.
- The Hybrid Policy Escalator simulation uses these projected Tart values. Its efficiency metrics (e.g., "86.1% latency savings") are **analytically computed projections**, not empirically validated results.

### 6.2 Proxy Results vs. Empirical Evidence

In accordance with academic integrity requirements, this study clearly separates:

| Data Category | Label | Source |
|---|---|---|
| Seatbelt security probe results | **Empirical (Measured)** | Real `sandbox-exec` kernel enforcement on macOS host |
| Seatbelt benchmark latencies | **Empirical (Measured)** | `time.perf_counter()` instrumentation during actual execution |
| Tart isolation properties | **Architectural (Documented)** | Apple Virtualization.framework documentation and Tart source code |
| Tart latency estimates | **Projected (Literature)** | Published benchmarks and community reports |
| Hybrid Policy simulation metrics | **Analytical (Simulated)** | Computed from measured Seatbelt + projected Tart values |

---

## 7. References

1. Apple Inc. "App Sandbox Design Guide." Apple Developer Documentation.
2. Apple Inc. "Virtualization Framework." Apple Developer Documentation.
3. Tart. "Tart — macOS and Linux VMs on Apple Silicon." https://tart.run
4. MITRE ATT&CK. "Enterprise Techniques." https://attack.mitre.org/techniques/enterprise/
