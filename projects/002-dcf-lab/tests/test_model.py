import datetime as dt
import unittest
from fractions import Fraction

from dcf_lab.assumptions import Assumption, AssumptionError
from dcf_lab.model import Capital, Drivers, Grid, ModelError, Plan, project

from tests.support import a, capital, drivers, rng_for, series


def _plan(base=1000.0, **kwargs):
    return Plan(base_revenue=a("base revenue", base), drivers=drivers(**kwargs))


class Projection(unittest.TestCase):
    def test_revenue_compounds_the_growth_series(self):
        # The closing revenue is computed independently in exact rational
        # arithmetic, so the test is not the implementation written twice.
        growth = (Fraction(1, 10), Fraction(1, 20), Fraction(-1, 25))
        exact = Fraction(1000)
        for g in growth:
            exact *= (1 + g)
        rows = project(_plan(1000.0, years=3, growth=[float(g) for g in growth]))
        self.assertAlmostEqual(rows[-1].revenue, float(exact), places=9)

        previous = 500.0
        for row in project(_plan(500.0, years=4, growth=0.07)):
            self.assertAlmostEqual(row.revenue, previous * 1.07, places=9)
            previous = row.revenue

    def test_free_cash_flow_is_the_stated_identity(self):
        rows = project(_plan(1200.0, years=5, growth=0.06, margin=0.14, tax=0.28,
                             da=0.055, capex=0.07, nwc=0.2))
        for row in rows:
            self.assertAlmostEqual(
                row.fcff, row.nopat + row.da - row.capex - row.nwc_change, places=9)
            self.assertAlmostEqual(row.nopat, row.ebit * (1 - row.tax_rate), places=9)
            self.assertAlmostEqual(row.ebit, row.revenue * row.margin, places=9)

    def test_ebitda_is_ebit_plus_depreciation(self):
        rows = project(_plan(1000.0, years=3, da=0.06))
        for row in rows:
            self.assertAlmostEqual(row.ebitda, row.ebit + row.da, places=9)
            self.assertAlmostEqual(row.metric("ebit"), row.ebit, places=12)
            self.assertAlmostEqual(row.metric("ebitda"), row.ebitda, places=12)

    def test_capex_equal_to_depreciation_cancels_out_of_cash_flow(self):
        # The steady-state simplification everyone reaches for; here it is exact.
        rows = project(_plan(1000.0, years=4, da=0.06, capex=0.06, nwc=0.0))
        for row in rows:
            self.assertAlmostEqual(row.fcff, row.nopat, places=9)

    def test_working_capital_follows_the_change_in_revenue_not_its_level(self):
        # The reason the driver is stated against the increment: a flat business
        # consumes nothing, and a shrinking one releases cash.
        for row in project(_plan(1000.0, years=4, growth=0.0, nwc=0.45)):
            self.assertAlmostEqual(row.nwc_change, 0.0, places=12)
        for row in project(_plan(1000.0, years=2, growth=-0.10, nwc=0.30)):
            self.assertLess(row.nwc_change, 0.0)

    def test_revenue_can_go_to_zero_but_not_through_it(self):
        rows = project(_plan(1000.0, years=2, growth=[-1.0, 0.5]))
        self.assertAlmostEqual(rows[0].revenue, 0.0, places=12)
        self.assertAlmostEqual(rows[1].revenue, 0.0, places=12)
        with self.assertRaises(ModelError):
            drivers(years=2, growth=[-1.2, 0.0])

    def test_structurally_impossible_projections_are_rejected(self):
        d = drivers(years=3)
        self.assertEqual(d.years, 3)
        with self.assertRaises(ModelError):
            d.year(0)
        with self.assertRaises(ModelError):
            d.year(4)
        with self.assertRaises(ModelError):
            Plan(base_revenue=a("base", -1.0), drivers=drivers(years=2))
        with self.assertRaises(ModelError) as ctx:
            Drivers(
                revenue_growth=series("g", [0.05, 0.05]),
                ebit_margin=series("m", [0.15]),
                tax_rate=series("t", [0.25, 0.25], kind="share"),
                da_pct_revenue=series("d", [0.05, 0.05]),
                capex_pct_revenue=series("c", [0.05, 0.05]),
                nwc_pct_revenue_change=series("n", [0.0, 0.0]),
            )
        self.assertIn("same number of years", str(ctx.exception))

    def test_a_constant_driver_counts_once_in_the_register(self):
        # A driver stated once and held flat is one assumption, not five.
        constant = a("flat margin", 0.15)
        d = Drivers(
            revenue_growth=series("g", [0.05] * 5),
            ebit_margin=[constant] * 5,
            tax_rate=series("t", [0.25] * 5, kind="share"),
            da_pct_revenue=series("d", [0.05] * 5),
            capex_pct_revenue=series("c", [0.05] * 5),
            nwc_pct_revenue_change=series("n", [0.0] * 5),
        )
        names = [x.name for x in d.assumptions()]
        self.assertEqual(names.count("flat margin"), 1)
        self.assertEqual(len(names), 26)


