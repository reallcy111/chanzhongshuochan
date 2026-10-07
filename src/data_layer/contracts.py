"""
src/data_layer/contracts.py — 缠中说禅 skill 数据契约

统一 5 个数据源 (westock / akshare / qveris / tavily / agent-browser)
的输出格式，确保 router + reliability 上层无需关心数据源差异。

按 plan 决策 (skills-fluttering-hinton.md):
- 不可变数据 (dataclass frozen=True)
- 必填 currency 字段（港股 HKD / 美股 USD，禁用人民币符号）
- 统一单位: volume 为"股" (westock 返回"手"，wrapper ×100)，amount 为"元"
- westock 'last' → contracts 'close'
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ============================================================
# 枚举
# ============================================================
class Market(str, Enum):
    """市场分类（按 westock 前缀）"""
    A_SH = "sh"      # 沪市/科创板
    A_SZ = "sz"      # 深市
    A_BJ = "bj"      # 北交所
    HK = "hk"        # 港股
    US = "us"        # 美股
    IDX = "idx"      # 指数（用 sh/sz 前缀）
    ETF = "etf"      # ETF（用 sh/sz 前缀）
    SECTOR = "pt"    # 板块


class Currency(str, Enum):
    """货币单位（key: currency 字段使用）"""
    CNY = "CNY"   # 人民币（A 股）
    HKD = "HKD"   # 港元（港股）
    USD = "USD"   # 美元（美股）

    @classmethod
    def for_market(cls, market: "Market") -> "Currency":
        """根据市场推断货币"""
        if market == Market.HK:
            return cls.HKD
        if market == Market.US:
            return cls.USD
        return cls.CNY


class Period(str, Enum):
    """K 线周期"""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    SEASON = "season"
    YEAR = "year"


class Adjust(str, Enum):
    """复权类型"""
    QFQ = "qfq"   # 前复权（推荐）
    HFQ = "hfq"   # 后复权
    BFQ = "bfq"   # 不复权


# ============================================================
# 数据契约（frozen=True 不可变）
# ============================================================
@dataclass(frozen=True)
class KlineRow:
    """K 线单条记录（统一 DataFrame 行）。

    字段约定:
    - volume 单位: 股（westock 返回手，wrapper 内 ×100）
    - amount 单位: 元
    - exchange: 交易所代码（"SH"/"SZ"/"HK"/"US"），非换手率
    """
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None
    exchange: str | None = None


@dataclass(frozen=True)
class QuoteResult:
    """实时报价（统一结果）。

    currency 字段强制必填: 港股 HKD / 美股 USD / A 股 CNY。
    展示层禁止套人民币符号（westock-data 文档规定）。

    v0.6.2 新增 staleness_minutes: 数据新鲜度（分钟），从分钟行情末行时间算
    > 60 分钟时建议视为过期。None 表示不可计算（如非 westock 数据源）。
    """
    symbol: str
    name: str
    price: float
    prev_close: float
    open: float
    high: float
    low: float
    change: float
    change_pct: float
    volume: float
    turnover_value: float
    turnover_rate: float | None = None
    pe: float | None = None
    pb: float | None = None
    total_mv: float | None = None
    currency: Currency = Currency.CNY
    staleness_minutes: int | None = None


@dataclass(frozen=True)
class FinanceRow:
    """财务报表单行（财报字段不固定，用 dict 存）。"""
    symbol: str
    end_date: str
    fields: dict[str, float] = field(default_factory=dict)
    currency: Currency = Currency.CNY


@dataclass(frozen=True)
class NewsItem:
    """新闻/公告单条（tier 按 Nuwa 规则: 1=一手, 2=二手）。"""
    title: str
    url: str = ""
    content: str = ""
    published_at: str = ""
    source: str = ""
    tier: int = 2


# ============================================================
# 工具函数
# ============================================================
def detect_market(symbol: str) -> Market:
    """从 westock 格式 symbol 前缀识别市场。

    Args:
        symbol: westock 格式代码，如 sh600519 / hk00700 / usAAPL

    Returns:
        Market 枚举

    Raises:
        ValueError: 无法识别的 symbol 前缀
    """
    s = symbol.lower().strip()
    if s.startswith("sh") or s.startswith("sz") or s.startswith("bj"):
        return Market(s[:2])
    if s.startswith("hk"):
        return Market.HK
    if s.startswith("us"):
        return Market.US
    if s.startswith("pt"):
        return Market.SECTOR
    raise ValueError(f"无法识别 symbol: {symbol}")


def detect_currency(symbol: str) -> Currency:
    """从 symbol 推断货币（高层 API 便捷方法）。"""
    return Currency.for_market(detect_market(symbol))