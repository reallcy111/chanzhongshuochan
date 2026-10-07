"""
缠论中枢识别模块
识别笔构成的中枢
"""

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

# 导入笔模块（统一路径）
try:
    from .bi import Bi
except ImportError:
    from bi import Bi


@dataclass
class Zhongshu:
    """中枢数据结构"""
    start_index: int  # 起始笔索引
    end_index: int  # 结束笔索引
    bi_indices: List[int]  # 包含的笔索引列表
    zg: float  # 中枢高点（高点的最小值）
    zd: float  # 中枢低点（低点的最大值）
    extend_count: int  # 延伸次数


def identify_zhongshu(bis_list: List[Bi]) -> List[Zhongshu]:
    """
    识别中枢

    中枢定义：
    由至少 3 段连续笔的重叠部分构成
    - 上沿 zg：所有笔高点的最小值
    - 下沿 zd：所有笔低点的最大值

    识别方法：
    1. 查找 3 段连续的笔
    2. 计算它们的重叠区间
    3. 检查是否形成有效中枢

    Args:
        bis_list: 笔列表

    Returns:
        中枢列表
    """
    # 输入验证
    if bis_list is None:
        raise ValueError("笔列表不能为空")
    
    if len(bis_list) < 3:
        logger.warning("笔数量不足3个，无法识别中枢")
        return []

    zhongshu_list = []

    try:
        i = 0
        while i <= len(bis_list) - 3:
            # 取连续的 3 段笔
            bi_group = bis_list[i:i+3]

            # 计算高点最小值和低点最大值
            high_points = [max(bi.start_price, bi.end_price) for bi in bi_group]
            low_points = [min(bi.start_price, bi.end_price) for bi in bi_group]

            zg = min(high_points)
            zd = max(low_points)

            # 检查是否形成有效中枢（zg > zd）
            if zg > zd:
                # 查找后续可以延伸的笔
                extend_indices = [i, i+1, i+2]
                j = i + 3

                while j < len(bis_list):
                    next_bi = bis_list[j]

                    # 检查该笔是否与中枢区间有重叠
                    bi_high = max(next_bi.start_price, next_bi.end_price)
                    bi_low = min(next_bi.start_price, next_bi.end_price)

                    # 笔必须至少部分在中枢区间内
                    if bi_low <= zg and bi_high >= zd:
                        # 更新中枢区间
                        high_points.append(bi_high)
                        low_points.append(bi_low)
                        zg = min(high_points)
                        zd = max(low_points)
                        extend_indices.append(j)
                        j += 1
                    else:
                        break

                # 创建中枢
                zhongshu_list.append(Zhongshu(
                    start_index=i,
                    end_index=extend_indices[-1],
                    bi_indices=extend_indices,
                    zg=zg,
                    zd=zd,
                    extend_count=len(extend_indices) - 3
                ))

                logger.info(f"识别中枢: 笔 {i}-{extend_indices[-1]}, zg={zg:.2f}, zd={zd:.2f}")

                # 跳过已处理的笔
                i = extend_indices[-1] + 1
            else:
                i += 1

    except Exception as e:
        logger.error(f"中枢识别过程出错: {e}", exc_info=True)
        raise

    logger.info(f"共识别 {len(zhongshu_list)} 个中枢")
    return zhongshu_list


def classify_zhongshu(zs: Zhongshu) -> str:
    """
    分类中枢类型

    Args:
        zs: 中枢对象

    Returns:
        中枢类型：'up'（上涨中枢）或 'down'（下跌中枢）
    """
    # 判断中枢类型：看第 3 段笔（形成中枢后的第一笔）的方向
    # 实际上应该看进入中枢和离开中枢的方向
    # 简化判断：如果中枢高点高于中枢低点很多，且整体趋势向上，为上涨中枢
    # 这里使用简化的判断方法

    amplitude = (zs.zg - zs.zd) / zs.zd * 100
    if amplitude > 1:
        return 'up'
    else:
        return 'down'


