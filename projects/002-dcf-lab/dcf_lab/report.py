"""Rendering. Three formats, one set of numbers.

The order of the sections is an argument. The cost of capital comes first
because it is the assumption with the largest effect and the least evidence
behind it. The decomposition comes before the sensitivity grid because the
reader should learn what fraction of the answer is terminal before being shown
how that fraction moves. The enterprise value itself is deliberately not the
first thing on the page.
"""

import datetime as _dt
import json
import textwrap

from .model import project
from .valuation import EXIT, GORDON, review, sensitivity, value

_WIDTH = 100


def _num(x, unit=""):
    if x is None:
        return "-"
    if abs(x) >= 1000 or x == int(x):
        s = "{:,.0f}".format(x)
    elif abs(x) >= 1:
        s = "{:,.2f}".format(x)
    else:
        s = "{:.4g}".format(x)
    return ("%s %s" % (s, unit)).strip()


def _rate(x):
    """Rates are printed as percentages to two decimals.

    Two rather than one because the whole tool is about the difference between
    a WACC of 8.06% and one of 8.1%, and rounding that away in the report while
    computing on it would be a small lie in a document about large ones.
    """
    return "-" if x is None else "{:.2f}%".format(x * 100.0)


def _share(x):
    return "-" if x is None else "{:.1f}%".format(x * 100.0)


def _multiple(x):
    return "-" if x is None else "{:.2f}x".format(x)


def _bar(share, width=28):
    if share is None:
        return ""
    return "#" * max(0, min(width, int(round(share * width))))


def _valuations(case, methods):
    out = []
    if GORDON in methods:
        out.append(value(case, method=GORDON))
    if EXIT in methods:
        out.append(value(case, method=EXIT))
    return out


def _methods(terminal):
    if terminal in (GORDON, EXIT):
        return [terminal]
    return [GORDON, EXIT]


_LABEL = {GORDON: "Gordon growth", EXIT: "Exit multiple"}


def _terminal_heading(valuations):
    """Both methods get a comparison heading; one method gets its own name.

    Naming the section "stated both ways" when only one way is shown would be
    the kind of small untruth this repository is meant not to contain.
    """
    if len(valuations) > 1:
        return "Terminal value, stated both ways"
    return "Terminal value (%s only)" % _LABEL[valuations[0].method].lower()


def _TERMINAL_ROWS(years):
    """The comparison rows, shared by the text and markdown reports.

    Shared rather than written twice so the two formats cannot drift into
    disagreeing about the same valuation.
    """
    return [
        ("Terminal value at year %d" % years, lambda v: _num(v.terminal_value)),
        ("Present value of terminal value", lambda v: _num(v.pv_terminal)),
        ("Enterprise value", lambda v: _num(v.enterprise_value)),
        ("Terminal share of enterprise value", lambda v: _share(v.terminal_share)),
        ("Implied exit multiple", lambda v: _multiple(v.implied_exit_multiple)
         + (" (stated)" if v.method == EXIT else "")),
        ("Implied perpetual growth", lambda v: _rate(v.implied_growth)
         + (" (stated)" if v.method == GORDON else "")),
    ]


