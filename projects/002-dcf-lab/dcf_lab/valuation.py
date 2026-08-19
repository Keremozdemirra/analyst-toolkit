"""Discounting, terminal value, and the decomposition that is the whole point.

A discounted cash flow produces one number and hides its own composition. In
almost every real model the forecast period -- the part that was argued over for
three weeks -- accounts for a minority of the value, and the majority comes from
a terminal value that follows mechanically from two parameters nobody
forecasted. This module computes the split and refuses to let it stay implicit.

Two terminal values are computed for every case, and each is translated into the
other's units. A Gordon value has an implied exit multiple; an exit multiple has
an implied perpetual growth rate. Those translations are the only honest test of
either: a growth rate of 2.5% sounds temperate until it turns out to imply
19x EBITDA, and 8x EBITDA sounds conservative until it turns out to imply
growth of minus 1%.
"""

import math
from dataclasses import dataclass
from typing import List, Optional

from .model import YearResult, project

GORDON = "gordon"
EXIT = "exit"
METHODS = (GORDON, EXIT)


class ValuationError(ValueError):
    """The valuation cannot be computed as specified, and clamping would lie."""


def discount_factors(wacc, years, mid_year=False):
    """Present value factors for years 1..``years``.

    End-year convention places every year's cash at its final instant:
    ``(1 + w)^-t``. The mid-year convention places it at the midpoint,
    ``(1 + w)^-(t - 0.5)``, which is closer to how a business actually collects
    cash and raises every factor by exactly ``(1 + w)^0.5``.

    The same shift is applied to the terminal value. Some practitioners discount
    the terminal value at ``t = N`` even when the forecast years are shifted; the
    result is a model whose terminal share depends on a convention that is meant
    to be about timing within a year. Applying the shift uniformly keeps the
    decomposition invariant, which is the property this tool is built to report.
    """
    if years < 1:
        raise ValuationError("cannot discount a forecast of %d years" % years)
    if wacc <= -1.0:
        raise ValuationError("a cost of capital of %g is below -100%%" % wacc)
    shift = 0.5 if mid_year else 0.0
    return [(1.0 + wacc) ** -(t - shift) for t in range(1, years + 1)]


def gordon_terminal_value(fcff_n, wacc, growth):
    """``TV_N = FCFF_N * (1 + g) / (w - g)``, refused when ``g >= w``.

    The refusal matters more than the formula. At ``g = w`` the expression is a
    division by zero and at ``g > w`` it returns a negative number that a
    spreadsheet will happily add to a positive forecast value and present as a
    valuation. Clamping ``g`` to just below ``w`` -- the usual workaround -- is
    worse still, because it silently substitutes a different model whose value
    is unbounded as the clamp tightens.
    """
    if growth >= wacc:
        raise ValuationError(
            "terminal growth of %.4g is not below the cost of capital of %.4g. "
            "A perpetuity growing at or above its discount rate has infinite "
            "value; there is no number to report and no defensible clamp. "
            "Either the growth rate or the cost of capital is wrong."
            % (growth, wacc)
        )
    return fcff_n * (1.0 + growth) / (wacc - growth)


def exit_multiple_terminal_value(metric_n, multiple):
    """``TV_N = multiple * metric_N``. No guard is needed; none is honest either.

    An exit multiple cannot be arithmetically infeasible, which is exactly why
    it is the more dangerous of the two: it never complains. The complaint has
    to come from :func:`implied_growth`.
    """
    return metric_n * multiple


def implied_growth(terminal_value, fcff_n, wacc):
    """The perpetual growth rate a given terminal value is asserting.

    Invert the Gordon formula for ``g``:

        TV = F (1 + g) / (w - g)
        TV w - TV g = F + F g
        g = (TV w - F) / (TV + F)

    For positive ``F`` this is always strictly below ``w``, as it must be. For
    ``F <= 0`` the Gordon model has no meaning to invert, and the caller is told
    so rather than handed an arithmetic artefact.
    """
    if fcff_n <= 0:
        raise ValuationError(
            "terminal-year free cash flow is %.6g; a perpetuity growth rate "
            "cannot be inferred from a non-positive cash flow" % fcff_n
        )
    denominator = terminal_value + fcff_n
    if denominator == 0:
        raise ValuationError("terminal value and terminal cash flow cancel; growth is undefined")
    return (terminal_value * wacc - fcff_n) / denominator


