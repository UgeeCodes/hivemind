"""
Risk taxonomy, threat indicators, and heuristic rule matching catalog
for the Hybrid Policy Escalator.

Rules are divided into two classes:
- Command-level rules: Match patterns in the command string itself.
- Metadata-level rules: Evaluate execution parameters (inherit_home, allow_network, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class RiskTier(str, Enum):
    """Risk classification tiers determining routing policy."""
    LOW = "low"            # Score 0-29 -> Seatbelt
    MEDIUM = "medium"      # Score 30-49 -> Seatbelt (monitored)
    HIGH = "high"          # Score 50-79 -> Tart microVM
    CRITICAL = "critical"  # Score 80-100 -> Tart microVM (strict)


class ThreatCategory(str, Enum):
    """Threat dimensions evaluated by the policy escalator."""
    CREDENTIAL_ACCESS = "credential_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    PERSISTENCE = "persistence"
    NETWORK_EXFILTRATION = "network_exfiltration"
    SYSTEM_MODIFICATION = "system_modification"
    OBFUSCATION = "obfuscation"


class RuleSource(str, Enum):
    """Whether the rule matches against the command string or request metadata."""
    COMMAND = "command"
    METADATA = "metadata"


@dataclass(frozen=True)
class ThreatRule:
    """Definition of a threat heuristic rule with regex pattern and severity weight."""
    rule_id: str
    category: ThreatCategory
    source: RuleSource
    pattern: str  # Regex pattern for command rules; metadata field name for metadata rules
    weight: int   # Additive score contribution (0-50)
    description: str


@dataclass
class RuleMatch:
    """Record of a rule that matched during command evaluation."""
    rule_id: str
    category: ThreatCategory
    weight: int
    matched_pattern: str
    description: str


def _match_command_rule(rule: ThreatRule, command: str) -> Optional[RuleMatch]:
    """Evaluate a command-level rule against a command string.

    Returns a RuleMatch if the pattern is found, None otherwise.
    """
    match = re.search(rule.pattern, command, re.IGNORECASE)
    if match:
        return RuleMatch(
            rule_id=rule.rule_id,
            category=rule.category,
            weight=rule.weight,
            matched_pattern=match.group(0),
            description=rule.description,
        )
    return None


def evaluate_command_rules(
    command: str,
    rules: Optional[List[ThreatRule]] = None,
) -> List[RuleMatch]:
    """Evaluate all command-level rules against a command string.

    Args:
        command: The shell command to analyze.
        rules: Rule catalog (defaults to DEFAULT_RULES).

    Returns:
        List of RuleMatch for every triggered rule.
    """
    rule_list = rules or DEFAULT_RULES
    matches = []
    for rule in rule_list:
        if rule.source != RuleSource.COMMAND:
            continue
        m = _match_command_rule(rule, command)
        if m is not None:
            matches.append(m)
    return matches


def evaluate_metadata_rules(
    inherit_home: bool = False,
    allow_network: bool = True,
    rules: Optional[List[ThreatRule]] = None,
) -> List[RuleMatch]:
    """Evaluate metadata-level rules against execution parameters.

    Args:
        inherit_home: Whether the job uses the real host HOME directory.
        allow_network: Whether network access is permitted.
        rules: Rule catalog (defaults to DEFAULT_RULES).

    Returns:
        List of RuleMatch for every triggered metadata rule.
    """
    rule_list = rules or DEFAULT_RULES
    matches = []
    for rule in rule_list:
        if rule.source != RuleSource.METADATA:
            continue
        if rule.pattern == "inherit_home" and inherit_home:
            matches.append(RuleMatch(
                rule_id=rule.rule_id,
                category=rule.category,
                weight=rule.weight,
                matched_pattern="inherit_home=True",
                description=rule.description,
            ))
    return matches


# ---------------------------------------------------------------------------
# Standard heuristic rule catalog
# ---------------------------------------------------------------------------

DEFAULT_RULES: List[ThreatRule] = [
    # Credential Access
    ThreatRule(
        rule_id="RULE-CRED-KEY",
        category=ThreatCategory.CREDENTIAL_ACCESS,
        source=RuleSource.COMMAND,
        pattern=r"(id_rsa|id_ed25519|id_ecdsa|\.ssh/|login\.keychain|\.aws/credentials|\.netrc|\.env\b)",
        weight=35,
        description="Command references host credential stores or private keys.",
    ),

    # Privilege Escalation
    ThreatRule(
        rule_id="RULE-PRIV-SUDO",
        category=ThreatCategory.PRIVILEGE_ESCALATION,
        source=RuleSource.COMMAND,
        pattern=r"\b(sudo|su\s+-|doas|chmod\s+\+s|chown\s+root)\b",
        weight=40,
        description="Command attempts privilege escalation via sudo, su, or setuid modification.",
    ),

    # Persistence
    ThreatRule(
        rule_id="RULE-PERSIST-AGENT",
        category=ThreatCategory.PERSISTENCE,
        source=RuleSource.COMMAND,
        pattern=r"(LaunchAgents|LaunchDaemons|launchctl\s+load|crontab\s+-|com\.apple\.loginitems)",
        weight=40,
        description="Command attempts to install persistence mechanisms via LaunchAgents or cron.",
    ),

    # Network Exfiltration — piped remote execution
    ThreatRule(
        rule_id="RULE-NET-PIPE",
        category=ThreatCategory.NETWORK_EXFILTRATION,
        source=RuleSource.COMMAND,
        pattern=r"(curl|wget|fetch)\s+.*\|\s*(sh|bash|zsh|python|ruby|perl)",
        weight=50,
        description="Command pipes remote content directly into a shell interpreter (curl|sh pattern).",
    ),

    # Network Exfiltration — raw listeners / scanners
    ThreatRule(
        rule_id="RULE-NET-RAW",
        category=ThreatCategory.NETWORK_EXFILTRATION,
        source=RuleSource.COMMAND,
        pattern=r"\b(nc\s+-l|ncat\s+-l|nmap\s|socat\s)",
        weight=30,
        description="Command opens a raw network listener or runs a port scanner.",
    ),

    # System Modification
    ThreatRule(
        rule_id="RULE-SYS-ROOT",
        category=ThreatCategory.SYSTEM_MODIFICATION,
        source=RuleSource.COMMAND,
        pattern=r"(/Library/Preferences|/etc/|/System/|kill\s+-\d+\s+1\b|rm\s+-rf\s+/)",
        weight=35,
        description="Command targets system directories, root daemons, or dangerous recursive deletions.",
    ),

    # Obfuscation — eval / base64 decode piped to shell
    ThreatRule(
        rule_id="RULE-OBFUSC-EVAL",
        category=ThreatCategory.OBFUSCATION,
        source=RuleSource.COMMAND,
        pattern=r"(base64\s+-[dD].*\|\s*(sh|bash|zsh)|eval\s+\$\(|\bexec\s+['\"])",
        weight=45,
        description="Command uses obfuscation techniques (base64 decode to shell, eval injection).",
    ),

    # Metadata — inherit_home risk factor
    ThreatRule(
        rule_id="RULE-ENV-HOME",
        category=ThreatCategory.CREDENTIAL_ACCESS,
        source=RuleSource.METADATA,
        pattern="inherit_home",
        weight=25,
        description="Execution uses real host HOME directory, exposing credential stores.",
    ),
]