def text_report(case, terminal="both", stale_after_months=24, as_of=None):
    as_of = as_of or _dt.date.today()
    methods = _methods(terminal)
    valuations = _valuations(case, methods)
    lines = []
    lines.append(case.name)
    lines.append("=" * _WIDTH)

    lines.append("  Cost of capital")
    lines.append("  " + "-" * (_WIDTH - 2))
    for label, amount, kind in case.capital.build_up():
        rendered = _share(amount) if kind == "weight" else _rate(amount)
        indent = 2 if kind == "total" else 4
        lines.append("%s%s %s" % (" " * indent, label.ljust(50 - indent), rendered.rjust(12)))
    lines.append("")

    years = project(case.plan)
    base = valuations[0]
    lines.append("  Projection (%s), %s discounting" % (
        case.unit, "mid-year" if case.mid_year else "end-year"))
    lines.append("  " + "-" * (_WIDTH - 2))
    row_format = "  %4s %9s %7s %9s %7s %9s %8s %8s %8s %9s %9s"
    lines.append(row_format % (
        "Year", "Revenue", "Growth", "EBIT", "Margin", "NOPAT", "+D&A", "-Capex",
        "-dNWC", "FCFF", "PV"))
    for y, pv in zip(years, base.pv_by_year):
        lines.append(row_format % (
            y.year, _num(y.revenue), _rate(y.growth), _num(y.ebit), _rate(y.margin),
            _num(y.nopat), _num(y.da), _num(y.capex), _num(y.nwc_change),
            _num(y.fcff), _num(pv)))
    lines.append("  " + "-" * (_WIDTH - 2))
    lines.append("  %-60s %s" % ("Forecast period present value",
                                 _num(base.pv_forecast, case.unit).rjust(36)))
    lines.append("")

    lines.append("  %s" % _terminal_heading(valuations))
    lines.append("  " + "-" * (_WIDTH - 2))

    def _row(label, cells):
        lines.append("  %-36s%s" % (label, "".join("%28s" % c for c in cells)))

    _row("", [_LABEL[v.method] for v in valuations])
    for label, fn in _TERMINAL_ROWS(case.plan.years):
        _row(label, [fn(v) for v in valuations])
    both = {v.method: v for v in valuations}
    gordon = both.get(GORDON)
    exit_based = both.get(EXIT)
    if gordon is not None and exit_based is not None and exit_based.enterprise_value:
        ratio = gordon.enterprise_value / exit_based.enterprise_value
        lines.append("")
        lines.append("  The Gordon enterprise value is %.2fx the exit-multiple value. The last two"
                     % ratio)
        lines.append("  rows are each method restated in the other's units, which is the only")
        lines.append("  check either of them has.")
    lines.append("")

    lines.append("  Where the value comes from")
    lines.append("  " + "-" * (_WIDTH - 2))
    for v in valuations:
        lines.append("  %s" % _LABEL[v.method])
        lines.append("    %-26s %16s %8s  %s" % (
            "Forecast period PV", _num(v.pv_forecast), _share(v.forecast_share),
            _bar(v.forecast_share)))
        lines.append("    %-26s %16s %8s  %s" % (
            "Terminal PV", _num(v.pv_terminal), _share(v.terminal_share),
            _bar(v.terminal_share)))
        lines.append("    %-26s %16s %8s" % (
            "Enterprise value", _num(v.enterprise_value, case.unit), "100.0%"))
    lines.append("")
    if base.terminal_share is not None:
        lines.append("  %s of the %s valuation is a terminal value: a figure produced by two" % (
            _share(base.terminal_share), _LABEL[base.method]))
        lines.append("  parameters applied to the last forecast year, not by the forecast itself.")
        lines.append("")

    grid = sensitivity(case)
    lines.append("  Sensitivity: enterprise value, and terminal share beneath it")
    lines.append("  " + "-" * (_WIDTH - 2))
    header = "  %-12s" % "WACC \\ g"
    for g in grid.growths:
        header += "%16s" % _rate(g)
    lines.append(header)
    for w, row in zip(grid.waccs, grid.cells):
        value_line = "  %-12s" % _rate(w)
        share_line = "  %-12s" % ""
        for cell in row:
            if cell.feasible:
                value_line += "%16s" % _num(cell.enterprise_value)
                share_line += "%16s" % _share(cell.terminal_share)
            else:
                value_line += "%16s" % "g >= w"
                share_line += "%16s" % "-"
        lines.append(value_line)
        lines.append(share_line)
    low, high = grid.value_range
    if low is not None:
        lines.append("  " + "-" * (_WIDTH - 2))
        lines.append("  Enterprise value across the grid: %s to %s (%.2fx)" % (
            _num(low), _num(high, case.unit), (high / low) if low else float("nan")))
        share_low, share_high = grid.terminal_share_range
        lines.append("  Terminal share across the grid: %s to %s" % (
            _share(share_low), _share(share_high)))
    lines.append("")

    notes = review(case)
    if notes:
        lines.append("  Review")
        lines.append("  " + "-" * (_WIDTH - 2))
        for note in notes:
            wrapped = textwrap.wrap(note, width=_WIDTH - 6)
            lines.append("  ! %s" % wrapped[0])
            for continuation in wrapped[1:]:
                lines.append("    %s" % continuation)
        lines.append("")

    lines.append("  Assumption register")
    lines.append("  " + "-" * (_WIDTH - 2))
    for a in case.assumptions():
        flags = []
        if not a.verified:
            flags.append("UNVERIFIED")
        if a.is_stale(stale_after_months, as_of):
            flags.append("STALE %dm" % a.age_months(as_of))
        flag = ("  [%s]" % ", ".join(flags)) if flags else ""
        lines.append("  %-52s %20s  %s" % (a.name[:52], _num(a.value, a.unit), a.as_of.isoformat()))
        lines.append("      %s%s" % (a.source, flag))
    return "\n".join(lines)


