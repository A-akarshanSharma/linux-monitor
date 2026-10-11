"""Run with Python's unittest; no GUI/display or backend dependencies needed."""

import importlib.util
import io
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

spec = importlib.util.spec_from_file_location("native", Path(__file__).parents[1] / "native.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeTests(unittest.TestCase):
    def test_irregular_chart_times_and_missing_rates(self):
        points = [
            {"collected_at": "2026-10-07T10:00:00Z", "rate": 0},
            {"collected_at": "2026-10-07T10:00:10Z", "rate": None},
            {"collected_at": "2026-10-07T10:01:00Z", "rate": 100},
        ]
        self.assertEqual(
            native.chart_segments(points, "rate", 120, 100, 100), [[52, 112], [172, 12]]
        )
        self.assertEqual(native.chart_segments([], "rate", 120, 100, 100), [])

    def test_one_endpoint_failure_does_not_discard_other_readings(self):
        class Opener:
            def open(self, url, timeout):
                if url.endswith("/metrics/current"):
                    raise URLError("unreachable")
                return io.BytesIO(json.dumps({"source": url}).encode())

        data, errors = native.collect("http://127.0.0.1:8765/", Opener())
        self.assertEqual(set(errors), {"current"})
        self.assertEqual(set(data), set(native.ENDPOINTS) - {"current"})

    def test_pause_during_request_drops_result_and_resume_fetches_fresh_data(self):
        entered, finish = threading.Event(), threading.Event()
        calls = []

        def collect(*args):
            calls.append(len(calls) + 1)
            entered.set()
            self.assertTrue(finish.wait(2))
            return ({"reading": len(calls)}, {})

        poller = native.Poller("http://localhost", interval=100)
        with patch.object(native, "collect", collect):
            poller.thread.start()
            try:
                self.assertTrue(entered.wait(2))
                poller.set_visible(False)
                self.assertTrue(poller.results.empty())
                # Return before the slow, old request completes. Its result must
                # still be discarded even though the window is now visible.
                poller.set_visible(True)
                finish.set()
                self.assertEqual(poller.results.get(timeout=2), ({"reading": 2}, {}))
                self.assertEqual(calls, [1, 2])
            finally:
                poller.stop()
                finish.set()
                poller.thread.join(2)
        self.assertFalse(poller.thread.is_alive())

    def test_pending_results_are_bounded_even_without_gui_consumption(self):
        poller = native.Poller("http://localhost", interval=0.001)
        count = 0
        completed = threading.Event()

        def collect(*args):
            nonlocal count
            count += 1
            if count == 20:
                completed.set()
            return ({"reading": count}, {})

        with patch.object(native, "collect", collect):
            poller.thread.start()
            try:
                self.assertTrue(completed.wait(2))
            finally:
                poller.stop()
                poller.thread.join(2)
        self.assertEqual(poller.results.qsize(), 1)


if __name__ == "__main__":
    unittest.main()
