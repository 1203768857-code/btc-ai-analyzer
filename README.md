# BTC 行情助手：可运行的初版

Python 3.12+，仅使用标准库，无需 pip install，不需要 API 密钥。

规则摘要只描述历史振幅，不构成交易建议，也不会自动下单。

## 命令行

真实行情（需要网络能访问 Binance）：

```bash
python analyzer.py
```

离线演示（明确标为模拟数据）：

```bash
python analyzer.py --demo
```

真实行情失败会退出并返回非零状态，不会用模拟数据代替。

## 本地网页

在浏览器查看同一份报告。默认只监听本机。

真实行情：

```bash
python web.py
```

在浏览器打开 <http://127.0.0.1:8000>。

离线演示（不访问 Binance，页面会标明演示数据）：

```bash
python web.py --demo
```

`python -m web --demo` 效果相同。也可以设置环境变量 `BTC_DEMO=1`。服务以实时模式启动时，打开 <http://127.0.0.1:8000/?demo=1> 只让这一次请求使用演示数据。

页面大约每 30 秒自动刷新，也可以点「刷新报告」。

- `GET /`：中文报告页
- `GET /api/report`：JSON，包含价格、涨跌、最高最低、振幅、波动提示、完整 `text`，以及是否为 `demo`

实时请求失败时，页面显示中文错误，接口返回 HTTP 502。两种情况都不会改用演示数据。

可选参数：`--host`（默认 `127.0.0.1`）、`--port`（默认 `8000`）。

## 检查

离线：

```bash
python analyzer.py --demo
python -m unittest test_smoke.py
python web.py --demo
```

真实行情检查需要能访问 `https://api.binance.com`。系统若只有 `python3` 命令，把上面的 `python` 换成 `python3`。

## Codex 环境设置

- 仓库：1203768857-code/btc-ai-analyzer
- 分支：main
- 安装命令：无需安装依赖。
- 离线启动检查：`python analyzer.py --demo`；`python web.py --demo` 后打开 http://127.0.0.1:8000
- 真实行情检查：`python analyzer.py` 或 `python web.py`
- 网络要求：允许 HTTPS 访问 api.binance.com；部分地区可能限制访问。

## 当前功能与边界

输出 BTC/USDT 最新价、过去24小时涨跌、最高最低价和振幅，数字显示一位小数。
按振幅阈值给出波动提示；阈值是可解释的规则，不是回测验证的风险模型。
不会把显示精度当作预测准确度，不输出未经验证的涨跌概率。

命令行每次执行生成一份报告。网页在服务运行期间按请求生成报告。
尚未接入大模型、每日调度或推送。
不读取账户、不处理交易密钥、不自动下单。
