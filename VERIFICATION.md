# Final verification record

Verified on 19 October 2026.

## Automated checks

`python -m unittest -v` passes **28 tests**:

- 15 core tests: non-preemptive timing, FIFO and priority selection, urgency and congestion changes, tie handling, finite-buffer drops, deadlines, empty input, zero waiting capacity, deterministic generation, CSV replay, and invalid input.
- 5 experiment tests: trace reuse, repeatability, conservation, paired differences, sample standard deviation, exports, and invalid configuration.
- 8 dashboard tests: reference replay, generated-data replay, empty exports, request validation, malformed CSV, download archive, route isolation, cross-origin rejection, busy handling, and cache eviction.

The suite passed with the bundled Python 3.12 runtime and the installed Python **3.14.3** selected by `py -3`. JavaScript syntax validation also passed.

## Browser checks

The local application was opened in a desktop browser and checked for:

- Reference dataset loading: 4,750 input rows; congested scenario MedNet on-time success 66.39%.
- Normal/congested scenario switching: reference normal scenario shows 100% on-time delivery.
- Link-rate change: at 2 Mbps, seed-42 congested traffic has 3,395 on-time deliveries and no drops or late deliveries for all three policies.
- CSV file selection and replay: the saved dataset reproduces 66.39% MedNet on-time success at the default 1 Mbps rate.
- Per-class metric selection: buffer loss and mean delay tables update.
- Download: the browser saved the ZIP containing trace.csv, metrics.csv, outcomes.csv, and config.json. Its CSV contents match the reference outputs byte for byte.
- Browser console: no warnings or errors were reported during the checked interactions.

The temporary preview used port 8766; the distributed launcher defaults to 8765. The report includes the observed dashboard screenshot. Browser testing was performed on the desktop layout.

## Results and reproducibility

The seed-42 reference CSV outputs are byte-identical to the Review 2 outputs. The trace SHA-256 is:

`472053455d80dae3172aa8f77125210d9e213cea4da9b864b78c110d1dbcb333`

The benchmark uses 10 seeds and four loads: 40 common traces and 120 policy simulations. Its CSV tables, settings, source hashes, and per-trace fingerprints are included in `experiments/`. Paired differences compare policies on the same trace. Sample standard deviations describe variation across seeds; they are not confidence intervals or clinical validation.

The 15-page report was rendered and every page inspected for layout. The title and report omit the removed project descriptor. The product remains a synthetic single-link simulation with explicitly chosen workload settings.
