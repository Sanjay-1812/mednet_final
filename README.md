# MedNet — Emergency Packet Prioritization Using a Synthetic Traffic Dataset

MedNet compares FIFO, fixed priority, and a custom dynamic priority heuristic using a Python-generated synthetic packet dataset. A local browser dashboard lets you generate traffic, replay a saved CSV, inspect policy comparisons, and download results. A separate experiment runner compares multiple traffic loads and random seeds.

This is a computer networks simulation project. It models one finite-buffer bottleneck link. It does not capture live network traffic, connect to medical devices, or establish clinical performance guarantees.

## Run the app

Use **Python 3.10 or newer**. No third-party packages, account, or internet connection are needed to run the project after Python is installed.

Extract the entire project folder. On Windows, double-click `start_mednet.bat`; it checks `py -3`, then `python`. Alternatively, open a terminal in this folder:

```text
python app.py
```

The app opens **http://127.0.0.1:8765** and serves only on this computer's loopback address. Keep the terminal open. Press **Ctrl+C** to stop. To use another port or avoid opening a browser automatically:

```text
python app.py --port 8766 --no-browser
```

Open `http://127.0.0.1:8766` yourself in that case. [START_HERE.md](START_HERE.md) contains a short demonstration sequence and troubleshooting.

## Dashboard workflow

- **Generated traffic:** select the settings and click **Run comparison**. The seed makes repeated generation reproducible with the same code and settings.
- **Use saved dataset:** replay the bundled `results/trace.csv` with the default experiment settings.
- **CSV replay:** select a previously saved synthetic trace. Set the duration to include every arrival. Seed and traffic multipliers do not modify imported packets.
- **Compare results:** examine both scenarios and individual traffic classes. Read delay alongside losses and deadline outcomes.
- **Download results ZIP:** save `trace.csv`, `metrics.csv`, `outcomes.csv`, and `config.json` together.

The labels **normal** and **congested** identify the two scenarios. Whether a scenario actually experiences congestion depends on its offered traffic and the chosen link and buffer settings.

Dashboard results are held temporarily in memory, with the eight most recent runs available for download. Stopping the app clears that cache. The bundled files in `results` are separate from browser runs.

## Default experiment

| Setting | Default |
|---|---:|
| Random seed | 42 |
| Packet arrival duration | 20 seconds |
| Link rate | 1 Mbps |
| Waiting buffer | 40 packets |
| Normal traffic multiplier | 1.0 |
| Congested traffic multiplier | 2.4 |
| Urgency weight | 3.0 |
| Critical-class congestion boost | 0.75 |
| Congestion threshold | 0.75 of the waiting buffer |

Each traffic class has independent exponential interarrival times. Its rate below is multiplied by the scenario's traffic multiplier. Packet sizes vary uniformly from 80% to 120% of the nominal size, rounded to whole bytes. Each absolute deadline is the arrival time plus the class's relative deadline. All these values are **chosen synthetic experiment settings**, not measurements or medical standards.

| CSV class | Base priority | Nominal bytes | Base packets/second | Relative deadline |
|---|---:|---:|---:|---:|
| `emergency` | 5 | 256 | 3 | 80 ms |
| `monitoring` | 5 | 512 | 12 | 150 ms |
| `video` | 4 | 1200 | 32 | 200 ms |
| `images` | 3 | 1400 | 16 | 600 ms |
| `records` | 2 | 1000 | 5 | 1000 ms |
| `admin` | 1 | 700 | 3 | 1500 ms |

The generator starts from the chosen seed for each scenario. Each policy receives exactly the same trace within that scenario. The two scenario traces are generated separately; they are not identical packet lists.

## Model and scheduling policies

A discrete-event simulator processes arrivals and transmission completions. One packet can be transmitted at a time. Transmission is nonpreemptive: a new urgent arrival cannot interrupt the packet already being sent. Serialization time is `size_bytes × 8 / link_bps`.

The finite capacity counts **waiting packets**, excluding the packet currently transmitting. If the waiting buffer is full, the new arrival is dropped regardless of its class. Packets are not discarded for passing their deadlines. Arrivals stop at the configured duration, and admitted packets then drain from the system. If an arrival and completion occur at exactly the same time, completion and selection of an existing waiting packet happen first.

| Policy | Next waiting packet selected |
|---|---|
| FIFO | Earliest arrival |
| Fixed priority | Highest base class priority |
| MedNet | Highest dynamic score, recalculated at each selection |

Ties use arrival time, then packet ID. MedNet's dynamic score is:

```text
urgency = clamp((now - arrival) / (deadline - arrival), 0, 1)
congestion = clamp((waiting_occupancy - threshold) / (1 - threshold), 0, 1)
score = base_priority + urgency_weight * urgency
        + critical_boost * congestion  [emergency and monitoring only]
```

Here `waiting_occupancy` is waiting count divided by queue capacity before selection. A zero deadline window has urgency 1. The congestion term is used only for a nonempty waiting queue; a zero-capacity buffer cannot hold waiting packets.

This is a normalized waiting-time heuristic, not earliest-deadline-first scheduling. Setting both `urgency_weight` and `critical_boost` to zero makes its ordering equivalent to fixed priority. Its effects must be measured: it need not outperform either baseline for every metric or traffic class.

## Read the outputs

| File | Contents |
|---|---|
| `trace.csv` | Input packet events, once per scenario; reusable for replay |
| `metrics.csv` | Scenario, policy, and class-level results, including an `ALL` row |
| `outcomes.csv` | Each packet's delivered or buffer-dropped outcome under every policy, with transmission timestamps where applicable |
| `config.json` | Experiment settings, traffic-class definitions, provenance, and metric conventions |

