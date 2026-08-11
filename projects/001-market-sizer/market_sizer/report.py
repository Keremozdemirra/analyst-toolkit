"""Rendering. Three formats, one set of numbers."""

import datetime as _dt
import json

from .reconcile import reconcile, solve_for

_WIDTH = 86


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


def _pct(x):
    return "-" if x is None else "{:+.1f}%".format(x * 100.0)


def text_report(market, tolerance=0.20, stale_after_months=24, as_of=None, solve=None):
    rec = reconcile(market)
    as_of = as_of or _dt.date.today()
    lines = []
    lines.append(market.name)
    lines.append("=" * _WIDTH)
    lines.append("  %-24s %s" % ("Top-down", _num(rec.top_down, market.unit).rjust(28)))
    lines.append("  %-24s %s" % ("Bottom-up", _num(rec.bottom_up, market.unit).rjust(28)))
    lines.append("  %-24s %s" % ("Gap", _num(rec.gap, market.unit).rjust(28)))
    ratio = "{:.2f}x".format(rec.ratio) if rec.top_down else "-"
    lines.append("  %-24s %s" % ("Bottom-up / top-down", ratio.rjust(28)))
    lines.append("")
    verdict = "RECONCILED" if rec.agrees_within(tolerance) else "DOES NOT RECONCILE"
    lines.append("  %s at a tolerance of %.0f%%" % (verdict, tolerance * 100.0))
    lines.append("")

    lines.append("  Bottom-up by segment")
    lines.append("  " + "-" * (_WIDTH - 2))
    total = rec.bottom_up
    for s in market.bottom_up.segments:
        share = (s.value / total) if total else 0.0
        bar = "#" * int(round(share * 24))
        lines.append("  %-36s %-24s %s" % (s.name[:36], bar, _num(s.value, market.unit).rjust(20)))
    lines.append("  " + "-" * (_WIDTH - 2))
    lines.append("  %-36s %-24s %s" % ("Total", "", _num(total, market.unit).rjust(20)))
    lines.append("")

    targets = [solve] if solve else [a.name for a in market.assumptions()]
    lines.append("  What would have to be true for the two to agree")
    lines.append("  " + "-" * (_WIDTH - 2))
    lines.append("  %-42s %14s %14s %10s" % ("Assumption", "Assumed", "Implied", "Multiple"))
    for name in targets:
        r = solve_for(market, name)
        implied = _num(r.implied) if r.feasible else "infeasible"
        mult = "{:.2f}x".format(r.multiple) if (r.feasible and r.multiple is not None) else "-"
        lines.append("  %-42s %14s %14s %10s" % (name[:42], _num(r.current), implied, mult))
        if not r.feasible and r.reason:
            lines.append("      ! %s" % r.reason)
    lines.append("")

    lines.append("  Assumption register")
    lines.append("  " + "-" * (_WIDTH - 2))
    for a in market.assumptions():
        flags = []
        if not a.verified:
            flags.append("UNVERIFIED")
        if a.is_stale(stale_after_months, as_of):
            flags.append("STALE %dm" % a.age_months(as_of))
        flag = ("  [%s]" % ", ".join(flags)) if flags else ""
        lines.append("  %-42s %18s  %s" % (a.name[:42], _num(a.value, a.unit), a.as_of.isoformat()))
        lines.append("      %s%s" % (a.source, flag))
    return "\n".join(lines)


def markdown_report(market, tolerance=0.20, stale_after_months=24, as_of=None, solve=None):
    rec = reconcile(market)
    as_of = as_of or _dt.date.today()
    out = ["# %s" % market.name, ""]
    out.append("| Sizing | Value |")
    out.append("| --- | ---: |")
    out.append("| Top-down | %s |" % _num(rec.top_down, market.unit))
    out.append("| Bottom-up | %s |" % _num(rec.bottom_up, market.unit))
    out.append("| Gap | %s |" % _num(rec.gap, market.unit))
    out.append("| Bottom-up / top-down | %s |" % ("{:.2f}x".format(rec.ratio) if rec.top_down else "-"))
    out.append("")
    out.append("**%s** at a tolerance of %.0f%%." % (
        "Reconciled" if rec.agrees_within(tolerance) else "Does not reconcile", tolerance * 100.0))
    out.append("")
    out.append("## Bottom-up by segment")
    out.append("")
    out.append("| Segment | Value | Share |")
    out.append("| --- | ---: | ---: |")
    for s in market.bottom_up.segments:
        share = (s.value / rec.bottom_up) if rec.bottom_up else 0.0
        out.append("| %s | %s | %.1f%% |" % (s.name, _num(s.value, market.unit), share * 100.0))
    out.append("")
    out.append("## Implied assumptions")
    out.append("")
    out.append("| Assumption | Assumed | Implied | Multiple |")
    out.append("| --- | ---: | ---: | ---: |")
    for name in ([solve] if solve else [a.name for a in market.assumptions()]):
        r = solve_for(market, name)
        implied = _num(r.implied) if r.feasible else "infeasible"
        mult = "{:.2f}x".format(r.multiple) if (r.feasible and r.multiple is not None) else "-"
        out.append("| %s | %s | %s | %s |" % (name, _num(r.current), implied, mult))
    out.append("")
    out.append("## Assumption register")
    out.append("")
    out.append("| Assumption | Value | Vintage | Source | Flags |")
    out.append("| --- | ---: | --- | --- | --- |")
    for a in market.assumptions():
        flags = []
        if not a.verified:
            flags.append("unverified")
        if a.is_stale(stale_after_months, as_of):
            flags.append("stale (%dm)" % a.age_months(as_of))
        out.append("| %s | %s | %s | %s | %s |" % (
            a.name, _num(a.value, a.unit), a.as_of.isoformat(), a.source, ", ".join(flags) or "-"))
    return "\n".join(out)


def json_report(market, tolerance=0.20, stale_after_months=24, as_of=None, solve=None):
    rec = reconcile(market)
    as_of = as_of or _dt.date.today()
    payload = {
        "market": market.name,
        "unit": market.unit,
        "reconciliation": rec.to_dict(),
        "tolerance": tolerance,
        "reconciled": rec.agrees_within(tolerance),
        "segments": [
            {"name": s.name, "value": s.value,
             "share": (s.value / rec.bottom_up) if rec.bottom_up else None}
            for s in market.bottom_up.segments
        ],
        "implied": [
            solve_for(market, name).to_dict()
            for name in ([solve] if solve else [a.name for a in market.assumptions()])
        ],
        "assumptions": [
            dict(a.to_dict(), age_months=a.age_months(as_of),
                 stale=a.is_stale(stale_after_months, as_of))
            for a in market.assumptions()
        ],
        "as_of": as_of.isoformat(),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


RENDERERS = {"text": text_report, "markdown": markdown_report, "json": json_report}
