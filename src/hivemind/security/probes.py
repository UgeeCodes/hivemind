"""
Security evaluation and probe suite for Hivemind isolation backends.

Provides standardized threat model definitions, synthetic diagnostic probes,
and empirical scorecard generators to compare isolation boundaries between
Seatbelt (OS sandboxing) and Tart (Apple Virtualization microVMs).
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import List


class ProbeCategory(str, Enum):
    """The 5 empirical threat model evaluation categories."""
    CREDENTIAL_ISOLATION = "credential_isolation"
    FILESYSTEM_CONFINEMENT = "filesystem_confinement"
    PERSISTENCE_PREVENTION = "persistence_prevention"
    NETWORK_CONFINEMENT = "network_confinement"
    PROCESS_ISOLATION = "process_isolation"


@dataclass(frozen=True)
class SecurityProbe:
    """Definition of a diagnostic security containment probe."""
    probe_id: str
    category: ProbeCategory
    name: str
    description: str
    command: str
    expected_exit_code: int = 1
    allow_network: bool = True


DEFAULT_PROBES: List[SecurityProbe] = [
    # Vector 1: Credential Isolation
    SecurityProbe(
        probe_id="PROBE-CRED-01",
        category=ProbeCategory.CREDENTIAL_ISOLATION,
        name="SSH Key Read Check",
        description="Verify that SSH private keys cannot be read from the host filesystem.",
        command="cat ~/.ssh/id_rsa 2>/dev/null || cat ~/.ssh/id_ed25519 2>/dev/null",
        expected_exit_code=1,
    ),
    SecurityProbe(
        probe_id="PROBE-CRED-02",
        category=ProbeCategory.CREDENTIAL_ISOLATION,
        name="Apple Keychain DB Access",
        description="Verify that the macOS Keychain database login.keychain-db is inaccessible.",
        command="ls -la ~/Library/Keychains/login.keychain-db 2>/dev/null",
        expected_exit_code=1,
    ),
    SecurityProbe(
        probe_id="PROBE-CRED-03",
        category=ProbeCategory.CREDENTIAL_ISOLATION,
        name="Cloud Credentials Access (AWS)",
        description="Verify that ~/.aws/credentials cannot be read from the sandbox.",
        command="cat ~/.aws/credentials 2>/dev/null",
        expected_exit_code=1,
    ),
    SecurityProbe(
        probe_id="PROBE-CRED-04",
        category=ProbeCategory.CREDENTIAL_ISOLATION,
        name="Netrc Auth Token Access",
        description="Verify that ~/.netrc credentials store cannot be read from the sandbox.",
        command="cat ~/.netrc 2>/dev/null",
        expected_exit_code=1,
    ),

    # Vector 2: Filesystem Confinement
    SecurityProbe(
        probe_id="PROBE-FS-01",
        category=ProbeCategory.FILESYSTEM_CONFINEMENT,
        name="Host Home Shell Config Modification",
        description="Verify that writing outside the sandbox to user's real ~/.zshrc is denied.",
        command="touch ~/.zshrc_probe_canary 2>/dev/null",
        expected_exit_code=1,
    ),
    SecurityProbe(
        probe_id="PROBE-FS-02",
        category=ProbeCategory.FILESYSTEM_CONFINEMENT,
        name="System Library Write Access",
        description="Verify that creating files in /Library/Preferences is denied.",
        command="touch /Library/Preferences/probe_canary 2>/dev/null",
        expected_exit_code=1,
    ),

    # Vector 3: Persistence Prevention
    SecurityProbe(
        probe_id="PROBE-PERSIST-01",
        category=ProbeCategory.PERSISTENCE_PREVENTION,
        name="Host LaunchAgent Persistence Drop",
        description="Verify that dropping persistence plists into ~/Library/LaunchAgents is blocked.",
        command="touch ~/Library/LaunchAgents/com.probe.canary.plist 2>/dev/null",
        expected_exit_code=1,
    ),

    # Vector 4: Network Confinement
    SecurityProbe(
        probe_id="PROBE-NET-01",
        category=ProbeCategory.NETWORK_CONFINEMENT,
        name="Outbound Socket Policy Confinement",
        description="Verify that network socket creation is blocked when allow_network is False.",
        command="python3 -c \"import socket; s = socket.socket(); s.connect(('1.1.1.1', 80))\" 2>/dev/null",
        expected_exit_code=1,
        allow_network=False,
    ),

    # Vector 5: Process Isolation
    SecurityProbe(
        probe_id="PROBE-PROC-01",
        category=ProbeCategory.PROCESS_ISOLATION,
        name="Host Root Daemon Signaling",
        description="Verify that processes inside the sandbox cannot signal or inspect host launchd (PID 1).",
        command="kill -0 1 2>/dev/null",
        expected_exit_code=1,
    ),
]
