"""Helpers for building models in tests without repeating provenance boilerplate."""

import datetime as _dt
import random

from market_sizer.assumptions import Assumption
from market_sizer.model import BottomUp, Market, Segment, TopDown

VINTAGE = _dt.date(2025, 1, 1)


def a(name, value, kind="value", unit=""):
    return Assumption(name=name, value=value, source="test fixture", as_of=VINTAGE,
                      kind=kind, unit=unit)


def simple_market(universe=1000.0, factors=(0.5, 0.4), segments=((10.0, 0.5, 20.0),)):
    td = TopDown(
        universe=a("universe", universe),
        factors=[a("f%d" % i, v, kind="share") for i, v in enumerate(factors)],
    )
    segs = []
    for i, drivers in enumerate(segments):
        segs.append(Segment(
            name="seg%d" % i,
            drivers=[a("s%dd%d" % (i, j), v) for j, v in enumerate(drivers)],
        ))
    return Market(name="test", unit="EUR", top_down=td, bottom_up=BottomUp(segments=segs))


def random_market(rng):
    """A structurally valid market with awkward but finite numbers."""
    universe = rng.uniform(1e3, 1e10)
    factors = [rng.uniform(0.01, 1.0) for _ in range(rng.randint(1, 4))]
    segments = []
    for _ in range(rng.randint(1, 5)):
        segments.append(tuple(rng.uniform(0.05, 5e4) for _ in range(rng.randint(1, 4))))
    return simple_market(universe, factors, tuple(segments))


def rng_for(seed):
    return random.Random(seed)