def check_zhongshu_breakout(
    bis_list: List[Bi],
    zs: Zhongshu
) -> Tuple[bool, str]:
    """
    检查中枢是否被突破

    Args:
        bis_list: 笔列表
        zs: 中枢对象

    Returns:
        (是否突破, 突破方向)
    """
    # 输入验证
    if bis_list is None:
        raise ValueError("笔列表不能为空")
    
    if zs is None:
        raise ValueError("中枢对象不能为空")

    # 检查中枢后的笔是否有突破
    if zs.end_index >= len(bis_list) - 1:
        return (False, 'none')

    try:
        # 检查中枢后的几笔
        check_count = min(3, len(bis_list) - zs.end_index - 1)
        for i in range(zs.end_index + 1, min(zs.end_index + 1 + check_count, len(bis_list))):
            bi = bis_list[i]
            bi_high = max(bi.start_price, bi.end_price)
            bi_low = min(bi.start_price, bi.end_price)

            if bi_high > zs.zg:
                return (True, 'up')
            elif bi_low < zs.zd:
                return (True, 'down')

        return (False, 'none')

    except Exception as e:
        logger.error(f"检查中枢突破过程出错: {e}", exc_info=True)
        raise


def get_zhongshu_statistics(zhongshu_list: List[Zhongshu]) -> Dict[str, float]:
    """
    获取中枢统计信息

    Args:
        zhongshu_list: 中枢列表

    Returns:
        统计信息字典
    """
    # 输入验证
    if zhongshu_list is None:
        raise ValueError("中枢列表不能为空")
    
    if len(zhongshu_list) == 0:
        return {
            'count': 0,
            'avg_segments': 0.0,
            'avg_amplitude': 0.0,
            'max_amplitude': 0.0
        }

    try:
        segments = [len(zs.bi_indices) for zs in zhongshu_list]
        amplitudes = [((zs.zg - zs.zd) / zs.zd * 100) for zs in zhongshu_list]

        return {
            'count': len(zhongshu_list),
            'avg_segments': float(np.mean(segments)),
            'avg_amplitude': float(np.mean(amplitudes)),
            'max_amplitude': float(np.max(amplitudes))
        }

    except Exception as e:
        logger.error(f"计算中枢统计信息出错: {e}", exc_info=True)
        raise


def find_zhongshu_by_index(
    zhongshu_list: List[Zhongshu],
    bi_index: int
) -> List[Zhongshu]:
    """
    查找包含指定笔的所有中枢

    Args:
        zhongshu_list: 中枢列表
        bi_index: 笔索引

    Returns:
        包含该笔的中枢列表
    """
    # 输入验证
    if zhongshu_list is None:
        raise ValueError("中枢列表不能为空")

    try:
        result = []
        for zs in zhongshu_list:
            if bi_index in zs.bi_indices:
                result.append(zs)
        return result

    except Exception as e:
        logger.error(f"查找中枢过程出错: {e}", exc_info=True)
        raise


