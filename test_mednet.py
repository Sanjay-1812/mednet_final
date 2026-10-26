"""Hand-calculable checks: run python -m unittest -v."""

import csv
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from mednet import Packet, ScoreConfig, choose_packet, dynamic_score, generate_trace, read_dataset, simulate


def packet(number, kind="admin", arrival=0.0, size=100, deadline=10.0):
    return Packet(number, kind, arrival, size, deadline)


def order(result):
    return [o.packet.packet_id for o in result.outcomes if o.status == "delivered"]


class SchedulingTests(unittest.TestCase):
    def test_fifo_and_priority_are_nonpreemptive(self):
        trace = [packet(0), packet(1, arrival=0.1), packet(2, "emergency", 0.2)]
        # At 800 bit/s, each 100-byte packet requires exactly one second.
        fifo = simulate(trace, "fifo", horizon_s=0.2, link_bps=800)
        priority = simulate(trace, "priority", horizon_s=0.2, link_bps=800)
        self.assertEqual(order(fifo), [0, 1, 2])
        self.assertEqual(order(priority), [0, 2, 1])
        self.assertEqual([o.finish_s for o in fifo.outcomes], [1.0, 2.0, 3.0])
        self.assertAlmostEqual(fifo.metrics[-1]["mean_wait_ms"], 900.0)
        self.assertAlmostEqual(fifo.metrics[-1]["mean_delay_ms"], 1900.0)
        self.assertAlmostEqual(fifo.observation_s, 3.0)
        self.assertAlmostEqual(fifo.metrics[-1]["throughput_mbps"], 0.0008)
        self.assertAlmostEqual(fifo.metrics[-1]["link_time_pct"], 100.0)

    def test_deadline_urgency_reorders_waiting_packets(self):
        # At t=.1: emergency score 5.03; aged video score 5.5.
        waiting = [packet(0, "emergency"), packet(1, "video", deadline=0.2)]
        self.assertEqual(choose_packet(waiting, "priority", 0.1, 10, ScoreConfig()), 0)
        self.assertEqual(choose_packet(waiting, "mednet", 0.0, 10, ScoreConfig()), 0)
        self.assertEqual(choose_packet(waiting, "mednet", 0.1, 10, ScoreConfig()), 1)

    def test_congestion_boost_can_change_an_order(self):
        waiting = [packet(0, "emergency"), packet(1, "video", deadline=0.2)]
        self.assertEqual(choose_packet(waiting, "mednet", 0.1, 10, ScoreConfig()), 1)
        self.assertEqual(choose_packet(waiting, "mednet", 0.1, 2, ScoreConfig()), 0)
        self.assertAlmostEqual(dynamic_score(waiting[1], 100, 1, ScoreConfig()), 7.0)

    def test_equal_scores_use_arrival_then_id(self):
        waiting = [packet(5), packet(3), packet(1, arrival=0.1)]
        for policy in ("fifo", "priority", "mednet"):
            self.assertEqual(choose_packet(waiting, policy, 0.2, 10, ScoreConfig(0, 0)), 1)

    def test_tail_drop_accounting_and_deadlines(self):
        trace = [packet(0, deadline=1.0), packet(1, arrival=0.1, deadline=1.5),
                 packet(2, "emergency", 0.2, deadline=0.3)]
        result = simulate(trace, "priority", 0.2, 800, capacity=1)
        total = result.metrics[-1]
        self.assertEqual(order(result), [0, 1])  # High priority arrivals do not evict.
        self.assertEqual(total["generated"], 3)
        self.assertEqual(total["delivered"], 2)
        self.assertEqual(total["buffer_dropped"], 1)
        self.assertEqual(total["delivered_on_time"], 1)
        self.assertEqual(total["delivered_late"], 1)
        self.assertEqual(total["deadline_buffer_drops"], 1)
        self.assertAlmostEqual(total["on_time_success_pct"], 100 / 3)

    def test_zero_capacity_and_simultaneous_completion(self):
        trace = [packet(0), packet(1, arrival=0.5), packet(2, arrival=1.0)]
        result = simulate(trace, "mednet", 1, 800, capacity=0)
        self.assertEqual(order(result), [0, 2])
        self.assertEqual(result.metrics[-1]["buffer_dropped"], 1)

    def test_empty_trace_and_idle_observation(self):
        empty = simulate([], "mednet", horizon_s=0)
        self.assertEqual(empty.metrics[-1]["generated"], 0)
        self.assertEqual(empty.metrics[-1]["throughput_mbps"], 0)
        result = simulate([packet(0)], "fifo", horizon_s=10, link_bps=800)
        self.assertAlmostEqual(result.metrics[-1]["link_time_pct"], 10)
        self.assertAlmostEqual(result.metrics[-1]["throughput_mbps"], 0.00008)

    def test_seeded_trace_is_reusable_and_accounted_for(self):
        trace = generate_trace(2, 42, 2.4)
        self.assertEqual(trace, generate_trace(2, 42, 2.4))
        original = list(trace)
        for policy in ("fifo", "priority", "mednet"):
            result = simulate(trace, policy, 2)
            total = result.metrics[-1]
            self.assertEqual(total["generated"], total["delivered"] + total["buffer_dropped"])
            self.assertEqual(total["delivered"], total["delivered_on_time"] + total["delivered_late"])
            self.assertLessEqual(total["link_time_pct"], 100.000001)
        self.assertEqual(trace, original)


