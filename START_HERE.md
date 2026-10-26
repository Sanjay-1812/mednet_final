# Start MedNet

MedNet is a Python packet-scheduling simulator with a local browser dashboard. Its dataset is synthetic: it contains generated packet events, not hospital measurements or patient information.

## Open the dashboard

1. Extract the entire project ZIP to a folder. Keep `app.py`, `mednet.py`, `static`, and `results` together.
2. Install **Python 3.10 or newer** if needed. The project uses the Python standard library; no extra packages are required.
3. On Windows, double-click **`start_mednet.bat`**. Keep its window open.
4. Your browser should open **http://127.0.0.1:8765**. If it does not, open that address yourself.

To start manually, open a terminal in the extracted project folder and run:

```text
python app.py
```

If Windows recognizes `py` instead, use `py -3 app.py`.

## Try a first comparison

1. Click **Use saved dataset** to replay the bundled synthetic CSV using the default settings.
2. Compare **FIFO**, **Fixed priority**, and **MedNet** in each scenario. Check class-level results as well as the overall result.
3. Explain **on-time success**, **delay**, and **buffer drops** together. A policy can help urgent traffic while making another class wait longer.
4. Choose **Generated traffic**, change one setting, and click **Run comparison**. For example, increase link capacity to see how congestion changes.
5. Click **Download results ZIP** to keep the dataset, metrics, packet outcomes, and settings used for that run.

Browser results are temporary. Download them before stopping the app; the app retains only its eight most recent runs while it is running. To stop, return to the launcher window and press **Ctrl+C**.

## Use your own saved synthetic dataset

Choose **CSV replay**, select a `trace.csv` exported by MedNet, and set the duration to cover its latest packet arrival. Click **Run comparison**. The three policies receive identical packets within each scenario. Replay uses the selected CSV; the random seed and load multipliers do not change its arrivals.

For the required columns and accepted class names, see [README.md](README.md#dataset-format).

## If something does not open

- **Python is missing:** install it from [python.org](https://www.python.org/downloads/), enabling the Python launcher or adding Python to PATH. Then reopen the launcher.
- **The address is already in use:** close another running MedNet window, or run `python app.py --port 8766` and open `http://127.0.0.1:8766`.
- **The page cannot connect:** keep the launcher window open and use the address printed there. Run the app from the extracted folder, not from inside the ZIP.
- **The saved dataset cannot be found:** check that the extracted folder contains `results/trace.csv`.
- **A CSV is rejected:** use MedNet's six required columns and valid class labels. The duration must cover every arrival. The dashboard accepts at most 50,000 packets and limits request size to 4 MB; use a comfortably smaller CSV.
- **The experiment is too large:** reduce duration or the traffic multipliers. The dashboard reports the setting that needs attention.

## What the product demonstrates

“We generated a repeatable synthetic packet dataset and compared three queue-scheduling policies on one finite-buffer network link. We measured delivery delay, buffer loss, and success against experiment-defined deadlines. The project studies scheduling tradeoffs; the traffic settings are not clinical requirements.”

See [README.md](README.md) for the model and command-line experiments, and [REFERENCES.md](REFERENCES.md) for the seven related papers and their precise connection to this work.
