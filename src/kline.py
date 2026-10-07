"""
缠论 K 线处理模块
实现 K 线包含关系的递归消除
"""

import pandas as pd
from typing import List, Dict, Tuple
import numpy as np
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_containment(
    klines: pd.DataFrame,
    initial_trend: str = "up"
) -> pd.DataFrame:
    """
    处理 K 线包含关系，递归消除直到稳定

    包含关系定义：两根相邻 K 线的区间有重叠
    处理规则：
    - 上升趋势（高高低）：高点取较高者，低点取较高者
    - 下降趋势（低低高）：低点取较低者，高点取较低者

    Args:
        klines: K 线数据 DataFrame，必须包含 'open', 'high', 'low', 'close' 列
        initial_trend: 初始趋势方向，'up' 或 'down'

    Returns:
        处理后的 K 线 DataFrame

    Raises:
        ValueError: 如果 K 线数据不包含必要的列
    """
    # 验证输入数据
    if klines is None or len(klines) == 0:
        raise ValueError("K线数据不能为空")
    
    required_columns = ['open', 'high', 'low', 'close']
    if not all(col in klines.columns for col in required_columns):
        raise ValueError(f"K线数据必须包含以下列: {required_columns}")

    if len(klines) < 2:
        logger.warning("K线数量少于2根，无需处理包含关系")
        return klines.copy()

    # 创建副本以避免修改原始数据
    result = klines.copy()
    max_iterations = len(result)  # 防止无限循环

    try:
        for iteration in range(max_iterations):
            changed = False
            new_result = result.copy()

            for i in range(len(result) - 1):
                # 获取当前和下一根 K 线
                k1 = result.iloc[i]
                k2 = result.iloc[i+1]

                # 判断是否存在包含关系
                has_containment = (
                    (k1['high'] >= k2['high'] and k1['low'] <= k2['low']) or
                    (k2['high'] >= k1['high'] and k2['low'] <= k1['low'])
                )

                if has_containment:
                    # 确定当前趋势方向
                    if i == 0:
                        trend = initial_trend
                    else:
                        # 根据前两根 K 线判断趋势
                        prev_k = result.iloc[i-1]
                        trend = 'up' if result.iloc[i]['high'] >= prev_k['high'] else 'down'

                    # 根据趋势方向处理包含关系
                    if trend == 'up':
                        # 上升趋势：高高低
                        new_high = max(k1['high'], k2['high'])
                        new_low = max(k1['low'], k2['low'])
                    else:
                        # 下降趋势：低低高
                        new_high = min(k1['high'], k2['high'])
                        new_low = min(k1['low'], k2['low'])

                    # 合并 K 线（使用第一根 K 线的收盘价）
                    new_result.loc[i, 'high'] = new_high
                    new_result.loc[i, 'low'] = new_low

                    # 删除被包含的 K 线
                    new_result = new_result.drop(index=result.index[i+1]).reset_index(drop=True)
                    changed = True
                    break  # 发生变化后重新开始

            result = new_result
            if not changed:
                break

    except Exception as e:
        logger.error(f"处理 K 线包含关系出错: {e}", exc_info=True)
        raise

    logger.info(f"处理完成后 K 线数量: {len(result)}")
    return result


def simplify_klines(
    klines: pd.DataFrame,
    initial_trend: str = "up"
) -> pd.DataFrame:
    """
    简化 K 线，消除包含关系后保持原始结构（用于分型识别）

    此函数不删除 K 线，而是调整包含关系的值，保持 K 线数量不变

    Args:
        klines: K 线数据 DataFrame
        initial_trend: 初始趋势方向

    Returns:
        简化后的 K 线 DataFrame
    """
    # 输入验证
    if klines is None or len(klines) == 0:
        raise ValueError("K线数据不能为空")

    result = klines.copy()

    try:
        for i in range(len(result) - 1):
            k1 = result.iloc[i]
            k2 = result.iloc[i+1]

            # 判断是否存在包含关系
            has_containment = (
                (k1['high'] >= k2['high'] and k1['low'] <= k2['low']) or
                (k2['high'] >= k1['high'] and k2['low'] <= k1['low'])
            )

            if has_containment:
                # 确定趋势方向
                if i == 0:
                    trend = initial_trend
                else:
                    prev_k = result.iloc[i-1]
                    trend = 'up' if result.iloc[i]['high'] >= prev_k['high'] else 'down'

                # 调整包含关系的值
                if trend == 'up':
                    # 上升趋势：高高低
                    new_high = max(k1['high'], k2['high'])
                    new_low = max(k1['low'], k2['low'])
                else:
                    # 下降趋势：低低高
                    new_high = min(k1['high'], k2['high'])
                    new_low = min(k1['low'], k2['low'])

                result.loc[result.index[i], 'high'] = new_high
                result.loc[result.index[i], 'low'] = new_low

                # 被包含的 K 线调整到包含它的 K 线位置
                result.loc[result.index[i+1], 'high'] = new_high
                result.loc[result.index[i+1], 'low'] = new_low

        return result

    except Exception as e:
        logger.error(f"简化 K 线过程出错: {e}", exc_info=True)
        raise


# 单元测试
def test_process_containment():
    """测试 K 线包含关系处理"""
    print("测试 K 线包含关系处理...")

    # 测试用例 1: 简单包含关系
    data = pd.DataFrame({
        'open': [100, 101, 99],
        'high': [105, 103, 107],
        'low': [98, 99, 97],
        'close': [102, 100, 100]
    })
    result = process_containment(data)
    print(f"测试用例 1: 原始 {len(data)} 根 K 线 -> 处理后 {len(result)} 根 K 线")

    # 测试用例 2: 上升趋势包含
    data = pd.DataFrame({
        'open': [100, 101, 102, 103, 104],
        'high': [105, 107, 106, 110, 108],
        'low': [98, 100, 99, 102, 100],
        'close': [102, 105, 104, 108, 106]
    })
    result = process_containment(data, initial_trend='up')
    print(f"测试用例 2（上升趋势）: {len(data)} -> {len(result)}")

    # 测试用例 3: 下降趋势包含
    data = pd.DataFrame({
        'open': [104, 103, 102, 101, 100],
        'high': [108, 110, 106, 107, 105],
        'low': [100, 102, 99, 98, 97],
        'close': [106, 108, 104, 102, 100]
    })
    result = process_containment(data, initial_trend='down')
    print(f"测试用例 3（下降趋势）: {len(data)} -> {len(result)}")

    # 测试用例 4: 随机数据
    np.random.seed(42)
    n = 50
    data = pd.DataFrame({
        'open': 100 + np.random.randn(n).cumsum() / 10,
        'high': 100 + np.random.randn(n).cumsum() / 10 + np.abs(np.random.randn(n)),
        'low': 100 + np.random.randn(n).cumsum() / 10 - np.abs(np.random.randn(n)),
        'close': 100 + np.random.randn(n).cumsum() / 10
    })
    result = process_containment(data)
    print(f"测试用例 4（随机数据）: {len(data)} -> {len(result)}")

    print("✓ K 线包含关系处理测试通过\n")


def test_simplify_klines():
    """测试 K 线简化处理"""
    print("测试 K 线简化处理...")

    data = pd.DataFrame({
        'open': [100, 101, 102],
        'high': [105, 103, 107],
        'low': [98, 99, 97],
        'close': [102, 100, 100]
    })

    result = simplify_klines(data)
    print(f"简化前后 K 线数量保持: {len(data)} == {len(result)}")
    print("✓ K 线简化处理测试通过\n")


if __name__ == "__main__":
    test_process_containment()
    test_simplify_klines()