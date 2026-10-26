"""MedNet: synthetic single-link packet scheduling, Python stdlib only.

This is a discrete-event teaching prototype, not a hospital network deployment.
All traffic rates and deadlines below are invented experiment parameters.
"""

import argparse
import csv
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean


@dataclass(frozen=True)
class TrafficClass:
    priority: int
    packet_bytes: int
    rate_per_s: float
    deadline_ms: float


CLASSES = {
    "emergency": TrafficClass(5, 256, 3, 80),
    "monitoring": TrafficClass(5, 512, 12, 150),
    "video": TrafficClass(4, 1200, 32, 200),
    "images": TrafficClass(3, 1400, 16, 600),
    "records": TrafficClass(2, 1000, 5, 1000),
    "admin": TrafficClass(1, 700, 3, 1500),
}
POLICIES = ("fifo", "priority", "mednet")
CRITICAL = {"emergency", "monitoring"}


@dataclass(frozen=True)
class Packet:
    packet_id: int
    kind: str
    arrival_s: float
    size_bytes: int
    deadline_s: float  # Absolute synthetic deadline, measured from time zero.


@dataclass(frozen=True)
class ScoreConfig:
    urgency_weight: float = 3.0
    critical_boost: float = 0.75
    congestion_threshold: float = 0.75


@dataclass
class Outcome:
    packet: Packet
    status: str
    start_s: float = None
    finish_s: float = None


@dataclass
class SimulationResult:
    outcomes: list
    metrics: list
    observation_s: float
    busy_s: float


def validate_number(value, name, minimum=0.0, strict=False):
    """Reject nonnumeric, boolean and nonfinite API inputs before doing work."""
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and (value > minimum if strict else value >= minimum))
    except OverflowError:
        valid = False
    if not valid:
        relation = "greater than" if strict else "at least"
        raise ValueError(f"{name} must be a finite number {relation} {minimum}")


def validate_config(horizon_s, link_bps, capacity, score):
    validate_number(horizon_s, "Horizon")
    validate_number(link_bps, "Link rate", strict=True)
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0:
        raise ValueError("Waiting capacity must be a nonnegative integer")
    if not isinstance(score, ScoreConfig):
        raise ValueError("Score must be a ScoreConfig")
    validate_number(score.urgency_weight, "Urgency weight")
    validate_number(score.critical_boost, "Critical boost")
    validate_number(score.congestion_threshold, "Congestion threshold")
    if score.congestion_threshold >= 1:
        raise ValueError("Congestion threshold must be less than 1")


def generate_trace(horizon_s, seed, load=1.0):
    """Independent Poisson arrivals; seeded sizes vary by +/-20 percent."""
    validate_number(horizon_s, "Horizon")
    validate_number(load, "Load")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Seed must be an integer")
    if any(not math.isfinite(spec.rate_per_s * load) for spec in CLASSES.values()):
        raise ValueError("Load is too large")
    rng = random.Random(seed)
    trace = []
    for kind, spec in CLASSES.items():
        time_s = 0.0
        rate = spec.rate_per_s * load
        if rate <= 0:
            continue
        while True:
            time_s += rng.expovariate(rate)
            if time_s >= horizon_s:
                break
            size = max(1, round(spec.packet_bytes * rng.uniform(0.8, 1.2)))
            trace.append((time_s, kind, size, time_s + spec.deadline_ms / 1000))
    trace.sort()
    return [Packet(i, kind, arrival, size, deadline)
            for i, (arrival, kind, size, deadline) in enumerate(trace)]


