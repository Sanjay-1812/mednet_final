"""MedNet local dashboard. Python standard library only; bind to loopback."""
import argparse
import csv
import hashlib
import io
import json
import math
import tempfile
import threading
import webbrowser
import zipfile
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import mednet

ROOT = Path(__file__).resolve().parent
DEFAULTS = dict(seed=42, horizon=20.0, link_mbps=1.0, queue_capacity=40,
                normal_load=1.0, congested_load=2.4, urgency_weight=3.0,
                critical_boost=0.75, congestion_threshold=0.75)
LIMITS = dict(seed=(0, 2147483647), horizon=(0.1, 120), link_mbps=(0.01, 100),
              queue_capacity=(0, 200), normal_load=(0, 10), congested_load=(0, 10),
              urgency_weight=(0, 10), critical_boost=(0, 10), congestion_threshold=(0, 0.99))
MAX_PACKETS = 50000
MAX_BODY = 4 * 1024 * 1024
FILES = ('trace.csv', 'metrics.csv', 'outcomes.csv', 'config.json')
RUNS = OrderedDict()
RUN_LOCK = threading.Lock()


def validate_request(payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected an experiment object.')
    mode = payload.get('mode', 'generate')
    if mode not in ('generate', 'example', 'replay'):
        raise ValueError('Choose generated traffic, the saved dataset, or CSV replay.')
    params = {}
    for key, default in DEFAULTS.items():
        value = payload.get(key, default)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or isinstance(value, float) and not math.isfinite(value)):
            raise ValueError(f'{key}: enter a finite number.')
        low, high = LIMITS[key]
        if not low <= value <= high:
            raise ValueError(f'{key}: use a value between {low} and {high}.')
        if key in ('seed', 'queue_capacity'):
            if int(value) != value:
                raise ValueError(f'{key}: enter a whole number.')
            value = int(value)
        params[key] = value
    if mode == 'generate':
        expected = params['horizon'] * sum(c.rate_per_s for c in mednet.CLASSES.values()) * (
            params['normal_load'] + params['congested_load'])
        if expected > MAX_PACKETS * 0.9:
            raise ValueError('This experiment is too large for the dashboard. Reduce duration or load.')
    if mode == 'replay':
        dataset = payload.get('dataset_csv')
        if not isinstance(dataset, str) or not dataset.strip():
            raise ValueError('Select a synthetic trace CSV to replay.')
    return mode, params


def build_run(payload):
    """Use the same core/export path as the CLI, then retain a bounded download cache."""
    mode, params = validate_request(payload)
    work = ROOT / '.work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='run-', dir=work) as directory:
        directory = Path(directory)
        dataset = None
        if mode == 'example':
            dataset = ROOT / 'results' / 'trace.csv'
        elif mode == 'replay':
            dataset = directory / 'uploaded.csv'
            dataset.write_text(payload['dataset_csv'], encoding='utf-8')
        if dataset:
            loaded = mednet.read_dataset(dataset, params['horizon'])
            if sum(map(len, loaded.values())) > MAX_PACKETS:
                raise ValueError(f'The dashboard accepts at most {MAX_PACKETS:,} packets.')
        else:
            # Check the actual seeded count before allowing the core experiment.
            count = sum(len(mednet.generate_trace(params['horizon'], params['seed'], params[k]))
                        for k in ('normal_load', 'congested_load'))
            if count > MAX_PACKETS:
                raise ValueError('Too many packets. Reduce duration or load.')
        output = directory / 'results'
        mednet.run_experiment(SimpleNamespace(**params, input_dataset=dataset, output=output))
        config = json.loads((output / 'config.json').read_text(encoding='utf-8'))
        # Downloads describe provenance without a machine-specific temporary path.
        config['input_dataset'] = ('bundled results/trace.csv' if mode == 'example'
                                   else 'uploaded synthetic trace.csv' if mode == 'replay' else None)
        config['dashboard_version'] = '1.0'
        config['trace_sha256'] = hashlib.sha256((output / 'trace.csv').read_bytes()).hexdigest()
        (output / 'config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
        with (output / 'metrics.csv').open(newline='', encoding='utf-8') as handle:
            metrics = list(csv.DictReader(handle))
        for row in metrics:
            for key, value in row.items():
                if key not in ('scenario', 'policy', 'traffic_class'):
                    row[key] = float(value)
        previews = {}
        with (output / 'outcomes.csv').open(newline='', encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                key = row['scenario'] + '/' + row['policy']
                previews.setdefault(key, []).append(row)
        for key, rows in previews.items():
            rows.sort(key=lambda row: (float(row['arrival_s']), int(row['packet_id'])))
            previews[key] = rows[:100]
        files = {name: (output / name).read_bytes() for name in FILES}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        files['results.zip'] = stream.getvalue()
    run_id = uuid4().hex
    RUNS[run_id] = files
    while len(RUNS) > 8:
        RUNS.popitem(last=False)
    return dict(run_id=run_id, config=config, metrics=metrics, previews=previews,
                parameters=params, mode=mode)


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, data, mime, status=200, filename=None):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, data, status=200):
        self.send_bytes(json.dumps(data, allow_nan=False).encode(), 'application/json; charset=utf-8', status)

    def do_GET(self):
        path = urlsplit(self.path).path
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in assets:
            name, mime = assets[path]
            return self.send_bytes((ROOT / 'static' / name).read_bytes(), mime)
        if path == '/api/info':
            return self.json_response(dict(defaults=DEFAULTS, limits=LIMITS,
                classes={k: vars(v) for k, v in mednet.CLASSES.items()}))
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'download':
            run_id, name = parts[1:]
            with RUN_LOCK:
                data = RUNS.get(run_id, {}).get(name)
            if data is None:
                return self.json_response({'error': 'Download expired. Run the experiment again.'}, 404)
            mime = 'application/zip' if name.endswith('.zip') else 'application/json' if name.endswith('.json') else 'text/csv; charset=utf-8'
            return self.send_bytes(data, mime, filename='mednet-results.zip' if name == 'results.zip' else name)
        return self.json_response({'error': 'Not found.'}, 404)

    def do_POST(self):
        if urlsplit(self.path).path != '/api/run':
            return self.json_response({'error': 'Not found.'}, 404)
        # Browsers may only submit from this loopback page; no cross-origin API.
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            return self.json_response({'error': 'Open the dashboard at its local address.'}, 403)
        if self.headers.get_content_type() != 'application/json':
            return self.json_response({'error': 'Send application/json.'}, 415)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('Choose a CSV smaller than 4 MB.')
            payload = json.loads(self.rfile.read(length))
            if not RUN_LOCK.acquire(blocking=False):
                return self.json_response({'error': 'An experiment is running. Try again shortly.'}, 409)
            try:
                result = build_run(payload)
            finally:
                RUN_LOCK.release()
            return self.json_response(result)
        except (ValueError, TypeError, OverflowError, csv.Error, UnicodeError) as error:
            return self.json_response({'error': str(error)}, 400)
        except OSError as error:
            print(f'File error: {error}')
            return self.json_response({'error': 'Could not read the dataset or write temporary output. Check folder permissions.'}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as error:
        parser.exit(1, f'Cannot start MedNet: {error}\nTry python app.py --port 8766\n')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'MedNet is ready: {url}\nKeep this terminal open. Press Ctrl+C to stop.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nMedNet stopped.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
