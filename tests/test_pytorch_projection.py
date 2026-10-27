import json
import tempfile
import unittest
from pathlib import Path

from tools.profile_pytorch import CATEGORY, STAGE, public_projection, validate_projection, write_example
from tracebudget.core import InputError, parse_trace


def recorded_samples(count=30):
    return [{"ph": "X", "name": STAGE, "cat": CATEGORY, "pid": 98765, "tid": 45678,
             "ts": 9007199254740992 + i * 1000, "dur": 250}
            for i in range(count)]


class ProducerProjectionTests(unittest.TestCase):
    def test_only_fixed_annotation_and_allowlisted_fields_survive(self):
        sentinel = "private-producer-" + "fixture"
        events = recorded_samples()
        for event in events:
            event["args"] = {"path": sentinel}
        events += [{"ph": "M", "name": "process_name", "args": {"name": sentinel}},
                   {"ph": "X", "name": sentinel, "cat": "internal", "ts": 0, "dur": 1}]
        capture = parse_trace({"traceEvents": events, "host": sentinel})
        output = public_projection(capture)
        text = json.dumps(output)
        self.assertNotIn(sentinel, text)
        self.assertNotIn("98765", text)
        self.assertNotIn("45678", text)
        self.assertEqual(len(output["traceEvents"]), 30)
        for event in output["traceEvents"]:
            self.assertEqual(set(event), {"ph", "name", "cat", "pid", "tid", "ts", "dur"})
            self.assertEqual((event["pid"], event["tid"]), (1, 1))

    def test_relative_timestamps_preserve_large_integer_differences(self):
        output = public_projection(parse_trace(recorded_samples()))
        self.assertEqual(output["traceEvents"][0]["ts"], 0)
        self.assertEqual(output["traceEvents"][1]["ts"], 1000)
        self.assertEqual(output["traceEvents"][0]["dur"], 250)

    def test_missing_extra_and_wrong_category_spans_fail(self):
        for events in (recorded_samples(29), recorded_samples(31),
                       [{**event, "cat": "different"} for event in recorded_samples()]):
            with self.subTest(count=len(events)), self.assertRaises(InputError):
                public_projection(parse_trace(events))

    def test_expected_sample_count_is_validated(self):
        capture = parse_trace(recorded_samples())
        for count in (True, 0, -1, 1.5, 10001):
            with self.subTest(count=count), self.assertRaises(InputError):
                public_projection(capture, count)

    def test_projection_keeps_selected_statistics_and_decision(self):
        events = recorded_samples()
        events += [{"ph": "X", "name": "other", "cat": "cpu_op", "ts": 0, "dur": 123}]
        raw = parse_trace(events)
        public = public_projection(raw)
        validate_projection(raw, raw, public, public)

    def test_altered_projection_is_rejected(self):
        raw = parse_trace(recorded_samples())
        public = public_projection(raw)
        changed = {**public, "traceEvents": [
            {**event, "dur": event["dur"] * 3} for event in public["traceEvents"]]}
        with self.assertRaises(InputError):
            validate_projection(raw, raw, public, changed)

    def test_example_writes_complete_review_artifacts_without_torch(self):
        public = public_projection(parse_trace(recorded_samples()))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            report = write_example(folder, public, public, [])
            self.assertEqual(report["exit_code"], 0)
            self.assertEqual(report["results"][0]["baseline"]["count"], 27)
            self.assertEqual({path.name for path in folder.iterdir()},
                             {"baseline.json", "candidate.json", "policy.json", "report.json",
                              "index.html", "junit.xml", "method.json"})
            method = json.loads((folder / "method.json").read_text(encoding="utf-8"))
            self.assertEqual(method["retained_samples_per_variant"], 27)
            self.assertEqual(method["producer_version"], "2.14.1+cpu")
