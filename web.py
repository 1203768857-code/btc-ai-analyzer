"""Local browser UI for the BTC market report. Python 3.12+, stdlib only."""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from urllib.parse import parse_qs, urlparse

import analyzer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
TRUE_VALUES = {"1", "true", "yes", "on"}
REFRESH_SECONDS = 30

PAGE_STYLE = """
:root {
  color-scheme: light dark;
  --bg: #f4f1ea;
  --card: #fffdf8;
  --text: #1c1917;
  --muted: #57534e;
  --line: #e7e5e4;
  --demo-bg: #fef3c7;
  --demo-text: #92400e;
  --live-bg: #d1fae5;
  --live-text: #065f46;
  --error-bg: #fee2e2;
  --error-text: #991b1b;
  --up: #b91c1c;
  --down: #047857;
  --high: #b91c1c;
  --mid: #b45309;
  --low: #047857;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1917;
    --card: #292524;
    --text: #fafaf9;
    --muted: #a8a29e;
    --line: #44403c;
    --demo-bg: #451a03;
    --demo-text: #fcd34d;
    --live-bg: #022c22;
    --live-text: #6ee7b7;
    --error-bg: #450a0a;
    --error-text: #fca5a5;
    --up: #fca5a5;
    --down: #6ee7b7;
    --high: #fca5a5;
    --mid: #fcd34d;
    --low: #6ee7b7;
  }
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
    "Noto Sans SC", "Microsoft YaHei", sans-serif;
  line-height: 1.5;
}
main { max-width: 40rem; margin: 0 auto; padding: 2.5rem 1.25rem 3rem; }
article {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1.5rem;
}
.kicker { margin: 0; color: var(--muted); font-size: 0.85rem; letter-spacing: 0.04em; }
h1 { margin: 0.15rem 0 1rem; font-size: 1.7rem; }
.banner {
  margin: 0 0 1rem;
  padding: 0.7rem 0.9rem;
  border-radius: 10px;
  font-weight: 700;
}
.banner.demo { background: var(--demo-bg); color: var(--demo-text); }
.banner.live { background: var(--live-bg); color: var(--live-text); }
.banner.error { background: var(--error-bg); color: var(--error-text); }
.hint { margin: -0.4rem 0 1rem; color: var(--muted); }
.asof { margin: 0; color: var(--muted); font-size: 0.92rem; }
.price {
  margin: 0.2rem 0 1rem;
  font-size: 2.6rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}
.price small { font-size: 1rem; font-weight: 600; color: var(--muted); letter-spacing: 0; }
dl { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 0 0 1rem; }
dl div { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
dt { color: var(--muted); font-size: 0.85rem; }
dd { margin: 0.15rem 0 0; font-size: 1.15rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.up { color: var(--up); }
.down { color: var(--down); }
.flat { color: var(--text); }
.volatility { margin: 0 0 0.4rem; }
#volatility { font-size: 1.05rem; }
#volatility.high { color: var(--high); }
#volatility.mid { color: var(--mid); }
#volatility.low { color: var(--low); }
.rule, .disclaimer, .source { margin: 0.35rem 0; }
.disclaimer { font-weight: 600; }
pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--bg);
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 0.92rem;
  line-height: 1.55;
}
h2 { margin: 1.2rem 0 0.5rem; font-size: 1rem; }
.actions { display: flex; align-items: center; gap: 0.75rem; margin: 1rem 0 0; }
button {
  font: inherit;
  background: var(--text);
  color: var(--bg);
  border: 0;
  border-radius: 999px;
  padding: 0.45rem 0.95rem;
  cursor: pointer;
}
button:disabled { opacity: 0.6; cursor: wait; }
button:focus-visible { outline: 2px solid var(--text); outline-offset: 3px; }
#refresh-note { color: var(--muted); font-size: 0.9rem; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
@media (max-width: 560px) {
  main { padding: 1.25rem 0.9rem 2rem; }
  dl { grid-template-columns: 1fr; }
  .price { font-size: 2.1rem; }
}
"""

