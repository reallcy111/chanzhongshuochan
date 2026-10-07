"""
缠论笔划分模块
连接顶底分型形成笔
"""

import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入分型模块（统一路径）
try:
    from .fenxing import Fenxing, get_fenxing_pairs
except ImportError:
    from fenxing import Fenxing, get_fenxing_pairs


@dataclass
class Bi:
    """笔数据结构"""
    start_index: int  # 起点 K 线索引
    end_index: int  # 终点 K 线索引
    start_type: str  # 起点分型类型 ('top' 或 'bottom')
    end_type: str  # 终点分型类型
    start_price: float  # 起点价格
    end_price: float  # 终点价格
    kline_count: int  # 包含的 K 线数量
    amplitude: float  # 涨跌幅度（百分比）


def identify_bis(
    fenxing_list: List[Fenxing],
    klines: pd.DataFrame,
    min_amplitude: float = 0.5,
    min_klines: int = 5
) -> List[Bi]:
    """
    识别笔

    笔的定义：
    1. 连接相邻的顶底分型（必须是顶分型-底分型 或 底分型-顶分型）
    2. 至少包含 5 根 K 线
    3. 涨跌幅度 ≥ min_amplitude%

    Args:
        fenxing_list: 分型列表
        klines: K 线数据 DataFrame
        min_amplitude: 最小幅度（百分比）
        min_klines: 最少 K 线数量

    Returns:
        笔列表

    Raises:
        ValueError: 如果 K 线数据缺少必要列或输入无效
    """
    # 输入验证
    if fenxing_list is None:
        raise ValueError("分型列表不能为空")
    
    if len(fenxing_list) < 2:
        logger.warning("分型数量不足2个，无法识别笔")
        return []

    if klines is None or len(klines) == 0:
        raise ValueError("K线数据不能为空")

    if 'close' not in klines.columns:
        raise ValueError("K线数据必须包含 'close' 列")

    # 数据类型验证
    try:
        close_prices = klines['close'].astype(float)
    except (ValueError, TypeError) as e:
        raise ValueError(f"K线收盘价数据必须为数值类型: {e}")

    bis_list = []

    try:
        # 获取分型对
        pairs = get_fenxing_pairs(fenxing_list)

        for fx_start, fx_end in pairs:
            # 计算包含的 K 线数量
            kline_count = fx_end.index - fx_start.index + 1

            # 检查最小 K 线数量
            if kline_count < min_klines:
                logger.debug(f"跳过笔: K线数量 {kline_count} < {min_klines}")
                continue

            # 确定起点和终点价格
            if fx_start.type == 'top':
                start_price = fx_start.high
            else:
                start_price = fx_start.low

            if fx_end.type == 'top':
                end_price = fx_end.high
            else:
                end_price = fx_end.low

            # 计算涨跌幅度
            if start_price == 0:
                logger.warning(f"起点价格为0，跳过笔识别")
                continue
                
            amplitude = abs((end_price - start_price) / start_price * 100)

            # 检查最小幅度
            if amplitude < min_amplitude:
                logger.debug(f"跳过笔: 幅度 {amplitude:.2f}% < {min_amplitude}%")
                continue

            # 创建笔
            bis_list.append(Bi(
                start_index=fx_start.index,
                end_index=fx_end.index,
                start_type=fx_start.type,
                end_type=fx_end.type,
                start_price=start_price,
                end_price=end_price,
                kline_count=kline_count,
                amplitude=amplitude
            ))

        logger.info(f"识别到 {len(bis_list)} 笔")

    except Exception as e:
        logger.error(f"笔识别过程出错: {e}", exc_info=True)
        raise

    return bis_list


