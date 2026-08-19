"""The unit of input: a number that knows where it came from.

A discounted cash flow is a long chain of assumptions with a currency figure at
the end of it, and the figure inherits the authority of none of them. So
provenance is not optional metadata here -- an :class:`Assumption` will not
construct without a source and a date.

The kind system exists to catch the two errors that survive review most often:
a percentage entered where a fraction was meant, and a multiple entered as a
rate. Both produce a number that looks plausible in a table.
"""

import datetime as _dt
from dataclasses import dataclass
from typing import Optional

#: A quantity declared as a share must lie in [0, 1]: tax rates, payout
#: fractions, weights. A rate may be negative -- margins and growth both go
#: below zero and a model that forbids that is lying about the business.
SHARE = "share"
RATE = "rate"
MULTIPLE = "multiple"
COUNT = "count"
PRICE = "price"
VALUE = "value"

KINDS = (SHARE, RATE, MULTIPLE, COUNT, PRICE, VALUE)


class AssumptionError(ValueError):
    """An assumption is missing provenance, or is inconsistent with its kind."""


def _parse_date(raw, where):
    if isinstance(raw, _dt.date):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise AssumptionError("%s: as_of is required (ISO date, e.g. 2025-11-30)" % where)
    try:
        return _dt.date.fromisoformat(raw.strip())
    except ValueError:
        raise AssumptionError("%s: as_of %r is not an ISO date (YYYY-MM-DD)" % (where, raw))


@dataclass(frozen=True)
class Assumption:
    """A single number with its provenance attached.

    ``source`` and ``as_of`` are mandatory. ``as_of`` is the vintage of the
    figure -- when the source published or measured it -- not when it was copied
    into the model. In a DCF that distinction bites harder than it does in a
    sizing: a risk-free rate from 2021 and one from 2025 are different models of
    the world, not different roundings of the same one.
    """

    name: str
    value: float
    source: str
    as_of: _dt.date
    unit: str = ""
    kind: str = VALUE
    note: str = ""
    verified: bool = True

    def __post_init__(self):
        where = "assumption %r" % (self.name or "<unnamed>")
        if not str(self.name).strip():
            raise AssumptionError("every assumption needs a name")
        if not isinstance(self.source, str) or not self.source.strip():
            raise AssumptionError(
                "%s: source is required. If you genuinely do not have one, say so "
                "explicitly and set verified=false -- do not leave it blank." % where
            )
        if self.kind not in KINDS:
            raise AssumptionError("%s: kind %r must be one of %s" % (where, self.kind, ", ".join(KINDS)))
        try:
            value = float(self.value)
        except (TypeError, ValueError):
            raise AssumptionError("%s: value %r is not a number" % (where, self.value))
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "as_of", _parse_date(self.as_of, where))
        if self.kind == SHARE and not (0.0 <= value <= 1.0):
            raise AssumptionError(
                "%s: declared as a share but value is %g. Shares are fractions, "
                "not percentages." % (where, value)
            )
        if self.kind in (COUNT, PRICE, MULTIPLE) and value < 0:
            raise AssumptionError("%s: a %s cannot be negative (%g)" % (where, self.kind, value))

    def age_months(self, as_of=None):
        """Whole months between this assumption's vintage and ``as_of``."""
        ref = as_of or _dt.date.today()
        months = (ref.year - self.as_of.year) * 12 + (ref.month - self.as_of.month)
        if ref.day < self.as_of.day:
            months -= 1
        return months

    def is_stale(self, stale_after_months, as_of=None):
        return self.age_months(as_of) >= stale_after_months

    def replace(self, value):
        """Return a copy carrying a different value, provenance preserved."""
        return Assumption(
            name=self.name,
            value=value,
            source=self.source,
            as_of=self.as_of,
            unit=self.unit,
            kind=self.kind,
            note=self.note,
            verified=self.verified,
        )

    def to_dict(self):
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "kind": self.kind,
            "source": self.source,
            "as_of": self.as_of.isoformat(),
            "note": self.note,
            "verified": self.verified,
        }


def from_dict(raw, where="assumption"):
    if not isinstance(raw, dict):
        raise AssumptionError("%s: expected an object, got %r" % (where, type(raw).__name__))
    unknown = set(raw) - {
        "name", "value", "unit", "kind", "source", "as_of", "note", "verified",
    }
    if unknown:
        raise AssumptionError("%s: unknown field(s) %s" % (where, ", ".join(sorted(unknown))))
    missing = [k for k in ("name", "value", "source", "as_of") if k not in raw]
    if missing:
        raise AssumptionError("%s: missing required field(s) %s" % (where, ", ".join(missing)))
    return Assumption(
        name=raw["name"],
        value=raw["value"],
        source=raw["source"],
        as_of=raw["as_of"],
        unit=raw.get("unit", ""),
        kind=raw.get("kind", VALUE),
        note=raw.get("note", ""),
        verified=bool(raw.get("verified", True)),
    )
