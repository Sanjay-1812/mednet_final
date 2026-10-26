"""Checks for paired experiments, accounting and statistical summaries."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from experiment import aggregate, run_benchmark, save_benchmark


class ExperimentTests(unittest.TestCase):
    def test_reproducibility_and_same_trace_across_policies(self):
        result = run_benchmark([1, 2], [1, 2.4], horizon_s=1)
        self.assertEqual(result, run_benchmark([1, 2], [1, 2.4], horizon_s=1))
        self.assertEqual(len(result["trace_manifest"]), 4)
        self.assertEqual(len(result["raw_metrics"]), 4 * 3 * 7)
        for trace in result["trace_manifest"]:
            matching = [r for r in result["raw_metrics"]
                        if r["seed"] == trace["seed"] and r["load"] == trace["load"]]
            self.assertEqual({r["trace_sha256"] for r in matching}, {trace["trace_sha256"]})
            self.assertEqual({r["generated"] for r in matching if r["traffic_class"] == "ALL"},
                             {trace["packets"]})

    def test_accounting_and_paired_differences(self):
        result = run_benchmark([4, 5], [2.4], horizon_s=2, capacity=10)
        raw = {(r["seed"], r["load"], r["policy"], r["traffic_class"]): r
               for r in result["raw_metrics"]}
        for row in raw.values():
            self.assertEqual(row["generated"], row["delivered"] + row["buffer_dropped"])
            self.assertEqual(row["delivered"], row["delivered_on_time"] + row["delivered_late"])
            self.assertLessEqual(row["link_time_pct"], 100.000001)
        for row in result["paired_differences"]:
            candidate = raw[(row["seed"], row["load"], row["candidate"], row["traffic_class"])]
            baseline = raw[(row["seed"], row["load"], row["baseline"], row["traffic_class"])]
            self.assertEqual(row["on_time_success_pct_delta"],
                             candidate["on_time_success_pct"] - baseline["on_time_success_pct"])
            self.assertEqual(row["generated_delta"], 0)

    def test_summary_uses_sample_standard_deviation(self):
        result = aggregate([{"load": 1, "value": 1}, {"load": 1, "value": 3}],
                           ["load"], ["value"])
        self.assertEqual(result[0]["n_runs"], 2)
        self.assertEqual(result[0]["value_mean"], 2)
        self.assertAlmostEqual(result[0]["value_std"], 2 ** 0.5)
        single = aggregate([{"load": 1, "value": 3}], ["load"], ["value"])
        self.assertEqual(single[0]["value_std"], 0)

    def test_invalid_run_configuration(self):
        for kwargs in [{"seeds": []}, {"seeds": [1, 1]}, {"seeds": [True]},
                       {"loads": []}, {"loads": [1, 1.0]}, {"loads": [float("nan")]},
                       {"loads": [-1]}, {"horizon_s": float("inf")}, {"capacity": -1}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_benchmark(**kwargs)

    def test_output_files_and_zero_packet_run(self):
        result = run_benchmark([1], [0], horizon_s=1)
        self.assertTrue(all(row["generated"] == 0 for row in result["raw_metrics"]))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            save_benchmark(result, folder)
            path = Path(folder)
            with (path / "raw_metrics.csv").open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 21)
            config = json.loads((path / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["simulation_count"], 3)
            self.assertEqual(len(list(path.glob("*.csv"))), 5)


if __name__ == "__main__":
    unittest.main()
