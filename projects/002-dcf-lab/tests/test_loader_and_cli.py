import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from dcf_lab.assumptions import AssumptionError
from dcf_lab.cli import main
from dcf_lab.loader import loads
from dcf_lab.model import ModelError
from dcf_lab.valuation import EXIT, value

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(HERE, "examples", "helios-components.json")

_PROVENANCE = {"source": "test fixture", "as_of": "2025-01-01"}


def _rate(name, v):
    return dict(name=name, value=v, kind="rate", **_PROVENANCE)


MINIMAL = {
    "company": "c", "unit": "EUR m", "years": 3,
    "base_revenue": dict(name="base revenue", value=1000, **_PROVENANCE),
    "drivers": {
        "revenue_growth": _rate("growth", 0.05),
        "ebit_margin": _rate("margin", 0.20),
        "tax_rate": dict(name="tax", value=0.25, kind="share", **_PROVENANCE),
        "da_pct_revenue": _rate("da", 0.05),
        "capex_pct_revenue": _rate("capex", 0.05),
        "nwc_pct_revenue_change": _rate("nwc", 0.0),
    },
    "wacc": {
        "risk_free": _rate("rf", 0.0),
        "beta": dict(name="beta", value=1.0, **_PROVENANCE),
        "equity_risk_premium": _rate("erp", 0.10),
        "cost_of_debt_pretax": _rate("kd", 0.0),
        "marginal_tax_rate": dict(name="marginal tax", value=0.0, kind="share", **_PROVENANCE),
        "market_value_equity": dict(name="equity", value=1000, **_PROVENANCE),
        "market_value_debt": dict(name="debt", value=0, **_PROVENANCE),
    },
    "terminal": {
        "growth": _rate("terminal growth", 0.05),
        "exit_multiple": dict(name="exit multiple", value=8.0, kind="multiple", **_PROVENANCE),
        "long_run_nominal_gdp": _rate("gdp", 0.06),
    },
}


def _copy(**overrides):
    doc = json.loads(json.dumps(MINIMAL))
    doc.update(overrides)
    return doc


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _written(doc):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(doc, fh)
    fh.close()
    return fh.name


