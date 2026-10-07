"""
src/data_layer/router.py — 多源路由器（v0.6 5 级降级编排）

按 plan 决策 (skills-fluttering-hinton.md):

降级链 (含 westock-data):
- A 股 K 线:    akshare → westock → qveris → tavily → agent-browser
- 港/美 K 线:  westock → akshare → qveris → tavily → agent-browser
- 报价 (全市场): westock → qveris → akshare → tavily → agent-browser
- 公告/新闻:    westock → qveris → akshare → tavily → agent-browser

每跳一级失败:
- CircuitBreaker 熔断检查
- catch TransientError / PermanentError → 跳下一源
- 所有源都失败 → 抛 AllSourcesFailedError

v0.6.2 新增:
- K 线 staleness 阈值: westock 返回 staleness_days > STALENESS_THRESHOLD_DAYS 时视为过期，自动跳下一源
  （westock 腾讯接口数据可能滞后 1-2 周，详见 docs/sdk-westock-data.md 已知限制）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .contracts import KlineRow, QuoteResult, NewsItem, Market, Currency, detect_market

logger = logging.getLogger(__name__)


# K 线 staleness 阈值（超过则视为过期，跳下一源）
STALENESS_THRESHOLD_DAYS = 3


# ============================================================
# 异常类
# ============================================================
class RouterError(Exception):
    """路由器异常的基类"""


class AllSourcesFailedError(RouterError):
    """所有数据源都失败"""

    def __init__(self, symbol: str, data_type: str, attempts: list[tuple[str, str]]):
        self.symbol = symbol
        self.data_type = data_type
        self.attempts = attempts
        super().__init__(
            f"{data_type} {symbol} 全部数据源失败 ({len(attempts)} 个): "
            + "; ".join(f"{s}: {e}" for s, e in attempts)
        )


# ============================================================
# 数据源开关
# ============================================================
@dataclass
class RouterConfig:
    """路由器配置（按数据类型启用/禁用数据源）"""
    enabled_kline_sources: dict[str, bool] = field(default_factory=lambda: {
        "akshare": True,
        "westock": True,
        "qveris": True,
        "tavily": True,
        "agent_browser": True,
    })
    enabled_quote_sources: dict[str, bool] = field(default_factory=lambda: {
        "westock": True,
        "qveris": True,
        "akshare": True,
        "tavily": True,
        "agent_browser": True,
    })
    # K 线 staleness 阈值（天），None 表示禁用 staleness 检查
    staleness_threshold_days: Optional[int] = STALENESS_THRESHOLD_DAYS


_default_config = RouterConfig()


def get_config() -> RouterConfig:
    """获取默认配置"""
    return _default_config


def disable_source(data_type: str, source_name: str) -> None:
    """禁用某个数据源（紧急回退 L2）"""
    cfg = get_config()
    if data_type == "kline":
        cfg.enabled_kline_sources[source_name] = False
    elif data_type == "quote":
        cfg.enabled_quote_sources[source_name] = False


# ============================================================
# 降级链定义（按 market 分化）
# ============================================================
def _kline_chain(market: Market) -> list[str]:
    """返回 K 线降级链（按 market 分化）"""
    if market in (Market.HK, Market.US):
        return ["westock", "akshare", "qveris", "tavily", "agent_browser"]
    return ["akshare", "westock", "qveris", "tavily", "agent_browser"]


def _quote_chain() -> list[str]:
    """报价降级链（westock 全市场最强）"""
    return ["westock", "qveris", "akshare", "tavily", "agent_browser"]


def _news_chain() -> list[str]:
    """公告/新闻降级链"""
    return ["westock", "qveris", "akshare", "tavily", "agent_browser"]


# ============================================================
# K 线路由
# ============================================================
def route_kline(
    symbol: str,
    market: Optional[Market] = None,
    days: int = 120,
    period: str = "day",
    adjust: str = "qfq",
) -> tuple[pd.DataFrame, str]:
    """K 线路由：按 market 选降级链，逐源尝试。

    Args:
        symbol: westock 格式 (sh600519 / hk00700 / usAAPL)
        market: Market 枚举（None=自动 detect）
        days: 天数
        period: day/week/month/season/year
        adjust: qfq/hfq/bfq

    Returns:
        (DataFrame, source_name)

    v0.6.2 行为:
    - westock 返回 staleness_days > 阈值时视为过期，自动跳下一源
    - 阈值由 RouterConfig.staleness_threshold_days 控制（None = 禁用）

    Raises:
        AllSourcesFailedError: 全部数据源失败
    """
    if market is None:
        market = detect_market(symbol)

    chain = _kline_chain(market)
    cfg = get_config()
    attempts: list[tuple[str, str]] = []

    for source_name in chain:
        if not cfg.enabled_kline_sources.get(source_name, False):
            logger.debug("[router] kline %s 跳过（已禁用）", source_name)
            continue

        try:
            df, staleness_days = _call_kline_source(
                source_name, symbol, days, period, adjust
            )
            if df is None or df.empty:
                attempts.append((source_name, "空数据"))
                continue
            # v0.6.2: staleness 阈值检查（仅 westock 会返回非 None）
            threshold = cfg.staleness_threshold_days
            if (
                staleness_days is not None
                and threshold is not None
                and staleness_days > threshold
            ):
                attempts.append(
                    (source_name, f"数据过期 {staleness_days} 天（阈值 {threshold}）")
                )
                logger.warning(
                    "[router] kline %s 数据过期 (%d 天 > %d 阈值)，跳下一源",
                    source_name, staleness_days, threshold,
                )
                continue
            logger.info(
                "[router] kline %s → %s (%d 行, staleness=%s 天)",
                symbol, source_name, len(df),
                staleness_days if staleness_days is not None else "n/a",
            )
            return df, source_name
        except Exception as e:
            attempts.append((source_name, f"{type(e).__name__}: {e}"))
            logger.warning("[router] kline %s 失败 (%s): %s", source_name, symbol, e)

    raise AllSourcesFailedError(symbol, "kline", attempts)


def _call_kline_source(
    source_name: str,
    symbol: str,
    days: int,
    period: str,
    adjust: str,
) -> tuple[Optional[pd.DataFrame], Optional[int]]:
    """调度到具体 wrapper。

    Returns:
        (DataFrame, staleness_days): 非 westock 源 staleness_days=None
    """
    if source_name == "akshare":
        from . import akshare_wrapper as w
        market = detect_market(symbol)
        if market == Market.HK:
            return w.get_kline_hk(symbol, days=days, adjust=adjust), None
        if market == Market.US:
            return w.get_kline_us(symbol, days=days, adjust=adjust), None
        return w.get_kline_zh_a(symbol, days=days, adjust=adjust), None

    if source_name == "westock":
        from . import westock_wrapper as w
        return w.get_kline(symbol, period=period, limit=min(days, w.MAX_LIMIT), fq=adjust)

    if source_name == "qveris":
        raise NotImplementedError("qveris 暂不支持 K 线")

    if source_name == "tavily":
        raise NotImplementedError("tavily 暂不支持 K 线")

    if source_name == "agent_browser":
        from . import agent_browser as w
        text = w.fetch_a_kline_via_sina(symbol)
        if text is None:
            return None, None
        raise NotImplementedError("agent_browser K 线解析待实现")

    raise ValueError(f"未知数据源: {source_name}")


# ============================================================
# 报价路由
# ============================================================
def route_quote(
    symbol: str,
) -> tuple[QuoteResult, str]:
    """报价路由：westock 优先（最稳定跨市场）。"""
    chain = _quote_chain()
    cfg = get_config()
    attempts: list[tuple[str, str]] = []

    for source_name in chain:
        if not cfg.enabled_quote_sources.get(source_name, False):
            continue

        try:
            quote = _call_quote_source(source_name, symbol)
            if quote is not None:
                logger.info("[router] quote %s → %s", symbol, source_name)
                return quote, source_name
            attempts.append((source_name, "返回 None"))
        except Exception as e:
            attempts.append((source_name, f"{type(e).__name__}: {e}"))
            logger.warning("[router] quote %s 失败 (%s): %s", source_name, symbol, e)

    raise AllSourcesFailedError(symbol, "quote", attempts)


def _call_quote_source(source_name: str, symbol: str) -> Optional[QuoteResult]:
    if source_name == "westock":
        from . import westock_wrapper as w
        return w.get_quote(symbol)

    if source_name == "qveris":
        from . import qveris_wrapper as w
        return w.get_quote(symbol)

    if source_name == "akshare":
        from . import akshare_wrapper as w
        market = detect_market(symbol)
        if market in (Market.HK, Market.US):
            raise NotImplementedError("akshare 报价当前仅支持 A 股")
        return w.get_quote_zh_a(symbol)

    if source_name == "tavily":
        raise NotImplementedError("tavily 不支持实时报价")

    if source_name == "agent_browser":
        raise NotImplementedError("agent_browser 报价待实现")

    raise ValueError(f"未知数据源: {source_name}")


# ============================================================
# 公告/新闻路由
# ============================================================
def route_news(
    query: str,
    max_results: int = 10,
) -> tuple[list[NewsItem], str]:
    """公告/新闻路由：westock 优先。"""
    chain = _news_chain()
    attempts: list[tuple[str, str]] = []

    for source_name in chain:
        try:
            items = _call_news_source(source_name, query, max_results)
            if items:
                logger.info("[router] news '%s' → %s (%d 条)", query, source_name, len(items))
                return items, source_name
            attempts.append((source_name, "空结果"))
        except Exception as e:
            attempts.append((source_name, f"{type(e).__name__}: {e}"))
            logger.warning("[router] news %s 失败 (%s): %s", source_name, query, e)

    raise AllSourcesFailedError(query, "news", attempts)


def _call_news_source(
    source_name: str,
    query: str,
    max_results: int,
) -> list[NewsItem]:
    if source_name == "westock":
        from . import westock_wrapper as w
        df = w.search(query)
        return [
            NewsItem(
                title=str(row.get("name", "")),
                url="",
                content="",
                published_at="",
                source="westock:search",
                tier=1,
            )
            for _, row in df.iterrows()
        ]

    if source_name == "qveris":
        from . import qveris_wrapper as w
        return w.search_finance_news(query, count=max_results)

    if source_name == "akshare":
        from . import akshare_wrapper as w
        df = w.get_disclosure_zh_a(query)
        items = []
        for _, row in df.iterrows():
            title = str(row.get("公告标题", row.get("title", "")))
            if not title:
                continue
            items.append(NewsItem(
                title=title,
                url=str(row.get("公告链接", row.get("url", ""))),
                published_at=str(row.get("公告时间", row.get("date", ""))),
                source="akshare:disclosure",
                tier=1,
            ))
            if len(items) >= max_results:
                break
        return items

    if source_name == "tavily":
        from . import tavily_wrapper as w
        return w.search_news(query, max_results=max_results, topic="finance")

    if source_name == "agent_browser":
        raise NotImplementedError("agent_browser 公告爬取待实现")

    raise ValueError(f"未知数据源: {source_name}")


# ============================================================
# 自检
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    print("=== 跨市场 K 线测试 ===")
    for sym, mkt in [("sh600519", Market.A_SH), ("hk00700", Market.HK),
                     ("usAAPL", Market.US), ("sh510300", Market.A_SH)]:
        try:
            df, src = route_kline(sym, market=mkt, days=10)
            print(f"  {sym} ({mkt.value}): {len(df)} 行, 来源: {src}, 列: {list(df.columns)}")
        except Exception as e:
            print(f"  {sym} ({mkt.value}): FAIL - {e}")

    print()
    print("=== 跨市场报价测试 ===")
    for sym in ["sh600519", "hk00700", "usAAPL"]:
        try:
            quote, src = route_quote(sym)
            print(f"  {sym}: {quote.currency} {quote.price} (来源: {src})")
        except Exception as e:
            print(f"  {sym}: FAIL - {e}")

    print()
    print("[OK] router.py self-check passed")