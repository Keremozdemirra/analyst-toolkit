"""Reading a case from JSON.

JSON rather than a spreadsheet because a DCF is nested -- six driver series, a
cost of capital with an open list of premia, two terminal specifications -- and
because a driver in a cell has nowhere to record where it came from. The
provenance is the reason the format is what it is.

A driver may be written either as a single object, meaning the same value in
every forecast year, or as a list of one object per year. The single-object form
is not a convenience: a driver that is constant across the forecast is a
statement, and writing it once makes that statement visible instead of burying
it in five identical rows.
"""

import json

from .assumptions import AssumptionError, from_dict
from .model import (
    DRIVER_NAMES, Capital, Case, Drivers, Grid, ModelError, Plan, Terminal,
)

_TOP_LEVEL = {
    "company", "unit", "years", "base_revenue", "drivers", "wacc", "terminal",
    "discounting", "sensitivity", "notes",
}
_WACC_FIELDS = {
    "risk_free", "beta", "equity_risk_premium", "premia", "cost_of_debt_pretax",
    "marginal_tax_rate", "market_value_equity", "market_value_debt",
}
_TERMINAL_FIELDS = {"growth", "exit_multiple", "metric", "long_run_nominal_gdp"}


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
    for required in ("company", "unit", "years", "base_revenue", "drivers", "wacc", "terminal"):
        if required not in raw:
            raise ModelError("%s: missing required field %r" % (where, required))

    years = raw["years"]
    if not isinstance(years, int) or isinstance(years, bool) or years < 1:
        raise ModelError("%s: 'years' must be a positive whole number" % where)

    base_revenue = from_dict(raw["base_revenue"], where="%s: base_revenue" % where)
    drivers, declared = _parse_drivers(raw["drivers"], years, where)
    capital = _parse_capital(raw["wacc"], where)
    terminal = _parse_terminal(raw["terminal"], where)
    grid = _parse_grid(raw.get("sensitivity"), where)

    discounting = raw.get("discounting") or {}
    if not isinstance(discounting, dict):
        raise ModelError("%s: 'discounting' must be an object" % where)
    unknown = set(discounting) - {"mid_year"}
    if unknown:
        raise ModelError("%s: unknown discounting field(s) %s" % (where, ", ".join(sorted(unknown))))
    mid_year = bool(discounting.get("mid_year", False))

    declared = ([base_revenue] + declared + capital.assumptions() + terminal.assumptions())
    _reject_duplicate_names(declared, where)

    return Case(
        name=raw["company"],
        unit=raw["unit"],
        plan=Plan(base_revenue=base_revenue, drivers=drivers),
        capital=capital,
        terminal=terminal,
        mid_year=mid_year,
        grid=grid,
    )


def _parse_drivers(raw, years, where):
    if not isinstance(raw, dict):
        raise ModelError("%s: 'drivers' must be an object" % where)
    unknown = set(raw) - set(DRIVER_NAMES)
    if unknown:
        raise ModelError(
            "%s: unknown driver(s) %s. The projection takes exactly these six: %s"
            % (where, ", ".join(sorted(unknown)), ", ".join(DRIVER_NAMES))
        )
    missing = [d for d in DRIVER_NAMES if d not in raw]
    if missing:
        raise ModelError(
            "%s: missing driver(s) %s. Every driver must be stated even where it is "
            "zero; an omitted capex ratio is indistinguishable from a forgotten one."
            % (where, ", ".join(missing))
        )

    series = {}
    declared = []
    for name in DRIVER_NAMES:
        entry = raw[name]
        if isinstance(entry, dict):
            a = from_dict(entry, where="%s: drivers.%s" % (where, name))
            series[name] = [a] * years
            declared.append(a)
        elif isinstance(entry, list):
            if len(entry) != years:
                raise ModelError(
                    "%s: driver %r has %d year(s) but the forecast is %d year(s) long"
                    % (where, name, len(entry), years)
                )
            values = [
                from_dict(e, where="%s: drivers.%s[%d]" % (where, name, i))
                for i, e in enumerate(entry)
            ]
            series[name] = values
            declared.extend(values)
        else:
            raise ModelError(
                "%s: driver %r must be an object (constant across the forecast) or a "
                "list of %d objects (one per year)" % (where, name, years)
            )
    return Drivers(**series), declared


