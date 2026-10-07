# AKShare SDK 标准调用规范

> 来源：Context7 /akfamily/akshare（2026-06-23 验证）
> 用途：缠中说禅 skill 数据获取层 1 级数据源（K 线 + 报价 + 公告）

## 安装

```bash
pip install akshare
```

## A 股 K 线（必备）

### `ak.stock_zh_a_hist_tx` — 腾讯源（推荐，无条数限制）

```python
import akshare as ak

df = ak.stock_zh_a_hist_tx(
    symbol="sz000001",          # 必填，含市场前缀 (sz/sh/bj)
    start_date="20200101",      # 选填，YYYYMMDD 格式
    end_date="20231027",        # 选填，YYYYMMDD 格式
    adjust="qfq",               # 选填: '' (不复权) | 'qfq' (前复权) | 'hfq' (后复权)
    timeout=None,               # 选填，秒
)
# 返回 DataFrame 列: date / open / close / high / low / amount
```

### `ak.stock_zh_a_hist` — 东财源（备选）

```python
df = ak.stock_zh_a_hist(
    symbol="000001",            # 必填，**不含**市场前缀
    period="daily",             # 必填: 'daily' | 'weekly' | 'monthly'
    start_date="20210301",      # 必填，YYYYMMDD
    end_date="20240528",        # 必填，YYYYMMDD
    adjust="qfq",
    timeout=None,
)
# 返回 DataFrame 列: 日期 / 股票代码 / 开盘 / 收盘 / 最高 / 最低 / 成交量 / 成交额 / 振幅 / 涨跌幅 / 涨跌额 / 换手率
```

## 港股 K 线

```python
df = ak.stock_hk_hist(
    symbol="00700",             # 5 位数字
    period="daily",
    start_date="20200101",
    end_date="20231027",
    adjust="qfq",
)
```

## 美股 K 线

```python
df = ak.stock_us_hist(
    symbol="105.MSFT",          # 需要从 ak.stock_us_spot_em() 获取带前缀的代码
    period="daily",
    start_date="20200101",
    end_date="20231027",
    adjust="qfq",
)
```

## A 股实时报价

### `ak.stock_zh_a_spot_em` — 东财实时行情（推荐）

```python
df = ak.stock_zh_a_spot_em()
# 返回 ~5316 行 DataFrame，列: 序号/代码/名称/最新价/涨跌幅/涨跌额/成交量/成交额/振幅/最高/最低/今开/昨收/量比/换手率/市盈率-动态/市净率/总市值/流通市值/涨速/5分钟涨跌/60日涨跌幅/年初至今涨跌幅
```

**注意事项**：东财接口对频繁调用敏感（可能限流）。需在 wrapper 中加 sleep 间隔。

## A 股公告

```python
df = ak.stock_zh_a_disclosure_report(
    symbol="000001",
    start_date="2023-01-01",
    end_date="2023-12-31",
)
```

## 已知陷阱

1. **限流**：东财接口高频调用会临时封 IP — wrapper 内部加 1-2s sleep
2. **代码格式**：A 股 `stock_zh_a_hist` 不要市场前缀，`stock_zh_a_hist_tx` 必须有
3. **超时**：复杂查询建议显式设 `timeout=10`
4. **复权**：量化分析建议 `qfq`（前复权）
5. **美股代码**：`stock_us_hist` 需要带 `105.` 这样的市场前缀（从 `stock_us_spot_em` 获取）

## 内联测试

```python
if __name__ == '__main__':
    df = ak.stock_zh_a_hist_tx(symbol="sz000001", start_date="20240101", end_date="20240623", adjust="qfq")
    print(f"行数: {len(df)}")
    print(f"列: {list(df.columns)}")
    print(df.head())
```

## 异常处理建议

```python
import akshare as ak
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def safe_fetch_klines(symbol, start, end):
    try:
        return ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start, end_date=end, adjust="qfq", timeout=10)
    except Exception as e:
        raise RuntimeError(f"akshare fetch failed: {e}") from e
```
