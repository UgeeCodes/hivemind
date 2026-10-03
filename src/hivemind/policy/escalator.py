"""
PolicyEscalator — adaptive routing classifier for isolation backend selection.

Evaluates shell commands and execution metadata against a threat heuristic
catalog, computes a deterministic risk score, and produces an auditable
EscalationDecision routing to Seatbelt (fast path) or Tart (secure path).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hivemind.policy.rules import (
    DEFAULT_RULES,
    RiskTier,
    RuleMatch,
    ThreatRule,
    evaluate_command_rules,
    evaluate_metadata_rules,
)


@dataclass
class EscalationDecision:
    """Auditable routing decision produced by the PolicyEscalator."""
    target_backend: str        # "seatbelt" or "tart"
    risk_score: int            # 0 to 100 (clamped)
    risk_tier: RiskTier
    matches: List[RuleMatch]
    rationale: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class PolicyEscalator:
    """Deterministic risk-scoring engine for adaptive isolation routing.

    Attributes:
        threshold: Risk score at or above which tasks escalate to Tart.
                   Default is 50. Configurable for sensitivity analysis.
        rules: Threat heuristic rule catalog.
    """

    def __init__(
        self,
        threshold: int = 50,
        rules: Optional[List[ThreatRule]] = None,
    ):
        self.threshold = threshold
        self.rules = rules or DEFAULT_RULES

    def evaluate(
        self,
        command: str,
        inherit_home: bool = False,
        allow_network: bool = True,
    ) -> EscalationDecision:
        """Evaluate a command and its metadata to produce a routing decision.

        Args:
            command: The shell command string to analyze.
            inherit_home: Whether the job uses the real host HOME.
            allow_network: Whether network access is permitted.

        Returns:
            EscalationDecision with target backend, score, tier, and rationale.
        """
        # Collect all matches from both command and metadata rules
        cmd_matches = evaluate_command_rules(command, self.rules)
        meta_matches = evaluate_metadata_rules(inherit_home, allow_network, self.rules)
        all_matches = cmd_matches + meta_matches

        # Compute composite score (clamped to 0-100)
        raw_score = sum(m.weight for m in all_matches)
        risk_score = min(100, max(0, raw_score))

        # Determine risk tier
        if risk_score >= 80:
            risk_tier = RiskTier.CRITICAL
        elif risk_score >= 50:
            risk_tier = RiskTier.HIGH
        elif risk_score >= 30:
            risk_tier = RiskTier.MEDIUM
        else:
            risk_tier = RiskTier.LOW

        # Route based on threshold
        target_backend = "tart" if risk_score >= self.threshold else "seatbelt"

        # Build human-readable rationale
        if not all_matches:
            rationale = "No threat indicators detected. Routing to fast path (Seatbelt)."
        else:
            indicators = []
            for m in all_matches:
                indicators.append("{id}: {desc} (matched '{pat}', +{w})".format(
                    id=m.rule_id,
                    desc=m.description,
                    pat=m.matched_pattern,
                    w=m.weight,
                ))
            indicator_text = "; ".join(indicators)
            if target_backend == "tart":
                rationale = "Risk score {score} >= threshold {thresh}. Escalating to Tart microVM. Indicators: {ind}".format(
                    score=risk_score, thresh=self.threshold, ind=indicator_text,
                )
            else:
                rationale = "Risk score {score} < threshold {thresh}. Routing to Seatbelt fast path. Indicators: {ind}".format(
                    score=risk_score, thresh=self.threshold, ind=indicator_text,
                )

        return EscalationDecision(
            target_backend=target_backend,
            risk_score=risk_score,
            risk_tier=risk_tier,
            matches=all_matches,
            rationale=rationale,
            metadata={
                "command": command,
                "inherit_home": inherit_home,
                "allow_network": allow_network,
                "threshold": self.threshold,
            },
        )

    @staticmethod
    def tier_from_score(score: int) -> RiskTier:
        """Convert a numeric risk score to a RiskTier."""
        if score >= 80:
            return RiskTier.CRITICAL
        elif score >= 50:
            return RiskTier.HIGH
        elif score >= 30:
            return RiskTier.MEDIUM
        return RiskTier.LOW