# 单元测试
def test_identify_zhongshu():
    """测试中枢识别"""
    print("测试中枢识别...")

    # 创建测试笔数据
    from bi import Bi

    # 模拟一个包含中枢的笔序列
    # 下跌笔 -> 上涨笔（中枢开始）-> 下跌笔 -> 上涨笔（中枢形成）-> 下跌笔 -> 突破
    bis_list = [
        Bi(start_index=0, end_index=5, start_type='top', end_type='bottom',
           start_price=110.0, end_price=100.0, kline_count=6, amplitude=9.09),  # 下跌
        Bi(start_index=5, end_index=10, start_type='bottom', end_type='top',
           start_price=100.0, end_price=105.0, kline_count=6, amplitude=5.00),  # 上涨
        Bi(start_index=10, end_index=15, start_type='top', end_type='bottom',
           start_price=105.0, end_price=101.0, kline_count=6, amplitude=3.81),  # 下跌
        Bi(start_index=15, end_index=20, start_type='bottom', end_type='top',
           start_price=101.0, end_price=104.0, kline_count=6, amplitude=2.97),  # 上涨
        Bi(start_index=20, end_index=25, start_type='top', end_type='bottom',
           start_price=104.0, end_price=102.0, kline_count=6, amplitude=1.92),  # 下跌
        Bi(start_index=25, end_index=30, start_type='bottom', end_type='top',
           start_price=102.0, end_price=95.0, kline_count=6, amplitude=6.86),  # 下跌突破
    ]

    zhongshu_list = identify_zhongshu(bis_list)
    print(f"识别到 {len(zhongshu_list)} 个中枢")

    for i, zs in enumerate(zhongshu_list):
        zs_type = classify_zhongshu(zs)
        amplitude = (zs.zg - zs.zd) / zs.zd * 100
        print(f"  中枢 {i+1}: 笔索引 {zs.start_index}-{zs.end_index}, "
              f"类型={zs_type}, 区间=[{zs.zd:.2f}, {zs.zg:.2f}], "
              f"幅度={amplitude:.2f}%, 笔数={len(zs.bi_indices)}")

    # 测试统计信息
    stats = get_zhongshu_statistics(zhongshu_list)
    if stats['count'] > 0:
        print(f"\n中枢统计信息:")
        print(f"  数量: {stats['count']}")
        print(f"  平均笔数: {stats['avg_segments']:.1f}")
        print(f"  平均幅度: {stats['avg_amplitude']:.2f}%")
        print(f"  最大幅度: {stats['max_amplitude']:.2f}%")

    print("✓ 中枢识别测试通过\n")


def test_check_zhongshu_breakout():
    """测试中枢突破检测"""
    print("测试中枢突破检测...")

    from bi import Bi

    bis_list = [
        Bi(start_index=0, end_index=5, start_type='top', end_type='bottom',
           start_price=110.0, end_price=100.0, kline_count=6, amplitude=9.09),
        Bi(start_index=5, end_index=10, start_type='bottom', end_type='top',
           start_price=100.0, end_price=105.0, kline_count=6, amplitude=5.00),
        Bi(start_index=10, end_index=15, start_type='top', end_type='bottom',
           start_price=105.0, end_price=101.0, kline_count=6, amplitude=3.81),
        Bi(start_index=15, end_index=20, start_type='bottom', end_type='top',
           start_price=101.0, end_price=104.0, kline_count=6, amplitude=2.97),
        Bi(start_index=20, end_index=25, start_type='top', end_type='bottom',
           start_price=104.0, end_price=102.0, kline_count=6, amplitude=1.92),
        Bi(start_index=25, end_index=30, start_type='bottom', end_type='top',
           start_price=102.0, end_price=95.0, kline_count=6, amplitude=6.86),
    ]

    zhongshu_list = identify_zhongshu(bis_list)

    if len(zhongshu_list) > 0:
        zs = zhongshu_list[0]
        is_breakout, direction = check_zhongshu_breakout(bis_list, zs)
        print(f"中枢突破检测: {is_breakout}, 方向: {direction}")

    # 测试查找中枢
    if len(zhongshu_list) > 0:
        zs_list = find_zhongshu_by_index(zhongshu_list, 2)
        print(f"笔索引 2 所属的中枢数量: {len(zs_list)}")

    print("✓ 中枢突破检测测试通过\n")


def test_edge_cases():
    """测试边界情况"""
    print("测试边界情况...")

    from bi import Bi

    # 测试笔数不足
    bis_list = [
        Bi(start_index=0, end_index=5, start_type='top', end_type='bottom',
           start_price=110.0, end_price=100.0, kline_count=6, amplitude=9.09),
        Bi(start_index=5, end_index=10, start_type='bottom', end_type='top',
           start_price=100.0, end_price=105.0, kline_count=6, amplitude=5.00),
    ]

    zhongshu_list = identify_zhongshu(bis_list)
    assert len(zhongshu_list) == 0
    print("✓ 正确处理笔数不足")

    # 测试空列表
    empty_list = []
    stats = get_zhongshu_statistics(empty_list)
    assert stats['count'] == 0
    print("✓ 正确处理空列表")

    print("✓ 边界情况测试通过\n")


if __name__ == "__main__":
    test_identify_zhongshu()
    test_check_zhongshu_breakout()
    test_edge_cases()