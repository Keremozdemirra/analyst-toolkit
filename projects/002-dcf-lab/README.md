# dcf-lab

A discounted cash flow produces a single currency figure, and the figure
inherits an authority that none of its inputs deserve. The forecast period is
where the work goes: three weeks of margin bridges, capex phasing and working
capital. The terminal value is where the value is, and it is two parameters
long.

This tool projects free cash flow to the firm from six named drivers, builds
the cost of capital up from its components rather than accepting a rate, values
the terminal period twice, and then reports the number the exercise is actually
about: how much of the enterprise value comes from the years that were
forecast, and how much from the years that were not. On the shipped example
that split is 21% forecast and 79% terminal, and the 79% moves between 73% and
85% across a sensitivity grid one percentage point wide in either direction.

Provenance is enforced, not encouraged. An assumption will not construct
without a source and a vintage, so an unsourced beta cannot quietly enter the
model at all.

No dependencies beyond the Python standard library.

## Install

```bash
git clone <this repo>
cd projects/002-dcf-lab
python3 -m unittest discover -s tests -t .   # 72 tests, no deps needed
```

## Use

Input is a JSON document. Each driver is either one object, meaning the same
value in every forecast year, or a list of one object per year.

```json
{
  "company": "Helios Components NV, enterprise value",
  "unit": "EUR m",
  "years": 5,
  "base_revenue": {"name": "base year revenue", "value": 1200, "unit": "EUR m",
                   "source": "…", "as_of": "2025-12-31"},
  "drivers": {
    "revenue_growth": [
      {"name": "revenue growth y1", "value": 0.09, "kind": "rate",
       "source": "…", "as_of": "2026-01-15"}
    ],
    "ebit_margin": [{"name": "EBIT margin y1", "value": 0.13, "kind": "rate",
                     "source": "…", "as_of": "2026-01-15"}],
    "tax_rate": {"name": "effective tax rate", "value": 0.25, "kind": "share",
                 "source": "…", "as_of": "2025-06-30"},
    "da_pct_revenue": {"name": "D&A share of revenue", "value": 0.052,
                       "kind": "rate", "source": "…", "as_of": "2025-12-31"},
    "capex_pct_revenue": [{"name": "capex share of revenue y1", "value": 0.075,
                           "kind": "rate", "source": "…", "as_of": "2026-01-15"}],
    "nwc_pct_revenue_change": {"name": "working capital per unit of growth",
                               "value": 0.18, "kind": "rate",
                               "source": "…", "as_of": "2025-12-31"}
  },
  "wacc": {
    "risk_free": {"name": "risk-free rate", "value": 0.029, "kind": "rate",
                  "source": "…", "as_of": "2026-01-31"},
    "beta": {"name": "levered beta", "value": 1.1, "source": "…", "as_of": "2025-12-31"},
    "equity_risk_premium": {"name": "equity risk premium", "value": 0.048,
                            "kind": "rate", "source": "…", "as_of": "2025-07-01"},
    "premia": [{"name": "size premium", "value": 0.015, "kind": "rate",
                "source": "…", "as_of": "2025-07-01"}],
    "cost_of_debt_pretax": {"name": "pre-tax cost of debt", "value": 0.052,
                            "kind": "rate", "source": "…", "as_of": "2026-01-31"},
    "marginal_tax_rate": {"name": "marginal tax rate", "value": 0.25,
                          "kind": "share", "source": "…", "as_of": "2025-06-30"},
    "market_value_equity": {"name": "market value of equity", "value": 1450,
                            "unit": "EUR m", "source": "…", "as_of": "2026-01-31"},
    "market_value_debt": {"name": "market value of debt", "value": 520,
                          "unit": "EUR m", "source": "…", "as_of": "2026-01-31"}
  },
  "terminal": {
    "metric": "ebitda",
    "growth": {"name": "terminal growth", "value": 0.021, "kind": "rate",
               "source": "…", "as_of": "2026-01-31"},
    "exit_multiple": {"name": "exit EV/EBITDA multiple", "value": 8.5,
                      "kind": "multiple", "source": "…", "as_of": "2026-01-31"},
    "long_run_nominal_gdp": {"name": "long-run nominal GDP growth", "value": 0.032,
                             "kind": "rate", "source": "…", "as_of": "2025-10-01"}
  },
  "discounting": {"mid_year": false},
  "sensitivity": {"wacc_deltas": [-0.01, -0.005, 0.0, 0.005, 0.01],
                  "growth_deltas": [-0.01, -0.005, 0.0, 0.005, 0.01]}
}
```