PAGE_SCRIPT = """
"use strict";
const note = document.getElementById("refresh-note");
const button = document.getElementById("refresh");

function apply(data) {
  const status = document.getElementById("status");
  const error = document.getElementById("error");
  const hint = document.getElementById("hint");
  const report = document.getElementById("report");
  const transcript = document.getElementById("transcript");
  if (!data.ok) {
    status.hidden = true;
    report.hidden = true;
    transcript.hidden = true;
    error.hidden = false;
    hint.hidden = false;
    error.textContent = data.error || "获取或分析失败";
    return;
  }
  error.hidden = true;
  hint.hidden = true;
  status.hidden = false;
  report.hidden = false;
  transcript.hidden = false;
  document.title = data.title;
  status.textContent = data.banner;
  status.className = "banner " + (data.demo ? "demo" : "live");
  document.getElementById("price").textContent = data.price_display;
  const change = document.getElementById("change");
  change.textContent = data.change_display;
  const delta = Number(data.change_percent);
  change.className = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  document.getElementById("high").textContent = data.high_display;
  document.getElementById("low").textContent = data.low_display;
  document.getElementById("amplitude").textContent = data.amplitude_display;
  document.getElementById("timestamp").textContent = data.timestamp;
  const volatility = document.getElementById("volatility");
  volatility.textContent = data.volatility;
  volatility.className = data.volatility_class;
  document.getElementById("rule").textContent = data.rule;
  document.getElementById("disclaimer").textContent = data.disclaimer;
  document.getElementById("source").textContent = "来源：" + data.source + "。";
  document.getElementById("text").textContent = data.text;
}

async function refresh(manual) {
  button.disabled = true;
  try {
    const response = await fetch("/api/report" + location.search, {cache: "no-store"});
    const data = await response.json();
    apply(data);
    if (manual) note.textContent = data.ok ? "已刷新" : "刷新失败";
  } catch (err) {
    apply({ok: false, error: "获取或分析失败：无法连接本地服务"});
    if (manual) note.textContent = "刷新失败";
  } finally {
    button.disabled = false;
  }
}

button.addEventListener("click", function () { refresh(true); });
setInterval(function () { refresh(false); }, __REFRESH_MS__);
"""


def resolve_demo(cli_flag, environ=None):
    if cli_flag:
        return True
    env = os.environ if environ is None else environ
    return env.get("BTC_DEMO", "").strip().lower() in TRUE_VALUES


def query_requests_demo(query):
    return any(item.strip().lower() in TRUE_VALUES for item in query.get("demo", []))


def report_response(demo):
    try:
        report = analyzer.build_report(bool(demo))
    except Exception as error:
        return 502, {
            "ok": False,
            "demo": bool(demo),
            "error": analyzer.failure_message(error),
        }
    demo_flag = bool(report["demo"])
    vol_class = {"高波动": "high", "中等波动": "mid", "较低波动": "low"}.get(
        report["volatility"], "mid")
    body = {
        "ok": True,
        "banner": "演示数据，非实时行情" if demo_flag else "实时数据：Binance BTCUSDT 24小时行情",
        "title": ("【演示】" if demo_flag else "") + "BTC/USDT 行情报告",
        "volatility_class": vol_class,
    }
    body.update(report)
    return 200, body


def _field(report, key):
    if not report:
        return "—"
    return escape(str(report[key]))


