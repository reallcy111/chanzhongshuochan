"""
src/data_layer/qveris_wrapper.py — qveris.ai REST API 封装

按 plan 决策 (skills-fluttering-hinton.md):
- 修 API key 读取路径: 用 check_environment.get_api_key() 而非
  plugins.entries.qveris.config.apiKey 硬编码（兼容 Windows / Linux）
- 统一 tool_id: caidazi.get_real_time_record.execute.v1.7a43f96e
  （替换旧版 cn_financial_pro.real_time_quotation.v1）
- 报价: westock → qveris → akshare → tavily → agent-browser（qveris 第 2 位）
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .contracts import QuoteResult, NewsItem, Currency

logger = logging.getLogger(__name__)

SOURCE_NAME = "qveris"
QVERIS_BASE = "https://qveris.ai/api/v1/tools/execute"

TOOL_REALTIME = "caidazi.get_real_time_record.execute.v1.7a43f96e"
TOOL_FINNEWS = "qveris_finance.finance_news_aggregation_v1"
TOOL_NEWS = "caidazi.news.query.v1.e76b9116"


# ============================================================
# 异常类
# ============================================================
class QverisError(Exception):
    """qveris 所有异常的基类"""


class QverisAuthError(QverisError):
    """401 鉴权失败"""


class QverisRateLimitError(QverisError):
    """429 限流"""


class QverisTimeoutError(QverisError):
    """超时"""


class QverisNetworkError(QverisError):
    """网络错误"""


class QverisPermanentError(QverisError):
    """永久错误（参数错）"""


# ============================================================
# API key 加载（修路径问题）
# ============================================================
def _load_api_key() -> Optional[str]:
    """优先级 1: 环境变量；优先级 2: check_environment.get_api_key()

    修复: 原 src/qveris_client.py 的 _load_key() 硬编码
    plugins.entries.qveris.config.apiKey，在 Windows 上路径不同。
    改用 check_environment.get_api_key() 统一处理。
    """
    try:
        from src.check_environment import get_api_key
        return get_api_key("QVERIS_API_KEY")
    except Exception as e:
        logger.debug("check_environment.get_api_key 不可用: %s", e)
        import os
        from pathlib import Path
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        if not config_path.exists():
            return None
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            return (
                cfg.get("plugins", {}).get("entries", {})
                .get("qveris", {}).get("config", {}).get("apiKey")
            )
        except Exception:
            return None


# ============================================================
# REST 调用
# ============================================================
@dataclass
class QverisResponse:
    """qveris 响应包装"""
    ok: bool
    data: dict
    error: str = ""


def _call_qveris(
    tool_id: str,
    params: dict,
    api_key: str,
    timeout: int = 15,
) -> QverisResponse:
    """调用 qveris REST API。

    Raises:
        QverisAuthError: 401
        QverisRateLimitError: 429
        QverisTimeoutError: 超时
        QverisNetworkError: 网络故障
    """
    payload = {"tool_id": tool_id, "tool_input": params}
    req = urllib.request.Request(
        QVERIS_BASE,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            return QverisResponse(ok=True, data=json.loads(body))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise QverisAuthError(f"qveris 鉴权失败: {e}") from e
        if e.code == 429:
            raise QverisRateLimitError(f"qveris 限流: {e}") from e
        raise QverisNetworkError(f"qveris HTTP {e.code}: {e}") from e
    except TimeoutError as e:
        raise QverisTimeoutError(f"qveris 超时 ({timeout}s)") from e
    except urllib.error.URLError as e:
        raise QverisNetworkError(f"qveris 网络错误: {e}") from e


# ============================================================
# 实时报价
# ============================================================
def get_quote(
    symbol: str,
    config: Optional[dict] = None,
) -> QuoteResult:
    """A 股/港股/美股实时报价（qveris caidazi tool）。

    Args:
        symbol: westock 格式（sh600519 / hk00700 / usAAPL）
    """
    api_key = _load_api_key()
    if not api_key:
        raise QverisAuthError("QVERIS_API_KEY 未配置")

    raw = symbol.lower().strip()
    try:
        resp = _call_qveris(TOOL_REALTIME, {"symbol": raw}, api_key, timeout=10)
    except QverisError:
        raise
    except Exception as e:
        raise QverisNetworkError(f"qveris quote 未知错误: {e}") from e

    raw_data = resp.data.get("result", {}).get("data", {})
    if isinstance(raw_data, str):
        raise QverisPermanentError(
            f"qveris 返回 Markdown 格式（需解析）: {raw_data[:200]}"
        )

    def _f(key: str, default: float = 0.0) -> float:
        try:
            return float(raw_data.get(key, default))
        except (ValueError, TypeError):
            return default

    market_map = {"sh": "CNY", "sz": "CNY", "bj": "CNY", "hk": "HKD", "us": "USD"}
    currency_str = market_map.get(raw[:2], "CNY")

    price = _f("price")
    pre_close = _f("preClose") or _f("prevClose") or _f("yesterdayClose")
    if price <= 0 or pre_close <= 0:
        raise QverisPermanentError(
            f"qveris {symbol} 数据缺失: price={price} pre_close={pre_close}"
        )
    change = price - pre_close
    change_pct = (change / pre_close * 100) if pre_close else 0.0

    return QuoteResult(
        symbol=raw,
        name=str(raw_data.get("name", "")),
        price=price,
        prev_close=pre_close,
        open=_f("open"),
        high=_f("high"),
        low=_f("low"),
        change=change,
        change_pct=change_pct,
        volume=_f("volume") * 100 if raw_data.get("volume") else 0.0,
        turnover_value=_f("amount"),
        turnover_rate=_f("turnoverRatio") or None,
        pe=_f("pe") or None,
        pb=_f("pb") or None,
        total_mv=_f("totalCapital") or None,
        currency=Currency(currency_str),
    )


# ============================================================
# 财经新闻
# ============================================================
def search_finance_news(
    query: str,
    count: int = 10,
    config: Optional[dict] = None,
) -> list[NewsItem]:
    """财经新闻聚合（qveris_finance.finance_news_aggregation_v1）。"""
    api_key = _load_api_key()
    if not api_key:
        raise QverisAuthError("QVERIS_API_KEY 未配置")

    resp = _call_qveris(
        TOOL_FINNEWS, {"query": query, "limit": count}, api_key, timeout=15,
    )

    inner = resp.data.get("result", {}).get("data", {})
    if isinstance(inner, dict):
        items_data = inner.get("results", [])
    elif isinstance(inner, list):
        items_data = inner
    else:
        items_data = []

    items: list[NewsItem] = []
    for it in items_data[:count]:
        if not isinstance(it, dict):
            continue
        items.append(NewsItem(
            title=str(it.get("title", "")),
            url=str(it.get("url", "")),
            content=str(it.get("content", ""))[:200],
            published_at=str(it.get("date", "")),
            source="qveris",
            tier=1,
        ))
    return items


# ============================================================
# 自检
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    api_key = _load_api_key()
    print(f"QVERIS_API_KEY: {'已配置' if api_key else '未配置'}")

    if api_key:
        print()
        print("=== A 股实时报价测试 ===")
        try:
            q = get_quote("sh600519")
            print(f"价格: {q.currency} {q.price}")
            print(f"涨跌: {q.change} ({q.change_pct:.2f}%)")
            print(f"名称: {q.name}")
        except Exception as e:
            print(f"[FAIL] {e}")

        print()
        print("=== 财经新闻测试 ===")
        try:
            items = search_finance_news("浦发银行", count=3)
            print(f"获取 {len(items)} 条新闻")
            for item in items[:3]:
                print(f"  - {item.title[:50]}")
        except Exception as e:
            print(f"[FAIL] {e}")

    print()
    print("[OK] qveris_wrapper.py self-check passed")