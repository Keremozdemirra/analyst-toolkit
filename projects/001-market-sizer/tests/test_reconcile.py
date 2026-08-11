import unittest

from market_sizer.model import BottomUp, Market, Segment, TopDown
from market_sizer.reconcile import reconcile, solve_all, solve_for

from tests.support import a, random_market, rng_for, simple_market


def _substitute(market, result):
    """Rebuild the market with the solved assumption set to its implied value."""
    if result.side == "top-down":
        universe = market.top_down.universe
        if universe.name == result.name:
            universe = universe.replace(result.implied)
        factors = [f.replace(result.implied) if f.name == result.name else f
                   for f in market.top_down.factors]
        top_down = TopDown(universe=universe, factors=factors)
        bottom_up = market.bottom_up
    else:
        top_down = market.top_down
        segments = []
        for s in market.bottom_up.segments:
            drivers = [d.replace(result.implied) if d.name == result.name else d
                       for d in s.drivers]
            segments.append(Segment(name=s.name, drivers=drivers))
        bottom_up = BottomUp(segments=segments)
    return Market(name=market.name, unit=market.unit, top_down=top_down, bottom_up=bottom_up)


class TheGap(unittest.TestCase):
    def test_gap_is_bottom_up_minus_top_down(self):
        m = simple_market(1000.0, (0.5,), ((100.0, 4.0),))
        r = reconcile(m)
        self.assertAlmostEqual(r.top_down, 500.0, places=9)
        self.assertAlmostEqual(r.bottom_up, 400.0, places=9)
        self.assertAlmostEqual(r.gap, -100.0, places=9)
        self.assertAlmostEqual(r.ratio, 0.8, places=12)
        self.assertAlmostEqual(r.relative_gap, -0.2, places=12)

    def test_ratio_is_invariant_under_a_common_rescaling(self):
        # Changing the currency unit must not change whether the two agree.
        base = simple_market(1000.0, (0.5, 0.4), ((100.0, 4.0), (20.0, 3.0)))
        k = 7.5
        scaled = simple_market(1000.0 * k, (0.5, 0.4), ((100.0 * k, 4.0), (20.0 * k, 3.0)))
        self.assertAlmostEqual(reconcile(base).ratio, reconcile(scaled).ratio, places=9)

    def test_agreement_verdict_does_not_depend_on_the_denominator(self):
        # 100 vs 125 is 25% one way and 20% the other; measuring against the
        # larger side is what makes the verdict symmetric.
        forward = reconcile(simple_market(100.0, (1.0,), ((125.0,),)))
        backward = reconcile(simple_market(125.0, (1.0,), ((100.0,),)))
        for tol in (0.1, 0.2, 0.25, 0.5):
            self.assertEqual(forward.agrees_within(tol), backward.agrees_within(tol))

    def test_identical_sizings_agree_at_zero_tolerance(self):
        m = simple_market(200.0, (1.0,), ((200.0,),))
        self.assertTrue(reconcile(m).agrees_within(0.0))

    def test_negative_tolerance_is_rejected(self):
        with self.assertRaises(ValueError):
            reconcile(simple_market()).agrees_within(-0.1)


class TheInversion(unittest.TestCase):
    """The property that makes the tool worth using.

    ``solve_for`` claims that if you set an assumption to the implied value, the
    two sizings agree. That is a closed-form inversion, so it can be checked
    directly: substitute the answer back in and the gap must vanish.
    """

    def test_substituting_the_implied_value_closes_the_gap(self):
        rng = rng_for(2027)
        checked = 0
        for _ in range(120):
            m = random_market(rng)
            for result in solve_all(m):
                if not result.feasible:
                    continue
                rebuilt = _substitute(m, result)
                r = reconcile(rebuilt)
                scale = max(abs(r.top_down), abs(r.bottom_up), 1.0)
                self.assertLess(abs(r.gap) / scale, 1e-9,
                                msg="solving for %r left a gap" % result.name)
                checked += 1
        self.assertGreater(checked, 300, "the sweep should exercise many assumptions")

    def test_every_top_down_multiple_equals_the_bottom_up_over_top_down_ratio(self):
        # Top-down is one product, so closing the gap scales any single factor by
        # exactly the same amount, whichever factor you choose.
        rng = rng_for(7)
        for _ in range(40):
            m = random_market(rng)
            expected = reconcile(m).ratio
            for f in m.top_down.assumptions():
                r = solve_for(m, f.name)
                # Compared as a ratio: these totals span ten orders of magnitude,
                # so an absolute tolerance would be meaningless at the top end.
                self.assertAlmostEqual(r.multiple / expected, 1.0, places=12)

    def test_solving_a_model_that_already_agrees_returns_the_same_value(self):
        m = simple_market(1000.0, (0.4,), ((200.0, 2.0),))
        self.assertAlmostEqual(reconcile(m).gap, 0.0, places=9)
        for r in solve_all(m):
            self.assertTrue(r.feasible)
            self.assertAlmostEqual(r.multiple, 1.0, places=9)


class Infeasibility(unittest.TestCase):
    def test_a_bottom_up_driver_cannot_close_a_gap_the_other_segments_already_exceed(self):
        # Top-down is 100; segment B alone is 400, so no value of segment A's
        # driver -- not even zero -- gets the sum down to 100.
        m = simple_market(100.0, (1.0,), ((50.0,), (400.0,)))
        r = solve_for(m, "s0d0")
        self.assertFalse(r.feasible)
        self.assertIsNone(r.implied)
        self.assertIn("already above", r.reason)

    def test_an_implied_share_above_one_is_reported_as_infeasible(self):
        # Top-down 1000, bottom-up 100: the share would have to be 10x its 0.2.
        m = Market(
            name="t", unit="EUR",
            top_down=TopDown(universe=a("u", 1000.0), factors=[a("f", 1.0, kind="share")]),
            bottom_up=BottomUp(segments=[Segment("s", [
                a("count", 500.0, kind="count"),
                a("penetration", 0.2, kind="share"),
                a("price", 1.0, kind="price"),
            ])]),
        )
        r = solve_for(m, "penetration")
        self.assertFalse(r.feasible)
        self.assertIn("exceeds 100%", r.reason)
        self.assertAlmostEqual(r.implied, 2.0, places=9)

    def test_a_factor_pinned_at_zero_cannot_be_scaled(self):
        m = simple_market(1000.0, (0.0,), ((10.0,),))
        r = solve_for(m, "f0")
        self.assertFalse(r.feasible)
        self.assertIsNone(r.implied)

    def test_unknown_and_ambiguous_names_raise(self):
        m = simple_market()
        with self.assertRaises(KeyError):
            solve_for(m, "not-a-thing")
        ambiguous = Market(
            name="t", unit="EUR",
            top_down=TopDown(universe=a("u", 10.0), factors=[a("dup", 0.5, kind="share")]),
            bottom_up=BottomUp(segments=[Segment("s", [a("dup", 2.0)])]),
        )
        with self.assertRaises(KeyError):
            solve_for(ambiguous, "dup")


if __name__ == "__main__":
    unittest.main()
