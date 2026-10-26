"""Reproducible MedNet comparison across traffic loads and independent seeds.

Every policy receives the identical packet trace for a (seed, load) pair.
Summaries are unweighted means and sample standard deviations of per-run
metrics. Paired differences are candidate minus baseline on that same trace.
"""

import argparse
import hashlib
import json
import platform
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import mean, stdev

from mednet import (CLASSES, POLICIES, ScoreConfig, generate_trace, simulate,
                    validate_config, validate_number, write_csv)


COMPARISONS = (("priority", "fifo"), ("mednet", "fifo"), ("mednet", "priority"))


def trace_hash(trace):
    data = json.dumps([asdict(p) for p in trace], separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def aggregate(rows, group_fields, metric_fields):
    """Sample SD measures seed variation, not a confidence interval."""
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)
    summary = []
    for key, group in sorted(groups.items()):
        row = dict(zip(group_fields, key))
        row["n_runs"] = len(group)
        for metric in metric_fields:
            values = [item[metric] for item in group]
            row[metric + "_mean"] = mean(values)
            row[metric + "_std"] = stdev(values) if len(values) > 1 else 0.0
        summary.append(row)
    return summary


def run_benchmark(seeds=tuple(range(1, 11)), loads=(1.0, 1.8, 2.4, 3.0),
                  horizon_s=20.0, link_bps=1_000_000, capacity=40, score=ScoreConfig()):
    """Return all tables in memory; saving is a separate explicit operation."""
    validate_config(horizon_s, link_bps, capacity, score)
    seeds, loads = list(seeds), list(loads)
    if not seeds or any(isinstance(s, bool) or not isinstance(s, int) for s in seeds):
        raise ValueError("Seeds must be a nonempty list of integers")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be unique")
    if not loads:
        raise ValueError("Loads must be a nonempty list")
    for load in loads:
        validate_number(load, "Load")
    if len(set(loads)) != len(loads):
        raise ValueError("Loads must be unique")
    raw, paired, manifest = [], [], []
    metric_fields = None
    for load in loads:
        for seed in seeds:
            trace = generate_trace(horizon_s, seed, load)
            digest = trace_hash(trace)
            offered_bytes = sum(p.size_bytes for p in trace)
            offered_mbps = offered_bytes * 8 / horizon_s / 1e6 if horizon_s else 0.0
            manifest.append({"seed": seed, "load": load, "packets": len(trace),
                             "offered_bytes": offered_bytes, "offered_mbps": offered_mbps,
                             "trace_sha256": digest})
            results = {}
            for policy in POLICIES:
                result = simulate(trace, policy, horizon_s, link_bps, capacity, score)
                results[policy] = {row["traffic_class"]: row for row in result.metrics}
                for row in result.metrics:
                    raw.append({"seed": seed, "load": load, "policy": policy,
                                "trace_sha256": digest, "offered_mbps": offered_mbps, **row})
                if metric_fields is None:
                    metric_fields = [key for key in result.metrics[0] if key != "traffic_class"]
            for candidate, baseline in COMPARISONS:
                for kind in [*CLASSES, "ALL"]:
                    row = {"seed": seed, "load": load, "candidate": candidate,
                           "baseline": baseline, "traffic_class": kind, "trace_sha256": digest}
                    row.update({metric + "_delta": results[candidate][kind][metric]
                                - results[baseline][kind][metric] for metric in metric_fields})
                    paired.append(row)
    summary = aggregate(raw, ["load", "policy", "traffic_class"], ["offered_mbps", *metric_fields])
    paired_summary = aggregate(paired, ["load", "candidate", "baseline", "traffic_class"],
                               [metric + "_delta" for metric in metric_fields])
    config = {
        "seeds": seeds, "loads": loads, "arrival_horizon_s": horizon_s,
        "link_bps": link_bps, "waiting_capacity_packets": capacity,
        "score": asdict(score), "policies": list(POLICIES),
        "classes": {name: asdict(spec) for name, spec in CLASSES.items()},
        "trace_count": len(manifest), "simulation_count": len(manifest) * len(POLICIES),
        "python_version": platform.python_version(),
        "mednet_source_sha256": hashlib.sha256(Path(__file__).with_name("mednet.py").read_bytes()).hexdigest(),
        "experiment_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "trace_hash_method": "SHA256 of UTF-8 compact JSON list of Packet dataclass dictionaries, trace order.",
        "pairing": "Generate once per seed/load, then reuse identical packets for all three policies.",
        "summary_method": "Unweighted mean and sample standard deviation across seeds; n=1 SD is 0 by convention. "
                          "Per-run p95 delays are averaged, not pooled into a common percentile. "
                          "These SDs are descriptive, not confidence intervals or significance tests.",
        "paired_method": "candidate minus baseline, first calculated within each seed/load; "
                         "positive on_time_success_pct_delta means improvement in percentage points. "
                         "Negative mean_delay_ms_delta means lower delivered-packet delay.",
        "model": "One nonpreemptive link; finite waiting queue with tail drop; arrivals stop then admitted packets drain.",
        "observation": "Each run uses 0 to max(arrival horizon, last completion).",
        "metric_note": "On-time success divides by all generated packets including tail drops as failures. "
                       "Delay statistics describe delivered packets. All classes have synthetic deadlines.",
        "provenance": "Artificial traffic generated in Python. No clinical targets, hospital measurements, "
                      "or patient data. The experiment does not establish hospital performance or safety.",
    }
    return {"raw_metrics": raw, "summary": summary, "paired_differences": paired,
            "paired_summary": paired_summary, "trace_manifest": manifest, "config": config}


def save_benchmark(result, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name in ["raw_metrics", "summary", "paired_differences", "paired_summary", "trace_manifest"]:
        write_csv(output / (name + ".csv"), result[name])
    (output / "config.json").write_text(json.dumps(result["config"], indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(1, 11)))
    parser.add_argument("--loads", type=float, nargs="+", default=[1.0, 1.8, 2.4, 3.0])
    parser.add_argument("--horizon", type=float, default=20.0)
    parser.add_argument("--link-mbps", type=float, default=1.0)
    parser.add_argument("--queue-capacity", type=int, default=40)
    parser.add_argument("--urgency-weight", type=float, default=3.0)
    parser.add_argument("--critical-boost", type=float, default=0.75)
    parser.add_argument("--congestion-threshold", type=float, default=0.75)
    parser.add_argument("--output", type=Path, default=Path("experiments"))
    args = parser.parse_args()
    try:
        result = run_benchmark(args.seeds, args.loads, args.horizon, args.link_mbps * 1e6,
                               args.queue_capacity,
                               ScoreConfig(args.urgency_weight, args.critical_boost, args.congestion_threshold))
        save_benchmark(result, args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print("Synthetic traffic. On-time success includes dropped packets as failures.")
    print(" Load  Policy      Runs  On-time mean +/- SD (%)  Mean delay (ms)  Mean drops")
    for row in result["summary"]:
        if row["traffic_class"] == "ALL":
            print(f"{row['load']:5.1f}  {row['policy']:9} {row['n_runs']:4}  "
                  f"{row['on_time_success_pct_mean']:10.2f} +/- {row['on_time_success_pct_std']:5.2f} "
                  f"{row['mean_delay_ms_mean']:16.2f} {row['buffer_dropped_mean']:11.1f}")
    print(f"Saved {result['config']['simulation_count']} runs to {args.output.resolve()}")


if __name__ == "__main__":
    main()
