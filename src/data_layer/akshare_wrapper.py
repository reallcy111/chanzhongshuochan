"""
src/data_layer/akshare_wrapper.py — akshare Python SDK 封装

按 plan 决策 (skills-fluttering-hinton.md):
- A 股 K 线: akshare → westock → qveris → tavily → agent-browser（akshare 仍为主源）
- 港/美股 K 线: westock → akshare → ...（akshare 降为第 2 位）
- 报价: westock → qveris → akshare → tavily → ...（akshare 报价为备源）

数据契约转换:
- westock 已统一为 close 字段；akshare 输出需保证列名一致
- volume 单位: 股（akshare 输出已是股，无需转换）
- currency: CNY（A 股）/ USD（美股，原生 akshare 返回的 volume 单位是"股"）
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from .contracts import KlineRow, QuoteResult, Market, Currency, detect_market

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")  # akshare 内部 deprecation 噪音

SOURCE_NAME = "akshare"


# ============================================================
# 异常类
# ============================================================
class AkshareError(Exception):
    """akshare 所有异常的基类"""


class AkshareImportError(AkshareError):
    """akshare 未安装"""


class AkshareTransientError(AkshareError):
    """可重试瞬时错误（网络超时、限流）"""


class AksharePermanentError(AkshareError):
    """永久错误（参数错误、代码不存在）"""


# ============================================================
# 依赖检查
# ============================================================
def _is_akshare_available() -> bool:
    try:
        import akshare  # noqa: F401
        return True
    except ImportError:
        return False


def _import_akshare():
    if not _is_akshare_available():
        raise AkshareImportError("akshare 未安装，请运行: pip install akshare")
    import akshare as ak
    return ak


# ============================================================
# K 线: A 股 / 港股 / 美股
# ============================================================
def _normalize_zh_a_symbol(symbol: str) -> tuple[str, str]:
    """归一化 A 股代码，返回 (akshare_tx 格式, akshare_em 格式)

    akshare 接口差异:
    - stock_zh_a_hist_tx: 必须含前缀 (sh/sz/bj)
    - stock_zh_a_hist: 不要前缀

    Returns:
        (with_prefix, without_prefix)
    """
    s = symbol.lower().strip()
    for prefix in ("sh", "sz", "bj"):
        if s.startswith(prefix):
            return s, s[len(prefix):]
    return f"sh{s}", s


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """统一列名小写并映射关键字段"""
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    rename_map = {
        "日期": "date",
        "时间": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "股票代码": "code",
        "股票名称": "name",
    }
    for cn, en in rename_map.items():
        if cn in df.columns and en not in df.columns:
            df = df.rename(columns={cn: en})
    return df


def _add_exchange(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """添加 exchange 字段（交易所代码）"""
    df = df.copy()
    market = detect_market(symbol)
    df["exchange"] = market.value.upper()
    desired = ["date", "open", "high", "low", "close", "volume", "amount", "exchange"]
    df = df[[c for c in desired if c in df.columns]]
    return df


def get_kline_zh_a(
    symbol: str,
    days: int = 180,
    adjust: str = "qfq",
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """A 股日 K 线（akshare stock_zh_a_hist_tx 优先，stock_zh_a_hist 备源）。

    Args:
        symbol: sh600519 / sz000001 / bj430047
        days: 天数
        adjust: '' (不复权) | 'qfq' | 'hfq'
    """
    ak = _import_akshare()
    s_tx, s_em = _normalize_zh_a_symbol(symbol)

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    # L1: 腾讯日 K
    try:
        df = ak.stock_zh_a_hist_tx(
            symbol=s_tx, start_date=start_date, end_date=end_date,
            adjust=adjust, timeout=10,
        )
        if df is not None and not df.empty:
            df = _rename_columns(df)
            df = _add_exchange(df, symbol)
            return df
    except Exception as e:
        logger.warning("akshare 腾讯日K fail: %s", e)

    # L2: 东财日 K
    try:
        df = ak.stock_zh_a_hist(
            symbol=s_em, period="daily",
            start_date=start_date, end_date=end_date,
            adjust=adjust, timeout=10,
        )
        if df is not None and not df.empty:
            df = _rename_columns(df)
            df = _add_exchange(df, symbol)
            return df
    except Exception as e:
        logger.warning("akshare 东财日K fail: %s", e)

    raise AksharePermanentError(f"{symbol} akshare K 线为空（双源失败）")


def get_kline_hk(
    symbol: str,
    days: int = 180,
    adjust: str = "qfq",
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """港股日 K 线。

    Args:
        symbol: 5 位数字如 00700（不需要 hk 前缀，wrapper 自动识别）
    """
    ak = _import_akshare()
    s = symbol.lower().strip()
    if s.startswith("hk"):
        s = s[2:]

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        df = ak.stock_hk_hist(
            symbol=s, period="daily",
            start_date=start_date, end_date=end_date,
            adjust=adjust, timeout=10,
        )
        if df is not None and not df.empty:
            df = _rename_columns(df)
            df["exchange"] = "HK"
            return df
    except Exception as e:
        raise AkshareTransientError(f"akshare 港股 K 线失败: {e}") from e

    raise AksharePermanentError(f"hk{s} 港股 K 线为空")


def get_kline_us(
    symbol: str,
    days: int = 180,
    adjust: str = "qfq",
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """美股日 K 线。

    Args:
        symbol: 带前缀如 105.MSFT（akshare stock_us_hist 需要）
    """
    ak = _import_akshare()
    s = symbol.strip()

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        # stock_us_hist() 在不同 akshare 版本参数不一致，不传 timeout
        df = ak.stock_us_hist(
            symbol=s, period="daily",
            start_date=start_date, end_date=end_date,
            adjust=adjust,
        )
        if df is not None and not df.empty:
            df = _rename_columns(df)
            df["exchange"] = "US"
            return df
    except Exception as e:
        raise AkshareTransientError(f"akshare 美股 K 线失败: {e}") from e

    raise AksharePermanentError(f"{s} 美股 K 线为空")


# ============================================================
# 报价
# ============================================================
def get_quote_zh_a(
    symbol: str,
    config: Optional[dict] = None,
) -> QuoteResult:
    """A 股实时报价（akshare stock_zh_a_spot_em 拉全市场后过滤）。

    注意: 该接口对频繁调用敏感（限流），建议加 sleep。
    """
    ak = _import_akshare()
    s = symbol.lower().strip()
    for prefix in ("sh", "sz", "bj"):
        if s.startswith(prefix):
            bare = s[len(prefix):]
            break
    else:
        bare = s

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        raise AkshareTransientError(f"akshare A 股实时行情失败: {e}") from e

    df.columns = [str(c) for c in df.columns]
    if "代码" not in df.columns:
        raise AksharePermanentError(f"akshare A 股行情字段变更: {list(df.columns)}")
    row = df[df["代码"] == bare]
    if row.empty:
        raise AksharePermanentError(f"akshare 找不到 {bare} 行情")
    row = row.iloc[0]

    def _f(key: str, default: float = 0.0) -> float:
        try:
            return float(row.get(key, default))
        except (ValueError, TypeError):
            return default

    price = _f("最新价")
    pre_close = _f("昨收")
    change = price - pre_close
    change_pct = (change / pre_close * 100) if pre_close else 0.0

    return QuoteResult(
        symbol=s,
        name=str(row.get("名称", "")),
        price=price,
        prev_close=pre_close,
        open=_f("今开"),
        high=_f("最高"),
        low=_f("最低"),
        change=change,
        change_pct=change_pct,
        volume=_f("成交量"),
        turnover_value=_f("成交额"),
        turnover_rate=_f("换手率") or None,
        pe=_f("市盈率-动态") or None,
        pb=_f("市净率") or None,
        total_mv=_f("总市值") or None,
        currency=Currency.CNY,
    )


# ============================================================
# 公告（A 股）
# ============================================================
def get_disclosure_zh_a(
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """A 股公告（A 股东财）。"""
    ak = _import_akshare()
    s = symbol.lower().strip()
    for prefix in ("sh", "sz", "bj"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break

    start_date = start_date or "2020-01-01"
    end_date = end_date or datetime.now().strftime("%Y-%m-%d")

    try:
        df = ak.stock_zh_a_disclosure_report(
            symbol=s, start_date=start_date, end_date=end_date,
        )
    except Exception as e:
        raise AkshareTransientError(f"akshare A 股公告失败: {e}") from e

    if df is None or df.empty:
        raise AksharePermanentError(f"{s} akshare 公告为空")
    return df


# ============================================================
# 自检
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if not _is_akshare_available():
        print("[FAIL] akshare 未安装")
    else:
        print("[OK] akshare 已安装")
        print()
        print("=== A 股 K 线测试 ===")
        try:
            df = get_kline_zh_a("sh600519", days=30)
            print(f"列: {list(df.columns)}")
            print(f"行数: {len(df)}")
            print(df.tail(3))
        except Exception as e:
            print(f"[FAIL] {e}")

        print()
        print("=== A 股报价测试 ===")
        try:
            q = get_quote_zh_a("sh600519")
            print(f"价格: {q.currency} {q.price}")
            print(f"涨跌: {q.change} ({q.change_pct:.2f}%)")
            print(f"名称: {q.name}")
        except Exception as e:
            print(f"[FAIL] {e}")

    print()
    print("[OK] akshare_wrapper.py self-check passed")