def implied_exit_multiple(terminal_value, metric_n):
    """The exit multiple a given terminal value is asserting."""
    if metric_n == 0:
        raise ValuationError("the exit metric is zero, so no multiple is defined")
    return terminal_value / metric_n


@dataclass(frozen=True)
class Valuation:
    """One complete valuation and its decomposition."""

    method: str
    wacc: float
    growth: float
    exit_multiple: float
    metric: str
    mid_year: bool
    years: List[YearResult]
    factors: List[float]
    pv_by_year: List[float]
    pv_forecast: float
    terminal_value: float
    pv_terminal: float
    enterprise_value: float
    implied_exit_multiple: Optional[float] = None
    implied_growth: Optional[float] = None
    cross_check_note: str = ""

    @property
    def terminal_share(self):
        """Terminal present value as a fraction of enterprise value.

        The headline number. ``None`` only when enterprise value is zero, where
        a share is not defined rather than being 0 or 1.
        """
        if self.enterprise_value == 0:
            return None
        return self.pv_terminal / self.enterprise_value

    @property
    def forecast_share(self):
        share = self.terminal_share
        return None if share is None else 1.0 - share

    @property
    def terminal_fcff(self):
        return self.years[-1].fcff

    def to_dict(self):
        return {
            "method": self.method,
            "wacc": self.wacc,
            "terminal_growth": self.growth,
            "exit_multiple": self.exit_multiple,
            "exit_metric": self.metric,
            "mid_year": self.mid_year,
            "pv_forecast": self.pv_forecast,
            "terminal_value": self.terminal_value,
            "pv_terminal": self.pv_terminal,
            "enterprise_value": self.enterprise_value,
            "terminal_share": self.terminal_share,
            "forecast_share": self.forecast_share,
            "implied_exit_multiple": self.implied_exit_multiple,
            "implied_growth": self.implied_growth,
            "cross_check_note": self.cross_check_note,
            "years": [
                dict(y.to_dict(), discount_factor=f, present_value=pv)
                for y, f, pv in zip(self.years, self.factors, self.pv_by_year)
            ],
        }


def value(case, method=GORDON, wacc=None, growth=None, exit_multiple=None, mid_year=None):
    """Value one case, optionally overriding the cost of capital or growth.

    The overrides exist for the sensitivity grid. They move the discounting and
    the terminal value only: the projection is a statement about the business
    and does not change because someone revised their view of the equity risk
    premium. That is a modelling assumption in its own right and a slightly
    generous one -- in reality a higher cost of capital and a lower growth rate
    tend to arrive together, and the grid cannot see that.
    """
    if method not in METHODS:
        raise ValuationError("unknown method %r (expected one of %s)" % (method, ", ".join(METHODS)))
    w = case.capital.wacc if wacc is None else wacc
    g = case.terminal.growth.value if growth is None else growth
    m = case.terminal.exit_multiple.value if exit_multiple is None else exit_multiple
    half = case.mid_year if mid_year is None else mid_year

    years = project(case.plan)
    factors = discount_factors(w, len(years), mid_year=half)
    pv_by_year = [y.fcff * f for y, f in zip(years, factors)]
    pv_forecast = math.fsum(pv_by_year)

    last = years[-1]
    metric_n = last.metric(case.terminal.metric)
    if method == GORDON:
        terminal_value = gordon_terminal_value(last.fcff, w, g)
    else:
        terminal_value = exit_multiple_terminal_value(metric_n, m)

    pv_terminal = terminal_value * factors[-1]
    enterprise_value = pv_forecast + pv_terminal

    note = []
    try:
        implied_multiple = implied_exit_multiple(terminal_value, metric_n)
    except ValuationError as exc:
        implied_multiple = None
        note.append(str(exc))
    try:
        implied_g = implied_growth(terminal_value, last.fcff, w)
    except ValuationError as exc:
        implied_g = None
        note.append(str(exc))

    return Valuation(
        method=method,
        wacc=w,
        growth=g,
        exit_multiple=m,
        metric=case.terminal.metric,
        mid_year=half,
        years=years,
        factors=factors,
        pv_by_year=pv_by_year,
        pv_forecast=pv_forecast,
        terminal_value=terminal_value,
        pv_terminal=pv_terminal,
        enterprise_value=enterprise_value,
        implied_exit_multiple=implied_multiple,
        implied_growth=implied_g,
        cross_check_note="; ".join(note),
    )


