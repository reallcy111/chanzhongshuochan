"""
src/main.py — 缠中说禅技能 v0.6 引导式入口

按 plan 决策 (skills-fluttering-hinton.md):
- Phase D 重写 main.py（v0.5.x 已归档）
- 引导式询问用户输入（symbol/level/days/initial_trend）
- 用 router 路由 K 线 + 报价（不直接调 wrapper）
- 跑核心缠论算法（kline → fenxing → bi → zhongshu → beichi → maimaidian）
- 返回 dict（OpenClaw skill prompt 可直接渲染）

调用方式:
    from src.main import analyze_symbol
    result = analyze_symbol("sh600519", days=120)
    # 或 CLI:
    python -m src.main
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Optional

from . import (
    simplify_klines,
    identify_fenxing,
    filter_valid_fenxing,
    identify_bis,
    validate_bis,
    identify_zhongshu,
    calculate_macd,
    detect_trend_beichi,
    detect_all_trend_beichis,
    identify_buy_sell_points,
)
from .data_layer import route_kline, route_quote
from .data_layer.contracts import QuoteResult

logger = logging.getLogger(__name__)


# ============================================================
# 高层入口（OpenClaw 调用）
# ============================================================
def analyze_symbol(
    symbol: str,
    name: str = "",
    days: int = 120,
    initial_trend: str = "up",
    with_quote: bool = True,
) -> dict:
    """分析一只股票，返回结构化结果（Mavis skill 调用方使用）。

    Args:
        symbol: westock 格式（sh600519 / hk00700 / usAAPL）
        name: 股票名称（可选）
        days: K 线天数（默认 120）
        initial_trend: 初始趋势 up/down
        with_quote: 是否获取实时报价

    Returns:
        dict 含 kline / fenxing / bis / zhongshus / macd / beichi / maimaidian / quote
    """
    symbol = symbol.lower().strip()
    result: dict = {
        "symbol": symbol,
        "name": name,
        "timestamp": datetime.now().isoformat(),
        "status": "ok",
        "errors": [],
    }

    # 1. 拉 K 线（router 5 级降级）
    try:
        df, source = route_kline(symbol, days=days)
        result["kline_source"] = source
        result["kline_rows"] = len(df)
        if df.empty:
            result["status"] = "no_data"
            result["errors"].append("K 线为空")
            return result
    except Exception as e:
        result["status"] = "error"
        result["errors"].append(f"获取 K 线失败: {e}")
        logger.exception("analyze_symbol: K 线失败")
        return result

    # 1.5 K 线位置摘要（P0 修复 — 真实"当前价"，不是 recent_fenxing）
    # 见 tests/chanzhongshuochan-issues-20260624.md P0
    try:
        last = df.iloc[-1]
        result["kline_latest"] = {
            "date": str(last["date"]),
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
            # akshare 列只有 amount,没有 volume;westock 才有 volume。用 .get 兼容两者
            "volume": float(last["volume"]) if "volume" in df.columns else 0.0,
            "amount": float(last["amount"]) if "amount" in df.columns else 0.0,
            "exchange": str(last.get("exchange", "")),
        }
        result["kline_latest_close"] = float(last["close"])
        result["kline_latest_date"] = str(last["date"])

        tail = df.tail(30)
        if len(tail) >= 2:
            start_close = float(tail["close"].iloc[0])
            end_close = float(tail["close"].iloc[-1])
            result["kline_range_30d"] = {
                "high": float(tail["high"].max()),
                "low": float(tail["low"].min()),
                "start_close": start_close,
                "end_close": end_close,
                "change_pct": (end_close / start_close - 1) * 100 if start_close else 0.0,
                "trading_days": len(tail),
            }
        else:
            result["kline_range_30d"] = None
    except Exception as e:
        logger.warning("K 线位置摘要计算失败: %s", e)

    # 2. 缠论算法
    try:
        simplified = simplify_klines(df, initial_trend=initial_trend)
        fenxing_list = filter_valid_fenxing(identify_fenxing(simplified))
        result["fenxing_count"] = len(fenxing_list)

        bis = validate_bis(identify_bis(fenxing_list, df))
        result["bi_count"] = len(bis)

        zhongshus = identify_zhongshu(bis)
        result["zhongshu_count"] = len(zhongshus)

        macd_result = calculate_macd(df)
        result["macd_stats"] = macd_result.get("statistics", {})

        beichis = detect_all_trend_beichis(bis, macd_result)
        result["beichi_count"] = len(beichis)

        maimaidians = identify_buy_sell_points(bis, zhongshus, beichis) or []
        result["maimaidian_count"] = len(maimaidians)

        result["recent_fenxing"] = [_fenxing_to_dict(f) for f in fenxing_list[-5:]]
        result["recent_bi"] = [_bi_to_dict(b) for b in bis[-5:]]
        result["recent_maimaidian"] = [_maimaidian_to_dict(m) for m in maimaidians[-5:]]

    except Exception as e:
        result["status"] = "partial"
        result["errors"].append(f"缠论算法失败: {e}")
        logger.exception("analyze_symbol: 缠论算法失败")

    # 3. 报价（可选）
    if with_quote:
        try:
            quote, qsrc = route_quote(symbol)
            result["quote_source"] = qsrc
            result["quote"] = _quote_to_dict(quote)
        except Exception as e:
            result["errors"].append(f"报价失败: {e}")
            logger.warning("analyze_symbol: 报价失败: %s", e)

    return result


# ============================================================
# 数据类 → dict 转换（OpenClaw JSON 序列化）
# ============================================================
def _fenxing_to_dict(f) -> dict:
    return {
        "type": getattr(f, "type", ""),
        "index": getattr(f, "index", -1),
        "high": getattr(f, "high", 0.0),
        "low": getattr(f, "low", 0.0),
        "kline_index": getattr(f, "kline_index", -1),
    }


def _bi_to_dict(b) -> dict:
    return {
        "start_index": getattr(b, "start_index", -1),
        "end_index": getattr(b, "end_index", -1),
        "start_type": getattr(b, "start_type", ""),
        "end_type": getattr(b, "end_type", ""),
        "start_price": getattr(b, "start_price", 0.0),
        "end_price": getattr(b, "end_price", 0.0),
        "kline_count": getattr(b, "kline_count", 0),
        "amplitude": getattr(b, "amplitude", 0.0),
    }


def _maimaidian_to_dict(m) -> dict:
    return {
        "point_type": getattr(m, "point_type", ""),
        "index": getattr(m, "index", -1),
        "price": getattr(m, "price", 0.0),
        "confidence": getattr(m, "confidence", 0.0),
        "description": getattr(m, "description", ""),
    }


def _quote_to_dict(q: QuoteResult) -> dict:
    return {
        "symbol": q.symbol,
        "name": q.name,
        "price": q.price,
        "prev_close": q.prev_close,
        "change": q.change,
        "change_pct": q.change_pct,
        "volume": q.volume,
        "turnover_value": q.turnover_value,
        "currency": q.currency.value,
    }


# ============================================================
# 引导式 CLI（OpenClaw prompt 入口）
# ============================================================
def _prompt_user(prompt: str, default: str = "") -> str:
    """简单的输入提示（带默认值）"""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input or default
    return input(f"{prompt}: ").strip()


def main() -> int:
    """OpenClaw prompt 引导式入口（也可 python -m src.main 直接跑）"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 60)
    print("缠中说禅 skill v0.6")
    print("=" * 60)

    symbol = _prompt_user("股票代码", "sh600519")
    name = _prompt_user("股票名称（可选）", "")
    days_str = _prompt_user("K 线天数", "120")
    try:
        days = int(days_str)
    except ValueError:
        days = 120
    initial_trend = _prompt_user("初始趋势 (up/down)", "up")
    if initial_trend not in ("up", "down"):
        initial_trend = "up"

    print()
    print(f"开始分析: {symbol} ({name or '未命名'})")
    print(f"  K 线: {days} 天, 初始趋势: {initial_trend}")
    print()

    result = analyze_symbol(
        symbol=symbol, name=name, days=days, initial_trend=initial_trend,
    )

    print("-" * 60)
    print(f"状态: {result['status']}")
    print(f"K 线来源: {result.get('kline_source', 'N/A')}, 行数: {result.get('kline_rows', 0)}")
    print(f"分型: {result.get('fenxing_count', 0)} 个")
    print(f"笔:   {result.get('bi_count', 0)} 个")
    print(f"中枢: {result.get('zhongshu_count', 0)} 个")
    print(f"背驰: {result.get('beichi_count', 0)} 个")
    print(f"买卖点: {result.get('maimaidian_count', 0)} 个")

    if "quote" in result:
        q = result["quote"]
        print()
        print(f"报价 ({result.get('quote_source', 'N/A')}):")
        print(f"  {q['currency']} {q['price']:.2f} ({q['change_pct']:+.2f}%)")

    if result.get("errors"):
        print()
        print("错误:")
        for err in result["errors"]:
            print(f"  - {err}")

    if result.get("recent_maimaidian"):
        print()
        print("最近买卖点:")
        for m in result["recent_maimaidian"]:
            print(f"  - [{m['point_type']}] {m['description']} @ {m['price']:.2f}")

    print()
    print("=" * 60)
    return 0 if result["status"] != "error" else 1


# ============================================================
# CLI 入口
# ============================================================
if __name__ == "__main__":
    sys.exit(main())