def _parse_capital(raw, where):
    if not isinstance(raw, dict):
        raise ModelError("%s: 'wacc' must be an object" % where)
    unknown = set(raw) - _WACC_FIELDS
    if unknown:
        raise ModelError("%s: unknown wacc field(s) %s" % (where, ", ".join(sorted(unknown))))
    required = _WACC_FIELDS - {"premia"}
    missing = sorted(required - set(raw))
    if missing:
        raise ModelError(
            "%s: wacc is missing %s. The build-up is the input; a single WACC number "
            "is not accepted because it cannot be reviewed."
            % (where, ", ".join(missing))
        )
    premia_raw = raw.get("premia", [])
    if not isinstance(premia_raw, list):
        raise ModelError("%s: wacc.premia must be a list" % where)
    premia = [
        from_dict(p, where="%s: wacc.premia[%d]" % (where, i))
        for i, p in enumerate(premia_raw)
    ]
    return Capital(
        risk_free=from_dict(raw["risk_free"], where="%s: wacc.risk_free" % where),
        beta=from_dict(raw["beta"], where="%s: wacc.beta" % where),
        equity_risk_premium=from_dict(
            raw["equity_risk_premium"], where="%s: wacc.equity_risk_premium" % where),
        cost_of_debt_pretax=from_dict(
            raw["cost_of_debt_pretax"], where="%s: wacc.cost_of_debt_pretax" % where),
        marginal_tax_rate=from_dict(
            raw["marginal_tax_rate"], where="%s: wacc.marginal_tax_rate" % where),
        market_value_equity=from_dict(
            raw["market_value_equity"], where="%s: wacc.market_value_equity" % where),
        market_value_debt=from_dict(
            raw["market_value_debt"], where="%s: wacc.market_value_debt" % where),
        premia=premia,
    )


def _parse_terminal(raw, where):
    if not isinstance(raw, dict):
        raise ModelError("%s: 'terminal' must be an object" % where)
    unknown = set(raw) - _TERMINAL_FIELDS
    if unknown:
        raise ModelError("%s: unknown terminal field(s) %s" % (where, ", ".join(sorted(unknown))))
    for required in ("growth", "exit_multiple"):
        if required not in raw:
            raise ModelError(
                "%s: terminal.%s is required. Both terminal methods are mandatory "
                "because each is the only available check on the other."
                % (where, required)
            )
    gdp = raw.get("long_run_nominal_gdp")
    return Terminal(
        growth=from_dict(raw["growth"], where="%s: terminal.growth" % where),
        exit_multiple=from_dict(raw["exit_multiple"], where="%s: terminal.exit_multiple" % where),
        metric=raw.get("metric", "ebitda"),
        long_run_nominal_gdp=(
            from_dict(gdp, where="%s: terminal.long_run_nominal_gdp" % where)
            if gdp is not None else None
        ),
    )


def _parse_grid(raw, where):
    if raw is None:
        return Grid()
    if not isinstance(raw, dict):
        raise ModelError("%s: 'sensitivity' must be an object" % where)
    unknown = set(raw) - {"wacc_deltas", "growth_deltas"}
    if unknown:
        raise ModelError("%s: unknown sensitivity field(s) %s" % (where, ", ".join(sorted(unknown))))
    defaults = Grid()
    out = {}
    for name in ("wacc_deltas", "growth_deltas"):
        values = raw.get(name)
        if values is None:
            out[name] = getattr(defaults, name)
            continue
        if not isinstance(values, list) or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            raise ModelError("%s: sensitivity.%s must be a list of numbers" % (where, name))
        out[name] = tuple(float(v) for v in values)
    return Grid(**out)


def _reject_duplicate_names(declared, where):
    """Assumption names address rows in the register, so they must be unique.

    Catching this at load time is much kinder than letting a reader believe two
    different numbers on two different lines are the same figure.
    """
    names = [a.name for a in declared]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ModelError(
            "%s: assumption name(s) used more than once: %s. Two assumptions with "
            "one name cannot be told apart in the register."
            % (where, ", ".join(dupes))
        )