`source` and `as_of` are mandatory on every assumption. `kind` is optional but
worth setting: a `share` is checked to lie in [0, 1], which catches the single
most common input error — typing 25 where 0.25 was meant — while a `rate` is
left free to go negative, because margins and growth do.

Both terminal specifications are required. Each is the only available check on
the other, and a model carrying one of them can assert a terminal value nobody
would accept once it is translated into the other's units.

```bash
python3 -m dcf_lab.cli examples/helios-components.json --as-of 2026-08-19
```

```
  Cost of capital
  --------------------------------------------------------------------------------------------------
    Risk-free rate                                        2.90%
    Beta x equity risk premium                            5.28%
    size premium                                          1.50%
  Cost of equity                                          9.68%
    Pre-tax cost of debt                                  5.20%
    Less tax shield at 25.0%                             -1.30%
  After-tax cost of debt                                  3.90%
    Weight of equity                                      73.6%
    Weight of debt                                        26.4%
  WACC                                                    8.15%

  Projection (EUR m), end-year discounting
  --------------------------------------------------------------------------------------------------
  Year   Revenue  Growth      EBIT  Margin     NOPAT     +D&A   -Capex    -dNWC      FCFF        PV
     1     1,308   9.00%    170.04  13.00%    127.53    68.02    98.10    19.44     78.01     72.12
     2     1,406   7.50%    189.82  13.50%    142.37    73.12    98.43    17.66     99.40     84.98
     3     1,490   6.00%    208.67  14.00%    156.50    77.50    96.88    15.19    121.94     96.38
     4     1,565   5.00%    222.23  14.20%    166.67    81.38    93.90    13.41    140.74    102.86
     5     1,628   4.00%    231.12  14.20%    173.34    84.63    94.40    11.27    152.30    102.92
  --------------------------------------------------------------------------------------------------
  Forecast period present value                                                        459.26 EUR m

  Terminal value, stated both ways
  --------------------------------------------------------------------------------------------------
                                                     Gordon growth               Exit multiple
  Terminal value at year 5                                   2,568                       2,684
  Present value of terminal value                            1,736                       1,814
  Enterprise value                                           2,195                       2,273
  Terminal share of enterprise value                         79.1%                       79.8%
  Implied exit multiple                                      8.13x              8.50x (stated)
  Implied perpetual growth                          2.10% (stated)                       2.35%

  Where the value comes from
  --------------------------------------------------------------------------------------------------
  Gordon growth
    Forecast period PV                   459.26    20.9%  ######
    Terminal PV                           1,736    79.1%  ######################
    Enterprise value                2,195 EUR m   100.0%

  79.1% of the Gordon growth valuation is a terminal value: a figure produced by two
  parameters applied to the last forecast year, not by the forecast itself.

  Sensitivity: enterprise value, and terminal share beneath it
  --------------------------------------------------------------------------------------------------
  WACC \ g               1.10%           1.60%           2.10%           2.60%           3.10%
  7.15%                  2,273           2,445           2,651           2,902           3,215
                         79.2%           80.7%           82.2%           83.7%           85.3%
  7.65%                  2,091           2,234           2,402           2,604           2,851
                         77.7%           79.1%           80.6%           82.1%           83.6%
  8.15%                  1,934           2,055           2,195           2,360           2,559
                         76.3%           77.6%           79.1%           80.5%           82.1%
  8.65%                  1,799           1,901           2,019           2,157           2,319
                         74.8%           76.2%           77.6%           79.0%           80.5%
  9.15%                  1,680           1,768           1,869           1,985           2,120
                         73.4%           74.8%           76.1%           77.5%           79.0%
  --------------------------------------------------------------------------------------------------
  Enterprise value across the grid: 1,680 to 3,215 EUR m (1.91x)
  Terminal share across the grid: 73.4% to 85.3%
```

The exit-multiple decomposition and the cross-check paragraph are cut from this
excerpt for length; the tool prints both.

Read the last two blocks, not the first. The forecast contributes 459 of 2,195,
and moving the cost of capital and the terminal growth rate by one percentage
point in each direction moves the answer by more than the entire forecast period
is worth. Everywhere in that grid the terminal share stays above 73%. Nothing in
the five-year plan changes that; it is a property of discounting a business that
outlives the window it was projected over.

