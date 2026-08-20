"""The properties that make the tool worth trusting.

Almost every test here compares the code against a closed form derived
independently: a growing perpetuity, an inversion of the Gordon formula, or a
discount factor identity. A test that only asserted that a number came back
would pass just as happily on a model with the terminal value discounted at the
wrong year, which is the error this suite is built to catch.
"""

import math
import unittest

from dcf_lab.model import Grid, project
from dcf_lab.valuation import (
    EXIT, GORDON, ValuationError, discount_factors, exit_multiple_terminal_value,
    gordon_terminal_value, implied_exit_multiple, implied_growth, review,
    sensitivity, value,
)

from tests.support import (
    capital, capital_with_wacc, case, closed_form_ev, rng_for, steady_parameters,
)


class Discounting(unittest.TestCase):
    def test_end_year_factors_are_the_textbook_ones(self):
        for t, f in enumerate(discount_factors(0.08, 4), start=1):
            self.assertAlmostEqual(f, 1.0 / (1.08 ** t), places=12)
        rng = rng_for(3)
        for _ in range(30):
            w = rng.uniform(0.001, 0.4)
            factors = discount_factors(w, 12)
            for earlier, later in zip(factors, factors[1:]):
                self.assertAlmostEqual(later / earlier, 1.0 / (1.0 + w), places=12)

    def test_the_mid_year_convention_shifts_every_year_by_the_same_half_period(self):
        rng = rng_for(4)
        for _ in range(30):
            w = rng.uniform(0.001, 0.4)
            n = rng.randint(1, 20)
            end = discount_factors(w, n)
            mid = discount_factors(w, n, mid_year=True)
            expected = math.sqrt(1.0 + w)
            for e, m in zip(end, mid):
                self.assertAlmostEqual(m / e, expected, places=12)

    def test_mid_year_scales_the_whole_valuation_by_the_same_half_period(self):
        rng = rng_for(5)
        for _ in range(25):
            p = steady_parameters(rng)
            c = case(years=rng.randint(1, 12), wacc=p["wacc"], growth=p["growth"],
                     terminal_growth=p["growth"],
                     margin=p["margin"], tax=p["tax"], da=p["da"], capex=p["capex"],
                     nwc=p["nwc"])
            for method in (GORDON, EXIT):
                end = value(c, method=method, mid_year=False)
                mid = value(c, method=method, mid_year=True)
                self.assertAlmostEqual(
                    mid.enterprise_value / end.enterprise_value,
                    math.sqrt(1.0 + p["wacc"]), places=10)
                # The convention is about when cash arrives within a year. If it
                # moved the decomposition, the decomposition would be an artefact.
                self.assertAlmostEqual(end.terminal_share, mid.terminal_share, places=12)

    def test_impossible_discount_rates_and_horizons_are_refused(self):
        with self.assertRaises(ValuationError):
            discount_factors(-1.0, 3)
        with self.assertRaises(ValuationError):
            discount_factors(0.08, 0)


