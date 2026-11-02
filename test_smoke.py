"""Offline smoke tests for the report and the local web UI."""
import io
import json
import os
import selectors
import subprocess
import sys
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import analyzer
import web

ROOT = os.path.dirname(os.path.abspath(__file__))


@contextmanager
def patched_fetch(func):
    original = analyzer.fetch_ticker
    analyzer.fetch_ticker = func
    try:
        yield
    finally:
        analyzer.fetch_ticker = original


def fail_fetch(timeout=20):
    raise URLError("offline")


class ReportTests(unittest.TestCase):
    def test_demo_text_matches_cli_wording(self):
        now = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
        report = analyzer.build_report(True, now=now)
        expected = "\n".join([
            "【演示数据，非实时行情】",
            "# BTC/USDT 行情报告",
            "数据时间（UTC）：2026-11-02T08:00:00+00:00",
            "最新价格：101,000.0 USDT",
            "过去24小时涨跌：+1.0%",
            "过去24小时最高 / 最低：104,000.0 / 100,000.0 USDT",
            "过去24小时振幅（以最低价为基准）：4.0%",
            "波动提示：中等波动",
            "规则：振幅≥8%为高波动，≥4%为中等波动，其余为较低波动。",
            "这是历史行情的规则摘要，较低波动不等于低投资风险；不提供涨跌概率或自动交易。",
            "来源：Binance BTCUSDT 24小时行情。",
        ])
        self.assertEqual(report["text"], expected)
        self.assertTrue(report["demo"])
        self.assertEqual(report["volatility"], "中等波动")

    def test_analyze_omits_demo_banner(self):
        text = analyzer.analyze(analyzer.demo_ticker())
        self.assertTrue(text.startswith("# BTC/USDT 行情报告"))
        self.assertNotIn("演示", text)

    def test_volatility_boundaries(self):
        now = datetime.now(timezone.utc)
        close = int(now.timestamp() * 1000)

        def label(low, high, price):
            return analyzer.report_fields({
                "lastPrice": str(price),
                "priceChangePercent": "0",
                "highPrice": str(high),
                "lowPrice": str(low),
                "closeTime": close,
            }, now=now)["volatility"]

        self.assertEqual(label(100, 108, 104), "高波动")
        self.assertEqual(label(100, 107.9, 104), "中等波动")
        self.assertEqual(label(100, 104, 102), "中等波动")
        self.assertEqual(label(100, 103.9, 102), "较低波动")

    def test_rejects_stale_invalid_and_incomplete_tickers(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=11)
        with self.assertRaises(ValueError):
            analyzer.report_fields(analyzer.demo_ticker(old))
        now = datetime.now(timezone.utc)
        below = analyzer.demo_ticker(now)
        below["lastPrice"] = "90000"
        with self.assertRaises(ValueError):
            analyzer.report_fields(below, now=now)
        nan_price = analyzer.demo_ticker(now)
        nan_price["lastPrice"] = "nan"
        with self.assertRaises(ValueError):
            analyzer.report_fields(nan_price, now=now)
        missing = analyzer.demo_ticker(now)
        del missing["lowPrice"]
        with self.assertRaises(ValueError) as caught:
            analyzer.report_fields(missing, now=now)
        self.assertIn("lowPrice", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            analyzer.report_fields({"code": -1121, "msg": "Invalid symbol"}, now=now)
        self.assertIn("Invalid symbol", str(caught.exception))

    def test_http_errors_are_chinese(self):
        class Response:
            def __init__(self, code, body):
                self.code = code
                self._body = body

            def read(self):
                return self._body

        restricted = analyzer._http_error_message(Response(451, b'{"msg":"restricted"}'))
        self.assertEqual(restricted, "Binance 拒绝从当前网络地区提供行情（HTTP 451）")
        invalid = analyzer._http_error_message(Response(400, b'{"msg":"Invalid symbol"}'))
        self.assertEqual(invalid, "Binance 返回 HTTP 400：Invalid symbol")

    def test_live_report_uses_fetch_and_skips_banner(self):
        sample = analyzer.demo_ticker()

        def fake_fetch(timeout=20):
            return sample

        with patched_fetch(fake_fetch):
            report = analyzer.build_report(False)
        self.assertFalse(report["demo"])
        self.assertNotIn("演示", report["text"])
        self.assertIn("101,000.0", report["text"])

    def test_cli_demo_command(self):
        result = subprocess.run(
            [sys.executable, "analyzer.py", "--demo"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("【演示数据，非实时行情】", result.stdout)
        self.assertIn("# BTC/USDT 行情报告", result.stdout)
        self.assertIn("不提供涨跌概率或自动交易", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_cli_live_failure_does_not_print_a_report(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patched_fetch(fail_fetch):
            real_out, real_err = sys.stdout, sys.stderr
            try:
                sys.stdout, sys.stderr = stdout, stderr
                code = analyzer.main([])
            finally:
                sys.stdout, sys.stderr = real_out, real_err
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("获取或分析失败", stderr.getvalue())
        self.assertNotIn("101,000.0", stderr.getvalue())


class WebTests(unittest.TestCase):
    def setUp(self):
        self.server = web.ReportServer(("127.0.0.1", 0), web.Handler, demo=False)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_demo_page_and_api(self):
        calls = []

        def tracking_fetch(timeout=20):
            calls.append(timeout)
            raise AssertionError("demo request must not hit Binance")

        with patched_fetch(tracking_fetch):
            with urlopen(self.base + "/?demo=1", timeout=5) as response:
                html = response.read().decode()
                self.assertEqual(response.status, 200)
                self.assertIn("text/html", response.headers["Content-Type"])
            with urlopen(self.base + "/api/report?demo=1", timeout=5) as response:
                body = json.load(response)
        self.assertEqual(calls, [])
        self.assertIn("演示数据，非实时行情", html)
        self.assertIn("101,000.0", html)
        self.assertIn("不提供涨跌概率或自动交易", html)
        self.assertIn("刷新报告", html)
        self.assertTrue(body["ok"])
        self.assertTrue(body["demo"])
        self.assertEqual(body["volatility"], "中等波动")
        self.assertIn("【演示数据，非实时行情】", body["text"])
        self.assertIn("price", body)
        self.assertIn("amplitude_percent", body)

    def test_live_failure_is_explicit(self):
        with patched_fetch(fail_fetch):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base + "/api/report", timeout=5)
            self.assertEqual(caught.exception.code, 502)
            body = json.load(caught.exception)
            with urlopen(self.base + "/", timeout=5) as response:
                html = response.read().decode()
                self.assertEqual(response.status, 200)
        self.assertFalse(body["ok"])
        self.assertFalse(body["demo"])
        self.assertIn("获取或分析失败", body["error"])
        self.assertNotIn("101000", json.dumps(body))
        self.assertNotIn("price", body)
        self.assertIn("获取或分析失败", html)
        self.assertIn("这次没有改用演示数据", html)
        self.assertNotIn("101,000.0", html)
        self.assertNotIn("实时数据：Binance", html)

    def test_demo_flag_must_be_explicit(self):
        with patched_fetch(fail_fetch):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base + "/api/report?demo=0", timeout=5)
        body = json.load(caught.exception)
        self.assertFalse(body["ok"])
        self.assertFalse(body["demo"])

    def test_mocked_live_page_is_labeled_live(self):
        def fake_fetch(timeout=20):
            return analyzer.demo_ticker()

        with patched_fetch(fake_fetch):
            with urlopen(self.base + "/", timeout=5) as response:
                html = response.read().decode()
        self.assertIn("实时数据：Binance BTCUSDT 24小时行情", html)
        self.assertNotIn("演示数据，非实时行情", html)
        self.assertNotIn("【演示数据，非实时行情】", html)
        self.assertIn("101,000.0", html)

    def test_unknown_path(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + "/missing", timeout=5)
        self.assertEqual(caught.exception.code, 404)
        self.assertIn("未找到", caught.exception.read().decode())

    def test_server_demo_mode_ignores_network(self):
        calls = []

        def tracking_fetch(timeout=20):
            calls.append(1)
            raise AssertionError("server demo mode must not fetch")

        server = web.ReportServer(("127.0.0.1", 0), web.Handler, demo=True)
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            with patched_fetch(tracking_fetch):
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(base + "/api/report", timeout=5) as response:
                    body = json.load(response)
                with urlopen(base + "/", timeout=5) as response:
                    html = response.read().decode()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(calls, [])
        self.assertTrue(body["demo"])
        self.assertIn("演示数据，非实时行情", html)

    def test_error_page_escapes_html(self):
        html = web.render_page(error="获取或分析失败：<script>alert(1)</script>")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_module_demo_command(self):
        env = os.environ.copy()
        env["BTC_DEMO"] = ""
        proc = subprocess.Popen(
            [sys.executable, "-m", "web", "--demo", "--port", "0"],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        selector = selectors.DefaultSelector()
        try:
            selector.register(proc.stdout, selectors.EVENT_READ)
            if not selector.select(5):
                proc.kill()
                self.fail(proc.stderr.read())
            line = proc.stdout.readline()
            self.assertIn("http://127.0.0.1:", line)
            url = line.strip().split()[-1]
            with urlopen(url + "api/report", timeout=5) as response:
                body = json.load(response)
            with urlopen(url, timeout=5) as response:
                html = response.read().decode()
        finally:
            selector.close()
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()
        self.assertTrue(body["ok"])
        self.assertTrue(body["demo"])
        self.assertIn("演示数据，非实时行情", html)
        self.assertIn("不提供涨跌概率或自动交易", html)

    def test_resolve_demo_env(self):
        self.assertTrue(web.resolve_demo(False, {"BTC_DEMO": "1"}))
        self.assertFalse(web.resolve_demo(False, {"BTC_DEMO": "0"}))
        self.assertTrue(web.resolve_demo(True, {}))


if __name__ == "__main__":
    unittest.main()
