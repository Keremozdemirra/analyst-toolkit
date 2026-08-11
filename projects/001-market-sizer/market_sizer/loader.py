"""Reading a market definition from JSON.

JSON rather than CSV because the shape is genuinely nested -- segments have
drivers, drivers have provenance -- and flattening that into a spreadsheet is
exactly the failure mode this repository exists to avoid.
"""

import json

from .assumptions import AssumptionError, from_dict
from .model import BottomUp, Market, ModelError, Segment, TopDown

_TOP_LEVEL = {"market", "unit", "top_down", "bottom_up", "notes"}


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return loads(fh.read(), where=path)


def loads(text, where="<string>"):
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelError("%s: not valid JSON (%s)" % (where, exc))
    return parse(raw, where=where)


def parse(raw, where="<input>"):
    if not isinstance(raw, dict):
        raise ModelError("%s: expected a JSON object at the top level" % where)
    unknown = set(raw) - _TOP_LEVEL
    if unknown:
        raise ModelError("%s: unknown top-level field(s) %s" % (where, ", ".join(sorted(unknown))))
    for required in ("market", "unit", "top_down", "bottom_up"):
        if required not in raw:
            raise ModelError("%s: missing required field %r" % (where, required))

    td_raw = raw["top_down"]
    if not isinstance(td_raw, dict) or "universe" not in td_raw:
        raise ModelError("%s: top_down needs a 'universe' object" % where)
    universe = from_dict(td_raw["universe"], where="%s: top_down.universe" % where)
    factors = [
        from_dict(f, where="%s: top_down.factors[%d]" % (where, i))
        for i, f in enumerate(td_raw.get("factors", []))
    ]
    top_down = TopDown(universe=universe, factors=factors)

    bu_raw = raw["bottom_up"]
    if not isinstance(bu_raw, dict) or "segments" not in bu_raw:
        raise ModelError("%s: bottom_up needs a 'segments' list" % where)
    segments = []
    for i, s in enumerate(bu_raw["segments"]):
        if not isinstance(s, dict) or "name" not in s:
            raise ModelError("%s: bottom_up.segments[%d] needs a name" % (where, i))
        drivers = [
            from_dict(d, where="%s: segment %r driver[%d]" % (where, s["name"], j))
            for j, d in enumerate(s.get("drivers", []))
        ]
        segments.append(Segment(name=s["name"], drivers=drivers))
    bottom_up = BottomUp(segments=segments)

    _reject_duplicate_names(top_down, bottom_up, where)
    return Market(name=raw["market"], unit=raw["unit"], top_down=top_down, bottom_up=bottom_up)


def _reject_duplicate_names(top_down, bottom_up, where):
    """Assumption names are the addressing scheme for --solve, so they must be unique.

    Catching this at load time is much kinder than letting --solve fail on an
    ambiguous name after the user has already read the report.
    """
    names = [a.name for a in top_down.assumptions()] + [a.name for a in bottom_up.assumptions()]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ModelError(
            "%s: assumption name(s) used more than once: %s. Names address "
            "assumptions for solving, so they must be unique across the model."
            % (where, ", ".join(dupes))
        )