class CostOfCapital(unittest.TestCase):
    """A WACC is a weighted average, and weighted averages have known properties."""

    def test_cost_of_equity_is_the_capm_sum_plus_each_premium(self):
        c = capital(risk_free=0.03, beta=1.2, erp=0.05, premia=(0.015, 0.005))
        self.assertAlmostEqual(c.cost_of_equity, 0.03 + 1.2 * 0.05 + 0.015 + 0.005, places=12)
        without = capital(premia=()).cost_of_equity
        self.assertAlmostEqual(capital(premia=(0.017,)).cost_of_equity - without, 0.017, places=12)

    def test_cost_of_equity_is_linear_in_beta_with_slope_equal_to_the_premium(self):
        erp = 0.055
        low = capital(beta=0.8, erp=erp).cost_of_equity
        high = capital(beta=1.4, erp=erp).cost_of_equity
        self.assertAlmostEqual((high - low) / 0.6, erp, places=12)

    def test_the_tax_shield_reduces_the_cost_of_debt_and_the_wacc_proportionally(self):
        self.assertAlmostEqual(capital(kd=0.06, tax=0.30).after_tax_cost_of_debt,
                               0.06 * 0.70, places=12)
        # d(WACC)/d(tau) = -w_d * k_d, so a ten point change in tax moves the
        # WACC by a tenth of the debt-weighted pre-tax cost of debt.
        low = capital(tax=0.20, kd=0.06, equity=700.0, debt=300.0)
        high = capital(tax=0.30, kd=0.06, equity=700.0, debt=300.0)
        self.assertAlmostEqual(low.wacc - high.wacc, 0.10 * 0.3 * 0.06, places=12)

    def test_at_the_extremes_the_wacc_collapses_to_one_component(self):
        all_equity = capital(equity=1000.0, debt=0.0)
        self.assertAlmostEqual(all_equity.wacc, all_equity.cost_of_equity, places=12)
        all_debt = capital(equity=0.0, debt=1000.0)
        self.assertAlmostEqual(all_debt.wacc, all_debt.after_tax_cost_of_debt, places=12)

    def test_wacc_lies_between_the_two_component_costs(self):
        rng = rng_for(31)
        for _ in range(60):
            c = capital(
                risk_free=rng.uniform(0.0, 0.05),
                beta=rng.uniform(0.4, 2.0),
                erp=rng.uniform(0.03, 0.08),
                kd=rng.uniform(0.01, 0.12),
                tax=rng.uniform(0.0, 0.4),
                equity=rng.uniform(1.0, 5000.0),
                debt=rng.uniform(0.0, 5000.0),
            )
            low = min(c.cost_of_equity, c.after_tax_cost_of_debt)
            high = max(c.cost_of_equity, c.after_tax_cost_of_debt)
            self.assertGreaterEqual(c.wacc, low - 1e-12)
            self.assertLessEqual(c.wacc, high + 1e-12)

    def test_weights_are_market_value_shares_and_depend_only_on_their_ratio(self):
        c = capital(equity=750.0, debt=250.0)
        self.assertAlmostEqual(c.equity_weight, 0.75, places=12)
        self.assertAlmostEqual(c.debt_weight, 0.25, places=12)
        self.assertAlmostEqual(c.equity_weight + c.debt_weight, 1.0, places=12)
        # Doubling both market values changes nothing, which is what makes the
        # weights weights rather than amounts.
        self.assertAlmostEqual(capital(equity=800.0, debt=200.0).wacc,
                               capital(equity=8000.0, debt=2000.0).wacc, places=12)

    def test_the_build_up_reproduces_the_wacc_it_reports_and_names_every_premium(self):
        c = capital(premia=(0.012, 0.004))
        labels = [label for label, _, _ in c.build_up()]
        self.assertIn("premium 0", labels)
        self.assertIn("premium 1", labels)
        rows = dict((label, amount) for label, amount, _ in c.build_up())
        self.assertAlmostEqual(rows["Cost of equity"], c.cost_of_equity, places=12)
        self.assertAlmostEqual(rows["After-tax cost of debt"], c.after_tax_cost_of_debt, places=12)
        self.assertAlmostEqual(
            rows["WACC"],
            rows["Weight of equity"] * rows["Cost of equity"]
            + rows["Weight of debt"] * rows["After-tax cost of debt"],
            places=12)

    def test_a_firm_with_no_capital_at_all_is_rejected(self):
        with self.assertRaises(ModelError):
            capital(equity=0.0, debt=0.0)

    def test_negative_market_values_are_rejected(self):
        with self.assertRaises(ModelError):
            capital(equity=-100.0)
        with self.assertRaises(ModelError):
            capital(debt=-100.0)

    def test_a_grid_without_its_own_centre_is_rejected(self):
        Grid(wacc_deltas=(-0.01, 0.0, 0.01), growth_deltas=(0.0,))
        with self.assertRaises(ModelError):
            Grid(wacc_deltas=(-0.01, 0.01), growth_deltas=(0.0,))
        with self.assertRaises(ModelError):
            Grid(wacc_deltas=(0.0,), growth_deltas=())


