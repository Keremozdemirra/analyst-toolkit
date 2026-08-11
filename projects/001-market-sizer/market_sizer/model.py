"""The two sizings.

Both are deliberately multiplicative and nothing more. A top-down size is a
universe narrowed by successive factors; a bottom-up size is a sum of segments,
each of which is a product of drivers. Keeping the algebra this thin is what
makes the reconciliation in :mod:`market_sizer.reconcile` solvable in closed
form rather than by search.
"""

from dataclasses import dataclass, field
from typing import List, Sequence

from .assumptions import Assumption, AssumptionError


class ModelError(ValueError):
    """The model is structurally unusable -- no universe, no segments, no drivers."""


@dataclass(frozen=True)
class TopDown:
    """A universe narrowed by successive factors.

    ``total = universe.value * prod(f.value for f in factors)``
    """

    universe: Assumption
    factors: List[Assumption] = field(default_factory=list)

    def __post_init__(self):
        if self.universe is None:
            raise ModelError("top-down sizing needs a universe")
        if not self.factors:
            raise ModelError(
                "top-down sizing with no narrowing factors is just the universe; "
                "state at least one factor even if it is 1.0"
            )

    @property
    def total(self):
        return top_down_total(self)

    def assumptions(self):
        return [self.universe] + list(self.factors)


@dataclass(frozen=True)
class Segment:
    """One bottom-up cell: a product of drivers.

    Typically count x attach rate x price, but the tool does not care how many
    drivers there are or what they mean -- only that they multiply.
    """

    name: str
    drivers: List[Assumption] = field(default_factory=list)

    def __post_init__(self):
        if not str(self.name).strip():
            raise ModelError("every segment needs a name")
        if not self.drivers:
            raise ModelError("segment %r has no drivers" % self.name)

    @property
    def value(self):
        out = 1.0
        for d in self.drivers:
            out *= d.value
        return out

    def assumptions(self):
        return list(self.drivers)


@dataclass(frozen=True)
class BottomUp:
    """A sum of segments."""

    segments: List[Segment] = field(default_factory=list)

    def __post_init__(self):
        if not self.segments:
            raise ModelError("bottom-up sizing needs at least one segment")
        names = [s.name for s in self.segments]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ModelError("duplicate segment name(s): %s" % ", ".join(dupes))

    @property
    def total(self):
        return bottom_up_total(self)

    def segment(self, name):
        for s in self.segments:
            if s.name == name:
                return s
        raise KeyError("no segment named %r (have: %s)" % (name, ", ".join(s.name for s in self.segments)))

    def assumptions(self):
        out = []
        for s in self.segments:
            out.extend(s.assumptions())
        return out


def top_down_total(model):
    out = model.universe.value
    for f in model.factors:
        out *= f.value
    return out


def bottom_up_total(model):
    return sum(s.value for s in model.segments)


@dataclass(frozen=True)
class Market:
    """A named market sized both ways."""

    name: str
    unit: str
    top_down: TopDown
    bottom_up: BottomUp

    def assumptions(self):
        return self.top_down.assumptions() + self.bottom_up.assumptions()

    def unverified(self):
        return [a for a in self.assumptions() if not a.verified]

    def stale(self, stale_after_months, as_of=None):
        return [a for a in self.assumptions() if a.is_stale(stale_after_months, as_of)]


def elasticity(model, name, rel_step=1e-6):
    """Central-difference elasticity of the total with respect to one assumption.

    Returned as ``(dT/T) / (dx/x)``. For a purely multiplicative model this is
    exactly 1 for every top-down factor, and exactly the segment's share of the
    total for a bottom-up driver. The tests pin both identities: they are the
    cheapest available check that the arithmetic has not drifted.
    """
    target = None
    for a in model.assumptions():
        if a.name == name:
            if target is not None:
                raise KeyError("assumption name %r is ambiguous within this model" % name)
            target = a
    if target is None:
        raise KeyError("no assumption named %r" % name)
    if target.value == 0:
        raise ModelError("elasticity is undefined at zero for %r" % name)

    base = _total(model)
    if base == 0:
        raise ModelError("elasticity is undefined when the total is zero")
    h = abs(target.value) * rel_step
    up = _total(_perturbed(model, name, target.value + h))
    down = _total(_perturbed(model, name, target.value - h))
    return ((up - down) / (2 * h)) * (target.value / base)


def _total(model):
    if isinstance(model, TopDown):
        return top_down_total(model)
    if isinstance(model, BottomUp):
        return bottom_up_total(model)
    raise TypeError("expected TopDown or BottomUp, got %s" % type(model).__name__)


def _perturbed(model, name, new_value):
    """A copy of ``model`` with one assumption's value replaced.

    Validation is bypassed on purpose: a perturbation of 1e-6 around a share of
    1.0 steps outside [0, 1], and refusing that would make the derivative
    unobtainable exactly where it matters.
    """
    if isinstance(model, TopDown):
        universe = model.universe
        if universe.name == name:
            universe = _raw_replace(universe, new_value)
        factors = [_raw_replace(f, new_value) if f.name == name else f for f in model.factors]
        return TopDown(universe=universe, factors=factors)
    segments = []
    for s in model.segments:
        drivers = [_raw_replace(d, new_value) if d.name == name else d for d in s.drivers]
        segments.append(Segment(name=s.name, drivers=drivers))
    return BottomUp(segments=segments)


def _raw_replace(assumption, value):
    clone = object.__new__(Assumption)
    for f_name in ("name", "value", "source", "as_of", "unit", "kind", "note", "verified"):
        object.__setattr__(clone, f_name, getattr(assumption, f_name))
    object.__setattr__(clone, "value", float(value))
    return clone