class GrowingPerpetuity(unittest.TestCase):
    """The identity the whole projection-plus-terminal-value machine must satisfy.

    A business whose drivers never change is a growing perpetuity, and a growing
    perpetuity has a value of ``FCFF_1 / (w - g)`` that owes nothing to where the
    forecast happens to stop. If the projection, the discounting and the Gordon
    terminal value are each right, they reproduce it; if any one of them is off
    by a year, they do not.
    """

    def test_the_closed_form_is_reproduced_across_many_parameter_sets(self):
        # The simplest instance first, written out longhand: a flat business is
        # worth its cash flow over the discount rate, and nothing else.
        flat = case(years=10, wacc=0.08, growth=0.0, terminal_growth=0.0,
                    margin=0.20, tax=0.25, da=0.05, capex=0.05, nwc=0.3,
                    base_revenue=1000.0)
        fcff = project(flat.plan)[0].fcff
        self.assertAlmostEqual(fcff, 1000.0 * 0.20 * 0.75, places=9)
        self.assertAlmostEqual(value(flat).enterprise_value, fcff / 0.08, places=6)

        rng = rng_for(2029)
        checked = 0
        for _ in range(200):
            p = steady_parameters(rng)
            years = rng.randint(1, 30)
            base = rng.uniform(50.0, 5e5)
            c = case(years=years, wacc=p["wacc"], growth=p["growth"],
                     terminal_growth=p["growth"], base_revenue=base,
                     margin=p["margin"], tax=p["tax"], da=p["da"],
                     capex=p["capex"], nwc=p["nwc"])
            expected = closed_form_ev(
                base, p["growth"], p["wacc"], margin=p["margin"], tax=p["tax"],
                da=p["da"], capex=p["capex"], nwc=p["nwc"])
            got = value(c).enterprise_value
            self.assertAlmostEqual(got / expected, 1.0, places=10,
                                   msg="closed form missed at %r" % (p,))
            checked += 1
        self.assertEqual(checked, 200)

    def test_extending_the_forecast_does_not_create_value(self):
        # Value cannot be manufactured by lengthening the window it is looked at
        # through. Any drift here is a discounting error hiding inside the
        # terminal value.
        rng = rng_for(17)
        for _ in range(40):
            p = steady_parameters(rng)
            common = dict(wacc=p["wacc"], growth=p["growth"], terminal_growth=p["growth"],
                          margin=p["margin"], tax=p["tax"], da=p["da"],
                          capex=p["capex"], nwc=p["nwc"])
            short = value(case(years=3, **common)).enterprise_value
            long = value(case(years=28, **common)).enterprise_value
            self.assertAlmostEqual(long / short, 1.0, places=10)

    def test_a_ramp_followed_by_steady_state_is_also_horizon_invariant(self):
        # The realistic shape: three years of an explicit plan, then a fade to a
        # constant. Everything after the fade must be worth the same whether it
        # is projected or capitalised.
        steady = 0.03
        for years in (5, 9, 22):
            growth = [0.14, 0.10, 0.06] + [steady] * (years - 3)
            c = case(years=years, wacc=0.085, growth=growth, terminal_growth=steady,
                     margin=0.16, tax=0.26, da=0.05, capex=0.055, nwc=0.25)
            got = value(c).enterprise_value
            if years == 5:
                reference = got
            else:
                self.assertAlmostEqual(got / reference, 1.0, places=9)

    def test_enterprise_value_scales_with_the_business(self):
        common = dict(years=6, wacc=0.09, growth=0.04, terminal_growth=0.02, nwc=0.2)
        small = value(case(base_revenue=100.0, **common)).enterprise_value
        large = value(case(base_revenue=250.0, **common)).enterprise_value
        self.assertAlmostEqual(large / small, 2.5, places=9)


class TerminalGuard(unittest.TestCase):
    def test_growth_at_or_above_the_discount_rate_is_refused_rather_than_negated(self):
        # The failure worth guarding: above the discount rate the formula returns
        # a negative number, and a spreadsheet adds it to the forecast without
        # comment. At the discount rate it divides by zero.
        with self.assertRaises(ValuationError):
            gordon_terminal_value(100.0, 0.08, 0.08)
        with self.assertRaises(ValuationError) as ctx:
            gordon_terminal_value(100.0, 0.08, 0.12)
        self.assertIn("0.12", str(ctx.exception))
        self.assertIn("0.08", str(ctx.exception))

    def test_the_refusal_reaches_the_valuation_and_is_not_clamped(self):
        c = case(years=5, wacc=0.07, terminal_growth=0.075)
        with self.assertRaises(ValuationError):
            value(c)

    def test_growth_just_below_the_discount_rate_is_computed_not_capped(self):
        # No clamp means the value is allowed to be absurd, and being allowed to
        # be absurd is what makes it informative.
        near = value(case(years=5, wacc=0.08, terminal_growth=0.0799))
        far = value(case(years=5, wacc=0.08, terminal_growth=0.02))
        self.assertGreater(near.enterprise_value, 50 * far.enterprise_value)
        self.assertGreater(near.terminal_share, 0.99)