def render_page(report=None, error=None):
    demo = bool(report and report.get("demo"))
    title = report["title"] if report else "BTC/USDT 行情报告"
    if error:
        status = '<p id="status" class="banner" role="status" hidden></p>'
        error_html = f'<p id="error" class="banner error" role="alert">{escape(error)}</p>'
        hint = (
            '<p id="hint" class="hint">这次没有改用演示数据。'
            "离线查看界面可用 <code>python web.py --demo</code>。</p>"
        )
        report_hidden = " hidden"
        change_class = "flat"
    else:
        status = (
            f'<p id="status" class="banner {"demo" if demo else "live"}" role="status">'
            f"{escape(report['banner'])}</p>"
        )
        error_html = '<p id="error" class="banner error" role="alert" hidden></p>'
        hint = (
            '<p id="hint" class="hint" hidden>这次没有改用演示数据。'
            "离线查看界面可用 <code>python web.py --demo</code>。</p>"
        )
        report_hidden = ""
        delta = report["change_percent"]
        change_class = "up" if delta > 0 else "down" if delta < 0 else "flat"
    script = PAGE_SCRIPT.replace("__REFRESH_MS__", str(REFRESH_SECONDS * 1000))
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{PAGE_STYLE}</style>
</head>
<body>
<main>
<article>
<p class="kicker">BTC/USDT · 24小时</p>
<h1>行情报告</h1>
{status}
{error_html}
{hint}
<section id="report"{report_hidden}>
<p class="asof">数据时间（UTC） <time id="timestamp">{_field(report, "timestamp")}</time></p>
<p class="price"><span id="price">{_field(report, "price_display")}</span> <small>USDT</small></p>
<dl>
<div><dt>过去24小时涨跌</dt><dd id="change" class="{change_class}">{_field(report, "change_display")}</dd></div>
<div><dt>过去24小时振幅（以最低价为基准）</dt><dd id="amplitude">{_field(report, "amplitude_display")}</dd></div>
<div><dt>最高</dt><dd id="high">{_field(report, "high_display")}</dd></div>
<div><dt>最低</dt><dd id="low">{_field(report, "low_display")}</dd></div>
</dl>
<p class="volatility">波动提示 <strong id="volatility" class="{escape(report["volatility_class"]) if report else "mid"}">{_field(report, "volatility")}</strong></p>
<p id="rule" class="rule">{_field(report, "rule")}</p>
<p id="source" class="source">{("来源：" + escape(report["source"]) + "。") if report else "—"}</p>
</section>
<p id="disclaimer" class="disclaimer">{_field(report, "disclaimer") if report else escape(analyzer.DISCLAIMER)}</p>
<section id="transcript"{report_hidden}>
<h2>与命令行相同的报告</h2>
<pre id="text">{_field(report, "text")}</pre>
</section>
<p class="actions"><button type="button" id="refresh">刷新报告</button><span id="refresh-note"></span></p>
<noscript><p class="hint">未启用脚本时不会自动刷新，请重新打开页面以更新报告。</p></noscript>
</article>
</main>
<script>{script}</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        demo = bool(getattr(self.server, "demo", False)) or query_requests_demo(parse_qs(parsed.query))
        if path == "/":
            self._page(demo)
            return
        if path == "/api/report":
            self._api(demo)
            return
        self._send(404, "未找到该页面。\n", "text/plain; charset=utf-8")

    def _page(self, demo):
        _, body = report_response(demo)
        if body["ok"]:
            self._send(200, render_page(body), "text/html; charset=utf-8")
            return
        self._send(200, render_page(error=body["error"]), "text/html; charset=utf-8")

    def _api(self, demo):
        status, body = report_response(demo)
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self._send(status, encoded, "application/json; charset=utf-8")

    def _send(self, status, body, content_type):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


class ReportServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, request_handler, demo=False):
        super().__init__(server_address, request_handler)
        self.demo = demo


def main(argv=None):
    parser = argparse.ArgumentParser(description="在本地浏览器查看 BTC 行情报告")
    parser.add_argument("--demo", action="store_true", help="离线演示，非真实行情")
    parser.add_argument("--host", default=DEFAULT_HOST, help="默认只监听 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    demo = resolve_demo(args.demo)
    try:
        server = ReportServer((args.host, args.port), Handler, demo=demo)
    except OSError as error:
        print(f"无法启动网页服务：{error}", file=sys.stderr)
        return 1
    host, port = server.server_address[:2]
    shown = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    print(f"在浏览器打开 http://{shown}:{port}/", flush=True)
    if demo:
        print("当前为演示模式：页面显示的是模拟数据，不是实时行情。", flush=True)
    else:
        print("当前为实时模式：每次请求都会访问 Binance。失败时只显示错误，不会改用演示数据。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
