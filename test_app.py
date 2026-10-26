"""Dashboard integration checks. No browser, network, or extra packages required."""
import csv
import hashlib
import io
import json
import unittest
import zipfile
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import app


class FakeSocket:
    def __init__(self, request):
        self.request = io.BytesIO(request)
        self.response = bytearray()

    def makefile(self, *args, **kwargs):
        return self.request

    def sendall(self, data):
        self.response.extend(data)


def http_request(path, body=None, origin=None, content_type='application/json'):
    method = 'GET' if body is None else 'POST'
    content = b'' if body is None else json.dumps(body).encode()
    headers = [f'{method} {path} HTTP/1.0', 'Host: 127.0.0.1:8765']
    if body is not None:
        headers += [f'Content-Length: {len(content)}', f'Content-Type: {content_type}']
    if origin:
        headers.append('Origin: ' + origin)
    request = FakeSocket(('\r\n'.join(headers) + '\r\n\r\n').encode() + content)
    with patch.object(app.Handler, 'log_message'), redirect_stdout(io.StringIO()):
        app.Handler(request, ('127.0.0.1', 12345), SimpleNamespace())
    head, data = bytes(request.response).split(b'\r\n\r\n', 1)
    return int(head.split()[1]), head.decode(), data


class DashboardTests(unittest.TestCase):
    def setUp(self):
        app.RUNS.clear()

    def run_data(self, payload):
        with redirect_stdout(io.StringIO()):
            return app.build_run(payload)

    def test_saved_dataset_reproduces_reference_and_complete_zip(self):
        result = self.run_data({'mode': 'example'})
        files = app.RUNS[result['run_id']]
        for name in ('trace.csv', 'metrics.csv', 'outcomes.csv'):
            self.assertEqual(files[name], (app.ROOT / 'results' / name).read_bytes())
        self.assertEqual(result['config']['trace_sha256'], hashlib.sha256(files['trace.csv']).hexdigest())
        with zipfile.ZipFile(io.BytesIO(files['results.zip'])) as archive:
            self.assertEqual(set(archive.namelist()), set(app.FILES))
            self.assertIsNone(archive.testzip())
        self.assertEqual(len(result['metrics']), 42)
        self.assertTrue(all(len(rows) == 100 for rows in result['previews'].values()))

    def test_generation_and_csv_replay_have_identical_results(self):
        generated = self.run_data({'horizon': 1, 'seed': 23})
        files = app.RUNS[generated['run_id']]
        replay = self.run_data({'mode': 'replay', 'dataset_csv': files['trace.csv'].decode(), 'horizon': 1})
        self.assertEqual(generated['metrics'], replay['metrics'])
        self.assertEqual(files['outcomes.csv'], app.RUNS[replay['run_id']]['outcomes.csv'])
        self.assertEqual(replay['config']['input_origin'], 'csv_replay')
        self.assertIsNone(replay['config']['seed'])

    def test_empty_workload_has_valid_exports(self):
        result = self.run_data({'normal_load': 0, 'congested_load': 0})
        self.assertTrue(all(row['generated'] == 0 for row in result['metrics']))
        rows = list(csv.DictReader(io.StringIO(app.RUNS[result['run_id']]['trace.csv'].decode())))
        self.assertEqual(rows, [])

    def test_request_validation_rejects_unsafe_or_unbounded_inputs(self):
        for data in ([], {'horizon': float('inf')}, {'seed': 10**400}, {'seed': True}, {'seed': 1.5},
                     {'queue_capacity': -1}, {'link_mbps': 0}, {'mode': 'unknown'},
                     {'mode': 'replay'}, {'horizon': 120, 'normal_load': 10, 'congested_load': 10}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                app.validate_request(data)

    def test_bad_csv_and_horizon_are_reported(self):
        for payload in ({'mode':'replay','dataset_csv':'bad,header\n1,2\n'},
                        {'mode':'example','horizon':1}):
            with self.subTest(payload=payload):
                status, _, data = http_request('/api/run', payload)
                self.assertEqual(status, 400)
                self.assertIn('error', json.loads(data))

    def test_http_routes_generation_and_download(self):
        status, _, data = http_request('/api/run', {'horizon': 0.1})
        self.assertEqual(status, 200)
        run = json.loads(data)
        status, head, data = http_request('/download/' + run['run_id'] + '/results.zip')
        self.assertEqual(status, 200)
        self.assertIn('attachment; filename="mednet-results.zip"', head)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()), set(app.FILES))
        self.assertEqual(http_request('/download/missing/results.zip')[0], 404)
        self.assertEqual(http_request('/../../app.py')[0], 404)
        self.assertEqual(http_request('/api/info')[0], 200)
        self.assertEqual(http_request('/')[0], 200)

    def test_cross_origin_and_wrong_content_type_are_rejected(self):
        self.assertEqual(http_request('/api/run', {}, origin='https://example.com')[0], 403)
        self.assertEqual(http_request('/api/run', {}, content_type='text/plain')[0], 415)

    def test_busy_request_and_cache_eviction(self):
        app.RUN_LOCK.acquire()
        try:
            self.assertEqual(http_request('/api/run', {})[0], 409)
        finally:
            app.RUN_LOCK.release()
        first = None
        for _ in range(9):
            result = self.run_data({'normal_load': 0, 'congested_load': 0})
            first = first or result['run_id']
        self.assertEqual(len(app.RUNS), 8)
        self.assertNotIn(first, app.RUNS)


if __name__ == '__main__':
    unittest.main()
