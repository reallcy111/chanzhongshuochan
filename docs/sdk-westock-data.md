# westock-data SDK 标准调用规范

> 来源：Context7 / 实际 npx westock-data-skillhub@1.0.3 实测（2026-06-24 验证）
> 用途：缠中说禅 skill 数据获取层 — 1 级数据源（跨 A 股 + 港股 + 美股 + 指数 + ETF）
> 文档同步：westock 包 1.0.3 实测字段（与官方文档可能存在差异）

## 简介

**westock-data** = Node.js CLI 工具（`npx -y westock-data-skillhub@1.0.3`），底层是腾讯自选股 / 腾讯财经接口。

**结构性优势**：
- 完全免费 + 免 Token（用户已装 Node.js 即可用）
- 跨 A 股 + 港股 + 美股 + 指数 + 板块 + ETF
- 30+ 命令：kline / minute / finance / profile / chip / technical / search / hot / board / calendar / ipo / shareholder / dividend / exdiv / reserve / suspension / etf / asfund / hkfund / usfund
- 稳定性比 akshare 港/美股高（akshare 海外节点易断）

**已知限制**：
- 首次调用 `npx -y` 自动下载 npm 包（需外网 + 4-30s）
- 腾讯接口无 SLA，可能间歇性断
- westock 没有 `quote` 命令（**实测发现** — 官方文档列出但 1.0.3 未实现）
- 返回 Markdown 表格格式（需自写解析）
- `volume` 在 A 股是"手"（需 ×100），港/美股是"股"（不需转换）
- **数据可能滞后 1-2 周**（腾讯自选股 API 缓存所致；v0.6.2 router 已在 staleness > 3 天时自动降级到 akshare/qveris/tavily）

---

## 环境要求

```bash
node >= 18.0.0（实测 24.14.0 OK）
npx 11+（随 Node 18+ 自带）
```

无需 Token / 注册 / 付费。

## 安装

不需要安装。直接通过 npx 调用：

```bash
npx -y westock-data-skillhub@1.0.3 <command> <args>
```

首次调用会自动下载到 `~/.npm/_npx/`。

---

## 股票代码格式（实测）

| 市场 | 格式 | 示例 |
|---|---|---|
| 沪市 / 科创板 | `sh` + 6位 | `sh600519`（茅台）、`sh688981`（中芯国际） |
| 深市 | `sz` + 6位 | `sz000001`（平安银行） |
| 北交所 | `bj` + 6位 | `bj430047` |
| 港股 | `hk` + 5位 | `hk00700`（腾讯）、`hk03690`（美团） |
| 美股 | `us` + 代码 | `usAAPL`（苹果）、`usTSLA`（特斯拉）、`usBABA` |
| 板块 | `pt` + ID | `pt01801081`（半导体） |

---

## 可用命令清单（实测 1.0.3）

| 命令 | 用途 | 支持市场 | 返回格式 |
|---|---|---|---|
| `kline` | K 线 | A/HK/US/指数/板块/ETF | Markdown 表格 |
| `minute` | 分时 | A/HK/US/指数/板块 | Markdown 表格 |
| `finance` | 三表 | A/HK/US | 多子表（**lrb**/**zcfz**/**xjll**） |
| `profile` | 公司简况 | A/HK/US | Markdown 表格 |
| `chip` | 筹码成本 | 沪深京 A | Markdown 表格 |
| `asfund` | A 股资金流向 | 仅沪深 | Markdown 表格 |
| `hkfund` | 港股资金流向 | 仅港股 | Markdown 表格 |
| `usfund` | 美股卖空 | 仅美股 | Markdown 表格 |
| `search` | 搜索股票/板块 | 全部 | Markdown 表格 |
| `technical` | 技术指标 | 全部 | Markdown 表格（按 group） |
| `shareholder` | 股东结构 | A/HK | Markdown 表格 |
| `dividend` | 分红 | 全部 | Markdown 表格 |
| `lhb` | 龙虎榜 | 沪深 | Markdown 表格 |
| `blocktrade` | 大宗交易 | 沪深 | Markdown 表格 |
| `margintrade` | 融资融券 | 沪深 | Markdown 表格 |
| `hot` | 热搜 | A | Markdown 表格 |
| `board` | 板块行情 | 全部 | Markdown 表格 |
| `calendar` | 投资日历 | 全部 | Markdown 表格 |
| `ipo` | 新股 | 沪深/HK/US | Markdown 表格 |
| `exdiv` | 除权日历 | 全部 | Markdown 表格 |
| `reserve` | 业绩预告 | 全部 | Markdown 表格 |
| `suspension` | 停复牌 | 沪深 | Markdown 表格 |
| `etf` | ETF 详情 | A | Markdown 表格 |
| `etf-holdings` | ETF 持仓 | A | Markdown 表格 |
| `etf-nav` | ETF 净值 | A | Markdown 表格 |
| `etf-company` | ETF 公司 | A | Markdown 表格 |
| `etf-holders` | ETF 持有人 | A | Markdown 表格 |
| `etf-financial` | ETF 财务 | A | Markdown 表格 |
| `buyback` | 回购 | A | Markdown 表格 |