def read_dataset(path, horizon_s):
    """Load synthetic CSV packet rows; never evaluate file contents as code."""
    validate_number(horizon_s, "Horizon")
    required = {"scenario", "packet_id", "kind", "arrival_s", "size_bytes", "deadline_s"}
    scenarios = {"normal": [], "congested": []}
    seen = set()
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        if not required.issubset(headers) or len(headers) != len(set(headers)):
            raise ValueError("Dataset requires unique headers: " + ", ".join(sorted(required)))
        for row in reader:
            try:
                scenario = row["scenario"]
                p = Packet(int(row["packet_id"]), row["kind"], float(row["arrival_s"]),
                           int(row["size_bytes"]), float(row["deadline_s"]))
                if (None in row or scenario not in scenarios or p.packet_id < 0
                        or p.kind not in CLASSES or not math.isfinite(p.arrival_s)
                        or not 0 <= p.arrival_s <= horizon_s or p.size_bytes <= 0
                        or not math.isfinite(p.deadline_s) or p.deadline_s < p.arrival_s):
                    raise ValueError("unknown scenario/class, invalid number or time outside horizon")
                key = (scenario, p.packet_id)
                if key in seen:
                    raise ValueError("duplicate (scenario, packet_id)")
                seen.add(key)
                scenarios[scenario].append(p)
            except (ValueError, TypeError) as error:
                raise ValueError(f"Dataset CSV line {reader.line_num}: {error}") from error
    for packets in scenarios.values():
        packets.sort(key=lambda p: (p.arrival_s, p.packet_id))
    return scenarios


def dynamic_score(packet, now_s, occupancy, score):
    """Recalculate at dequeue: priority + bounded age urgency + critical boost.

    urgency = clamp(age / relative_deadline, 0, 1), for every traffic class.
    congestion = clamp((occupancy - threshold) / (1 - threshold), 0, 1).
    occupancy is waiting packets / waiting capacity BEFORE removing a packet.
    Once expired, urgency stays at 1; expiration never discards a packet.
    """
    window = packet.deadline_s - packet.arrival_s
    urgency = 1.0 if window <= 0 else min(1.0, max(0.0, (now_s - packet.arrival_s) / window))
    congestion = min(1.0, max(0.0, (occupancy - score.congestion_threshold)
                               / (1.0 - score.congestion_threshold)))
    boost = score.critical_boost * congestion if packet.kind in CRITICAL else 0.0
    return CLASSES[packet.kind].priority + score.urgency_weight * urgency + boost


def choose_packet(waiting, policy, now_s, capacity, score):
    """Return a queue index. All ties use arrival time, then packet ID."""
    def key(index):
        packet = waiting[index]
        value = 0.0
        if policy == "priority":
            value = CLASSES[packet.kind].priority
        elif policy == "mednet":
            value = dynamic_score(packet, now_s, len(waiting) / capacity, score)
        return (-value, packet.arrival_s, packet.packet_id)
    return min(range(len(waiting)), key=key)


def percentile95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1] if values else 0.0


def summarize(outcomes, observation_s, busy_s):
    rows = []
    for kind in [*CLASSES, "ALL"]:
        selected = [o for o in outcomes if kind == "ALL" or o.packet.kind == kind]
        delivered = [o for o in selected if o.status == "delivered"]
        drops = len(selected) - len(delivered)
        on_time = sum(o.finish_s <= o.packet.deadline_s + 1e-12 for o in delivered)
        waits = [(o.start_s - o.packet.arrival_s) * 1000 for o in delivered]
        delays = [(o.finish_s - o.packet.arrival_s) * 1000 for o in delivered]
        delivered_bytes = sum(o.packet.size_bytes for o in delivered)
        service_s = sum(o.finish_s - o.start_s for o in delivered)
        rows.append({
            "traffic_class": kind, "generated": len(selected),
            "delivered": len(delivered), "buffer_dropped": drops,
            "delivered_on_time": on_time, "delivered_late": len(delivered) - on_time,
            "deadline_buffer_drops": drops,
            "on_time_success_pct": 100 * on_time / len(selected) if selected else 0.0,
            "mean_wait_ms": mean(waits) if waits else 0.0,
            "mean_delay_ms": mean(delays) if delays else 0.0,
            "p95_delay_ms": percentile95(delays), "delivered_bytes": delivered_bytes,
            "throughput_mbps": delivered_bytes * 8 / observation_s / 1e6 if observation_s else 0.0,
            "link_time_pct": 100 * service_s / observation_s if observation_s else 0.0,
            "observation_s": observation_s,
        })
    assert sum(r["delivered"] for r in rows[:-1]) == rows[-1]["delivered"]
    assert abs(sum(o.finish_s - o.start_s for o in outcomes if o.status == "delivered") - busy_s) < 1e-7
    return rows