class AssumptionProvenance(unittest.TestCase):
    def test_a_source_and_an_iso_vintage_are_both_mandatory(self):
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="  ", as_of="2025-01-01")
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="s", as_of="last spring")
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="s", as_of="")

    def test_a_share_outside_zero_to_one_is_rejected(self):
        # The common version of this mistake is entering 25 for a 25% tax rate.
        with self.assertRaises(AssumptionError):
            Assumption(name="tax", value=25.0, source="s", as_of="2025-01-01", kind="share")
        Assumption(name="tax", value=1.0, source="s", as_of="2025-01-01", kind="share")

    def test_a_rate_may_be_negative_but_a_multiple_may_not(self):
        # Margins and growth go below zero; an EV/EBITDA multiple does not.
        Assumption(name="margin", value=-0.08, source="s", as_of="2025-01-01", kind="rate")
        with self.assertRaises(AssumptionError):
            Assumption(name="exit", value=-8.0, source="s", as_of="2025-01-01", kind="multiple")

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="s", as_of="2025-01-01", kind="vibes")

    def test_age_counts_whole_months_and_staleness_is_inclusive(self):
        old = Assumption(name="x", value=1.0, source="s", as_of="2024-03-15")
        self.assertEqual(old.age_months(dt.date(2025, 3, 14)), 11)   # one day short
        self.assertEqual(old.age_months(dt.date(2025, 3, 15)), 12)
        self.assertEqual(old.age_months(dt.date(2024, 3, 15)), 0)
        threshold = Assumption(name="y", value=1.0, source="s", as_of="2023-01-01")
        self.assertTrue(threshold.is_stale(24, dt.date(2025, 1, 1)))
        self.assertFalse(threshold.is_stale(25, dt.date(2025, 1, 1)))

    def test_replace_keeps_provenance(self):
        orig = Assumption(name="beta", value=1.1, source="Bloomberg", as_of="2025-01-01")
        new = orig.replace(1.3)
        self.assertEqual(new.value, 1.3)
        self.assertEqual(new.source, orig.source)
        self.assertEqual(new.as_of, orig.as_of)


if __name__ == "__main__":
    unittest.main()
