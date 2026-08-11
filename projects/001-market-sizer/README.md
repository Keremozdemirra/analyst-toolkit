# market-sizer

Every market sizing arrives at a number. The number is never the interesting
part — the argument behind it is. This tool sizes a market twice, from the top
down and from the bottom up, puts the two beside each other, and then does the
one thing spreadsheets almost never do: it inverts the model and reports what
each assumption would have to be for the two sizings to agree.

That inverted number is usually where the conversation should start. "These
reconcile only if 32% of mid-market importers buy this" is a claim someone in
the room can accept or reject. "The market is €25m" is not.

Provenance is enforced, not encouraged. An assumption will not construct
without a source and a vintage, so an unsourced number cannot quietly enter the
model at all.

No dependencies beyond the Python standard library.

## Install

```bash
git clone <this repo>
cd projects/001-market-sizer
python3 -m unittest discover -s tests -t .   # 49 tests, no deps needed
```

## Use

Input is a JSON document. Top-down is a universe narrowed by factors; bottom-up
is segments, each a product of drivers.

```json
{
  "market": "CBAM reporting software for EU importers, annual",
  "unit": "EUR/yr",
  "top_down": {
    "universe": {"name": "EU compliance software spend", "value": 4200000000,
                 "unit": "EUR/yr", "source": "…", "as_of": "2024-01-01"},
    "factors": [
      {"name": "share that is environmental compliance", "value": 0.11,
       "kind": "share", "source": "…", "as_of": "2024-01-01"}
    ]
  },
  "bottom_up": {
    "segments": [
      {"name": "Large importers", "drivers": [
        {"name": "large importers in scope", "value": 8000, "kind": "count",
         "unit": "firms", "source": "…", "as_of": "2024-06-01"},
        {"name": "large importer attach rate", "value": 0.22, "kind": "share",
         "source": "…", "as_of": "2025-01-01"},
        {"name": "large importer price", "value": 14000, "kind": "price",
         "unit": "EUR/yr", "source": "…", "as_of": "2025-01-01"}
      ]}
    ]
  }
}
```

`source` and `as_of` are mandatory on every assumption. `kind` is optional but
worth setting: a `share` is checked to lie in [0, 1], which catches the single
most common sizing error — typing 35 where 0.35 was meant.

```bash
python3 -m market_sizer.cli examples/eu-cbam-advisory.json --as-of 2026-08-11
```

```
Illustrative: CBAM reporting software for EU importers, annual
======================================================================================
  Top-down                            24,948,000 EUR/yr
  Bottom-up                           46,096,000 EUR/yr
  Gap                                 21,148,000 EUR/yr
  Bottom-up / top-down                            1.85x

  DOES NOT RECONCILE at a tolerance of 20%

  Bottom-up by segment
  ------------------------------------------------------------------------------------
  Large importers                      #############               24,640,000 EUR/yr
  Mid-market importers                 ########                    14,904,000 EUR/yr
  Customs and freight intermediaries   ###                          6,552,000 EUR/yr
  ------------------------------------------------------------------------------------
  Total                                                            46,096,000 EUR/yr

  What would have to be true for the two to agree
  ------------------------------------------------------------------------------------
  Assumption                                        Assumed        Implied   Multiple
  EU compliance software spend                4,200,000,000  7,760,269,360      1.85x
  share that is environmental compliance               0.11         0.2032      1.85x
  share addressable by a CBAM-specific tool            0.18         0.3326      1.85x
  share reachable by a single vendor                    0.3         0.5543      1.85x
  large importers in scope                            8,000          1,134      0.14x
  large importer attach rate                           0.22        0.03118      0.14x
  large importer price                               14,000          1,984      0.14x
  mid-market importers in scope                      46,000     infeasible          -
      ! the other segments alone come to 3.1192e+07, already above the top-down total of 2.4948e+07; no value of 'mid-market importers in scope' can close the gap
```

