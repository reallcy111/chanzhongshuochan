"""
src/data_layer — 缠中说禅 skill 数据获取层（v0.6 重构）

按 plan 决策 (skills-fluttering-hinton.md):
- 5 个 wrapper: westock / akshare / qveris / tavily / agent-browser
- 统一数据契约（contracts.py）：close 字段 + currency 必填
- 可靠性基础设施（reliability.py）：重试/熔断/缓存
- 多源路由（router.py）：按 market 5 级降级

降级链 (v0.6 含 westock-data):
- A 股 K 线: akshare → westock → qveris → tavily → agent-browser
- 港/美 K 线: westock → akshare → qveris → tavily → agent-browser
- 报价 (全):  westock → qveris → akshare → tavily → agent-browser

调用示例:
    from src.data_layer import route_kline, route_quote
    df, src = route_kline("sh600519", days=120)
    quotes, src = route_quote("sh600519")
"""

from .contracts import (
    KlineRow,
    QuoteResult,
    FinanceRow,
    NewsItem,
    Market,
    Currency,
    Period,
    Adjust,
    detect_market,
    detect_currency,
)

# reliability: 异常 + 重试 + 熔断 + 缓存
from .reliability import (
    DataSourceError,
    TransientError,
    PermanentError,
    RateLimitError,
    with_retry,
    CircuitBreaker,
    get_breaker,
    reset_all_breakers,
    Cache,
    get_cache,
    cached,
    classify_westock_error,
)

# router: 5 级降级编排
from .router import (
    RouterError,
    AllSourcesFailedError,
    RouterConfig,
    get_config as get_router_config,
    disable_source,
    route_kline,
    route_quote,
    route_news,
)

__version__ = "0.6.0"

__all__ = [
    # 数据契约
    "KlineRow", "QuoteResult", "FinanceRow", "NewsItem",
    "Market", "Currency", "Period", "Adjust",
    "detect_market", "detect_currency",
    # 可靠性
    "DataSourceError", "TransientError", "PermanentError", "RateLimitError",
    "with_retry", "CircuitBreaker", "get_breaker", "reset_all_breakers",
    "Cache", "get_cache", "cached", "classify_westock_error",
    # 路由器
    "RouterError", "AllSourcesFailedError", "RouterConfig",
    "get_router_config", "disable_source",
    "route_kline", "route_quote", "route_news",
]