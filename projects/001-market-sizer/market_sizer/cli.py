"""Command line entry point."""

import argparse
import datetime as _dt
import sys

from .assumptions import AssumptionError
from .loader import load
from .model import ModelError
from .report import RENDERERS


def build_parser():
    p = argparse.ArgumentParser(
        prog="market-sizer",
        description="Size a market top-down and bottom-up, and make the two reconcile.",
    )
    p.add_argument("input", help="JSON market definition (see examples/)")
    p.add_argument("--format", choices=sorted(RENDERERS), default="text")
    p.add_argument("--output", help="write to a file instead of stdout")
    p.add_argument("--tolerance", type=float, default=0.20,
                   help="fraction within which the two sizings count as agreeing (default 0.20)")
    p.add_argument("--solve", metavar="ASSUMPTION",
                   help="report the implied value for one assumption only")
    p.add_argument("--stale-after", type=int, default=24, metavar="MONTHS",
                   help="flag assumptions at least this old (default 24)")
    p.add_argument("--as-of", metavar="YYYY-MM-DD",
                   help="reference date for staleness (default: today)")
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero if the sizings do not reconcile, or if any "
                        "assumption is unverified or stale")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        as_of = _dt.date.fromisoformat(args.as_of) if args.as_of else _dt.date.today()
    except ValueError:
        print("error: --as-of %r is not an ISO date (YYYY-MM-DD)" % args.as_of, file=sys.stderr)
        return 2
    if args.tolerance < 0:
        print("error: --tolerance must not be negative", file=sys.stderr)
        return 2

    try:
        market = load(args.input)
    except (AssumptionError, ModelError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: cannot read %s (%s)" % (args.input, exc.strerror), file=sys.stderr)
        return 2

    try:
        rendered = RENDERERS[args.format](
            market,
            tolerance=args.tolerance,
            stale_after_months=args.stale_after,
            as_of=as_of,
            solve=args.solve,
        )
    except KeyError as exc:
        print("error: %s" % exc.args[0], file=sys.stderr)
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
        from .reconcile import reconcile
        problems = []
        if not reconcile(market).agrees_within(args.tolerance):
            problems.append("the two sizings do not reconcile")
        unverified = market.unverified()
        if unverified:
            problems.append("%d unverified assumption(s)" % len(unverified))
        stale = market.stale(args.stale_after, as_of)
        if stale:
            problems.append("%d stale assumption(s)" % len(stale))
        if problems:
            print("strict: " + "; ".join(problems), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