class DatasetTests(unittest.TestCase):
    HEADER = "scenario,packet_id,kind,arrival_s,size_bytes,deadline_s\n"

    def load(self, text):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "dataset.csv"
            path.write_text(text, encoding="utf-8")
            return read_dataset(path, horizon_s=2)

    def test_generated_trace_csv_replay_has_identical_metrics(self):
        traces = {name: generate_trace(2, 42, load)
                  for name, load in [("normal", 1), ("congested", 2.4)]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "dataset.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.HEADER.strip().split(","))
                writer.writeheader()
                for scenario, packets in traces.items():
                    writer.writerows({"scenario": scenario, **asdict(p)} for p in reversed(packets))
            replay = read_dataset(path, 2)
        self.assertEqual(replay, traces)
        for scenario in traces:
            for policy in ("fifo", "priority", "mednet"):
                self.assertEqual(simulate(traces[scenario], policy, 2).metrics,
                                 simulate(replay[scenario], policy, 2).metrics)

    def test_reject_invalid_headers_values_and_duplicate_ids(self):
        invalid = ["scenario,packet_id\n", self.HEADER + "normal,x,admin,0,100,1\n",
                   self.HEADER + "unknown,0,admin,0,100,1\n",
                   self.HEADER + "normal,0,unknown,0,100,1\n",
                   self.HEADER + "normal,0,admin,nan,100,1\n",
                   self.HEADER + "normal,0,admin,3,100,4\n",
                   self.HEADER + "normal,0,admin,0,0,1\n",
                   self.HEADER + "normal,0,admin,1,100,0\n",
                   self.HEADER + "normal,0,admin,0,100,inf\n",
                   self.HEADER + "normal,0,admin,0,100\n",
                   self.HEADER + "normal,0,admin,0,100,1\nnormal,0,video,1,100,2\n"]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.load(text)

    def test_header_only_and_same_id_in_separate_scenarios(self):
        self.assertEqual(self.load(self.HEADER), {"normal": [], "congested": []})
        replay = self.load(self.HEADER + "normal,0,admin,0,100,1\ncongested,0,admin,0,100,1\n")
        self.assertEqual(len(replay["normal"]), 1)
        self.assertEqual(len(replay["congested"]), 1)


class ValidationTests(unittest.TestCase):
    def test_generator_rejects_invalid_parameters(self):
        for kwargs in [{"horizon_s": float("nan")}, {"horizon_s": -1},
                       {"horizon_s": True}, {"load": float("inf")}, {"load": -1},
                       {"load": "2"}, {"load": 1e308}, {"seed": 1.5}, {"seed": False}]:
            arguments = {"horizon_s": 1, "seed": 42, "load": 1}
            arguments.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                generate_trace(**arguments)
        self.assertEqual(generate_trace(1, 42, 0), [])

    def test_simulator_rejects_invalid_configuration(self):
        for kwargs in [{"policy": "unknown"}, {"horizon_s": float("nan")},
                       {"link_bps": 0}, {"link_bps": "1000"}, {"capacity": True},
                       {"capacity": 1.5}, {"score": ScoreConfig(congestion_threshold=1)},
                       {"score": ScoreConfig(urgency_weight=float("inf"))}, {"score": None}]:
            arguments = {"trace": [], "policy": "fifo"}
            arguments.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                simulate(**arguments)

    def test_simulator_rejects_invalid_packets_before_sorting(self):
        invalid = [None, packet(-1), packet(True), packet("id"), packet(0, kind=[]),
                   packet(0, arrival=float("nan")), packet(0, arrival=True),
                   packet(0, size=True), packet(0, size=1.5), packet(0, deadline=float("inf"))]
        for candidate in invalid:
            with self.subTest(packet=candidate), self.assertRaises(ValueError):
                simulate([candidate], "fifo")
        with self.assertRaises(ValueError):
            simulate([packet(0), packet(0)], "fifo")

    def test_seed42_review2_totals_are_preserved(self):
        expected = {
            (1, "fifo"): (1355, 1355, 0, 0),
            (1, "priority"): (1355, 1355, 0, 0),
            (1, "mednet"): (1355, 1355, 0, 0),
            (2.4, "fifo"): (3395, 2385, 1010, 1559),
            (2.4, "priority"): (3395, 2377, 1018, 154),
            (2.4, "mednet"): (3395, 2382, 1013, 128),
        }
        for (load, policy), totals in expected.items():
            result = simulate(generate_trace(20, 42, load), policy).metrics[-1]
            self.assertEqual(tuple(result[key] for key in
                                   ["generated", "delivered", "buffer_dropped", "delivered_late"]), totals)


if __name__ == "__main__":
    unittest.main()
