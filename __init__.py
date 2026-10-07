"""
缠中说禅技能 v0.6 — westock-data 整合版
==========================================

v0.6 (2026-06-24) 主要变化:
  - 整合 westock-data（腾讯自选股 CLI）作为新一级数据源
  - 统一 data_layer 包（5 wrapper + router + contracts + reliability）
  - 删除 v0.5.x 的 data_fetcher / quant_detect / nuwa_pipeline
  - 引入 5 级降级链（按市场差异化）
  - 重写 main.py 为引导式入口

降级链 (v0.6):
- A 股 K 线:    akshare → westock → qveris → tavily → agent-browser
- 港/美 K 线:  westock → akshare → qveris → tavily → agent-browser
- 报价 (全):   westock → qveris → akshare → tavily → agent-browser

OpenClaw 调用方式:
    # Skill 入口（推荐）
    python -m src.main

    # 编程调用
    import sys
    sys.path.insert(0, '<skill_path>/src')
    from src.main import analyze_symbol
    result = analyze_symbol("sh600519", days=120)
"""

from src.main import analyze_symbol, main as run_main
from src.data_layer import (
    route_kline, route_quote, route_news,
    KlineRow, QuoteResult, NewsItem,
    Market, Currency, Period, Adjust,
    detect_market, detect_currency,
)

__version__ = "0.6.0"

__all__ = [
    "analyze_symbol",
    "run_main",
    "route_kline",
    "route_quote",
    "route_news",
    "KlineRow",
    "QuoteResult",
    "NewsItem",
    "Market",
    "Currency",
    "Period",
    "Adjust",
    "detect_market",
    "detect_currency",
]