def markdown_report(case, terminal="both", stale_after_months=24, as_of=None):
    as_of = as_of or _dt.date.today()
    methods = _methods(terminal)
    valuations = _valuations(case, methods)
    base = valuations[0]
    out = ["# %s" % case.name, ""]

    out.append("## Cost of capital")
    out.append("")
    out.append("| Component | Value |")
    out.append("| --- | ---: |")
    for label, amount, kind in case.capital.build_up():
        rendered = _share(amount) if kind == "weight" else _rate(amount)
        shown = "**%s**" % rendered if kind == "total" else rendered
        out.append("| %s | %s |" % (label, shown))
    out.append("")

    out.append("## Projection (%s)" % case.unit)
    out.append("")
    out.append("| Year | Revenue | Growth | EBIT | Margin | +D&A | -Capex | -dNWC | FCFF | PV |")
    out.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for y, pv in zip(project(case.plan), base.pv_by_year):
        out.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            y.year, _num(y.revenue), _rate(y.growth), _num(y.ebit), _rate(y.margin),
            _num(y.da), _num(y.capex), _num(y.nwc_change), _num(y.fcff), _num(pv)))
    out.append("")
    out.append("Forecast period present value: **%s**." % _num(base.pv_forecast, case.unit))
    out.append("")

    out.append("## %s" % _terminal_heading(valuations))
    out.append("")
    out.append("| | %s |" % " | ".join(_LABEL[v.method] for v in valuations))
    out.append("| --- |%s" % ("|".join([" ---: "] * len(valuations)) + "|"))
    for label, fn in _TERMINAL_ROWS(case.plan.years):
        out.append("| %s | %s |" % (label, " | ".join(fn(v) for v in valuations)))
    out.append("")

    out.append("## Where the value comes from")
    out.append("")
    out.append("| Method | Forecast PV | Terminal PV | Enterprise value | Terminal share |")
    out.append("| --- | ---: | ---: | ---: | ---: |")
    for v in valuations:
        out.append("| %s | %s | %s | %s | **%s** |" % (
            _LABEL[v.method], _num(v.pv_forecast), _num(v.pv_terminal),
            _num(v.enterprise_value), _share(v.terminal_share)))
    out.append("")

    grid = sensitivity(case)
    out.append("## Sensitivity: enterprise value (terminal share)")
    out.append("")
    out.append("| WACC \\ g | %s |" % " | ".join(_rate(g) for g in grid.growths))
    out.append("| --- |%s" % ("|".join([" ---: "] * len(grid.growths)) + "|"))
    for w, row in zip(grid.waccs, grid.cells):
        cells = []
        for cell in row:
            cells.append("%s (%s)" % (_num(cell.enterprise_value), _share(cell.terminal_share))
                         if cell.feasible else "g >= w")
        out.append("| %s | %s |" % (_rate(w), " | ".join(cells)))
    out.append("")

    notes = review(case)
    if notes:
        out.append("## Review")
        out.append("")
        for note in notes:
            out.append("- %s" % note)
        out.append("")

    out.append("## Assumption register")
    out.append("")
    out.append("| Assumption | Value | Vintage | Source | Flags |")
    out.append("| --- | ---: | --- | --- | --- |")
    for a in case.assumptions():
        flags = []
        if not a.verified:
            flags.append("unverified")
        if a.is_stale(stale_after_months, as_of):
            flags.append("stale (%dm)" % a.age_months(as_of))
        out.append("| %s | %s | %s | %s | %s |" % (
            a.name, _num(a.value, a.unit), a.as_of.isoformat(), a.source, ", ".join(flags) or "-"))
    return "\n".join(out)


def json_report(case, terminal="both", stale_after_months=24, as_of=None):
    as_of = as_of or _dt.date.today()
    valuations = _valuations(case, _methods(terminal))
    payload = {
        "company": case.name,
        "unit": case.unit,
        "as_of": as_of.isoformat(),
        "mid_year": case.mid_year,
        "cost_of_capital": {
            "cost_of_equity": case.capital.cost_of_equity,
            "after_tax_cost_of_debt": case.capital.after_tax_cost_of_debt,
            "equity_weight": case.capital.equity_weight,
            "debt_weight": case.capital.debt_weight,
            "wacc": case.capital.wacc,
            "build_up": [
                {"label": label, "value": amount, "kind": kind}
                for label, amount, kind in case.capital.build_up()
            ],
        },
        "valuations": [v.to_dict() for v in valuations],
        "sensitivity": sensitivity(case).to_dict(),
        "review": review(case),
        "assumptions": [
            dict(a.to_dict(), age_months=a.age_months(as_of),
                 stale=a.is_stale(stale_after_months, as_of))
            for a in case.assumptions()
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


RENDERERS = {"text": text_report, "markdown": markdown_report, "json": json_report}
