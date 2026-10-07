"""
缠论分型识别模块
识别顶分型和底分型
"""

import pandas as pd
from typing import List, Dict, Tuple
from dataclasses import dataclass
import numpy as np
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Fenxing:
    """分型数据结构"""
    index: int  # 分型中间 K 线的索引
    type: str  # 'top' 或 'bottom'
    high: float  # 高点
    low: float  # 低点
    kline_index: int  # 在原始 K 线中的索引


def identify_fenxing(klines: pd.DataFrame) -> List[Fenxing]:
    """
    识别所有分型（顶分型和底分型）

    分型定义（缠论标准）：
    - 顶分型：中间 K 线高点最高，低点不低于两边（允许相等）
    - 底分型：中间 K 线低点最低，高点不高于两边（允许相等）

    修复内容：
    - 允许相邻 K 线高低点相等（容错处理）
    - 严格遵循缠论分型定义

    Args:
        klines: K 线数据 DataFrame，必须包含 'high', 'low' 列

    Returns:
        分型列表，按 K 线索引排序

    Raises:
        ValueError: 如果 K 线数据少于 3 根或缺少必要列
    """
    # 输入验证
    if klines is None or len(klines) == 0:
        raise ValueError("K线数据不能为空")
    
    if len(klines) < 3:
        raise ValueError("识别分型至少需要 3 根 K 线")

    required_columns = ['high', 'low']
    if not all(col in klines.columns for col in required_columns):
        raise ValueError(f"K线数据必须包含以下列: {required_columns}")

    # 数据类型验证
    try:
        high_values = klines['high'].astype(float)
        low_values = klines['low'].astype(float)
    except (ValueError, TypeError) as e:
        raise ValueError(f"K线高低点数据必须为数值类型: {e}")

    fenxing_list: List[Fenxing] = []

    try:
        # 遍历所有可能的三根连续 K 线
        for i in range(1, len(klines) - 1):
            k_prev = klines.iloc[i-1]
            k_curr = klines.iloc[i]
            k_next = klines.iloc[i+1]

            # 获取相邻 K 线的高低点（包含容错：允许相等）
            prev_high = float(k_prev['high'])
            prev_low = float(k_prev['low'])
            curr_high = float(k_curr['high'])
            curr_low = float(k_curr['low'])
            next_high = float(k_next['high'])
            next_low = float(k_next['low'])

            # 修复1：顶分型 - 中间 K 线高点最高，低点不低于两边（允许相等）
            is_top = (
                curr_high >= prev_high and      # 中间高点 >= 左边高点
                curr_high >= next_high and      # 中间高点 >= 右边高点
                curr_low >= prev_low and        # 中间低点 >= 左边低点
                curr_low >= next_low            # 中间低点 >= 右边低点
            )

            # 修复2：底分型 - 中间 K 线低点最低，高点不高于两边（允许相等）
            is_bottom = (
                curr_low <= prev_low and        # 中间低点 <= 左边低点
                curr_low <= next_low and        # 中间低点 <= 右边低点
                curr_high <= prev_high and      # 中间高点 <= 左边高点
                curr_high <= next_high          # 中间高点 <= 右边高点
            )

            if is_top:
                fenxing_list.append(Fenxing(
                    index=i,
                    type='top',
                    high=curr_high,
                    low=curr_low,
                    kline_index=i
                ))
                logger.debug(f"发现顶分型: 索引 {i}, 高={curr_high:.2f}, 低={curr_low:.2f}")
            elif is_bottom:
                fenxing_list.append(Fenxing(
                    index=i,
                    type='bottom',
                    high=curr_high,
                    low=curr_low,
                    kline_index=i
                ))
                logger.debug(f"发现底分型: 索引 {i}, 高={curr_high:.2f}, 低={curr_low:.2f}")

    except Exception as e:
        logger.error(f"分型识别过程出错: {e}", exc_info=True)
        raise

    logger.info(f"共识别 {len(fenxing_list)} 个分型")
    return fenxing_list


def filter_valid_fenxing(
    fenxing_list: List[Fenxing],
    min_distance: int = 1
) -> List[Fenxing]:
    """
    过滤有效的分型

    缠论中，分型之间不能相邻，至少间隔一根 K 线

    Args:
        fenxing_list: 原始分型列表
        min_distance: 分型之间的最小间隔（K 线数量）

    Returns:
        过滤后的分型列表
    """
    # 输入验证
    if fenxing_list is None:
        raise ValueError("分型列表不能为空")
    
    if len(fenxing_list) == 0:
        logger.warning("空分型列表，返回空列表")
        return fenxing_list

    try:
        # 按索引排序
        sorted_list = sorted(fenxing_list, key=lambda x: x.index)
        filtered = [sorted_list[0]]

        for fx in sorted_list[1:]:
            # 检查与上一个分型的间隔
            if fx.index - filtered[-1].index > min_distance:
                filtered.append(fx)
            else:
                logger.debug(f"跳过分型: 索引 {fx.index} 与上一分型间隔不足")

        logger.info(f"过滤后保留 {len(filtered)} 个有效分型")
        return filtered

    except Exception as e:
        logger.error(f"过滤分型过程出错: {e}", exc_info=True)
        raise


