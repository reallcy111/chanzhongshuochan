"""
缠中说禅技能 v0.6 — westock-data 整合 + 5 wrapper + router
============================================================

v0.6 (2026-06-24) 主要变化:
  - 新增 data_layer/ 包: 5 个数据源 wrapper (westock/akshare/qveris/tavily/agent-browser)
  - 新增 contracts.py: 统一数据契约（KlineRow/QuoteResult 含 currency 必填）
  - 新增 reliability.py: 重试/熔断/SQLite 缓存 + WestockError 映射
  - 新增 router.py: 按 market 5 级降级编排
  - 集成 westock 环境检查到 check_environment.py
  - 清理: quant_detect.py / qveris_client.py / data_fetcher.py / main.py / analyze_symbol.py
    全部归档到 archive/v0.5.x/

降级链 (v0.6):
- A 股 K 线:    akshare → westock → qveris → tavily → agent-browser
- 港/美 K 线:  westock → akshare → qveris → tavily → agent-browser
- 报价 (全):   westock → qveris → akshare → tavily → agent-browser

调用方式:
    from src.data_layer import route_kline, route_quote, route_news
    df, src = route_kline("sh600519", days=120)
    quote, src = route_quote("hk00700")
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 核心缠论模块
from kline import simplify_klines, process_containment
from fenxing import identify_fenxing, filter_valid_fenxing, get_fenxing_pairs, Fenxing
from bi import identify_bis, validate_bis, get_bi_statistics, Bi
from zhongshu import identify_zhongshu, check_zhongshu_breakout, get_zhongshu_statistics, Zhongshu
from macd import calculate_macd, get_macd_signals, get_macd_statistics
from beichi import detect_trend_beichi, detect_all_trend_beichis, Beichi
from maimaidian import identify_buy_sell_points, Maimaidian

# v0.6 数据获取层
from data_layer import (
    # 数据契约
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
    # 可靠性基础设施
    with_retry,
    cached,
    get_breaker,
    CircuitBreaker,
    DataSourceError,
    TransientError,
    PermanentError,
    # 路由器
    route_kline,
    route_quote,
    route_news,
)


__version__ = "0.6.0"

__all__ = [
    # 核心缠论
    'simplify_klines', 'process_containment',
    'identify_fenxing', 'filter_valid_fenxing', 'get_fenxing_pairs', 'Fenxing',
    'identify_bis', 'validate_bis', 'get_bi_statistics', 'Bi',
    'identify_zhongshu', 'check_zhongshu_breakout', 'get_zhongshu_statistics', 'Zhongshu',
    'calculate_macd', 'get_macd_signals', 'get_macd_statistics',
    'detect_trend_beichi', 'detect_all_trend_beichis', 'Beichi',
    'identify_buy_sell_points', 'Maimaidian',
    # v0.6 数据契约
    'KlineRow', 'QuoteResult', 'FinanceRow', 'NewsItem',
    'Market', 'Currency', 'Period', 'Adjust',
    'detect_market', 'detect_currency',
    # v0.6 可靠性
    'with_retry', 'cached', 'get_breaker', 'CircuitBreaker',
    'DataSourceError', 'TransientError', 'PermanentError',
    # v0.6 路由器
    'route_kline', 'route_quote', 'route_news',
]