def filter_overlapping_bis(bis_list: List[Bi]) -> List[Bi]:
    """
    过滤重叠的笔

    如果两笔重叠（一笔的终点在下一笔的起点之后），保留笔幅较大的一笔

    Args:
        bis_list: 原始笔列表

    Returns:
        过滤后的笔列表
    """
    # 输入验证
    if bis_list is None:
        raise ValueError("笔列表不能为空")
    
    if len(bis_list) <= 1:
        return bis_list

    try:
        # 按起点索引排序
        sorted_bis = sorted(bis_list, key=lambda x: x.start_index)
        filtered = []

        i = 0
        while i < len(sorted_bis):
            current = sorted_bis[i]

            # 查找与当前笔重叠的后续笔
            overlapping = [current]
            j = i + 1
            while j < len(sorted_bis) and sorted_bis[j].start_index < current.end_index:
                overlapping.append(sorted_bis[j])
                j += 1

            # 如果有重叠，选择笔幅较大的一笔
            if len(overlapping) > 1:
                max_bi = max(overlapping, key=lambda x: x.amplitude)
                filtered.append(max_bi)
            else:
                filtered.append(current)

            i = j

        return filtered

    except Exception as e:
        logger.error(f"过滤重叠笔过程出错: {e}", exc_info=True)
        raise


def validate_bis(bis_list: List[Bi]) -> List[Bi]:
    """
    验证笔的有效性

    验证规则：
    1. 笔的类型必须交替（顶底交替）
    2. 笔的方向必须一致（顶->底 为下跌，底->顶 为上涨）

    Args:
        bis_list: 笔列表

    Returns:
        验证后的笔列表
    """
    # 输入验证
    if bis_list is None:
        raise ValueError("笔列表不能为空")
    
    if len(bis_list) == 0:
        return bis_list

    try:
        valid_bis = [bis_list[0]]

        for i in range(1, len(bis_list)):
            prev_bi = bis_list[i-1]
            curr_bi = bis_list[i]

            # 检查类型交替
            if prev_bi.end_type != curr_bi.start_type:
                # 不匹配，跳过当前笔
                logger.debug(f"验证失败: 笔 {i} 类型不匹配")
                continue

            # 检查方向一致性
            expected_direction = (curr_bi.end_price > curr_bi.start_price)
            if prev_bi.start_type == 'top':
                # 前一笔从顶到底，应该是下跌
                # 当前一笔应该从底到顶，应该是上涨
                if not expected_direction:
                    logger.debug(f"验证失败: 笔 {i} 方向不一致")
                    continue
            else:
                # 前一笔从底到顶，应该是上涨
                # 当前一笔应该从顶到底，应该是下跌
                if expected_direction:
                    logger.debug(f"验证失败: 笔 {i} 方向不一致")
                    continue

            valid_bis.append(curr_bi)

        logger.info(f"验证通过 {len(valid_bis)} 笔")

        return valid_bis

    except Exception as e:
        logger.error(f"验证笔过程出错: {e}", exc_info=True)
        raise


def get_bi_statistics(bis_list: List[Bi]) -> Dict[str, float]:
    """
    获取笔的统计信息

    Args:
        bis_list: 笔列表

    Returns:
        包含统计信息的字典
    """
    # 输入验证
    if bis_list is None:
        raise ValueError("笔列表不能为空")
    
    if len(bis_list) == 0:
        return {
            'count': 0,
            'avg_amplitude': 0.0,
            'avg_klines': 0.0,
            'max_amplitude': 0.0,
            'min_amplitude': 0.0
        }

    try:
        amplitudes = [bi.amplitude for bi in bis_list]
        klines = [bi.kline_count for bi in bis_list]

        return {
            'count': len(bis_list),
            'avg_amplitude': float(np.mean(amplitudes)),
            'avg_klines': float(np.mean(klines)),
            'max_amplitude': float(np.max(amplitudes)),
            'min_amplitude': float(np.min(amplitudes))
        }

    except Exception as e:
        logger.error(f"计算笔统计信息出错: {e}", exc_info=True)
        raise