**未实现的命令**（官方文档列出但 1.0.3 缺失）：
- `quote` — 实时报价（**1.0.3 不存在**，降级方案：从 `kline` 末行 + `minute` 末行组装）

---

## K 线调用规范

```bash
npx -y westock-data-skillhub@1.0.3 kline sh600519 --period day --limit 120 --fq qfq
```

参数：
- `--period day|week|month|season|year`（K 线周期）
- `--limit N`（返回条数，最大 2000）
- `--fq qfq|hfq|bfq`（前复权/后复权/不复权，默认前复权）
- `--start YYYY-MM-DD`（与 --limit 互斥）
- `--end YYYY-MM-DD`

返回字段（实测）：
```text
| date | open | last | high | low | volume | amount | exchange |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-24 | 1222.65 | 1207.68 | 1241.87 | 1207.51 | 45335 | 5176574460 | 0.34 |
```

**字段注意**：
- `last` 是收盘价（**不是** close）
- `volume` 单位因市场不同：
  - **A 股 = 手**（需 ×100 转"股"）
  - 港/美股 = 股
- `amount` = 成交额（元）
- `exchange` 字段实际是**换手率**（不是交易所代码！）

## 分钟级（分时）

```bash
npx -y westock-data-skillhub@1.0.3 minute sh600519 --days 1
```

返回：
```text
| code | time | price | volume | amount |
| --- | --- | --- | --- | --- |
| sh600519 | 0930 | 1222.65 | 341 | 41692365.00 |
| sh600519 | 0931 | 1223.00 | 973 | 119164782.58 |
```

- `time` 是 HHMM 格式
- 不支持批量

## 财务报表

```bash
npx -y westock-data-skillhub@1.0.3 finance sh600519 --num 1
```

返回**多子表**，用 `**lrb**` / `**zcfz**` / `**xjll**` 分段：
- A 股：`lrb`（利润表）/ `zcfz`（资产负债表）/ `xjll`（现金流量表）
- 港股：`zhsy` / `zcfz` / `xjll`
- 美股：`income` / `balance` / `cashflow`

**注意**：港股金额单位是港元 / 美元，**展示时必须标注正确货币**，禁止使用人民币符号。

## 筹码

```bash
npx -y westock-data-skillhub@1.0.3 chip sh600519
```

返回：
```text
| code | name | date | closePrice | chipProfitRate | chipAvgCost | chipConcentration90 | chipConcentration70 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sh600519 | 贵州茅台 | 2026-06-24 | 1208.01 | 0.01 | 1412.78 | 8.96 | 5.09 |
```

仅支持沪深京 A 股（`sh` / `sz` / `bj`）。

---

## Python 调用

```python
import subprocess

def run_westock(args: list[str], timeout: int = 30) -> str:
    """调 npx westock-data-skillhub，返回 stdout 字符串"""
    cmd = ["npx", "-y", "westock-data-skillhub@1.0.3"] + args
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"westock 失败: {proc.stderr}")
    return proc.stdout
```