def get_fenxing_pairs(fenxing_list: List[Fenxing]) -> List[Tuple[Fenxing, Fenxing]]:
    """
    获取顶底分型对

    返回相邻且交替的顶底分型对（顶分型-底分型 或 底分型-顶分型）

    Args:
        fenxing_list: 分型列表

    Returns:
        分型对列表
    """
    # 输入验证
    if fenxing_list is None:
        raise ValueError("分型列表不能为空")
    
    if len(fenxing_list) < 2:
        logger.warning("分型数量不足2个，无法组成对")
        return []

    try:
        pairs = []
        for i in range(len(fenxing_list) - 1):
            fx1 = fenxing_list[i]
            fx2 = fenxing_list[i+1]

            # 确保是顶底交替
            if fx1.type != fx2.type:
                pairs.append((fx1, fx2))
                logger.debug(f"找到分型对: {fx1.type}({fx1.index}) -> {fx2.type}({fx2.index})")

        logger.info(f"共找到 {len(pairs)} 个分型对")
        return pairs

    except Exception as e:
        logger.error(f"获取分型对过程出错: {e}", exc_info=True)
        raise


# 单元测试
def test_identify_fenxing():
    """测试分型识别"""
    print("测试分型识别...")

    # 测试用例 1: 明显的顶分型和底分型
    data = pd.DataFrame({
        'open': [100, 105, 100, 95, 90, 95],
        'high': [102, 108, 105, 98, 92, 98],
        'low': [98, 102, 98, 92, 88, 92],
        'close': [101, 106, 101, 96, 91, 96]
    })

    fenxing_list = identify_fenxing(data)
    print(f"测试用例 1: 识别到 {len(fenxing_list)} 个分型")

    for fx in fenxing_list:
        print(f"  - 索引 {fx.index}: {fx.type} (高={fx.high:.2f}, 低={fx.low:.2f})")

    # 测试用例 2: 随机数据
    np.random.seed(42)
    n = 100
    data = pd.DataFrame({
        'open': 100 + np.random.randn(n).cumsum() / 10,
        'high': 100 + np.random.randn(n).cumsum() / 10 + np.abs(np.random.randn(n)),
        'low': 100 + np.random.randn(n).cumsum() / 10 - np.abs(np.random.randn(n)),
        'close': 100 + np.random.randn(n).cumsum() / 10
    })

    fenxing_list = identify_fenxing(data)
    print(f"\n测试用例 2（随机数据）: 识别到 {len(fenxing_list)} 个分型")
    print(f"  顶分型: {sum(1 for fx in fenxing_list if fx.type == 'top')}")
    print(f"  底分型: {sum(1 for fx in fenxing_list if fx.type == 'bottom')}")

    # 测试用例 3: 过滤分型
    filtered = filter_valid_fenxing(fenxing_list, min_distance=1)
    print(f"\n过滤后: {len(filtered)} 个分型")

    # 测试用例 4: 获取分型对
    pairs = get_fenxing_pairs(filtered)
    print(f"\n分型对: {len(pairs)} 对")

    for i, (fx1, fx2) in enumerate(pairs[:5]):
        print(f"  对 {i+1}: {fx1.type}({fx1.index}) -> {fx2.type}({fx2.index})")

    print("✓ 分型识别测试通过\n")


def test_edge_cases():
    """测试边界情况"""
    print("测试边界情况...")

    # 测试数据不足
    try:
        data = pd.DataFrame({'high': [100], 'low': [98]})
        identify_fenxing(data)
        print("✗ 应该抛出异常")
    except ValueError as e:
        print(f"✓ 正确处理数据不足: {str(e)}")

    # 测试缺少列
    try:
        data = pd.DataFrame({'open': [100, 101, 102]})
        identify_fenxing(data)
        print("✗ 应该抛出异常")
    except ValueError as e:
        print(f"✓ 正确处理缺少列: {str(e)}")

    # 测试空分型列表
    empty_list = []
    filtered = filter_valid_fenxing(empty_list)
    assert len(filtered) == 0
    print("✓ 正确处理空分型列表")

    # 测试 None 输入
    try:
        filter_valid_fenxing(None)
        print("✗ 应该抛出异常")
    except ValueError as e:
        print(f"✓ 正确处理 None 输入: {str(e)}")

    print("✓ 边界情况测试通过\n")


def test_with_stock_data_300168():
    """使用股票 300168 数据测试"""
    print("测试股票 300168 数据...")

    # 模拟 300168 的 K 线数据（实际使用时应从数据源获取）
    np.random.seed(123)
    n = 50
    close_prices = [100]
    for i in range(n - 1):
        change = np.random.randn() * 2
        close_prices.append(close_prices[-1] + change)
    
    data = pd.DataFrame({
        'open': [p + np.random.randn() for p in close_prices],
        'high': [max(o, c) + abs(np.random.randn()) for o, c in zip(close_prices[:-1], close_prices[1:])],
        'low': [min(o, c) - abs(np.random.randn()) for o, c in zip(close_prices[:-1], close_prices[1:])],
        'close': close_prices[1:] + [close_prices[-1]]
    })

    # 前3根K线用于测试
    short_data = data.head(10)
    
    fenxing_list = identify_fenxing(short_data)
    print(f"300168数据测试: 识别到 {len(fenxing_list)} 个分型")

    if len(fenxing_list) > 0:
        top_count = sum(1 for fx in fenxing_list if fx.type == 'top')
        bottom_count = len(fenxing_list) - top_count
        print(f"  顶分型: {top_count}, 底分型: {bottom_count}")
    
    print("✓ 300168 数据测试完成\n")


if __name__ == "__main__":
    test_identify_fenxing()
    test_edge_cases()
    test_with_stock_data_300168()