# 单元测试
def test_identify_bis():
    """测试笔识别"""
    print("测试笔识别...")

    # 创建测试分型数据
    from fenxing import Fenxing

    fenxing_list = [
        Fenxing(index=0, type='top', high=110.0, low=108.0, kline_index=0),
        Fenxing(index=5, type='bottom', high=95.0, low=92.0, kline_index=5),
        Fenxing(index=10, type='top', high=105.0, low=103.0, kline_index=10),
        Fenxing(index=15, type='bottom', high=90.0, low=87.0, kline_index=15),
        Fenxing(index=20, type='top', high=100.0, low=97.0, kline_index=20),
    ]

    # 创建测试 K 线数据
    n = 25
    klines = pd.DataFrame({
        'open': 100 + np.random.randn(n).cumsum() / 10,
        'high': 100 + np.random.randn(n).cumsum() / 10 + np.abs(np.random.randn(n)),
        'low': 100 + np.random.randn(n).cumsum() / 10 - np.abs(np.random.randn(n)),
        'close': 100 + np.random.randn(n).cumsum() / 10
    })

    bis_list = identify_bis(fenxing_list, klines)
    print(f"识别到 {len(bis_list)} 笔")

    for bi in bis_list:
        direction = "上涨" if bi.end_price > bi.start_price else "下跌"
        print(f"  {bi.start_type}({bi.start_index}) -> {bi.end_type}({bi.end_index}): "
              f"{direction}, 幅度={bi.amplitude:.2f}%, K线数={bi.kline_count}")

    # 测试统计信息
    stats = get_bi_statistics(bis_list)
    print(f"\n笔统计信息:")
    print(f"  数量: {stats['count']}")
    print(f"  平均幅度: {stats['avg_amplitude']:.2f}%")
    print(f"  平均K线数: {stats['avg_klines']:.1f}")
    print(f"  最大幅度: {stats['max_amplitude']:.2f}%")
    print(f"  最小幅度: {stats['min_amplitude']:.2f}%")

    print("✓ 笔识别测试通过\n")


def test_filter_overlapping_bis():
    """测试过滤重叠笔"""
    print("测试过滤重叠笔...")

    from fenxing import Fenxing

    # 创建有重叠的笔
    bis_list = [
        Bi(start_index=0, end_index=5, start_type='top', end_type='bottom',
           start_price=110.0, end_price=95.0, kline_count=6, amplitude=13.64),
        Bi(start_index=3, end_index=7, start_type='bottom', end_type='top',
           start_price=95.0, end_price=105.0, kline_count=5, amplitude=10.53),
        Bi(start_index=8, end_index=12, start_type='top', end_type='bottom',
           start_price=105.0, end_price=90.0, kline_count=5, amplitude=14.29),
    ]

    filtered = filter_overlapping_bis(bis_list)
    print(f"原始笔数: {len(bis_list)}, 过滤后: {len(filtered)}")
    assert len(filtered) == 2
    print("✓ 过滤重叠笔测试通过\n")


def test_validate_bis():
    """测试笔验证"""
    print("测试笔验证...")

    # 创建有效的笔序列
    bis_list = [
        Bi(start_index=0, end_index=5, start_type='top', end_type='bottom',
           start_price=110.0, end_price=95.0, kline_count=6, amplitude=13.64),
        Bi(start_index=5, end_index=10, start_type='bottom', end_type='top',
           start_price=95.0, end_price=105.0, kline_count=6, amplitude=10.53),
        Bi(start_index=10, end_index=15, start_type='top', end_type='bottom',
           start_price=105.0, end_price=90.0, kline_count=6, amplitude=14.29),
    ]

    valid = validate_bis(bis_list)
    print(f"验证后笔数: {len(valid)}")
    assert len(valid) == 3

    # 创建无效的笔序列
    invalid_bis = [
        Bi(start_index=0, end_index=5, start_type='top', end_type='bottom',
           start_price=110.0, end_price=95.0, kline_count=6, amplitude=13.64),
        Bi(start_index=6, end_index=10, start_type='top', end_type='bottom',  # 类型不匹配
           start_price=105.0, end_price=90.0, kline_count=5, amplitude=14.29),
    ]

    valid = validate_bis(invalid_bis)
    print(f"无效序列验证后笔数: {len(valid)}")
    assert len(valid) == 1

    print("✓ 笔验证测试通过\n")


if __name__ == "__main__":
    test_identify_bis()
    test_filter_overlapping_bis()
    test_validate_bis()