import contextlib
import io
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from tracebudget.__main__ import main
from tracebudget.core import compare, parse_policy, parse_trace
from tracebudget.demo import POLICY, synthetic
from tracebudget.report import render_html, render_junit


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        old, new = synthetic()
        for name, data in (("old.json", old), ("new.json", new), ("policy.json", POLICY)):
            (self.folder / name).write_text(json.dumps(data), encoding="utf-8")
        self.args = [str(self.folder / "old.json"), str(self.folder / "new.json"),
                     "--policy", str(self.folder / "policy.json")]

    def run_cli(self, extra=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(self.args + (extra or []))
        return code, out.getvalue(), err.getvalue()

    def test_synthetic_regression_writes_all_formats(self):
        paths = [self.folder / name for name in ("report.json", "report.html", "report.xml")]
        extra = []
        for flag, path in zip(("--json", "--html", "--junit"), paths):
            extra += [flag, str(path)]
        code, out, err = self.run_cli(extra)
        self.assertEqual(code, 1, err)
        self.assertIn("REGRESSION", out)
        report = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["regressions"], 1)
        self.assertIn("TraceBudget", paths[1].read_text(encoding="utf-8"))
        suite = ET.fromstring(paths[2].read_text(encoding="utf-8"))
        self.assertEqual(suite.attrib["failures"], "1")

    def test_pass_exit(self):
        self.args[1] = self.args[0]
        self.assertEqual(self.run_cli()[0], 0)

    def test_invalid_json_exit_and_no_output(self):
        (self.folder / "new.json").write_text("{", encoding="utf-8")
        output = self.folder / "report.json"
        code, _, err = self.run_cli(["--json", str(output)])
        self.assertEqual(code, 2)
        self.assertIn("input error", err)
        self.assertFalse(output.exists())

    def test_output_cannot_overwrite_input(self):
        original = (self.folder / "old.json").read_bytes()
        self.assertEqual(self.run_cli(["--json", self.args[0]])[0], 2)
        self.assertEqual((self.folder / "old.json").read_bytes(), original)

    def test_existing_hardlink_input_alias_rejected(self):
        alias = self.folder / "input-alias.json"
        os.link(self.folder / "old.json", alias)
        self.assertEqual(self.run_cli(["--json", str(alias)])[0], 2)

    def test_existing_hardlink_output_aliases_rejected(self):
        first, second = self.folder / "first", self.folder / "second"
        first.write_text("", encoding="utf-8")
        os.link(first, second)
        self.assertEqual(self.run_cli(["--json", str(first), "--html", str(second)])[0], 2)

    def test_oversized_cli_limit_returns_two(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            main(self.args + ["--max-mb", "999999999999999999999999"])
        self.assertEqual(result.exception.code, 2)

    def test_outputs_must_be_distinct(self):
        target = str(self.folder / "report")
        self.assertEqual(self.run_cli(["--json", target, "--html", target])[0], 2)

    def test_malformed_unruled_event_is_not_hidden(self):
        data = json.loads((self.folder / "new.json").read_text(encoding="utf-8"))
        data["traceEvents"].append({"ph": "X", "name": "not-in-policy", "ts": 0, "dur": -1})
        (self.folder / "new.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.run_cli()[0], 2)

    def test_incomplete_has_junit_errors(self):
        target = self.folder / "report.xml"
        code, _, _ = self.run_cli(["--warmup", "60", "--junit", str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(ET.fromstring(target.read_text(encoding="utf-8")).attrib["errors"], "2")

    def test_event_limit_exit(self):
        self.assertEqual(self.run_cli(["--max-events", "1"])[0], 2)

    def test_output_write_failure_returns_two(self):
        target = self.folder / "is-a-directory"
        target.mkdir()
        self.assertEqual(self.run_cli(["--json", str(target)])[0], 2)
        self.assertEqual(list(target.iterdir()), [])

    def test_negative_cli_limits_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            main(self.args + ["--warmup", "-1"])
        self.assertEqual(result.exception.code, 2)


class ReportTests(unittest.TestCase):
    def test_markup_is_escaped_and_args_excluded(self):
        name = '<img src=x onerror="alert(1)">'
        cat = 'render&"ui'
        private = "private-fixture-" + "sentinel"
        events = [{"ph": "M", "args": {"path": private}},
                  {"ph": "X", "name": name, "cat": cat, "ts": 0,
                   "dur": 1, "args": {"credential": private}}]
        capture = parse_trace({"traceEvents": events, "private": private})
        policy = parse_policy({"version": 1, "min_samples": 1,
                               "rules": [{"name": name, "category": cat, "max_ms": 1}]})
        report = compare(capture, capture, policy)
        html = render_html(report)
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html)
        self.assertIn("&lt;img", html)
        self.assertIn("Content-Security-Policy", html)
        for text in (html, render_junit(report), json.dumps(report)):
            self.assertNotIn(private, text)
        self.assertEqual(ET.fromstring(render_junit(report))[0].attrib["name"], name + " [p95]")

    def test_empty_category_and_literal_uncategorized_stay_distinct(self):
        events = [{"ph": "X", "name": "stage", "cat": cat, "ts": 0, "dur": 1}
                  for cat in ("", "uncategorized")]
        capture = parse_trace(events)
        policy = parse_policy({"version": 1, "min_samples": 1, "rules": [
            {"name": "stage", "category": "", "max_ms": 1},
            {"name": "stage", "category": "uncategorized", "max_ms": 1}]})
        suite = ET.fromstring(render_junit(compare(capture, capture, policy)))
        identities = {(case.attrib["classname"], case.attrib["name"]) for case in suite}
        self.assertEqual(len(identities), 2)

    def test_junit_errors_and_failures_are_distinct(self):
        old, new = synthetic()
        report = compare(parse_trace(old), parse_trace(new), parse_policy(POLICY))
        suite = ET.fromstring(render_junit(report))
        self.assertEqual(len(suite.findall("testcase/failure")), 1)
        self.assertEqual(len(suite.findall("testcase/error")), 0)

    def test_html_rendering_is_deterministic(self):
        old, new = synthetic()
        report = compare(parse_trace(old), parse_trace(new), parse_policy(POLICY))
        self.assertEqual(render_html(report), render_html(report))
