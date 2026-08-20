"""Helpers for building cases in tests without repeating provenance boilerplate.

The steady-state builders exist because most of the analytical properties worth
pinning are properties of a business in steady state, where the closed form of
the answer is known independently of the code being tested.
"""

import datetime as _dt
import random

from dcf_lab.assumptions import Assumption
from dcf_lab.model import Capital, Case, Drivers, Grid, Plan, Terminal

VINTAGE = _dt.date(2025, 1, 1)


def a(name, value, kind="value", unit=""):
    return Assumption(name=name, value=value, source="test fixture", as_of=VINTAGE,
                      kind=kind, unit=unit)


def _expand(value, years):
    if isinstance(value, (list, tuple)):
        if len(value) != years:
            raise AssertionError("fixture driver has %d values for %d years" % (len(value), years))
        return list(value)
    return [value] * years


def series(prefix, values, kind="rate"):
    return [a("%s y%d" % (prefix, i + 1), v, kind=kind) for i, v in enumerate(values)]


def drivers(years=5, growth=0.05, margin=0.15, tax=0.25, da=0.05, capex=0.05, nwc=0.0):
    """Six driver series. Each argument is a scalar or a per-year sequence."""
    return Drivers(
        revenue_growth=series("growth", _expand(growth, years)),
        ebit_margin=series("margin", _expand(margin, years)),
        tax_rate=series("tax", _expand(tax, years), kind="share"),
        da_pct_revenue=series("da", _expand(da, years)),
        capex_pct_revenue=series("capex", _expand(capex, years)),
        nwc_pct_revenue_change=series("nwc", _expand(nwc, years)),
    )


def capital_with_wacc(wacc):
    """A build-up contrived to produce exactly ``wacc``.

    All equity, zero risk-free rate, unit beta: the WACC is then the equity risk
    premium and nothing rounds. Tests that care about the build-up itself use
    :func:`capital` instead.
    """
    return Capital(
        risk_free=a("rf", 0.0, kind="rate"),
        beta=a("beta", 1.0),
        equity_risk_premium=a("erp", wacc, kind="rate"),
        cost_of_debt_pretax=a("kd", 0.0, kind="rate"),
        marginal_tax_rate=a("marginal tax", 0.0, kind="share"),
        market_value_equity=a("equity", 1.0),
        market_value_debt=a("debt", 0.0),
    )


def capital(risk_free=0.03, beta=1.2, erp=0.05, kd=0.05, tax=0.25,
            equity=800.0, debt=200.0, premia=()):
    return Capital(
        risk_free=a("rf", risk_free, kind="rate"),
        beta=a("beta", beta),
        equity_risk_premium=a("erp", erp, kind="rate"),
        cost_of_debt_pretax=a("kd", kd, kind="rate"),
        marginal_tax_rate=a("marginal tax", tax, kind="share"),
        market_value_equity=a("equity", equity),
        market_value_debt=a("debt", debt),
        premia=[a("premium %d" % i, p, kind="rate") for i, p in enumerate(premia)],
    )


def terminal(growth=0.02, multiple=8.0, metric="ebitda", gdp=None):
    return Terminal(
        growth=a("terminal growth", growth, kind="rate"),
        exit_multiple=a("exit multiple", multiple, kind="multiple"),
        metric=metric,
        long_run_nominal_gdp=(a("gdp", gdp, kind="rate") if gdp is not None else None),
    )


def case(years=5, wacc=0.09, growth=0.05, terminal_growth=0.02, base_revenue=1000.0,
         multiple=8.0, mid_year=False, gdp=None, grid=None, capital_override=None,
         **driver_kwargs):
    return Case(
        name="test",
        unit="EUR m",
        plan=Plan(
            base_revenue=a("base revenue", base_revenue),
            drivers=drivers(years=years, growth=growth, **driver_kwargs),
        ),
        capital=capital_override or capital_with_wacc(wacc),
        terminal=terminal(growth=terminal_growth, multiple=multiple, gdp=gdp),
        mid_year=mid_year,
        grid=grid or Grid(),
    )


def closed_form_ev(base_revenue, growth, wacc, margin=0.15, tax=0.25, da=0.05,
                   capex=0.05, nwc=0.0):
    """The value of a business whose free cash flow grows at ``growth`` forever.

    With every driver constant, free cash flow in year t is

        FCFF_t = R_t (m(1-tau) + d - c) - n (R_t - R_{t-1})

    and since ``R_t = R_0 (1+g)^t`` the whole series is proportional to
    ``(1+g)^(t-1)``. A perpetuity growing at ``g`` from ``FCFF_1`` is worth
    ``FCFF_1 / (w - g)``, and that value is independent of where the forecast
    stops -- which is exactly what the projection plus a Gordon terminal value
    should reproduce.
    """
    conversion = margin * (1.0 - tax) + da - capex
    fcff1 = base_revenue * ((1.0 + growth) * conversion - nwc * growth)
    return fcff1 / (wacc - growth)


def rng_for(seed):
    return random.Random(seed)


def steady_parameters(rng):
    """Driver sets whose cash conversion is comfortably positive.

    Constrained on purpose: the closed-form identities hold for any drivers, but
    a test that compares two numbers relatively is meaningless when both are
    near zero, so the sweep stays away from that region.
    """
    margin = rng.uniform(0.10, 0.30)
    tax = rng.uniform(0.0, 0.40)
    da = rng.uniform(0.03, 0.07)
    capex = rng.uniform(0.02, 0.06)
    nwc = rng.uniform(0.0, 0.30)
    growth = rng.uniform(-0.02, 0.05)
    wacc = growth + rng.uniform(0.01, 0.15)
    return dict(margin=margin, tax=tax, da=da, capex=capex, nwc=nwc,
                growth=growth, wacc=wacc)
