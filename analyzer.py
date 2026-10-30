"""BTC market report. Python 3.12+, no third-party dependencies."""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def analyze(data):
    price, change, high, low = (
        float(data[key]) for key in
        ("lastPrice", "priceChangePercent", "highPrice", "lowPrice")
    )
    if not all(math.isfinite(x) for x in (price, change, high, low)):
        raise ValueError("行情包含无效数字")
    if min(price, high, low) <= 0 or high < low or not low <= price <= high:
        raise ValueError("行情价格范围无效")
    amplitude = (high - low) / low * 100
    # These are explicit heuristic thresholds, not calibrated probabilities.
    risk = "高波动" if amplitude >= 8 else "中等波动" if amplitude >= 4 else "较低波动"
    timestamp = datetime.fromtimestamp(int(data["closeTime"]) / 1000, timezone.utc)
    if abs((datetime.now(timezone.utc) - timestamp).total_seconds()) > 600:
        raise ValueError("行情时间超过10分钟，拒绝作为当前行情")
    return "\n".join([
        "# BTC/USDT 行情报告",
        f"数据时间（UTC）：{timestamp.isoformat()}",
        f"最新价格：{price:,.1f} USDT",
        f"过去24小时涨跌：{change:+.1f}%",
        f"过去24小时最高 / 最低：{high:,.1f} / {low:,.1f} USDT",
        f"过去24小时振幅（以最低价为基准）：{amplitude:.1f}%",
        f"波动提示：{risk}",
        "规则：振幅≥8%为高波动，≥4%为中等波动，其余为较低波动。",
        "这是历史行情的规则摘要，较低波动不等于低投资风险；不提供涨跌概率或自动交易。",
        "来源：Binance BTCUSDT 24小时行情。",
    ])


def main():
    parser = argparse.ArgumentParser(description="读取BTC行情并输出中文报告")
    parser.add_argument("--demo", action="store_true", help="离线演示，非真实行情")
    args = parser.parse_args()
    try:
        if args.demo:
            data = dict(lastPrice="101000", priceChangePercent="1",
                        highPrice="104000", lowPrice="100000",
                        closeTime=int(datetime.now(timezone.utc).timestamp() * 1000))
            print("【演示数据，非实时行情】")
        else:
            request = Request(
                "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",
                headers={"User-Agent": "btc-ai-analyzer/0.1"})
            with urlopen(request, timeout=20) as response:
                data = json.load(response)
        print(analyze(data))
    except Exception as error:
        print(f"获取或分析失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
