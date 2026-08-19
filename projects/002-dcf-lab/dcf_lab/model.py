"""The forecast, the cost of capital, and the terminal specification.

Everything in this module is arithmetic on drivers. Nothing here discounts
anything -- that lives in :mod:`dcf_lab.valuation`, and the separation is
deliberate: the projection is a claim about a business, the discounting is a
claim about a capital market, and conflating the two is how a DCF ends up with
no reviewable parts.

The projection is kept to one shape, six drivers per year:

    revenue_t   = revenue_{t-1} * (1 + g_t)
    ebit_t      = revenue_t * m_t
    nopat_t     = ebit_t * (1 - tau_t)
    fcff_t      = nopat_t + da_t - capex_t - dnwc_t

with ``da_t`` and ``capex_t`` stated as shares of revenue, and the working
capital movement stated as a share of the *change* in revenue rather than of
its level. That last choice is the one worth arguing about, and the reason for
it is stated on :class:`Drivers`.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .assumptions import Assumption

EBITDA = "ebitda"
EBIT = "ebit"
METRICS = (EBITDA, EBIT)

DRIVER_NAMES = (
    "revenue_growth",
    "ebit_margin",
    "tax_rate",
    "da_pct_revenue",
    "capex_pct_revenue",
    "nwc_pct_revenue_change",
)


class ModelError(ValueError):
    """The model is structurally unusable, or a driver is outside its domain."""


@dataclass(frozen=True)
class Drivers:
    """Six per-year driver series of equal length.

    ``nwc_pct_revenue_change`` is incremental working capital as a share of the
    increment in revenue, not working capital as a share of revenue. Both
    conventions are defensible; this one is chosen because it makes a flat
    business consume zero working capital without the analyst having to say so,
    which is the correct steady state and the one the level convention gets
    wrong whenever the base year is not itself in steady state.
    """

    revenue_growth: List[Assumption]
    ebit_margin: List[Assumption]
    tax_rate: List[Assumption]
    da_pct_revenue: List[Assumption]
    capex_pct_revenue: List[Assumption]
    nwc_pct_revenue_change: List[Assumption]

    def __post_init__(self):
        lengths = {name: len(getattr(self, name)) for name in DRIVER_NAMES}
        if not lengths:
            raise ModelError("a projection needs drivers")
        distinct = set(lengths.values())
        if len(distinct) != 1:
            detail = ", ".join("%s=%d" % (k, v) for k, v in sorted(lengths.items()))
            raise ModelError(
                "every driver must cover the same number of years (%s). A driver "
                "series that is one year short silently shortens the forecast." % detail
            )
        years = distinct.pop()
        if years < 1:
            raise ModelError("a projection needs at least one forecast year")
        for g in self.revenue_growth:
            if g.value < -1.0:
                raise ModelError(
                    "%s: revenue growth of %g implies negative revenue" % (g.name, g.value)
                )

    @property
    def years(self):
        return len(self.revenue_growth)

    def year(self, t):
        """The six drivers for forecast year ``t``, 1-indexed."""
        if not 1 <= t <= self.years:
            raise ModelError("year %d is outside the forecast (1..%d)" % (t, self.years))
        return {name: getattr(self, name)[t - 1] for name in DRIVER_NAMES}

    def assumptions(self):
        """Every distinct driver assumption, in declaration order.

        Deduplicated by identity: a driver stated once and held constant across
        the forecast is the same assumption in every year, and printing it five
        times in the register would misrepresent how many things were assumed.
        """
        out = []
        seen = set()
        for name in DRIVER_NAMES:
            for a in getattr(self, name):
                if id(a) in seen:
                    continue
                seen.add(id(a))
                out.append(a)
        return out


@dataclass(frozen=True)
class YearResult:
    """One projected year, every intermediate line kept.

    The intermediates are kept rather than collapsed because the reader of a DCF
    almost never disputes the free cash flow directly; they dispute a margin or
    a capex ratio, and can only do that if it is on the page.
    """

    year: int
    revenue: float
    growth: float
    ebit: float
    margin: float
    tax_rate: float
    nopat: float
    da: float
    capex: float
    nwc_change: float
    fcff: float

    @property
    def ebitda(self):
        return self.ebit + self.da

    def metric(self, which):
        if which == EBITDA:
            return self.ebitda
        if which == EBIT:
            return self.ebit
        raise ModelError("unknown exit metric %r (expected one of %s)" % (which, ", ".join(METRICS)))

    def to_dict(self):
        return {
            "year": self.year,
            "revenue": self.revenue,
            "growth": self.growth,
            "ebit": self.ebit,
            "ebitda": self.ebitda,
            "margin": self.margin,
            "tax_rate": self.tax_rate,
            "nopat": self.nopat,
            "da": self.da,
            "capex": self.capex,
            "nwc_change": self.nwc_change,
            "fcff": self.fcff,
        }


@dataclass(frozen=True)
class Plan:
    """A base year and the drivers that carry it forward."""

    base_revenue: Assumption
    drivers: Drivers

    def __post_init__(self):
        if self.base_revenue is None:
            raise ModelError("a projection needs a base revenue")
        if self.base_revenue.value < 0:
            raise ModelError("base revenue cannot be negative")

    @property
    def years(self):
        return self.drivers.years

    def project(self):
        return project(self)

    def assumptions(self):
        return [self.base_revenue] + self.drivers.assumptions()


def project(plan):
    """Roll the drivers forward into free cash flow to the firm, year by year.

    Free cash flow to the firm is used rather than free cash flow to equity
    because the discount rate built in :class:`Capital` is a blended cost of
    capital: matching an all-capital cash flow to an all-capital discount rate
    is the only pairing of the two that is not a category error.
    """
    out = []
    revenue = plan.base_revenue.value
    for t in range(1, plan.years + 1):
        d = plan.drivers.year(t)
        previous = revenue
        growth = d["revenue_growth"].value
        revenue = previous * (1.0 + growth)
        margin = d["ebit_margin"].value
        tax_rate = d["tax_rate"].value
        ebit = revenue * margin
        nopat = ebit * (1.0 - tax_rate)
        da = revenue * d["da_pct_revenue"].value
        capex = revenue * d["capex_pct_revenue"].value
        nwc_change = (revenue - previous) * d["nwc_pct_revenue_change"].value
        out.append(YearResult(
            year=t,
            revenue=revenue,
            growth=growth,
            ebit=ebit,
            margin=margin,
            tax_rate=tax_rate,
            nopat=nopat,
            da=da,
            capex=capex,
            nwc_change=nwc_change,
            fcff=nopat + da - capex - nwc_change,
        ))
    return out


@dataclass(frozen=True)
class Capital:
    """The cost of capital, built up rather than asserted.

    A single WACC number in a model is unreviewable: it hides a beta, an equity
    risk premium and a capital structure, and every one of those is contestable.
    So the build-up is the input and the rate is derived:

        ke  = rf + beta * erp + sum(premia)
        kd' = kd * (1 - tau)
        w   = we * ke + wd * kd'

    with ``we`` and ``wd`` market-value weights. Book weights are not offered.
    A cost of capital is what the market charges, and the market does not read
    the balance sheet.

    The premia list is open on purpose -- size, country, illiquidity, a small
    company premium someone insists on. Naming each one separately means the
    report can print them, and a premium that has to be printed is a premium
    someone has to defend.
    """

    risk_free: Assumption
    beta: Assumption
    equity_risk_premium: Assumption
    cost_of_debt_pretax: Assumption
    marginal_tax_rate: Assumption
    market_value_equity: Assumption
    market_value_debt: Assumption
    premia: List[Assumption] = field(default_factory=list)

    def __post_init__(self):
        if self.market_value_equity.value < 0 or self.market_value_debt.value < 0:
            raise ModelError("market values of equity and debt cannot be negative")
        if self.total_capital == 0:
            raise ModelError(
                "equity and debt are both zero, so there are no weights to form a "
                "cost of capital from"
            )
        if not 0.0 <= self.marginal_tax_rate.value <= 1.0:
            raise ModelError("the marginal tax rate must lie in [0, 1]")

    @property
    def total_capital(self):
        return self.market_value_equity.value + self.market_value_debt.value

    @property
    def equity_weight(self):
        return self.market_value_equity.value / self.total_capital

    @property
    def debt_weight(self):
        return self.market_value_debt.value / self.total_capital

    @property
    def cost_of_equity(self):
        return (self.risk_free.value
                + self.beta.value * self.equity_risk_premium.value
                + sum(p.value for p in self.premia))

    @property
    def after_tax_cost_of_debt(self):
        return self.cost_of_debt_pretax.value * (1.0 - self.marginal_tax_rate.value)

    @property
    def wacc(self):
        return (self.equity_weight * self.cost_of_equity
                + self.debt_weight * self.after_tax_cost_of_debt)

    def build_up(self):
        """The derivation as an ordered list of ``(label, value, kind)`` rows.

        Returned rather than printed so that all three report formats show the
        same derivation and cannot drift apart.
        """
        rows = [
            ("Risk-free rate", self.risk_free.value, "rate"),
            ("Beta x equity risk premium",
             self.beta.value * self.equity_risk_premium.value, "rate"),
        ]
        for p in self.premia:
            rows.append((p.name, p.value, "rate"))
        rows.append(("Cost of equity", self.cost_of_equity, "total"))
        rows.append(("Pre-tax cost of debt", self.cost_of_debt_pretax.value, "rate"))
        rows.append(("Less tax shield at %.1f%%" % (self.marginal_tax_rate.value * 100.0),
                     self.after_tax_cost_of_debt - self.cost_of_debt_pretax.value, "rate"))
        rows.append(("After-tax cost of debt", self.after_tax_cost_of_debt, "total"))
        rows.append(("Weight of equity", self.equity_weight, "weight"))
        rows.append(("Weight of debt", self.debt_weight, "weight"))
        rows.append(("WACC", self.wacc, "total"))
        return rows

    def assumptions(self):
        return [
            self.risk_free, self.beta, self.equity_risk_premium,
        ] + list(self.premia) + [
            self.cost_of_debt_pretax, self.marginal_tax_rate,
            self.market_value_equity, self.market_value_debt,
        ]


@dataclass(frozen=True)
class Terminal:
    """How the years after the forecast are valued, stated twice.

    Both a growth rate and an exit multiple are required. That is not
    redundancy: each is the cross-check on the other, and a model that carries
    only one of them can express a terminal value nobody would accept if it were
    translated into the other units.

    ``long_run_nominal_gdp`` is optional and does nothing to the arithmetic. It
    exists so the report can say that a terminal growth rate is above the growth
    of the economy the firm sells into, which is a claim about the firm
    eventually becoming the economy.
    """

    growth: Assumption
    exit_multiple: Assumption
    metric: str = EBITDA
    long_run_nominal_gdp: Optional[Assumption] = None

    def __post_init__(self):
        if self.metric not in METRICS:
            raise ModelError(
                "exit multiple metric %r must be one of %s" % (self.metric, ", ".join(METRICS))
            )

    def assumptions(self):
        out = [self.growth, self.exit_multiple]
        if self.long_run_nominal_gdp is not None:
            out.append(self.long_run_nominal_gdp)
        return out


@dataclass(frozen=True)
class Grid:
    """The axes of the sensitivity table, as offsets from the base case."""

    wacc_deltas: Sequence[float] = (-0.01, -0.005, 0.0, 0.005, 0.01)
    growth_deltas: Sequence[float] = (-0.01, -0.005, 0.0, 0.005, 0.01)

    def __post_init__(self):
        for name in ("wacc_deltas", "growth_deltas"):
            values = getattr(self, name)
            if not values:
                raise ModelError("%s must contain at least one offset" % name)
            if 0.0 not in tuple(values):
                raise ModelError(
                    "%s must include 0.0 so the grid contains the base case; a "
                    "sensitivity table without its own centre is unreadable" % name
                )


@dataclass(frozen=True)
class Case:
    """A named valuation: a plan, a cost of capital, and a terminal view."""

    name: str
    unit: str
    plan: Plan
    capital: Capital
    terminal: Terminal
    mid_year: bool = False
    grid: Grid = field(default_factory=Grid)

    def assumptions(self):
        return self.plan.assumptions() + self.capital.assumptions() + self.terminal.assumptions()

    def unverified(self):
        return [a for a in self.assumptions() if not a.verified]

    def stale(self, stale_after_months, as_of=None):
        return [a for a in self.assumptions() if a.is_stale(stale_after_months, as_of)]