- **On-time success (%)** divides on-time deliveries by all generated packets. Buffer drops count as failures.
- **Mean and p95 delay** describe delivered packets only, from arrival to transmission finish. Delay includes waiting and serialization. A lower delay among survivors can coexist with more loss.
- **Buffer drops** count arrivals rejected by the full waiting queue. `deadline_buffer_drops` also counts these dropped packets because every class has a synthetic deadline; it does not mean packets were removed on expiry.
- **Delivered late** counts delivered packets that finished after their absolute deadline.
- **Throughput** divides delivered bits by the observation duration: the larger of the arrival duration and the final transmission finish time. This includes initial idle time and draining.
- **Link time (%)** is the class's transmission-time share of the same observation duration. The `ALL` value is total link utilization.

Check packet counts before interpreting a zero metric: empty classes and runs use zero placeholders where there are no observations. All dashboard percentages and delay summaries come from the same simulator used by the command line.

## Dataset format

Required CSV header:

```csv
scenario,packet_id,kind,arrival_s,size_bytes,deadline_s
normal,0,emergency,0.100000,256,0.180000
congested,0,monitoring,0.050000,512,0.200000
```

This two-row example illustrates the format only. Use the bundled or generated full trace for a useful comparison.

`scenario` must be `normal` or `congested`; `kind` must match a class in the table above. Packet IDs are nonnegative integers, unique within each scenario. Arrival times must be finite, nonnegative, and no later than the selected duration. Packet sizes must be positive whole bytes. `deadline_s` is an **absolute** time in seconds, finite and at least the arrival time. The importer sorts by arrival and packet ID.

The dashboard limits experiments to 50,000 actual packets and request bodies to 4 MB. It also bounds the controls and checks expected generated workload before running. Larger controlled experiments can use the command line, subject to available memory and runtime.

## Command-line comparisons

Run these from the project folder. On Windows, `py -3` can replace `python`.

```text
python mednet.py --output results_new
python mednet.py --input-dataset results/trace.csv --output replay_results
python mednet.py --seed 43 --output results_seed43
python mednet.py --link-mbps 2 --output results_faster_link
python mednet.py --critical-boost 0 --output results_without_boost
python mednet.py --urgency-weight 0 --critical-boost 0 --output results_fixed_equivalent
```

Every invocation compares all three policies for both scenarios. `--output` chooses the destination folder; existing files of the same names in that folder are overwritten. Replay preserves CSV arrivals, sizes, and deadlines; link, buffer, score settings, and duration are still configurable.

Supported controls: `--seed`, `--horizon`, `--link-mbps`, `--queue-capacity`, `--normal-load`, `--congested-load`, `--urgency-weight`, `--critical-boost`, `--congestion-threshold`, `--input-dataset`, and `--output`. Use `python mednet.py --help` for details.

## Multiple seeds and traffic loads

```text
python experiment.py --output experiments_new
```

Defaults are seeds 1–10 and multipliers 1.0, 1.8, 2.4, and 3.0: **40 traces and 120 policy simulations**. One trace is generated per seed/load pair and reused by all policies. To choose a smaller experiment:

```text
python experiment.py --seeds 1 2 3 --loads 1 2.4 --horizon 20 --output experiments_small
```

The runner also accepts `--link-mbps`, `--queue-capacity`, `--urgency-weight`, `--critical-boost`, and `--congestion-threshold`.

| Output | Purpose |
|---|---|
| `raw_metrics.csv` | Every seed/load/policy/class result |
| `summary.csv` | Unweighted mean and sample standard deviation across seeds |
| `paired_differences.csv` | Candidate minus baseline for each seed/load/class on the same trace |
| `paired_summary.csv` | Mean and sample standard deviation of the paired differences |
| `trace_manifest.csv` | Packet counts, offered load, and trace hashes |
| `config.json` | Parameters, source hashes, Python version, and aggregation definitions |

A positive on-time-success difference means a gain in **percentage points**; a negative delay difference means lower delivered-packet delay. Standard deviations describe seed variation; they are not confidence intervals or significance tests. Summary p95 values are means of per-run p95 values, not pooled percentiles. With one seed, the standard deviation is recorded as zero by convention.

## Scope, evidence, and references

MedNet has no real hospital dataset, measured traffic calibration, TCP feedback, routing, wireless interference, retransmissions, multiple hops, or hardware deployment. Independent exponential arrivals omit important forms of burstiness and correlation. Class names provide a healthcare-themed use case; rates, sizes, deadlines, and weights remain explicit modeling choices.

The project contribution is an implemented simulator, repeatable synthetic dataset, local demonstration, and analysis of scheduling tradeoffs. Priority and deadline-aware scheduling are established research topics. The experiments do not establish a new universally better scheduler or a deadline guarantee.

Read [REFERENCES.md](REFERENCES.md) for seven verified papers, direct reading links, relevant sections, and the limits of each comparison. See [START_HERE.md](START_HERE.md) for a short usage sequence.

## Verification

Run `python -m unittest -v` from this folder. The final release passes 28 checks covering scheduling, input validation, dataset replay, repeated-seed summaries, dashboard requests, and result archives. Browser checks also covered scenario switching, a changed link rate, CSV upload/replay, class metric selection, and ZIP download. See `VERIFICATION.md` for the saved verification record and `MedNet_Review3_Final_Report.pdf` for the submission report.