Useful flags:

```bash
--terminal gordon|exit|both   # which terminal method to report (default both)
--mid-year                    # discount at t-0.5 rather than t (default off)
--end-year                    # force end-year even if the file asks for mid-year
--terminal-share-limit 0.75   # under --strict, fail above this share
--stale-after 18              # flag assumptions at least this many months old
--as-of 2026-08-19            # reference date for staleness (default: today)
--format markdown|json        # instead of the text report
--output valuation.md         # write to a file
--strict                      # exit 1 on unverified or stale assumptions, on
                              # terminal growth above the stated long-run GDP
                              # growth, or above --terminal-share-limit
```

`--terminal-share-limit` has no default, and that is not an oversight. There is
no published threshold above which a terminal share becomes indefensible, and
inventing one here would put an unsourced number into a tool built to keep
unsourced numbers out. Supply one if your house has a view.

`--strict` is the CI hook: put a valuation under version control and the build
fails when its inputs go stale, rather than when someone finally re-reads them.

As a library:

```python
from dcf_lab.loader import load
from dcf_lab.valuation import EXIT, sensitivity, value

case = load("examples/helios-components.json")
gordon = value(case)
print(gordon.enterprise_value)          # 2194.88...
print(gordon.terminal_share)            # 0.7907...
print(gordon.implied_exit_multiple)     # 8.134...
print(value(case, method=EXIT).implied_growth)   # 0.02346...
print(sensitivity(case).terminal_share_range)    # (0.734..., 0.853...)
```

## Method

**The projection.** Six drivers per year and nothing else:

```
revenue_t = revenue_{t-1} (1 + g_t)
ebit_t    = revenue_t m_t
nopat_t   = ebit_t (1 - tau_t)
fcff_t    = nopat_t + da_t - capex_t - dnwc_t
```

with `da_t` and `capex_t` as shares of revenue. Working capital is stated
against the *change* in revenue, `dnwc_t = n_t (revenue_t - revenue_{t-1})`,
rather than against its level. Both conventions are defensible. This one makes a
flat business consume zero working capital without the analyst having to say so,
which is the correct steady state and the one the level convention gets wrong
whenever the base year is not itself in steady state.

Free cash flow to the firm, not to equity, because the discount rate is a
blended cost of capital. Matching an all-capital cash flow to an all-capital
rate is the only pairing of the two that is not a category error.

**The cost of capital.** Built up, not asserted:

```
ke  = rf + beta ERP + sum(premia)
kd' = kd (1 - tau)
w   = we ke + wd kd'
```

with market-value weights. Book weights are not offered: a cost of capital is
what the market charges, and the market does not read the balance sheet. The
premia list is open, and every entry is printed by name, because a premium that
has to be printed is a premium someone has to defend.

**Discounting.** End-year by default: `(1 + w)^-t`. Mid-year is an explicit
option and shifts every factor to `(1 + w)^-(t - 0.5)`, raising each by exactly
`(1 + w)^0.5`. The shift is applied to the terminal value as well. Some
practitioners discount the terminal value at `t = N` even when the forecast
years are shifted; that produces a model whose terminal share depends on a
convention meant to be about timing within a year. Applying the shift uniformly
leaves the decomposition invariant, which is the property this tool exists to
report. It also means mid-year raises the whole valuation by 4% at an 8% WACC
and tells you nothing new, which is worth knowing before it is used to defend a
price.

**Terminal value, twice.**

```
Gordon:         TV_N = FCFF_N (1 + g) / (w - g)
Exit multiple:  TV_N = multiple x metric_N          (metric_N is EBITDA or EBIT)
```

Each is then restated in the other's units. The implied exit multiple of the
Gordon value is `TV_N / metric_N`. The implied growth of the exit-multiple value
comes from inverting the Gordon formula for `g`:

```
TV = F (1 + g) / (w - g)   =>   g = (TV w - F) / (TV + F)
```

For positive terminal cash flow that implied growth is always strictly below
`w`, which is why an exit multiple can never arithmetically fail and why it is
the more dangerous of the two. It never complains. The complaint has to come
from the translation.

