from dataclasses import dataclass
from enum import Enum


class SlotLabel(str, Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    POSSIBLE = "possible"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


@dataclass
class DecisionParams:
    tau_likely: float
    tau_possible: float
    cancel_penalty_eur: float
    monthly_budget_hours: int = 70
    max_slots_per_day: int = 2


def label_slot(p_cheap: float, expected_value: float, data_quality: str, params: DecisionParams) -> SlotLabel:
    """Degraded input data or high uncertainty routes the slot to a human (NEEDS_REVIEW)."""
    raise NotImplementedError
