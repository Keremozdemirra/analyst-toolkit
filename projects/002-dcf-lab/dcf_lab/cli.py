"""Command line entry point."""

import argparse
import datetime as _dt
import sys

from .assumptions import AssumptionError
from .loader import load
from .model import ModelError
from .report import RENDERERS
from .valuation import GORDON, ValuationError, value


def build_parser():
    p = argparse.ArgumentParser(
        prog="dcf-lab",
        description="Driver-based DCF that reports how much of the answer is terminal value.",
    )
    p.add_argument("input", help="JSON case definition (see examples/)")
    p.add_argument("--format", choices=sorted(RENDERERS), default="text")
    p.add_argument("--output", help="write to a file instead of stdout")
    p.add_argument("--terminal", choices=("gordon", "exit", "both"), default="both",
                   help="which terminal method to report (default both, which is the point)")
    timing = p.add_mutually_exclusive_group()
    timing.add_argument("--mid-year", dest="mid_year", action="store_true", default=None,
                        help="discount each year at t-0.5 rather than t")
    timing.add_argument("--end-year", dest="mid_year", action="store_false",
                        help="discount each year at t (the default)")
    p.add_argument("--terminal-share-limit", type=float, metavar="FRACTION",
                   help="under --strict, fail if the terminal share exceeds this. There "
                        "is no published threshold; supply one if your house has a view")
    p.add_argument("--stale-after", type=int, default=24, metavar="MONTHS",
                   help="flag assumptions at least this old (default 24)")
    p.add_argument("--as-of", metavar="YYYY-MM-DD",
                   help="reference date for staleness (default: today)")
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero if any assumption is unverified or stale, if "
                        "terminal growth exceeds the stated long-run GDP growth, or if "
                        "the terminal share exceeds --terminal-share-limit")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        as_of = _dt.date.fromisoformat(args.as_of) if args.as_of else _dt.date.today()
    except ValueError:
        print("error: --as-of %r is not an ISO date (YYYY-MM-DD)" % args.as_of, file=sys.stderr)
        return 2
    if args.terminal_share_limit is not None and not 0.0 <= args.terminal_share_limit <= 1.0:
        print("error: --terminal-share-limit must lie in [0, 1]", file=sys.stderr)
        return 2

    try:
        case = load(args.input)
    except (AssumptionError, ModelError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: cannot read %s (%s)" % (args.input, exc.strerror), file=sys.stderr)
        return 2

    if args.mid_year is not None:
        case = _with_mid_year(case, args.mid_year)

    try:
        rendered = RENDERERS[args.format](
            case,
            terminal=args.terminal,
            stale_after_months=args.stale_after,
            as_of=as_of,
        )
    except ValuationError as exc:
        # Refused rather than approximated. See gordon_terminal_value.
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except ModelError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(rendered + "\n")
        except OSError as exc:
            print("error: cannot write %s (%s)" % (args.output, exc.strerror), file=sys.stderr)
            return 2
    else:
        print(rendered)

    if args.strict:
        problems = []
        unverified = case.unverified()
        if unverified:
            problems.append("%d unverified assumption(s)" % len(unverified))
        stale = case.stale(args.stale_after, as_of)
        if stale:
            problems.append("%d stale assumption(s)" % len(stale))
        gdp = case.terminal.long_run_nominal_gdp
        if gdp is not None and case.terminal.growth.value > gdp.value:
            problems.append("terminal growth of %.2f%% exceeds long-run nominal GDP growth of %.2f%%"
                            % (case.terminal.growth.value * 100.0, gdp.value * 100.0))
        if args.terminal_share_limit is not None:
            share = value(case, method=GORDON).terminal_share
            if share is not None and share > args.terminal_share_limit:
                problems.append("terminal share of %.1f%% exceeds the limit of %.1f%%"
                                % (share * 100.0, args.terminal_share_limit * 100.0))
        if problems:
            print("strict: " + "; ".join(problems), file=sys.stderr)
            return 1
    return 0


def _with_mid_year(case, mid_year):
    """A copy of the case with the discounting convention overridden.

    Rebuilt rather than mutated because :class:`Case` is frozen, and it is
    frozen because a valuation that changes underneath a report is the failure
    mode this repository exists to avoid.
    """
    from .model import Case
    return Case(
        name=case.name,
        unit=case.unit,
        plan=case.plan,
        capital=case.capital,
        terminal=case.terminal,
        mid_year=mid_year,
        grid=case.grid,
    )


if __name__ == "__main__":
    sys.exit(main())
