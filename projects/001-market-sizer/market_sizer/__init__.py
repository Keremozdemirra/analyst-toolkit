"""Top-down and bottom-up market sizing, side by side, forced to reconcile."""

from .assumptions import Assumption, AssumptionError
from .model import BottomUp, Segment, TopDown, bottom_up_total, top_down_total
from .reconcile import Reconciliation, SolveResult, reconcile, solve_for

__all__ = [
    "Assumption",
    "AssumptionError",
    "TopDown",
    "BottomUp",
    "Segment",
    "top_down_total",
    "bottom_up_total",
    "Reconciliation",
    "SolveResult",
    "reconcile",
    "solve_for",
]

__version__ = "0.1.0"