**The refusal.** When terminal growth is at or above the cost of capital the
tool raises and exits non-zero. It does not clamp. At `g = w` the formula
divides by zero; above it, the formula returns a negative number that a
spreadsheet adds to a positive forecast value and presents as a valuation.
Clamping `g` to just below `w` — the usual workaround — is worse than either,
because it silently substitutes a different model whose value is unbounded as
the clamp tightens.

Terminal growth above the stated long-run nominal GDP growth is a warning
rather than a refusal. It is arithmetically fine and economically a claim that
the firm eventually becomes the economy, which the model has no mechanism to
stop. That is a judgement, so it is reported and left to the reader, and
`--strict` will fail on it for anyone who would rather it were not.

**The decomposition.** `EV = PV(forecast) + PV(terminal)`, and the terminal
share is the second over the sum. The sensitivity grid sweeps the cost of
capital against terminal growth on the Gordon value — the exit multiple does
not respond to terminal growth at all, so a grid over it would vary in one
direction and look reassuringly narrow for the wrong reason. Each cell carries
the value and the share. Cells where growth overtakes the cost of capital print
`g >= w` instead of a number.

**What the tests assert.** Not that the code runs. Almost every test compares
the implementation against a closed form derived independently of it. A business
whose drivers never change is a growing perpetuity worth `FCFF_1 / (w - g)`
regardless of where the forecast stops, and the projection plus a Gordon
terminal value reproduces that to within 1e-10 relative across 200 generated
parameter sets with horizons from one to thirty years. Lengthening the forecast
from three years to twenty-eight leaves enterprise value unchanged and lowers
the reported terminal share, so the value is the invariant and the share is not.
The mid-year convention multiplies every year's present value, and the total, by
exactly `(1 + w)^0.5`. The Gordon-implied exit multiple, fed back in as an exit
multiple, reproduces the same enterprise value to 1e-9 relative, and the
exit-implied growth rate does the same in the other direction. Terminal share
rises monotonically with terminal growth and falls monotonically with the cost
of capital, deterministically and across a random sweep. Growth at or above the
cost of capital raises rather than returning. 72 tests, standard library only.

**Staleness.** `as_of` is the vintage of the figure, not the date it was pasted
into the model. Age is counted in whole calendar months and the threshold is
inclusive: an assumption dated 2023-01-01 is stale at 24 months on 2025-01-01.
The distinction bites harder here than in a market sizing — a risk-free rate
from 2021 and one from 2025 are different models of the world, not different
roundings of the same one.

## What this is not

It is not a valuation. It is a machine for turning assumptions into a number
that looks objective, and it should be read as one. Every guard in it is a guard
on arithmetic. **The tool cannot tell you whether the drivers are right**, and
nothing in the report distinguishes a well-researched 14% EBIT margin from one
that was needed to make the answer work. A model with plausible-looking drivers
and a defensible WACC will produce a confident number from complete fiction, and
this one will produce it in three formats.

It does not bridge to equity value. Enterprise value is where it stops: no net
debt, no minorities, no pensions, no leases, no options. Those adjustments are a
separate argument with their own sources, and folding them in silently is how an
enterprise value becomes a share price nobody can reconstruct.

The cost of capital is an input, not a solution. Market values of equity and
debt are taken as given, so the circularity between the capital structure and
the value being computed is left open. Nothing here relevers a beta or iterates
to a consistent structure.

The sensitivity grid moves the cost of capital and terminal growth
independently. In reality they move together, and usually in the direction that
makes the corners of the grid less likely than the grid implies. The grid is
also silent on the drivers themselves: the projection does not change when the
discount rate does, which is generous to the model.

The terminal share is not comparable between models. It falls as the forecast
lengthens, so an analyst who dislikes the number can lower it by projecting ten
years instead of five without changing the valuation by a cent. That is a
property of the measure, it is asserted in the tests, and it is the reason the
tool reports the enterprise value alongside it rather than the share on its own.

There is no scenario machinery, no probability weighting and no distribution.
One case in, one case out. Scenarios are the next tool in this repository, not a
flag on this one.

## The example

`examples/helios-components.json` is illustrative. Every one of its thirty
figures is marked `"verified": false` and carries the source string
*"Illustrative placeholder — no published source"*, which is why `--strict`
fails on it and why the register prints `UNVERIFIED` against every line. That is
deliberate: the example demonstrates the shape of the argument and the size of
the terminal share, and no number in it should be quoted. Replace them with your
own sourced inputs.

## Licence

MIT.
