# Qveris SDK 标准调用规范

> 来源：从现有 `src/qveris_client.py` + `src/data_fetcher.py` 提取（2026-06-23 验证）
> 用途：缠中说禅 skill 数据获取层 2 级数据源（实时报价 + 财经新闻）
> 注：qveris 无官方 Python SDK，直接用 urllib 调用 REST API

## API Key 配置（OpenClaw vault）

```python
import os
import json
from pathlib import Path

def get_qveris_api_key() -> str:
    """优先级 1: 环境变量（OpenClaw 注入）；优先级 2: ~/.openclaw/openclaw.json env 字段"""
    key = os.environ.get("QVERIS_API_KEY")
    if key:
        return key
    # fallback: 直接读 OpenClaw config
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        return cfg.get("env", {}).get("QVERIS_API_KEY", "")
    raise RuntimeError("QVERIS_API_KEY 未配置")
```

## 端点

```
POST https://qveris.ai/api/v1/tools/execute
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

## 工具 ID（tool_id）

| tool_id | 用途 | 返回 |
|---|---|---|
| `caidazi.get_real_time_record.execute.v1.7a43f96e` | A 股/港股/美股实时报价 | 价格、涨跌、成交量 |
| `cn_financial_pro.real_time_quotation.v1` | 实时报价（data_fetcher 用的，不同 tool_id） | 同上 |
| `qveris_finance.finance_news_aggregation_v1` | 财经新闻聚合 | `results[]`，每条含 title/url/content/date |
| `caidazi.news.query.v1.e76b9116` | 通用新闻 | Markdown 表格格式 |

**注意**：现有 `data_fetcher.py` 用 `cn_financial_pro.real_time_quotation.v1`，`qveris_client.py` 用 `caidazi.get_real_time_record.execute.v1.7a43f96e` — **重复调用**。v0.6 统一用 `caidazi.get_real_time_record.execute.v1.7a43f96e`。

## 标准请求格式

```python
import urllib.request
import json
import ssl

def call_qveris(tool_id: str, params: dict, api_key: str, timeout: int = 10) -> dict:
    url = "https://qveris.ai/api/v1/tools/execute"
    payload = {
        "tool_id": tool_id,
        "tool_input": params,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    # qveris.ai 用 HTTPS 但部分环境需要宽松 SSL
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))
```

## 实时报价调用示例

```python
result = call_qveris(
    tool_id="caidazi.get_real_time_record.execute.v1.7a43f96e",
    params={"symbol": "sh600000"},   # 必填，含市场前缀
    api_key=api_key,
    timeout=10,
)
# 返回典型结构（需 wrapper 验证）:
# {
#   "data": {
#     "symbol": "sh600000",
#     "name": "浦发银行",
#     "price": 8.50,
#     "change": 0.05,
#     "change_pct": 0.59,
#     "volume": 12345678,
#     "time": "2026-06-23 15:00:00",
#   }
# }
```

## 财经新闻调用示例

```python
result = call_qveris(
    tool_id="qveris_finance.finance_news_aggregation_v1",
    params={"query": "浦发银行", "limit": 10},  # 或用 symbol
    api_key=api_key,
    timeout=15,
)
# 返回结构:
# {
#   "results": [
#     {
#       "title": "...",
#       "url": "https://...",
#       "content": "...",       # 摘要
#       "date": "2026-06-23",
#       "tier": 1,              # 1=一手, 2=二手
#     }
#   ]
# }
```

## 已知陷阱

1. **tool_id 重名/重复**：`data_fetcher.py` 和 `qveris_client.py` 用不同 tool_id，**v0.6 统一**
2. **超时**：建议 10-15s，部分查询可能慢
3. **SSL**：部分环境需要 `ssl.create_default_context()` 兜底
4. **错误响应**：检查 HTTP 状态码，401/403/429 各自含义不同
5. **字段缺失**：实时报价可能字段缺失，wrapper 需做容错（缺失字段返回 None）

## 内联测试

```python
if __name__ == '__main__':
    api_key = get_qveris_api_key()
    print(f"API key 长度: {len(api_key)}")
    # 测试实时报价
    quote = call_qveris(
        "caidazi.get_real_time_record.execute.v1.7a43f96e",
        {"symbol": "sh600000"},
        api_key,
    )
    print(f"实时报价: {json.dumps(quote, ensure_ascii=False, indent=2)}")
```

## 异常处理

```python
class QverisAPIError(Exception):
    """qveris API 错误基类"""
    pass

class QverisAuthError(QverisAPIError): pass       # 401
class QverisRateLimitError(QverisAPIError): pass  # 429
class QverisTimeoutError(QverisAPIError): pass    # timeout
class QverisNetworkError(QverisAPIError): pass    # 网络故障
```
