import datetime as dt
import unittest
from fractions import Fraction

from market_sizer.assumptions import Assumption, AssumptionError
from market_sizer.model import (
    BottomUp, ModelError, Segment, TopDown, bottom_up_total, elasticity, top_down_total,
)

from tests.support import a, random_market, rng_for, simple_market


class TopDownArithmetic(unittest.TestCase):
    def test_total_is_the_product_of_universe_and_factors(self):
        # Computed independently in exact rational arithmetic, so the test is not
        # just the implementation written twice.
        universe, factors = 8_400_000, (Fraction(1, 4), Fraction(3, 10), Fraction(7, 8))
        exact = Fraction(universe)
        for f in factors:
            exact *= f
        m = simple_market(universe, tuple(float(f) for f in factors))
        self.assertAlmostEqual(top_down_total(m.top_down), float(exact), places=6)

    def test_a_factor_of_one_changes_nothing(self):
        without = simple_market(1000.0, (0.5, 0.4)).top_down.total
        with_one = simple_market(1000.0, (0.5, 1.0, 0.4)).top_down.total
        self.assertAlmostEqual(without, with_one, places=12)

    def test_factor_order_does_not_matter(self):
        forward = simple_market(1234.5, (0.3, 0.7, 0.11)).top_down.total
        reverse = simple_market(1234.5, (0.11, 0.7, 0.3)).top_down.total
        self.assertAlmostEqual(forward, reverse, places=9)

    def test_top_down_needs_at_least_one_factor(self):
        with self.assertRaises(ModelError):
            TopDown(universe=a("u", 10.0), factors=[])


class BottomUpArithmetic(unittest.TestCase):
    def test_total_is_the_sum_of_segment_products(self):
        m = simple_market(segments=((2.0, 3.0), (4.0, 5.0, 0.5)))
        self.assertAlmostEqual(bottom_up_total(m.bottom_up), 2 * 3 + 4 * 5 * 0.5, places=12)

    def test_dropping_a_segment_removes_exactly_its_value(self):
        m = simple_market(segments=((2.0, 3.0), (4.0, 5.0), (7.0, 1.5)))
        total = m.bottom_up.total
        dropped = m.bottom_up.segments[1]
        rest = BottomUp(segments=[s for s in m.bottom_up.segments if s is not dropped])
        self.assertAlmostEqual(total - dropped.value, rest.total, places=9)

    def test_scaling_every_segment_scales_the_total(self):
        base = simple_market(segments=((2.0, 3.0), (4.0, 5.0)))
        k = 3.25
        scaled = simple_market(segments=((2.0 * k, 3.0), (4.0 * k, 5.0)))
        self.assertAlmostEqual(scaled.bottom_up.total, k * base.bottom_up.total, places=9)

    def test_duplicate_segment_names_are_rejected(self):
        with self.assertRaises(ModelError):
            BottomUp(segments=[
                Segment("dup", [a("x", 1.0)]),
                Segment("dup", [a("y", 1.0)]),
            ])

    def test_a_segment_needs_drivers(self):
        with self.assertRaises(ModelError):
            Segment("empty", [])

    def test_bottom_up_needs_segments(self):
        with self.assertRaises(ModelError):
            BottomUp(segments=[])


class Elasticities(unittest.TestCase):
    """A multiplicative model has elasticities that are known in closed form.

    These are the strongest cheap checks available: if any of the arithmetic
    drifts, the numerically measured elasticity stops matching the analytical
    value.
    """

    def test_every_top_down_factor_has_unit_elasticity(self):
        rng = rng_for(11)
        for _ in range(60):
            m = random_market(rng)
            for f in m.top_down.assumptions():
                self.assertAlmostEqual(elasticity(m.top_down, f.name), 1.0, places=5)

    def test_bottom_up_driver_elasticity_equals_its_segment_share(self):
        rng = rng_for(12)
        for _ in range(60):
            m = random_market(rng)
            total = m.bottom_up.total
            for seg in m.bottom_up.segments:
                expected = seg.value / total
                for d in seg.drivers:
                    self.assertAlmostEqual(elasticity(m.bottom_up, d.name), expected, places=5)

    def test_bottom_up_elasticities_sum_to_the_number_of_segments_weighted(self):
        # Sum over one driver per segment of (segment share) is exactly 1.
        m = simple_market(segments=((2.0, 3.0), (4.0, 5.0), (7.0, 1.5)))
        total = sum(elasticity(m.bottom_up, s.drivers[0].name) for s in m.bottom_up.segments)
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_unknown_assumption_raises(self):
        with self.assertRaises(KeyError):
            elasticity(simple_market().top_down, "nope")


class AssumptionProvenance(unittest.TestCase):
    def test_a_source_is_mandatory(self):
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="  ", as_of="2025-01-01")

    def test_a_vintage_is_mandatory_and_must_be_iso(self):
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="s", as_of="last spring")
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="s", as_of="")

    def test_a_share_outside_zero_to_one_is_rejected(self):
        # The common version of this mistake is entering 35 for 35%.
        with self.assertRaises(AssumptionError):
            Assumption(name="pen", value=35.0, source="s", as_of="2025-01-01", kind="share")
        with self.assertRaises(AssumptionError):
            Assumption(name="pen", value=-0.1, source="s", as_of="2025-01-01", kind="share")
        Assumption(name="pen", value=1.0, source="s", as_of="2025-01-01", kind="share")

    def test_a_negative_count_or_price_is_rejected(self):
        for kind in ("count", "price"):
            with self.assertRaises(AssumptionError):
                Assumption(name="x", value=-1.0, source="s", as_of="2025-01-01", kind=kind)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(AssumptionError):
            Assumption(name="x", value=1.0, source="s", as_of="2025-01-01", kind="vibes")

    def test_age_in_months_counts_whole_months_only(self):
        old = Assumption(name="x", value=1.0, source="s", as_of="2024-03-15")
        self.assertEqual(old.age_months(dt.date(2025, 3, 14)), 11)   # one day short
        self.assertEqual(old.age_months(dt.date(2025, 3, 15)), 12)
        self.assertEqual(old.age_months(dt.date(2025, 3, 16)), 12)
        self.assertEqual(old.age_months(dt.date(2024, 3, 15)), 0)

    def test_staleness_is_inclusive_at_the_threshold(self):
        old = Assumption(name="x", value=1.0, source="s", as_of="2023-01-01")
        self.assertTrue(old.is_stale(24, dt.date(2025, 1, 1)))
        self.assertFalse(old.is_stale(25, dt.date(2025, 1, 1)))

    def test_replace_keeps_provenance(self):
        orig = Assumption(name="x", value=1.0, source="Eurostat", as_of="2025-01-01", unit="t")
        new = orig.replace(2.0)
        self.assertEqual(new.value, 2.0)
        self.assertEqual(new.source, orig.source)
        self.assertEqual(new.as_of, orig.as_of)
        self.assertEqual(new.unit, orig.unit)


if __name__ == "__main__":
    unittest.main()