class CrossChecks(unittest.TestCase):
    """Each terminal method restated in the other's units."""

    def test_implied_growth_inverts_the_gordon_formula(self):
        rng = rng_for(41)
        for _ in range(60):
            w = rng.uniform(0.03, 0.20)
            g = rng.uniform(-0.05, w - 0.005)
            fcff = rng.uniform(1.0, 1e5)
            tv = gordon_terminal_value(fcff, w, g)
            self.assertAlmostEqual(implied_growth(tv, fcff, w), g, places=10)

    def test_implied_multiple_inverts_the_exit_multiple(self):
        tv = exit_multiple_terminal_value(250.0, 9.5)
        self.assertAlmostEqual(tv, 2375.0, places=9)
        self.assertAlmostEqual(implied_exit_multiple(tv, 250.0), 9.5, places=12)
        with self.assertRaises(ValuationError):
            implied_exit_multiple(1000.0, 0.0)

    def test_the_gordon_implied_multiple_round_trips_to_the_same_value(self):
        rng = rng_for(43)
        for _ in range(50):
            p = steady_parameters(rng)
            c = case(years=rng.randint(2, 15), wacc=p["wacc"], growth=p["growth"],
                     terminal_growth=min(p["growth"], p["wacc"] - 0.005),
                     margin=p["margin"], tax=p["tax"], da=p["da"],
                     capex=p["capex"], nwc=p["nwc"])
            gordon = value(c, method=GORDON)
            rebuilt = value(c, method=EXIT, exit_multiple=gordon.implied_exit_multiple)
            self.assertAlmostEqual(
                rebuilt.enterprise_value / gordon.enterprise_value, 1.0, places=9)
            self.assertAlmostEqual(
                rebuilt.terminal_share, gordon.terminal_share, places=9)

    def test_the_exit_multiple_implied_growth_round_trips_to_the_same_value(self):
        rng = rng_for(47)
        for _ in range(50):
            p = steady_parameters(rng)
            c = case(years=rng.randint(2, 15), wacc=p["wacc"], growth=p["growth"],
                     multiple=rng.uniform(4.0, 16.0),
                     terminal_growth=min(p["growth"], p["wacc"] - 0.005),
                     margin=p["margin"], tax=p["tax"], da=p["da"],
                     capex=p["capex"], nwc=p["nwc"])
            exit_based = value(c, method=EXIT)
            rebuilt = value(c, method=GORDON, growth=exit_based.implied_growth)
            self.assertAlmostEqual(
                rebuilt.enterprise_value / exit_based.enterprise_value, 1.0, places=9)

    def test_a_bigger_multiple_implies_faster_growth_but_never_reaches_the_discount_rate(self):
        # An exit multiple cannot secretly assert a growth rate the Gordon model
        # would have refused, however large the multiple is.
        implied = [value(case(years=5, wacc=0.09, growth=0.04, multiple=m),
                         method=EXIT).implied_growth
                   for m in (5.0, 20.0, 80.0, 400.0)]
        self.assertEqual(implied, sorted(implied))
        for g in implied:
            self.assertLess(g, 0.09)

    def test_growth_cannot_be_inferred_from_a_non_positive_cash_flow(self):
        with self.assertRaises(ValuationError):
            implied_growth(1000.0, 0.0, 0.09)
        with self.assertRaises(ValuationError):
            implied_growth(1000.0, -50.0, 0.09)
        # Capex far above depreciation: the last year burns cash, so the Gordon
        # cross-check on an exit multiple has nothing to invert and says so.
        v = value(case(years=4, wacc=0.09, growth=0.05, margin=0.05, tax=0.25,
                       da=0.04, capex=0.30, nwc=0.3), method=EXIT)
        self.assertIsNone(v.implied_growth)
        self.assertIn("non-positive", v.cross_check_note)


