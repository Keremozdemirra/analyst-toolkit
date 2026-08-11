import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from market_sizer.assumptions import AssumptionError
from market_sizer.cli import main
from market_sizer.loader import loads
from market_sizer.model import ModelError
from market_sizer.reconcile import reconcile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(HERE, "examples", "eu-cbam-advisory.json")

MINIMAL = {
    "market": "m", "unit": "EUR",
    "top_down": {
        "universe": {"name": "u", "value": 1000, "source": "s", "as_of": "2025-01-01"},
        "factors": [{"name": "f", "value": 0.5, "kind": "share", "source": "s", "as_of": "2025-01-01"}],
    },
    "bottom_up": {
        "segments": [{"name": "seg", "drivers": [
            {"name": "n", "value": 100, "kind": "count", "source": "s", "as_of": "2025-01-01"},
            {"name": "p", "value": 4, "kind": "price", "source": "s", "as_of": "2025-01-01"},
        ]}],
    },
}


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class Loading(unittest.TestCase):
    def test_minimal_document_parses_and_computes(self):
        m = loads(json.dumps(MINIMAL))
        self.assertAlmostEqual(m.top_down.total, 500.0, places=9)
        self.assertAlmostEqual(m.bottom_up.total, 400.0, places=9)

    def test_the_shipped_example_parses(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            m = loads(fh.read(), where=EXAMPLE)
        self.assertEqual(len(m.bottom_up.segments), 3)
        # The example is deliberately all-unverified; that is the point it makes.
        self.assertEqual(len(m.unverified()), len(m.assumptions()))

    def test_duplicate_assumption_names_are_rejected_at_load(self):
        doc = json.loads(json.dumps(MINIMAL))
        doc["bottom_up"]["segments"][0]["drivers"][1]["name"] = "f"
        with self.assertRaises(ModelError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("more than once", str(ctx.exception))

    def test_unknown_fields_are_rejected(self):
        doc = json.loads(json.dumps(MINIMAL))
        doc["tam"] = 1
        with self.assertRaises(ModelError):
            loads(json.dumps(doc))
        doc = json.loads(json.dumps(MINIMAL))
        doc["top_down"]["universe"]["provenance"] = "x"
        with self.assertRaises(AssumptionError):
            loads(json.dumps(doc))

    def test_missing_source_is_rejected_with_the_field_named(self):
        doc = json.loads(json.dumps(MINIMAL))
        del doc["top_down"]["universe"]["source"]
        with self.assertRaises(AssumptionError) as ctx:
            loads(json.dumps(doc))
        self.assertIn("source", str(ctx.exception))

    def test_malformed_json_is_reported_as_such(self):
        with self.assertRaises(ModelError):
            loads("{not json")


class CommandLine(unittest.TestCase):
    def test_every_output_format_runs(self):
        for fmt in ("text", "markdown", "json"):
            code, out, err = _run([EXAMPLE, "--format", fmt])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.strip())
        code, out, _ = _run([EXAMPLE, "--format", "json"])
        payload = json.loads(out)
        self.assertIn("reconciliation", payload)
        self.assertEqual(len(payload["segments"]), 3)

    def test_json_output_matches_the_library(self):
        with open(EXAMPLE, encoding="utf-8") as fh:
            m = loads(fh.read())
        code, out, _ = _run([EXAMPLE, "--format", "json"])
        payload = json.loads(out)
        self.assertAlmostEqual(payload["reconciliation"]["top_down"], m.top_down.total, places=6)
        self.assertAlmostEqual(payload["reconciliation"]["bottom_up"], m.bottom_up.total, places=6)

    def test_solve_narrows_the_report_to_one_assumption(self):
        code, out, err = _run([EXAMPLE, "--format", "json", "--solve", "mid-market attach rate"])
        self.assertEqual(code, 0, err)
        implied = json.loads(out)["implied"]
        self.assertEqual(len(implied), 1)
        self.assertEqual(implied[0]["name"], "mid-market attach rate")

    def test_solve_for_an_unknown_assumption_exits_two(self):
        code, _, err = _run([EXAMPLE, "--solve", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("nope", err)

    def test_strict_flags_unverified_assumptions(self):
        code, _, err = _run([EXAMPLE, "--strict", "--tolerance", "10"])
        self.assertEqual(code, 1)
        self.assertIn("unverified", err)

    def test_strict_passes_on_a_clean_reconciling_model(self):
        doc = json.loads(json.dumps(MINIMAL))
        doc["bottom_up"]["segments"][0]["drivers"][1]["value"] = 5   # 100 x 5 = 500 = top-down
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(doc, fh)
            path = fh.name
        try:
            code, _, err = _run([path, "--strict", "--as-of", "2025-06-01"])
            self.assertEqual(code, 0, err)
        finally:
            os.unlink(path)

    def test_output_to_a_file(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "report.md")
            code, out, err = _run([EXAMPLE, "--format", "markdown", "--output", dest])
            self.assertEqual(code, 0, err)
            self.assertEqual(out, "")
            with open(dest, encoding="utf-8") as fh:
                self.assertIn("| Sizing | Value |", fh.read())

    def test_missing_file_and_bad_date_exit_two(self):
        code, _, err = _run(["/nonexistent/market.json"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)
        code, _, err = _run([EXAMPLE, "--as-of", "yesterday"])
        self.assertEqual(code, 2)
        code, _, err = _run([EXAMPLE, "--tolerance", "-1"])
        self.assertEqual(code, 2)

    def test_a_document_with_a_bad_assumption_exits_two_rather_than_crashing(self):
        doc = json.loads(json.dumps(MINIMAL))
        doc["top_down"]["factors"][0]["value"] = 35   # 35 instead of 0.35
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(doc, fh)
            path = fh.name
        try:
            code, _, err = _run([path])
            self.assertEqual(code, 2)
            self.assertIn("share", err)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
