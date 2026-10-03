"""
Hybrid Policy Escalator for adaptive isolation backend routing.

Provides deterministic risk scoring, threat heuristic matching,
and explainable routing decisions that dynamically choose between
Seatbelt (fast path) and Tart (secure path) based on command analysis.
"""
from __future__ import annotations

from hivemind.policy.rules import (
    DEFAULT_RULES,
    RiskTier,
    RuleMatch,
    ThreatCategory,
    ThreatRule,
)
from hivemind.policy.escalator import (
    EscalationDecision,
    PolicyEscalator,
)

__all__ = [
    "DEFAULT_RULES",
    "EscalationDecision",
    "PolicyEscalator",
    "RiskTier",
    "RuleMatch",
    "ThreatCategory",
    "ThreatRule",
]