class Decomposition(unittest.TestCase):
    """The headline finding, asserted rather than asserted about."""

    def test_the_two_parts_sum_to_the_whole(self):
        rng = rng_for(53)
        for _ in range(40):
            p = steady_parameters(rng)
            c = case(years=rng.randint(1, 20), wacc=p["wacc"], growth=p["growth"],
                     terminal_growth=min(p["growth"], p["wacc"] - 0.005),
                     margin=p["margin"], tax=p["tax"], da=p["da"],
                     capex=p["capex"], nwc=p["nwc"])
            v = value(c)
            self.assertAlmostEqual(
                (v.pv_forecast + v.pv_terminal) / v.enterprise_value, 1.0, places=12)
            self.assertAlmostEqual(v.terminal_share + v.forecast_share, 1.0, places=12)
            self.assertAlmostEqual(math.fsum(v.pv_by_year) / v.pv_forecast, 1.0, places=12)

    def test_the_terminal_share_rises_with_growth_and_falls_with_the_discount_rate(self):
        c = case(years=6, wacc=0.09, growth=0.04, terminal_growth=0.02)
        by_growth = [value(c, growth=g).terminal_share
                     for g in (0.0, 0.01, 0.02, 0.03, 0.04, 0.05)]
        self.assertEqual(by_growth, sorted(by_growth))
        self.assertLess(by_growth[0], by_growth[-1])
        by_wacc = [value(c, wacc=w).terminal_share
                   for w in (0.06, 0.07, 0.08, 0.09, 0.11, 0.15)]
        self.assertEqual(by_wacc, sorted(by_wacc, reverse=True))
        self.assertGreater(by_wacc[0], by_wacc[-1])

    def test_both_monotonicities_hold_across_a_random_sweep(self):
        rng = rng_for(59)
        for _ in range(40):
            p = steady_parameters(rng)
            c = case(years=rng.randint(2, 15), wacc=p["wacc"], growth=p["growth"],
                     terminal_growth=p["wacc"] - 0.03,
                     margin=p["margin"], tax=p["tax"], da=p["da"],
                     capex=p["capex"], nwc=p["nwc"])
            base = value(c).terminal_share
            self.assertGreater(value(c, growth=p["wacc"] - 0.02).terminal_share, base)
            self.assertLess(value(c, wacc=p["wacc"] + 0.02).terminal_share, base)

    def test_a_longer_forecast_lowers_the_terminal_share_without_changing_the_value(self):
        # Worth knowing before quoting a terminal share: the same business,
        # honestly valued, reports a different share depending on how long the
        # analyst chose to project. The value is the invariant; the share is not.
        common = dict(wacc=0.09, growth=0.03, terminal_growth=0.03, nwc=0.2)
        short = value(case(years=3, **common))
        long = value(case(years=20, **common))
        self.assertAlmostEqual(long.enterprise_value / short.enterprise_value, 1.0, places=9)
        self.assertLess(long.terminal_share, short.terminal_share)

    def test_the_terminal_share_is_undefined_rather_than_zero_at_zero_value(self):
        c = case(years=3, wacc=0.09, growth=0.0, terminal_growth=0.0,
                 margin=0.0, tax=0.0, da=0.05, capex=0.05, nwc=0.0)
        v = value(c)
        self.assertAlmostEqual(v.enterprise_value, 0.0, places=9)
        self.assertIsNone(v.terminal_share)
        self.assertIsNone(v.forecast_share)