class Loading(unittest.TestCase):
    def test_a_minimal_document_parses_and_reaches_the_closed_form(self):
        # Constant drivers, growth equal to terminal growth: the answer is a
        # growing perpetuity, so the loader can be checked against arithmetic.
        case = loads(json.dumps(MINIMAL))
        self.assertEqual(case.plan.years, 3)
        self.assertAlmostEqual(case.capital.wacc, 0.10, places=12)
        expected = (1000 * 1.05 * 0.20 * 0.75) / (0.10 - 0.05)
        self.assertAlmostEqual(value(case).enterprise_value, expected, places=6)

    def test_a_driver_given_once_covers_every_forecast_year(self):
        case = loads(json.dumps(MINIMAL))
        self.assertEqual(len(case.plan.drivers.revenue_growth), 3)
        self.assertEqual(len({id(d) for d in case.plan.drivers.revenue_growth}), 1)
        # One statement, one entry in the register.
        self.assertEqual([a.name for a in case.assumptions()].count("growth"), 1)

    def test_the_shipped_example_parses_and_is_entirely_unverified(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            case = loads(fh.read(), where=EXAMPLE)
        self.assertEqual(len(case.unverified()), len(case.assumptions()))
        self.assertEqual(len(case.assumptions()), 30)
        gordon = value(case)
        self.assertAlmostEqual(gordon.enterprise_value, 2194.88, places=1)
        self.assertAlmostEqual(gordon.terminal_share, 0.7908, places=4)
        self.assertAlmostEqual(gordon.implied_exit_multiple, 8.134, places=3)
        exit_based = value(case, method=EXIT)
        self.assertAlmostEqual(exit_based.implied_growth, 0.02346, places=5)

    def test_driver_series_that_do_not_match_the_forecast_are_rejected(self):
        doc = _copy()
        doc["drivers"]["revenue_growth"] = [_rate("g1", 0.05), _rate("g2", 0.04)]
        with self.assertRaises(ModelError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("2 year(s)", str(ctx.exception))
        doc = _copy()
        del doc["drivers"]["capex_pct_revenue"]
        with self.assertRaises(ModelError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("capex_pct_revenue", str(ctx.exception))
        doc = _copy()
        doc["drivers"]["sbc_pct_revenue"] = _rate("sbc", 0.02)
        with self.assertRaises(ModelError):
            loads(json.dumps(doc))

    def test_the_build_up_and_both_terminal_methods_are_mandatory(self):
        doc = _copy()
        del doc["wacc"]["beta"]
        with self.assertRaises(ModelError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("cannot be reviewed", str(ctx.exception))
        doc = _copy(wacc={"value": 0.09})
        with self.assertRaises(ModelError):
            loads(json.dumps(doc))
        doc = _copy()
        del doc["terminal"]["exit_multiple"]
        with self.assertRaises(ModelError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("check on the other", str(ctx.exception))

    def test_duplicate_assumption_names_are_rejected_at_load(self):
        doc = _copy()
        doc["terminal"]["growth"]["name"] = "growth"
        with self.assertRaises(ModelError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("more than once", str(ctx.exception))

    def test_structural_and_provenance_errors_are_reported_where_they_are(self):
        doc = _copy()
        doc["equity_value"] = 1
        with self.assertRaises(ModelError):
            loads(json.dumps(doc))
        doc = _copy()
        del doc["base_revenue"]["source"]
        with self.assertRaises(AssumptionError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("source", str(ctx.exception))
        doc = _copy(years=0)
        with self.assertRaises(ModelError):
            loads(json.dumps(doc))
        with self.assertRaises(ModelError):
            loads("{not json")


class CommandLine(unittest.TestCase):
    def test_every_output_format_runs_and_json_matches_the_library(self):
        for fmt in ("text", "markdown", "json"):
            code, out, err = _run([EXAMPLE, "--format", fmt, "--as-of", "2026-08-19"])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.strip())
        code, out, _ = _run([EXAMPLE, "--format", "json", "--as-of", "2026-08-19"])
        payload = json.loads(out)
        with open(EXAMPLE, encoding="utf-8") as fh:
            case = loads(fh.read())
        self.assertAlmostEqual(payload["cost_of_capital"]["wacc"], case.capital.wacc, places=12)
        gordon = [v for v in payload["valuations"] if v["method"] == "gordon"][0]
        self.assertAlmostEqual(gordon["enterprise_value"],
                               value(case).enterprise_value, places=6)
        self.assertEqual(len(gordon["years"]), 5)
        self.assertEqual(len(payload["sensitivity"]["cells"]), 5)

    def test_the_text_report_leads_with_the_decomposition_not_the_answer(self):
        code, out, err = _run([EXAMPLE, "--as-of", "2026-08-19"])
        self.assertEqual(code, 0, err)
        self.assertIn("Where the value comes from", out)
        self.assertIn("is a terminal value", out)
        self.assertLess(out.index("Cost of capital"), out.index("Enterprise value"))

    def test_terminal_narrows_the_report_to_one_method(self):
        code, out, err = _run([EXAMPLE, "--format", "json", "--terminal", "exit"])
        self.assertEqual(code, 0, err)
        methods = [v["method"] for v in json.loads(out)["valuations"]]
        self.assertEqual(methods, ["exit"])

    def test_the_discounting_convention_can_be_overridden_either_way(self):
        code, out, _ = _run([EXAMPLE, "--format", "json", "--mid-year"])
        mid = json.loads(out)["valuations"][0]
        code, out, _ = _run([EXAMPLE, "--format", "json", "--end-year"])
        end = json.loads(out)["valuations"][0]
        self.assertTrue(mid["mid_year"])
        self.assertFalse(end["mid_year"])
        self.assertAlmostEqual(
            mid["enterprise_value"] / end["enterprise_value"],
            (1.0 + end["wacc"]) ** 0.5, places=10)

    def test_terminal_growth_above_the_cost_of_capital_exits_two(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["terminal"]["growth"]["value"] = 0.12
        path = _written(doc)
        try:
            code, _, err = _run([path])
            self.assertEqual(code, 2)
            self.assertIn("not below the cost of capital", err)
            self.assertIn("no defensible clamp", err)
        finally:
            os.unlink(path)

    def test_strict_fails_on_the_example_and_passes_on_a_clean_case(self):
        code, _, err = _run([EXAMPLE, "--strict", "--as-of", "2026-08-19"])
        self.assertEqual(code, 1)
        self.assertIn("unverified", err)
        path = _written(MINIMAL)
        try:
            code, _, err = _run([path, "--strict", "--as-of", "2025-06-01"])
            self.assertEqual(code, 0, err)
        finally:
            os.unlink(path)

    def test_strict_flags_growth_above_the_economy_and_a_terminal_share_limit(self):
        doc = _copy()
        doc["terminal"]["long_run_nominal_gdp"]["value"] = 0.032
        path = _written(doc)
        try:
            code, _, err = _run([path, "--strict", "--as-of", "2025-06-01"])
            self.assertEqual(code, 1)
            self.assertIn("nominal GDP", err)
        finally:
            os.unlink(path)
        # The minimal case is a pure perpetuity, so its terminal share is high.
        path = _written(MINIMAL)
        try:
            code, _, err = _run([path, "--strict", "--as-of", "2025-06-01",
                                 "--terminal-share-limit", "0.5"])
            self.assertEqual(code, 1)
            self.assertIn("terminal share", err)
            code, _, err = _run([path, "--strict", "--as-of", "2025-06-01",
                                 "--terminal-share-limit", "0.95"])
            self.assertEqual(code, 0, err)
        finally:
            os.unlink(path)

    def test_output_goes_to_a_file_when_asked(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "valuation.md")
            code, out, err = _run([EXAMPLE, "--format", "markdown", "--output", dest])
            self.assertEqual(code, 0, err)
            self.assertEqual(out, "")
            with open(dest, encoding="utf-8") as fh:
                self.assertIn("## Where the value comes from", fh.read())

    def test_unusable_arguments_exit_two_rather_than_crashing(self):
        code, _, err = _run(["/nonexistent/case.json"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)
        self.assertEqual(_run([EXAMPLE, "--as-of", "yesterday"])[0], 2)
        self.assertEqual(_run([EXAMPLE, "--terminal-share-limit", "1.5"])[0], 2)
        doc = _copy()
        doc["drivers"]["tax_rate"]["value"] = 25    # 25 instead of 0.25
        path = _written(doc)
        try:
            code, _, err = _run([path])
            self.assertEqual(code, 2)
            self.assertIn("share", err)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