Read the last block, not the first. The two sizings are a factor of 1.85 apart,
and the report says exactly what that costs: either the addressable share of EU
compliance software spend is 20% rather than 11%, or large-importer penetration
is 3% rather than 22%. Three of the bottom-up drivers cannot close the gap at
all — the other segments on their own already exceed the top-down total, so no
value of those drivers, not even zero, would do it. That is a finding about the
shape of the disagreement, and it is invisible if you only look at the gap.

Useful flags:

```bash
--solve "mid-market attach rate"   # invert one assumption only
--tolerance 0.10                   # how close counts as reconciled (default 0.20)
--stale-after 18                   # flag assumptions at least this many months old
--as-of 2026-08-11                 # reference date for staleness (default: today)
--format markdown|json             # instead of the text table
--output sizing.md                 # write to a file
--strict                           # exit 1 if it does not reconcile, or if any
                                   # assumption is unverified or stale
```

`--strict` is the CI hook: put a sizing under version control and the build
fails when its inputs go stale, rather than when someone finally re-reads it.

As a library:

```python
from market_sizer.loader import load
from market_sizer.reconcile import reconcile, solve_for

market = load("examples/eu-cbam-advisory.json")
print(reconcile(market).ratio)                    # 1.847...
print(solve_for(market, "large importer attach rate").implied)   # 0.0311...
```

## Method

Both sizings are deliberately kept to one algebraic shape:

```
top-down:   T = U · Π f_k
bottom-up:  B = Σ_s Π_j d_sj
```

Nothing else is allowed in. That restraint is what makes the inversion exact
rather than a numerical search.

**Top-down inversion.** `T` is a single product, so scaling any one factor by
`B/T` sets `T = B`. Every top-down assumption therefore has the *same* multiple
— which is itself the finding: top-down sizing cannot tell you which of its
factors is wrong, only that their product is.

**Bottom-up inversion.** `B` is a sum, so only the segment containing the
driver moves and the other segments act as a floor. Setting driver `d` in
segment `s` to

```
d' = d · (T − Σ_{s'≠s} V_s') / V_s
```

closes the gap when the numerator is non-negative, and is **infeasible** when it
is not. Infeasibility is reported rather than clamped, because "no value of this
driver can close the gap" is a stronger statement than any number would be.

The rest of the sum is computed by summing the other segments directly rather
than as `B − V_s`. That subtraction cancels most of the significant digits when
one segment dominates the total; the inversion test caught it doing so at a
relative error of 7e-8.

**What the tests assert.** Not that the code runs. The suite pins three
analytical properties of the model. Every top-down factor has an elasticity of
exactly 1; every bottom-up driver has an elasticity exactly equal to its
segment's share of the total; and — the one that matters — substituting a solved
implied value back into the model closes the gap to within 1e-9 relative, swept
over 120 randomly generated markets and every assumption in each.

**Staleness.** `as_of` is the vintage of the figure, not the date it was pasted
into the model. Age is counted in whole calendar months, and the threshold is
inclusive: an assumption dated 2023-01-01 is stale at 24 months on 2025-01-01.

**What this is not.** It is not a forecast — there is no time dimension
anywhere in it. It is not a validator: it will reconcile two equally wrong
sizings without complaint, and agreement between them is evidence of a shared
assumption at least as often as it is evidence of truth. It does no unit
conversion; if you mix EUR/yr with EUR/month it will add them. And it will not
tell you which sizing is right. It tells you what you would have to believe for
them to be the same, which is a different and more useful thing.

## The example

`examples/eu-cbam-advisory.json` is illustrative. Every figure in it is marked
`"verified": false` and carries the source string *"Illustrative placeholder —
no published source"*, which is why `--strict` fails on it and why the register
prints `UNVERIFIED` against all thirteen assumptions. That is deliberate: the
example demonstrates the shape of the argument, and no number in it should be
quoted. Replace them with your own sourced inputs.

## Licence

MIT.