class SensitivityGrid(unittest.TestCase):
    def test_the_centre_of_the_grid_is_the_base_case(self):
        c = case(years=6, wacc=0.09, growth=0.04, terminal_growth=0.02)
        grid = sensitivity(c)
        centre = grid.cell(grid.waccs.index(0.09 + 0.0), 2)
        base = value(c)
        self.assertAlmostEqual(centre.enterprise_value, base.enterprise_value, places=9)
        self.assertAlmostEqual(centre.terminal_share, base.terminal_share, places=12)
        shaped = sensitivity(case(
            years=4, grid=Grid(wacc_deltas=(-0.02, 0.0), growth_deltas=(0.0, 0.01, 0.02))))
        self.assertEqual(len(shaped.cells), 2)
        self.assertTrue(all(len(row) == 3 for row in shaped.cells))

    def test_value_rises_along_growth_and_falls_along_the_cost_of_capital(self):
        grid = sensitivity(case(years=6, wacc=0.09, growth=0.04, terminal_growth=0.02))
        for row in grid.cells:
            values = [c.enterprise_value for c in row]
            self.assertEqual(values, sorted(values))
        for column in zip(*grid.cells):
            values = [c.enterprise_value for c in column]
            self.assertEqual(values, sorted(values, reverse=True))

    def test_the_terminal_share_moves_the_same_way_across_the_grid(self):
        grid = sensitivity(case(years=6, wacc=0.09, growth=0.04, terminal_growth=0.02))
        for row in grid.cells:
            shares = [c.terminal_share for c in row]
            self.assertEqual(shares, sorted(shares))
        for column in zip(*grid.cells):
            shares = [c.terminal_share for c in column]
            self.assertEqual(shares, sorted(shares, reverse=True))

    def test_cells_where_growth_overtakes_the_discount_rate_are_marked_not_computed(self):
        c = case(years=5, wacc=0.05, terminal_growth=0.045,
                 grid=Grid(wacc_deltas=(-0.01, 0.0), growth_deltas=(0.0, 0.01)))
        grid = sensitivity(c)
        infeasible = [cell for row in grid.cells for cell in row if not cell.feasible]
        self.assertTrue(infeasible)
        for cell in infeasible:
            self.assertGreaterEqual(cell.growth, cell.wacc)
            self.assertIsNone(cell.enterprise_value)
            self.assertIn("not below", cell.reason)
        for cell in grid.feasible_cells:
            self.assertLess(cell.growth, cell.wacc)

    def test_the_reported_range_brackets_the_base_case(self):
        c = case(years=6, wacc=0.09, growth=0.04, terminal_growth=0.02)
        grid = sensitivity(c)
        low, high = grid.value_range
        base = value(c).enterprise_value
        self.assertLess(low, base)
        self.assertGreater(high, base)
        share_low, share_high = grid.terminal_share_range
        self.assertLessEqual(share_low, value(c).terminal_share)
        self.assertGreaterEqual(share_high, value(c).terminal_share)


class Fixtures(unittest.TestCase):
    def test_the_valuation_uses_the_build_up_it_was_given(self):
        # The contrived all-equity fixture is convenient; this checks the
        # valuation reads whatever the build-up produces, not a stored number.
        c = case(years=5, capital_override=capital(risk_free=0.03, beta=1.2, erp=0.05,
                                                   kd=0.05, tax=0.25, equity=800.0,
                                                   debt=200.0),
                 terminal_growth=0.02)
        self.assertAlmostEqual(value(c).wacc, c.capital.wacc, places=12)
        self.assertNotAlmostEqual(c.capital.wacc, capital_with_wacc(0.09).wacc, places=6)
        with self.assertRaises(ValuationError):
            value(c, method="hand-waving")


class Review(unittest.TestCase):
    def test_terminal_growth_is_flagged_only_when_it_exceeds_nominal_gdp(self):
        above = review(case(years=5, wacc=0.09, terminal_growth=0.045, gdp=0.032))
        self.assertTrue(any("exceeds the stated long-run nominal GDP" in n for n in above))
        below = review(case(years=5, wacc=0.09, terminal_growth=0.02, gdp=0.032))
        self.assertFalse(any("nominal GDP growth of" in n for n in below))

    def test_the_absence_of_a_gdp_assumption_is_itself_reported(self):
        notes = review(case(years=5, wacc=0.09, terminal_growth=0.02, gdp=None))
        self.assertTrue(any("nothing to be checked against" in n for n in notes))

    def test_a_non_positive_terminal_cash_flow_is_reported(self):
        notes = review(case(years=4, wacc=0.09, growth=0.05, gdp=0.03,
                            margin=0.05, tax=0.25, da=0.04, capex=0.30, nwc=0.3))
        self.assertTrue(any("Terminal-year free cash flow" in n for n in notes))

    def test_a_short_forecast_is_reported(self):
        self.assertTrue(any("forecast runs" in n
                            for n in review(case(years=2, wacc=0.09, gdp=0.03))))
        self.assertFalse(any("forecast runs" in n
                             for n in review(case(years=8, wacc=0.09, gdp=0.03))))


if __name__ == "__main__":
    unittest.main()
