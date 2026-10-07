#!/usr/bin/env python3
"""分型识别模块测试（v0.6.2 修复 — 函数名 detect_top_fenxing → identify_fenxing）

原 tests/test_fenxing.py 引入了 src.fenxing 中不存在的 detect_top_fenxing / detect_bottom_fenxing，
src.fenxing 实际只导出 identify_fenxing（按缠论标准合并识别顶/底分型）。

本文件替换原内容，直接测试 identify_fenxing 的真实签名。
"""

import sys
import logging

import pandas as pd
import numpy as np

# 关闭 fenxing 内部的 logging.basicConfig（pytest 收集时避免重复配置）
logging.disable(logging.CRITICAL)

from src.fenxing import (
    identify_fenxing,
    filter_valid_fenxing,
    get_fenxing_pairs,
    Fenxing,
)


def _make_klines(highs, lows):
    """便捷构造 K 线 DataFrame（用 high/low 计算 open/close）。"""
    return pd.DataFrame({
        "open": [(h + l) / 2 for h, l in zip(highs, lows)],
        "high": highs,
        "low": lows,
        "close": [(h + l) / 2 for h, l in zip(highs, lows)],
    })


def test_top_fenxing_basic():
    """中间 K 线高点最高 → 顶分型（i=1）"""
    klines = _make_klines(
        highs=[10.0, 11.0, 10.5],
        lows=[9.5, 10.8, 10.0],
    )
    result = identify_fenxing(klines)
    assert len(result) == 1, f"应有 1 个分型，实际 {len(result)}"
    fx = result[0]
    assert fx.type == "top", f"应为顶分型，实际 {fx.type}"
    assert fx.index == 1, f"索引应为 1，实际 {fx.index}"
    assert fx.high == 11.0
    assert fx.low == 10.8
    print("✅ 顶分型基础识别通过")


def test_bottom_fenxing_basic():
    """中间 K 线低点最低 → 底分型（i=1）"""
    klines = _make_klines(
        highs=[10.5, 10.0, 10.2],
        lows=[10.0, 9.5, 9.8],
    )
    result = identify_fenxing(klines)
    assert len(result) == 1, f"应有 1 个分型，实际 {len(result)}"
    fx = result[0]
    assert fx.type == "bottom", f"应为底分型，实际 {fx.type}"
    assert fx.index == 1
    assert fx.low == 9.5
    print("✅ 底分型基础识别通过")


def test_top_and_bottom_together():
    """K 线序列中同时含顶/底分型"""
    klines = _make_klines(
        highs=[10.0, 11.0, 10.2, 11.5, 10.3],
        lows=[9.5, 10.5, 9.5, 10.8, 9.8],
    )
    result = identify_fenxing(klines)
    types = [fx.type for fx in result]
    assert "top" in types, f"应含顶分型，实际 {types}"
    assert "bottom" in types, f"应含底分型，实际 {types}"
    print(f"✅ 顶底分型混合识别通过 ({len(result)} 个分型: {types})")


def test_identify_fenxing_insufficient_data():
    """数据不足 3 根 → ValueError"""
    try:
        identify_fenxing(_make_klines([10.0], [9.0]))
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "3" in str(e) or "至少" in str(e)
        print(f"✅ 数据不足正确抛错: {e}")


def test_identify_fenxing_missing_columns():
    """缺少 high/low 列 → ValueError"""
    try:
        identify_fenxing(pd.DataFrame({"open": [1, 2, 3], "close": [1, 2, 3]}))
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        print(f"✅ 缺列正确抛错: {e}")


def test_filter_valid_fenxing():
    """过滤有效分型（顶底交替 + 最小间隔）"""
    klines = _make_klines(
        highs=[10, 11, 10.5, 9.0, 10.0, 11.0],
        lows=[9.5, 10.5, 10.0, 8.5, 9.5, 10.5],
    )
    fenxing_list = identify_fenxing(klines)
    filtered = filter_valid_fenxing(fenxing_list, min_distance=1)
    assert all(isinstance(fx, Fenxing) for fx in filtered)
    print(f"✅ filter_valid_fenxing 通过 ({len(fenxing_list)} -> {len(filtered)})")


def test_get_fenxing_pairs():
    """顶底分型配对"""
    klines = _make_klines(
        highs=[10, 11, 10.5, 9.0, 10.0, 11.0, 9.5],
        lows=[9.5, 10.5, 10.0, 8.5, 9.5, 10.5, 9.0],
    )
    fenxing_list = identify_fenxing(klines)
    filtered = filter_valid_fenxing(fenxing_list, min_distance=1)
    pairs = get_fenxing_pairs(filtered)
    for fx1, fx2 in pairs:
        assert fx1.type != fx2.type, f"分型对必须交替: {fx1.type} -> {fx2.type}"
    print(f"✅ get_fenxing_pairs 通过 ({len(pairs)} 对)")


def test_random_data_stability():
    """随机数据：至少识别出 1 个分型"""
    np.random.seed(42)
    n = 50
    base = 100 + np.random.randn(n).cumsum() / 10
    highs = (base + np.abs(np.random.randn(n))).tolist()
    lows = (base - np.abs(np.random.randn(n))).tolist()
    klines = _make_klines(highs, lows)
    fenxing_list = identify_fenxing(klines)
    top_count = sum(1 for fx in fenxing_list if fx.type == "top")
    bottom_count = len(fenxing_list) - top_count
    print(f"✅ 随机数据分型识别: 共 {len(fenxing_list)} (顶 {top_count}, 底 {bottom_count})")
    assert len(fenxing_list) > 0, "随机数据应至少识别出 1 个分型"


if __name__ == "__main__":
    test_top_fenxing_basic()
    test_bottom_fenxing_basic()
    test_top_and_bottom_together()
    test_identify_fenxing_insufficient_data()
    test_identify_fenxing_missing_columns()
    test_filter_valid_fenxing()
    test_get_fenxing_pairs()
    test_random_data_stability()
    print("\n✅ 所有 fenxing 测试通过！")
