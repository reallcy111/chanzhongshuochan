# Tavily SDK 标准调用规范

> 来源：Context7 /tavily-ai/tavily-python（2026-06-23 验证）
> 用途：缠中说禅 skill 数据获取层 3 级数据源（消息面兜底 + 通用搜索）

## 安装

```bash
pip install tavily-python
```

## API Key 配置

```python
import os
from pathlib import Path
import json

def get_tavily_api_key() -> str:
    key = os.environ.get("TAVILY_API_KEY")
    if key:
        return key
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        return cfg.get("env", {}).get("TAVILY_API_KEY", "")
    raise RuntimeError("TAVILY_API_KEY 未配置")
```

## 标准搜索调用

```python
from tavily import TavilyClient

client = TavilyClient(api_key=get_tavily_api_key())

response = client.search(
    query="浦发银行 公告 2026",       # 必填
    search_depth="advanced",          # 选填: "basic" | "advanced" | "fast" | "ultra-fast"
    topic="finance",                  # 选填: "general" | "news" | "finance" — 金融场景用 "finance"
    max_results=10,                   # 选填: 1-100
    include_raw_content="markdown",   # 选填: True | "markdown" | "text"
    include_answer=False,             # 选填: True | "basic" | "advanced"
    timeout=60,                       # 选填: 秒，最大 120
)
# 返回结构:
# {
#     "results": [
#         {
#             "title": str,
#             "url": str,
#             "content": str,        # 摘要
#             "score": float,         # 0-1 相关度
#             "raw_content": str,     # 完整内容（如果 include_raw_content=True）
#         }
#     ],
#     "answer": str,                  # 直接回答（如果 include_answer=True）
#     "response_time": float,
#     "query": str,
# }
```

## topic 用法

| topic | 用途 | 适用 |
|---|---|---|
| `"general"` | 通用网页 | 默认，金融场景不推荐 |
| `"news"` | 新闻 | 突发新闻、公告 |
| `"finance"` | 金融 | **金融分析首选** |

## 时间过滤

```python
# 方式 1: time_range (相对)
client.search(query="...", time_range="week")  # "day" | "week" | "month" | "year"

# 方式 2: 绝对日期（ISO 格式）
client.search(query="...", start_date="2026-06-01", end_date="2026-06-23")

# 方式 3: 最近 N 天
client.search(query="...", days=7)
```

**注意**：上述三种方式互斥，不能同时用。

## 异常类型

```python
from tavily import (
    InvalidAPIKeyError,           # 401
    UsageLimitExceededError,      # 429
    BadRequestError,              # 400
    ForbiddenError,               # 403/432/433
    TavilyKeylessLimitError,      # 免 key 模式限流
    TimeoutError,                 # 超时
)
```

## 已知陷阱

1. **API key 区分 keyed / keyless 模式**：keyed 模式需要显式 `api_key=...`
2. **topic=finance 是新参数**：旧代码可能没用到
3. **include_raw_content 占用配额**：仅在需要完整页面时用
4. **超时上限 120s**：复杂查询建议 60-90s
5. **max_results 上限 100**：超过会报错

## 内联测试

```python
if __name__ == '__main__':
    client = TavilyClient(api_key=get_tavily_api_key())
    response = client.search(
        query="浦发银行 600000 公告",
        topic="finance",
        max_results=5,
    )
    print(f"找到 {len(response['results'])} 条结果")
    for r in response["results"]:
        print(f"- {r['title']} ({r['url']})")
```

## 异常处理示例

```python
from tavily import (
    TavilyClient, InvalidAPIKeyError, UsageLimitExceededError, TimeoutError,
)

def safe_search(query: str, **kwargs) -> dict:
    try:
        return client.search(query=query, **kwargs)
    except InvalidAPIKeyError:
        raise RuntimeError("TAVILY_API_KEY 无效")
    except UsageLimitExceededError:
        raise RuntimeError("Tavily 配额用尽")
    except TimeoutError:
        raise RuntimeError("Tavily 查询超时")
```