def simulate(trace, policy, horizon_s=20.0, link_bps=1_000_000, capacity=40,
             score=ScoreConfig()):
    """One nonpreemptive link; finite WAITING queue; drop new arrivals if full.

    Stop arrivals at the horizon and drain all admitted packets. Completions
    precede arrivals at equal timestamps. Waiting traffic starts immediately
    on a completion, before an arrival at that same timestamp is considered.
    Observation interval: [0, max(horizon_s, last packet completion)].
    """
    if policy not in POLICIES:
        raise ValueError("Unknown policy")
    validate_config(horizon_s, link_bps, capacity, score)
    try:
        packets = list(trace)
    except TypeError as error:
        raise ValueError("Trace must be an iterable of Packet objects") from error
    for p in packets:
        if (not isinstance(p, Packet) or isinstance(p.packet_id, bool)
                or not isinstance(p.packet_id, int) or p.packet_id < 0
                or not isinstance(p.kind, str) or p.kind not in CLASSES
                or isinstance(p.size_bytes, bool) or not isinstance(p.size_bytes, int)
                or p.size_bytes <= 0):
            raise ValueError("Invalid packet")
        validate_number(p.arrival_s, "Packet arrival")
        validate_number(p.deadline_s, "Packet deadline")
        if p.arrival_s > horizon_s or p.deadline_s < p.arrival_s:
            raise ValueError("Packet time lies outside the horizon or deadline precedes arrival")
        try:
            validate_number(p.size_bytes * 8 / link_bps, "Serialization duration", strict=True)
        except OverflowError as error:
            raise ValueError("Packet size is too large") from error
    if len({p.packet_id for p in packets}) != len(packets):
        raise ValueError("Packet IDs must be unique")
    packets.sort(key=lambda p: (p.arrival_s, p.packet_id))
    waiting, outcomes = [], []
    active = None
    last_finish, busy_s = 0.0, 0.0

    def start(packet, now_s):
        return Outcome(packet, "delivered", now_s, now_s + packet.size_bytes * 8 / link_bps)

    def complete(current):
        nonlocal busy_s, last_finish
        outcomes.append(current)
        busy_s += current.finish_s - current.start_s
        last_finish = current.finish_s
        if waiting:
            index = choose_packet(waiting, policy, last_finish, capacity, score)
            return start(waiting.pop(index), last_finish)
        return None

    for packet in packets:
        while active is not None and active.finish_s <= packet.arrival_s:
            active = complete(active)
        if active is None:
            active = start(packet, packet.arrival_s)
        elif len(waiting) < capacity:
            waiting.append(packet)
        else:
            outcomes.append(Outcome(packet, "buffer_drop"))
    while active is not None:
        active = complete(active)
    observation_s = max(horizon_s, last_finish)
    metrics = summarize(outcomes, observation_s, busy_s)
    return SimulationResult(outcomes, metrics, observation_s, busy_s)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_experiment(args):
    score = ScoreConfig(args.urgency_weight, args.critical_boost, args.congestion_threshold)
    validate_config(args.horizon, args.link_mbps * 1e6, args.queue_capacity, score)
    dataset = read_dataset(args.input_dataset, args.horizon) if args.input_dataset else None
    args.output.mkdir(parents=True, exist_ok=True)
    all_metrics, traces, events = [], [], []
    print("Synthetic deadlines only; arrivals stop at horizon, then queues drain.")
    print("Scenario   Policy     Sent  Delivered  Drops   Late  On-time%  Delay(ms)  Mbps  Link%")
    scenario_info = []
    for scenario, load in [("normal", args.normal_load), ("congested", args.congested_load)]:
        trace = dataset[scenario] if dataset is not None else generate_trace(args.horizon, args.seed, load)
        traces.extend({"scenario": scenario, **asdict(packet)} for packet in trace)
        offered_mbps = sum(p.size_bytes for p in trace) * 8 / args.horizon / 1e6 if args.horizon else 0.0
        scenario_info.append({"scenario": scenario, "load_multiplier": load if dataset is None else None,
                              "offered_mbps": offered_mbps})
        for policy in POLICIES:
            result = simulate(trace, policy, args.horizon, args.link_mbps * 1e6, args.queue_capacity, score)
            all_metrics.extend({"scenario": scenario, "policy": policy, **row} for row in result.metrics)
            for outcome in result.outcomes:
                events.append({"scenario": scenario, "policy": policy, **asdict(outcome.packet),
                               "status": outcome.status, "start_s": outcome.start_s,
                               "finish_s": outcome.finish_s})
            row = result.metrics[-1]
            print(f"{scenario:10} {policy:9} {row['generated']:5} {row['delivered']:10} "
                  f"{row['buffer_dropped']:6} {row['delivered_late']:6} "
                  f"{row['on_time_success_pct']:9.1f} {row['mean_delay_ms']:10.1f} "
                  f"{row['throughput_mbps']:5.3f} {row['link_time_pct']:6.1f}")
    write_csv(args.output / "metrics.csv", all_metrics)
    # Explicit field headers also make zero-packet experiments valid CSV files.
    for filename, rows, fields in [
        ("trace.csv", traces, ["scenario", "packet_id", "kind", "arrival_s", "size_bytes", "deadline_s"]),
        ("outcomes.csv", events, ["scenario", "policy", "packet_id", "kind", "arrival_s", "size_bytes",
                                  "deadline_s", "status", "start_s", "finish_s"]),
    ]:
        with (args.output / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    metadata = {
        "input_origin": "generated" if dataset is None else "csv_replay",
        "input_dataset": str(args.input_dataset.resolve()) if args.input_dataset else None,
        "seed": args.seed if dataset is None else None,
        "arrival_horizon_s": args.horizon, "link_bps": args.link_mbps * 1e6,
        "waiting_capacity_packets": args.queue_capacity, "score": asdict(score),
        "classes": {name: asdict(spec) for name, spec in CLASSES.items()}, "scenarios": scenario_info,
        "model": "One nonpreemptive link; finite waiting queue; tail drop; no expiry drops.",
        "deadline_note": "All deadlines and traffic parameters are synthetic, not clinical targets.",
        "dataset_note": "Synthetic experiment data, not calibrated to real hospital measurements. "
                        "Class priorities apply in both modes; class size/rate/deadline settings are generator "
                        "defaults only. Replay uses CSV arrival times, sizes and absolute deadlines.",
        "observation": "0 to max(arrival horizon, final completion), separately for each policy.",
        "metric_notes": "Delay statistics cover delivered packets; on-time success divides by all generated packets. "
                        "Every class has a deadline, so deadline_buffer_drops equals buffer_dropped. "
                        "Link time percent is class transmission time / observation; ALL is link utilization. "
                        "Throughput includes all delivered bytes over the same observation interval.",
    }
    (args.output / "config.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Saved metrics.csv, trace.csv, outcomes.csv and config.json to {args.output.resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--horizon", type=float, default=20.0)
    parser.add_argument("--link-mbps", type=float, default=1.0)
    parser.add_argument("--queue-capacity", type=int, default=40)
    parser.add_argument("--normal-load", type=float, default=1.0)
    parser.add_argument("--congested-load", type=float, default=2.4)
    parser.add_argument("--urgency-weight", type=float, default=3.0)
    parser.add_argument("--critical-boost", type=float, default=0.75)
    parser.add_argument("--congestion-threshold", type=float, default=0.75)
    parser.add_argument("--input-dataset", type=Path,
                        help="Replay a synthetic trace CSV instead of generating traffic")
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    if any(not math.isfinite(x) or x < 0 for x in [args.horizon, args.normal_load, args.congested_load]):
        parser.error("Horizon and load multipliers must be finite and nonnegative")
    try:
        run_experiment(args)
    except (ValueError, OSError, csv.Error) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
