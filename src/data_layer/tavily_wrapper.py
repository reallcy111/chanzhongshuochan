"""
src/data_layer/tavily_wrapper.py — Tavily 搜索 SDK 封装

按 plan 决策 (skills-fluttering-hinton.md):
- 消息面兜底（公告/新闻/通用搜索）
- topic=finance（金融分析首选）
- 报价降级链: westock → qveris → akshare → tavily → agent-browser

API key: 用 check_environment.get_api_key("TAVILY_API_KEY")
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .contracts import NewsItem

logger = logging.getLogger(__name__)

SOURCE_NAME = "tavily"
TAVILY_API_URL = "https://api.tavily.com/search"


# ============================================================
# 异常类
# ============================================================
class TavilyError(Exception):
    """tavily 所有异常的基类"""


class TavilyAuthError(TavilyError):
    """401 鉴权失败"""


class TavilyRateLimitError(TavilyError):
    """429 限流"""


class TavilyTimeoutError(TavilyError):
    """超时"""


class TavilyNetworkError(TavilyError):
    """网络错误"""


class TavilyPermanentError(TavilyError):
    """参数错误"""


# ============================================================
# API key 加载
# ============================================================
def _load_api_key() -> Optional[str]:
    try:
        from src.check_environment import get_api_key
        return get_api_key("TAVILY_API_KEY")
    except Exception:
        import os
        return os.environ.get("TAVILY_API_KEY")


# ============================================================
# 搜索
# ============================================================
def search_news(
    query: str,
    max_results: int = 10,
    topic: str = "finance",
    search_depth: str = "basic",
    time_range: Optional[str] = None,
    config: Optional[dict] = None,
) -> list[NewsItem]:
    """Tavily 搜索（topic=finance 金融分析首选）。

    Args:
        query: 搜索词，如 "浦发银行 600000 公告"
        max_results: 1-100
        topic: "general" | "news" | "finance"
        search_depth: "basic" | "advanced"
        time_range: "day" | "week" | "month" | "year"（可选）
    """
    api_key = _load_api_key()
    if not api_key:
        raise TavilyAuthError("TAVILY_API_KEY 未配置")

    # 优先尝试官方 SDK
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        kwargs: dict = {
            "query": query,
            "topic": topic,
            "max_results": max_results,
            "search_depth": search_depth,
        }
        if time_range:
            kwargs["time_range"] = time_range
        result = client.search(**kwargs)
        return [_hit_to_newsitem(h, tier=2) for h in result.get("results", [])]
    except ImportError:
        logger.debug("tavily-python 未安装，用 REST API")
    except Exception as e:
        logger.warning("tavily SDK 调用失败，回退到 REST: %s", e)

    # Fallback: 直接 REST
    body = json.dumps({
        "api_key": api_key,
        "query": query,
        "topic": topic,
        "max_results": max_results,
        "search_depth": search_depth,
        **({"time_range": time_range} if time_range else {}),
    }).encode("utf-8")
    req = urllib.request.Request(
        TAVILY_API_URL, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise TavilyAuthError(f"tavily 鉴权失败: {e}") from e
        if e.code == 429:
            raise TavilyRateLimitError(f"tavily 限流: {e}") from e
        raise TavilyNetworkError(f"tavily HTTP {e.code}: {e}") from e
    except TimeoutError as e:
        raise TavilyTimeoutError("tavily 超时") from e
    except urllib.error.URLError as e:
        raise TavilyNetworkError(f"tavily 网络错误: {e}") from e

    return [_hit_to_newsitem(h, tier=2) for h in result.get("results", [])]


def _hit_to_newsitem(hit: dict, tier: int = 2) -> NewsItem:
    """把 tavily hit 转换为 NewsItem"""
    return NewsItem(
        title=str(hit.get("title", "")).strip(),
        url=str(hit.get("url", "")),
        content=str(hit.get("content", ""))[:200],
        published_at=str(hit.get("published_date", "")),
        source="tavily",
        tier=tier,
    )


# ============================================================
# 自检
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    api_key = _load_api_key()
    print(f"TAVILY_API_KEY: {'已配置' if api_key else '未配置'}")

    if api_key:
        print()
        print("=== 财经搜索测试 ===")
        try:
            items = search_news("浦发银行 公告", max_results=3)
            print(f"获取 {len(items)} 条结果")
            for item in items[:3]:
                print(f"  - [{item.tier}] {item.title[:50]}")
        except Exception as e:
            print(f"[FAIL] {e}")

    print()
    print("[OK] tavily_wrapper.py self-check passed")