@dataclass(frozen=True)
class Cell:
    """One point of the sensitivity grid, or the reason there is no point."""

    wacc: float
    growth: float
    enterprise_value: Optional[float]
    terminal_share: Optional[float]
    feasible: bool
    reason: str = ""

    def to_dict(self):
        return {
            "wacc": self.wacc,
            "growth": self.growth,
            "enterprise_value": self.enterprise_value,
            "terminal_share": self.terminal_share,
            "feasible": self.feasible,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Sensitivity:
    """A WACC by terminal-growth grid, carrying value and terminal share.

    Carrying both is the point. A grid of enterprise values alone invites the
    reader to pick the corner they like; a grid that also shows the terminal
    share shows them that in every corner they are mostly picking a terminal
    value, and that the range across the grid is wider than the range of any
    forecast argument that produced it.
    """

    waccs: List[float]
    growths: List[float]
    cells: List[List[Cell]]

    def cell(self, wacc_index, growth_index):
        return self.cells[wacc_index][growth_index]

    @property
    def feasible_cells(self):
        return [c for row in self.cells for c in row if c.feasible]

    @property
    def value_range(self):
        values = [c.enterprise_value for c in self.feasible_cells]
        return (min(values), max(values)) if values else (None, None)

    @property
    def terminal_share_range(self):
        shares = [c.terminal_share for c in self.feasible_cells if c.terminal_share is not None]
        return (min(shares), max(shares)) if shares else (None, None)

    def to_dict(self):
        return {
            "waccs": self.waccs,
            "growths": self.growths,
            "cells": [[c.to_dict() for c in row] for row in self.cells],
        }


def sensitivity(case, grid=None):
    """Sweep WACC against terminal growth, on the Gordon terminal value.

    Gordon rather than the exit multiple because an exit multiple does not
    respond to terminal growth at all: a grid over it would vary in one
    direction only and would look reassuringly narrow for the wrong reason.
    """
    grid = grid or case.grid
    base_w = case.capital.wacc
    base_g = case.terminal.growth.value
    waccs = [base_w + d for d in grid.wacc_deltas]
    growths = [base_g + d for d in grid.growth_deltas]

    rows = []
    for w in waccs:
        row = []
        for g in growths:
            try:
                v = value(case, method=GORDON, wacc=w, growth=g)
            except ValuationError as exc:
                # First sentence only: the grid has one cell to say it in.
                row.append(Cell(w, g, None, None, False, str(exc).split(". ")[0]))
                continue
            row.append(Cell(w, g, v.enterprise_value, v.terminal_share, True))
        rows.append(row)
    return Sensitivity(waccs=waccs, growths=growths, cells=rows)


def review(case):
    """Everything wrong with the case that is not wrong enough to refuse.

    Returned as a list of sentences rather than raised, because each of these is
    a judgement the analyst is entitled to make and none of them is arithmetic.
    """
    out = []
    terminal = case.terminal
    g = terminal.growth.value
    gdp = terminal.long_run_nominal_gdp

    if gdp is not None and g > gdp.value:
        out.append(
            "Terminal growth of %.2f%% exceeds the stated long-run nominal GDP growth "
            "of %.2f%%. Perpetual growth above the economy means the firm eventually "
            "becomes the economy; the model has no mechanism to stop it."
            % (g * 100.0, gdp.value * 100.0)
        )
    if gdp is None:
        out.append(
            "No long-run nominal GDP growth was supplied, so terminal growth has "
            "nothing to be checked against."
        )

    years = project(case.plan)
    if years[-1].fcff <= 0:
        out.append(
            "Terminal-year free cash flow is %.6g. A Gordon terminal value built on "
            "a non-positive cash flow is negative or zero by construction and should "
            "not be used." % years[-1].fcff
        )
    if any(y.fcff < 0 for y in years[:-1]):
        negative = [str(y.year) for y in years[:-1] if y.fcff < 0]
        out.append(
            "Free cash flow is negative in year(s) %s. That is legitimate for a firm "
            "investing ahead of revenue, but it moves value into the terminal period "
            "rather than out of it." % ", ".join(negative)
        )
    if case.plan.years < 5:
        out.append(
            "The forecast runs %d year(s). A short forecast does not make the terminal "
            "value larger in principle, but it does mean more of the answer is settled "
            "by two parameters rather than by the projection."
            % case.plan.years
        )
    return out
