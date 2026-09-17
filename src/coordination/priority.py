from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PriorityClass(Enum):
    EMERGENCY = 5
    CRITICAL = 4
    HIGH = 3
    NORMAL = 2
    LOW = 1

    @classmethod
    def from_int(cls, val: int) -> "PriorityClass":
        if val >= 5:
            return cls.EMERGENCY
        elif val == 4:
            return cls.CRITICAL
        elif val == 3:
            return cls.HIGH
        elif val == 2:
            return cls.NORMAL
        else:
            return cls.LOW

    @classmethod
    def from_str(cls, s: str) -> "PriorityClass":
        s_upper = s.strip().upper()
        for member in cls:
            if member.name == s_upper:
                return member
        return cls.NORMAL


@dataclass
class PriorityWeights:
    """Configurable coefficients for transparent operational priority calculation."""
    w_urgency: float = 30.0
    w_sla_risk: float = 25.0
    w_pkg_importance: float = 20.0
    w_carrying: float = 40.0
    w_progress: float = 15.0
    w_battery: float = 10.0
    w_distance: float = 0.5
    w_congestion: float = 5.0


@dataclass
class PriorityEvaluation:
    score: float
    priority_class: PriorityClass
    factors: dict[str, float] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "priority_class": self.priority_class.name,
            "factors": {k: round(v, 2) for k, v in self.factors.items()},
            "explanation": self.explanation,
        }


class PriorityEvaluator:
    """
    Transparent operational priority evaluator.
    Calculates explainable priority scores based on task urgency, SLA risk,
    carrying status, progress, battery safety margins, and congestion cost.
    """

    def __init__(self, weights: PriorityWeights | None = None) -> None:
        self.weights = weights or PriorityWeights()

    def evaluate(
        self,
        robot_id: str,
        carrying_package: bool,
        task_priority: int,
        battery: float,
        time_step: int = 0,
        deadline: int | None = None,
        remaining_distance: int = 0,
        completed_steps: int = 0,
        congestion_score: float = 0.0,
        is_emergency: bool = False,
    ) -> PriorityEvaluation:
        # Determine priority class
        if is_emergency or task_priority >= 5:
            p_class = PriorityClass.EMERGENCY
        else:
            p_class = PriorityClass.from_int(task_priority)

        factors: dict[str, float] = {}

        # 1. Urgency / Class Factor
        urgency_factor = (p_class.value / 5.0) * self.weights.w_urgency
        factors["urgency"] = urgency_factor

        # 2. SLA Risk Factor
        if deadline is not None and deadline > time_step:
            slack = deadline - time_step
            # If distance exceeds or approaches slack, SLA risk surges
            min_needed = max(1, remaining_distance)
            ratio = min(3.0, min_needed / max(1, slack))
            sla_risk_factor = ratio * self.weights.w_sla_risk
        elif deadline is not None and deadline <= time_step:
            # Already violating SLA - critical escalation
            sla_risk_factor = self.weights.w_sla_risk * 1.5
        else:
            sla_risk_factor = 0.0
        factors["sla_risk"] = sla_risk_factor

        # 3. Package Importance Factor
        pkg_factor = (task_priority / 5.0) * self.weights.w_pkg_importance
        factors["pkg_importance"] = pkg_factor

        # 4. Carrying Status (+40 boost if carrying actual customer cargo)
        carrying_factor = self.weights.w_carrying if carrying_package else 0.0
        factors["carrying_status"] = carrying_factor

        # 5. Progress Factor (favor finishing a nearly completed task)
        total_steps = completed_steps + remaining_distance
        if total_steps > 0:
            progress_ratio = completed_steps / total_steps
            progress_factor = progress_ratio * self.weights.w_progress
        else:
            progress_factor = 0.0
        factors["progress"] = progress_factor

        # 6. Battery Safety Factor (if battery > 30%, slight positive; if <20%, drops)
        if battery >= 50.0:
            battery_factor = (battery / 100.0) * self.weights.w_battery
        elif battery >= 25.0:
            battery_factor = 0.0
        else:
            # Critically low battery penalizes high task priority over safety docking
            battery_factor = -((25.0 - battery) / 25.0) * self.weights.w_battery * 2.0
        factors["battery_safety"] = battery_factor

        # 7. Distance Cost
        distance_cost = remaining_distance * self.weights.w_distance
        factors["distance_cost"] = -distance_cost

        # 8. Congestion Cost
        congestion_cost = congestion_score * self.weights.w_congestion
        factors["congestion_cost"] = -congestion_cost

        # Calculate Total Score
        total_score = (
            urgency_factor
            + sla_risk_factor
            + pkg_factor
            + carrying_factor
            + progress_factor
            + battery_factor
            - distance_cost
            - congestion_cost
        )

        total_score = round(max(0.0, total_score), 2)

        # Build Explanation
        expl_parts = [
            f"Class: {p_class.name} ({p_class.value})",
            f"Urgency=+{urgency_factor:.1f}",
        ]
        if sla_risk_factor > 0:
            expl_parts.append(f"SLARisk=+{sla_risk_factor:.1f}")
        if carrying_factor > 0:
            expl_parts.append(f"CarryingCargo=+{carrying_factor:.1f}")
        if battery_factor < 0:
            expl_parts.append(f"LowBatteryPenalty={battery_factor:.1f}")
        if distance_cost > 0:
            expl_parts.append(f"DistCost=-{distance_cost:.1f}")

        explanation = "; ".join(expl_parts)

        return PriorityEvaluation(
            score=total_score,
            priority_class=p_class,
            factors=factors,
            explanation=explanation,
        )

    def arbitrate_contention(
        self,
        eval_a: PriorityEvaluation,
        eval_b: PriorityEvaluation,
        robot_a_id: str,
        robot_b_id: str,
    ) -> tuple[str, str, str]:
        """
        Determines which robot has precedence in narrow aisle contention.
        Returns (winner_id, loser_id, reason).
        """
        diff = round(eval_a.score - eval_b.score, 2)
        if abs(diff) < 0.01:
            # Deterministic tie break by lexicographical robot_id
            winner = robot_a_id if robot_a_id < robot_b_id else robot_b_id
            loser = robot_b_id if winner == robot_a_id else robot_a_id
            reason = f"Tie-breaker: {winner} won against {loser} (scores equal: {eval_a.score:.1f})"
            return winner, loser, reason

        if eval_a.score > eval_b.score:
            winner, loser = robot_a_id, robot_b_id
            win_eval, lose_eval = eval_a, eval_b
        else:
            winner, loser = robot_b_id, robot_a_id
            win_eval, lose_eval = eval_b, eval_a

        # Detail why winner won
        key_factor = "overall operational priority"
        if win_eval.factors.get("carrying_status", 0) > lose_eval.factors.get("carrying_status", 0):
            key_factor = "active customer cargo carriage (+40.0 precedence)"
        elif win_eval.factors.get("sla_risk", 0) > lose_eval.factors.get("sla_risk", 0) + 5:
            key_factor = "critical SLA deadline proximity"
        elif win_eval.priority_class.value > lose_eval.priority_class.value:
            key_factor = f"higher operational tier ({win_eval.priority_class.name} vs {lose_eval.priority_class.name})"

        reason = (
            f"{winner} granted right-of-way over {loser} (Score {win_eval.score:.1f} vs {lose_eval.score:.1f}) "
            f"due to {key_factor}. {loser} yields to side buffer cell."
        )
        return winner, loser, reason
