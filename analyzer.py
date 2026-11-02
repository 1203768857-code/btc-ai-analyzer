"""BTC market report. Python 3.12+, no third-party dependencies.

The command line and the local web UI both call build_report().
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
USER_AGENT = "btc-ai-analyzer/0.1"
SOURCE = "Binance BTCUSDT 24小时行情"
HIGH_AMPLITUDE = 8
MID_AMPLITUDE = 4
MAX_AGE_SECONDS = 600
RULE_TEXT = (
    f"规则：振幅≥{HIGH_AMPLITUDE}%为高波动，≥{MID_AMPLITUDE}%为中等波动，其余为较低波动。"
)
DISCLAIMER = "这是历史行情的规则摘要，较低波动不等于低投资风险；不提供涨跌概率或自动交易。"
DEMO_BANNER = "【演示数据，非实时行情】"
TICKER_FIELDS = ("lastPrice", "priceChangePercent", "highPrice", "lowPrice", "closeTime")


def demo_ticker(now=None):
    moment = now or datetime.now(timezone.utc)
    return {
        "lastPrice": "101000",
        "priceChangePercent": "1",
        "highPrice": "104000",
        "lowPrice": "100000",
        "closeTime": int(moment.timestamp() * 1000),
    }


def _http_error_message(error):
    if getattr(error, "code", None) == 451:
        return "Binance 拒绝从当前网络地区提供行情（HTTP 451）"
    detail = ""
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        payload = None
    if isinstance(payload, dict) and payload.get("msg"):
        detail = str(payload["msg"]).strip().replace("\n", " ")
        if len(detail) > 180:
            detail = detail[:180] + "…"
    if detail:
        return f"Binance 返回 HTTP {error.code}：{detail}"
    return f"Binance 返回 HTTP {error.code}"


def fetch_ticker(timeout=20):
    request = Request(BINANCE_TICKER_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        raise ValueError(_http_error_message(error)) from error
    except TimeoutError as error:
        raise ValueError("连接 Binance 超时") from error
    except URLError as error:
        raise ValueError(f"无法连接 Binance（{error.reason}）") from error


def volatility_label(amplitude):
    # These are explicit heuristic thresholds, not calibrated probabilities.
    if amplitude >= HIGH_AMPLITUDE:
        return "高波动"
    if amplitude >= MID_AMPLITUDE:
        return "中等波动"
    return "较低波动"


def report_fields(data, *, now=None):
    if not isinstance(data, dict):
        raise ValueError("行情响应格式无效")
    if "msg" in data and any(key not in data for key in TICKER_FIELDS):
        raise ValueError(f"Binance 返回错误：{data['msg']}")
    missing = [key for key in TICKER_FIELDS if key not in data]
    if missing:
        raise ValueError("行情缺少字段：" + "、".join(missing))
    price, change, high, low = (
        float(data[key]) for key in
        ("lastPrice", "priceChangePercent", "highPrice", "lowPrice")
    )
    if not all(math.isfinite(x) for x in (price, change, high, low)):
        raise ValueError("行情包含无效数字")
    if min(price, high, low) <= 0 or high < low or not low <= price <= high:
        raise ValueError("行情价格范围无效")
    amplitude = (high - low) / low * 100
    timestamp = datetime.fromtimestamp(int(data["closeTime"]) / 1000, timezone.utc)
    current = now or datetime.now(timezone.utc)
    if abs((current - timestamp).total_seconds()) > MAX_AGE_SECONDS:
        raise ValueError("行情时间超过10分钟，拒绝作为当前行情")
    return {
        "symbol": "BTCUSDT",
        "timestamp": timestamp.isoformat(),
        "price": price,
        "change_percent": change,
        "high": high,
        "low": low,
        "amplitude_percent": amplitude,
        "volatility": volatility_label(amplitude),
        "rule": RULE_TEXT,
        "disclaimer": DISCLAIMER,
        "source": SOURCE,
    }


def display_fields(fields):
    return {
        "price_display": f"{fields['price']:,.1f}",
        "change_display": f"{fields['change_percent']:+.1f}%",
        "high_display": f"{fields['high']:,.1f}",
        "low_display": f"{fields['low']:,.1f}",
        "amplitude_display": f"{fields['amplitude_percent']:.1f}%",
    }


def format_report(fields):
    shown = display_fields(fields)
    return "\n".join([
        "# BTC/USDT 行情报告",
        f"数据时间（UTC）：{fields['timestamp']}",
        f"最新价格：{shown['price_display']} USDT",
        f"过去24小时涨跌：{shown['change_display']}",
        f"过去24小时最高 / 最低：{shown['high_display']} / {shown['low_display']} USDT",
        f"过去24小时振幅（以最低价为基准）：{shown['amplitude_display']}",
        f"波动提示：{fields['volatility']}",
        fields["rule"],
        fields["disclaimer"],
        f"来源：{fields['source']}。",
    ])


def analyze(data):
    return format_report(report_fields(data))


def build_report(demo, *, now=None, timeout=20):
    data = demo_ticker(now) if demo else fetch_ticker(timeout=timeout)
    fields = report_fields(data, now=now)
    text = format_report(fields)
    if demo:
        text = f"{DEMO_BANNER}\n{text}"
    return {"demo": bool(demo), "text": text, **fields, **display_fields(fields)}


def failure_message(error):
    return f"获取或分析失败：{error}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="读取BTC行情并输出中文报告")
    parser.add_argument("--demo", action="store_true", help="离线演示，非真实行情")
    args = parser.parse_args(argv)
    try:
        print(build_report(args.demo)["text"])
    except Exception as error:
        print(failure_message(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