完整封装见 `src/data_layer/westock_wrapper.py`。

## Markdown 解析

westock 返回 Markdown 表格格式：

```text
| date | open | last | high | low | volume | amount | exchange |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-24 | 1222.65 | 1207.68 | 1241.87 | 1207.51 | 45335 | 5176574460 | 0.34 |
```

`src/data_layer/westock_wrapper.py` 内置 `_parse_markdown_table` 解析函数（不引依赖）。

## 数据契约转换（关键）

| 转换项 | 来源（westock） | 目标（contracts） | 规则 |
|---|---|---|---|
| 收盘价字段 | `last` | `close` | wrapper rename |
| 成交量单位（A 股） | `volume`（手） | `volume`（股） | × 100 |
| 成交量单位（港/美） | `volume`（股） | `volume`（股） | 不变 |
| 换手率 | `exchange` 字段 | DataFrame.attrs | 重命名后丢弃（实际是换手率，不是交易所代码） |
| 货币单位 | — | `currency = "CNY"/"HKD"/"USD"` | wrapper 按 market 自动推断 |

## 异常类（与 reliability.py 映射）

```python
class WestockError(Exception): pass
class WestockEnvError(WestockError): pass       # Node/npx 不可用
class WestockTransientError(WestockError): pass # subprocess 失败/超时
class WestockPermanentError(WestockError): pass # 股票代码不存在/未知命令
class WestockParseError(WestockError): pass     # Markdown 解析失败
```

`reliability.classify_westock_error()` 统一映射到 `TransientError` / `PermanentError`。

## 已知陷阱

1. **首次 npx 拉取包**耗时 4-30s（取决于网络）。预热方案：环境检查时跑一次 `--help`。
2. **K 线最大 2000 条**——超过会报错或截断。
3. **westock 没有 `quote` 命令**——1.0.3 实测未实现，需用 `kline` 末行 + `minute` 末行组装报价。
4. **美股 `minute` 命令可能不支持**——`usTSLA` 实测返回"数据为空"。**降级方案**：用 `kline` 末行作为 close 价 + 预留 `prev_close=0`。
5. **港/美股金额单位**——展示时必须标注 HKD/USD，禁用 ¥ 符号。
6. **Markdown 格式变更**——`_parse_markdown_table` 自动识别数值列，文本列（date/name/code）保持原样。
7. **Windows subprocess**——`subprocess.run(["npx", ...])` 找不到 `npx.cmd`，需用 `shutil.which("npx")` 拿绝对路径。

## 性能数据

- A 股 K 线 120 条：~1-2s（冷启 5-10s）
- 单次 minute --days 1：~2-3s
- `--help`：~4s

## 内联测试

```python
if __name__ == '__main__':
    print(run_westock(['kline', 'sh600519', '--limit', '5']))
```

## 完整调用示例

```python
from data_layer.westock_wrapper import get_kline, get_quote

# A 股 K 线
df = get_kline("sh600519", limit=120)
# 列: ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'exchange']
# 末行 close=1207.68, volume=4533500 股

# 港股 K 线（westock 自动 ×1，不需要 ×100）
df = get_kline("hk00700", limit=5)
# volume 已是"股"

# 美股 K 线
df = get_kline("usTSLA", limit=5)

# 报价（从 minute + kline 组装）
quote = get_quote("sh600519")
print(f"{quote.currency} {quote.price}")  # Currency.CNY 1207.68

# 港股报价
quote = get_quote("hk00700")
print(f"{quote.currency} {quote.price}")  # Currency.HKD 428.4
```

## 文档同步说明

⚠️ **本 SDK 文档与官方文档的差异**：
- 实测发现 `quote` 命令在 1.0.3 未实现（官方文档列出）
- 实测 `volume` 在 A 股是"手"（需 ×100）
- 实测 `exchange` 字段实际是换手率（官方文档描述为交易所代码）
- 实测 `minute` 对美股支持不完整

这些差异已记录到 v0.6 整合 plan。