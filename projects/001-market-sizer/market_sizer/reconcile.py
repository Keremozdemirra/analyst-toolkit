"""Forcing the two sizings to face each other.

Sizing a market twice is only useful if the two numbers are made to argue. The
gap is the easy part. The useful part is the inversion: for a chosen assumption,
what value would it have to take for the two sides to agree? That number is
often the whole finding -- "these reconcile only if penetration is 31%, and
nobody in the room believes 31%".
"""

from dataclasses import dataclass
from typing import List, Optional

from .assumptions import SHARE, Assumption
from .model import BottomUp, Market, ModelError, Segment, TopDown


@dataclass(frozen=True)
class Reconciliation:
    top_down: float
    bottom_up: float

    @property
    def gap(self):
        """Bottom-up minus top-down. Positive means bottom-up is the larger."""
        return self.bottom_up - self.top_down

    @property
    def ratio(self):
        if self.top_down == 0:
            raise ModelError("cannot express a ratio against a top-down total of zero")
        return self.bottom_up / self.top_down

    @property
    def relative_gap(self):
        """Gap as a fraction of the top-down total."""
        return self.ratio - 1.0

    def agrees_within(self, tolerance):
        """True if the two sides are within ``tolerance`` (a fraction) of each other.

        Measured against the larger of the two, so the verdict does not depend
        on which sizing happens to be called the denominator.
        """
        if tolerance < 0:
            raise ValueError("tolerance must not be negative")
        larger = max(abs(self.top_down), abs(self.bottom_up))
        if larger == 0:
            return True
        return abs(self.gap) / larger <= tolerance

    def to_dict(self):
        return {
            "top_down": self.top_down,
            "bottom_up": self.bottom_up,
            "gap": self.gap,
            "ratio": self.ratio if self.top_down else None,
            "relative_gap": self.relative_gap if self.top_down else None,
        }


@dataclass(frozen=True)
class SolveResult:
    """What one assumption would have to be for the two sizings to agree."""

    name: str
    side: str            # "top-down" or "bottom-up"
    segment: Optional[str]
    current: float
    implied: Optional[float]
    feasible: bool
    reason: str = ""

    @property
    def multiple(self):
        if self.implied is None or self.current == 0:
            return None
        return self.implied / self.current

    def to_dict(self):
        return {
            "name": self.name,
            "side": self.side,
            "segment": self.segment,
            "current": self.current,
            "implied": self.implied,
            "multiple": self.multiple,
            "feasible": self.feasible,
            "reason": self.reason,
        }


def reconcile(market):
    return Reconciliation(top_down=market.top_down.total, bottom_up=market.bottom_up.total)


def solve_for(market, name):
    """Invert the model for one named assumption.

    Top-down is a single product, so the implied value scales linearly with the
    required change in the total. Bottom-up is a sum of products, so only the
    one segment moves and the rest of the sum acts as a floor -- which is why a
    bottom-up solve can come back infeasible and a top-down one cannot.
    """
    td = market.top_down.total
    bu = market.bottom_up.total

    hits = _locate(market, name)
    if not hits:
        raise KeyError("no assumption named %r" % name)
    if len(hits) > 1:
        where = ", ".join("%s/%s" % (s or side, name) for side, s, _ in hits)
        raise KeyError("assumption name %r is ambiguous: %s" % (name, where))
    side, segment_name, assumption = hits[0]

    if side == "top-down":
        if td == 0:
            return SolveResult(name, side, None, assumption.value, None, False,
                               "top-down total is zero, so no factor can scale it")
        if assumption.value == 0:
            return SolveResult(name, side, None, 0.0, None, False,
                               "a factor pinned at zero cannot be scaled to close a gap")
        implied = assumption.value * (bu / td)
        return _verdict(name, side, None, assumption, implied)

    seg = market.bottom_up.segment(segment_name)
    # Summed directly rather than as ``bu - seg.value``. When one segment
    # dominates the total, that subtraction cancels most of its significant
    # digits and the implied value comes back visibly wrong -- the inversion
    # test caught it at a relative error of 7e-8.
    rest = sum(s.value for s in market.bottom_up.segments if s.name != segment_name)
    if seg.value == 0:
        return SolveResult(name, side, segment_name, assumption.value, None, False,
                           "segment %r is worth zero, so scaling one of its drivers "
                           "cannot move the total" % segment_name)
    required_segment = td - rest
    if required_segment < 0:
        return SolveResult(
            name, side, segment_name, assumption.value, None, False,
            "the other segments alone come to %.6g, already above the top-down total "
            "of %.6g; no value of %r can close the gap" % (rest, td, name),
        )
    implied = assumption.value * (required_segment / seg.value)
    return _verdict(name, side, segment_name, assumption, implied)


def _verdict(name, side, segment_name, assumption, implied):
    if assumption.kind == SHARE and implied > 1.0:
        return SolveResult(name, side, segment_name, assumption.value, implied, False,
                           "implied share of %.1f%% exceeds 100%%" % (implied * 100.0))
    if implied < 0:
        return SolveResult(name, side, segment_name, assumption.value, implied, False,
                           "implied value is negative")
    return SolveResult(name, side, segment_name, assumption.value, implied, True)


def solve_all(market):
    """Solve for every assumption in the model, in declaration order."""
    out = []
    for side, segment_name, a in _walk(market):
        out.append(solve_for(market, a.name))
    return out


def _walk(market):
    yield "top-down", None, market.top_down.universe
    for f in market.top_down.factors:
        yield "top-down", None, f
    for s in market.bottom_up.segments:
        for d in s.drivers:
            yield "bottom-up", s.name, d


def _locate(market, name):
    return [(side, seg, a) for side, seg, a in _walk(market) if a.name == name]
