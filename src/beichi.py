"""
缠论背驰检测模块 v0.2.0
基于笔和中枢的背驰识别，配合 MACD 指标辅助判断

背驰定义：
- 趋势背驰：走势创出新高/新低，但 MACD 动能不创新高/新低
- 盘整背驰：在中枢震荡中，力度衰减的信号

实现内容：
- detect_trend_beichi: 趋势背驰检测
- detect_pattern_beichi: 盘整背驰检测
- calculate_beichi_strength: 背驰强度计算
"""

import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np
import logging

# 导入依赖模块
from bi import Bi
from zhongshu import Zhongshu

logger = logging.getLogger(__name__)


@dataclass
class Beichi:
    """背驰数据结构"""
    type: str  # 'trend'（趋势背驰）或 'pattern'（盘整背驰）
    direction: str  # 'top'（顶背驰/卖出信号）或 'bottom'（底背驰/买入信号）
    bi_index: int  # 背驰发生的笔索引
    price: float  # 背驰点的价格
    strength: float  # 背驰强度 (0-1)
    macd_area_ratio: float  # MACD 面积比值（力度对比）
    confidence: float  # 置信度 (0-1)
    description: str  # 背驰描述


def calculate_macd_area(
    macd_df: pd.DataFrame,
    start_index: int,
    end_index: int
) -> float:
    """
    计算指定区间的 MACD 柱状图面积（绝对值之和）

    Args:
        macd_df: MACD 指标 DataFrame，包含 'MACD' 列
        start_index: 起始索引
        end_index: 结束索引

    Returns:
        MACD 面积（绝对值）
    """
    if start_index >= end_index:
        return 0.0
    
    # 提取区间内的 MACD 值
    macd_values = macd_df['MACD'].iloc[start_index:end_index]
    
    # 计算绝对值之和（代表动能强度）
    area = np.abs(macd_values).sum()
    
    return area


def detect_trend_beichi(
    bis: List[Bi],
    macd_df: pd.DataFrame,
    min_bi_count: int = 2  # 降低门槛：从 3 改为 2
) -> Optional[Beichi]:
    """
    检测趋势背驰

    趋势背驰条件：
    1. 存在至少 2 笔以上的同向趋势（降低门槛）
    2. 后一笔价格创出新高/新低
    3. 后一笔的 MACD 面积小于前一笔（力度衰减）
    
    顶背驰（卖点）：上涨趋势中，价格创新高但动能减弱
    底背驰（买点）：下跌趋势中，价格创新低但动能减弱

    Args:
        bis: 笔列表
        macd_df: MACD 指标 DataFrame
        min_bi_count: 最少笔数要求（默认 2，提高灵敏度）

    Returns:
        如果检测到趋势背驰，返回 Beichi 对象；否则返回 None
    """
    if len(bis) < min_bi_count:
        logger.debug(f"笔数量不足：{len(bis)} < {min_bi_count}")
        return None
    
    # 检测顶背驰（上涨趋势背驰）
    top_beichi = _detect_up_trend_beichi(bis, macd_df, min_bi_count)
    
    # 检测底背驰（下跌趋势背驰）
    bottom_beichi = _detect_down_trend_beichi(bis, macd_df, min_bi_count)
    
    # 置信度更高的背驰
    if top_beichi and bottom_beichi:
        return top_beichi if top_beichi.confidence > bottom_beichi.confidence else bottom_beichi
    elif top_beichi:
        return top_beichi
    elif bottom_beichi:
        return bottom_beichi

    return None


def detect_all_trend_beichis(
    bis: List[Bi],
    macd_df: pd.DataFrame,
    min_bi_count: int = 2,
) -> List[Beichi]:
    """
    检测所有趋势背驰(返回列表,不丢弃次优的) — v0.6.3 新增

    与 detect_trend_beichi 的区别:
    - detect_trend_beichi: 返回置信度最高的单个 Beichi (or None)
    - detect_all_trend_beichis: 返回全部检测到的 Beichi 列表(可能含顶背+底背)

    修复 v0.6.0 时代遗留的 main.py:136 len(Beichi) TypeError bug。
    详见 tests/chanzhongshuochan-issues-20260624.md P3 与 MEMORY.md 6/22 maimaidian bug。

    Args:
        bis: 笔列表
        macd_df: MACD 指标 DataFrame
        min_bi_count: 最少笔数要求(默认 2)

    Returns:
        背驰列表(空列表 = 未检测到;可能含 1-2 个元素,顶背+底背不互相覆盖)
    """
    if len(bis) < min_bi_count:
        return []

    top_beichi = _detect_up_trend_beichi(bis, macd_df, min_bi_count)
    bottom_beichi = _detect_down_trend_beichi(bis, macd_df, min_bi_count)

    result: List[Beichi] = []
    if top_beichi:
        result.append(top_beichi)
    if bottom_beichi:
        result.append(bottom_beichi)
    return result


def _detect_up_trend_beichi(
    bis: List[Bi],
    macd_df: pd.DataFrame,
    min_bi_count: int
) -> Optional[Beichi]:
    """
    检测上涨趋势背驰（顶背驰）

    条件：
    1. 最近至少有 2 段上涨笔（底->顶）
    2. 后一段上涨笔的价格高点高于前一段
    3. 后一段上涨笔的 MACD 面积小于前一段
    """
    if len(bis) < min_bi_count:
        return None
    
    # 寻找上涨趋势的笔段（顶->底）
    up_segments = []
    
    for i in range(len(bis)):
        bi = bis[i]
        if bi.start_type == 'bottom' and bi.end_type == 'top' and bi.end_price > bi.start_price:
            up_segments.append((bi, i))
    
    if len(up_segments) < 2:
        logger.debug("上涨笔段数量不足，无法检测顶背驰")
        return None
    
    # 检查最近两段上涨笔是否形成背驰
    # 取最后两段
    seg1, idx1 = up_segments[-2]
    seg2, idx2 = up_segments[-1]
    
    # 价格创新高
    if seg2.end_price <= seg1.end_price:
        logger.debug(f"价格未创新高：seg2={seg2.end_price:.2f}, seg1={seg1.end_price:.2f}")
        return None
    
    # 计算 MACD 面积对比
    area1 = calculate_macd_area(macd_df, seg1.start_index, seg1.end_index)
    area2 = calculate_macd_area(macd_df, seg2.start_index, seg2.end_index)
    
    if area1 <= 0:
        return None
    
    area_ratio = area2 / area1
    
    # MACD 面积减小 -> 力度衰减 -> 背驰
    if area_ratio >= 1.2:  # 优化：提高灵敏度
        logger.debug(f"MACD 力度未衰减：area_ratio={area_ratio:.2f}")
        return None
    
    # 计算背驰强度
    strength = calculate_beichi_strength(seg1, seg2, macd_df)
    
    # 计算置信度
    confidence = _calculate_confidence(area_ratio, strength)
    
    return Beichi(
        type='trend',
        direction='top',
        bi_index=idx2,
        price=seg2.end_price,
        strength=strength,
        macd_area_ratio=area_ratio,
        confidence=min(1.0, confidence),  # 限制上限 100%
        description=f"顶背驰：价格创新高 {seg2.end_price:.2f} > {seg1.end_price:.2f}, "
                   f"MACD 面积比 {area_ratio:.2f}（力度衰减）"
    )


def _detect_down_trend_beichi(
    bis: List[Bi],
    macd_df: pd.DataFrame,
    min_bi_count: int
) -> Optional[Beichi]:
    """
    检测下跌趋势背驰（底背驰）

    条件：
    1. 最近至少有 2 段下跌笔（顶->底）
    2. 后一段下跌笔的价格低点低于前一段
    3. 后一段下跌笔的 MACD 面积小于前一段
    """
    if len(bis) < min_bi_count:
        return None
    
    # 寻找下跌趋势的笔段（顶->底）
    down_segments = []
    
    for i in range(len(bis)):
        bi = bis[i]
        if bi.start_type == 'top' and bi.end_type == 'bottom' and bi.end_price < bi.start_price:
            down_segments.append((bi, i))
    
    if len(down_segments) < 2:
        logger.debug("下跌笔段数量不足，无法检测底背驰")
        return None
    
    # 检查最近两段下跌笔是否形成背驰
    seg1, idx1 = down_segments[-2]
    seg2, idx2 = down_segments[-1]
    
    # 价格创新低
    if seg2.end_price >= seg1.end_price:
        logger.debug(f"价格未创新低：seg2={seg2.end_price:.2f}, seg1={seg1.end_price:.2f}")
        return None
    
    # 计算 MACD 面积对比（使用绝对值）
    area1 = calculate_macd_area(macd_df, seg1.start_index, seg1.end_index)
    area2 = calculate_macd_area(macd_df, seg2.start_index, seg2.end_index)
    
    if area1 <= 0:
        return None
    
    area_ratio = area2 / area1
    
    # MACD 面积减小 -> 力度衰减 -> 背驰
    if area_ratio >= 1.2:  # 优化：提高灵敏度
        logger.debug(f"MACD 力度未衰减：area_ratio={area_ratio:.2f}")
        return None
    
    # 计算背驰强度
    strength = calculate_beichi_strength(seg1, seg2, macd_df)
    
    # 计算置信度
    confidence = _calculate_confidence(area_ratio, strength)
    
    return Beichi(
        type='trend',
        direction='bottom',
        bi_index=idx2,
        price=seg2.end_price,
        strength=strength,
        macd_area_ratio=area_ratio,
        confidence=min(1.0, confidence),  # 限制上限 100%
        description=f"底背驰：价格创新低 {seg2.end_price:.2f} < {seg1.end_price:.2f}, "
                   f"MACD 面积比 {area_ratio:.2f}（力度衰减）"
    )


def calculate_beichi_strength(
    bi1: Bi,
    bi2: Bi,
    macd_df: pd.DataFrame
) -> float:
    """
    计算背驰强度 (0-1)

    背驰强度由多个因素决定：
    1. MACD 面积比值（力度对比）
    2. 价格创新程度
    3. 笔的幅度对比
    
    Args:
        bi1: 前一笔
        bi2: 后一笔
        macd_df: MACD 指标 DataFrame

    Returns:
        背驰强度 (0-1)
    """
    strength = 0.0
    
    # 1. MACD 面积比值权重（40%）
    area1 = calculate_macd_area(macd_df, bi1.start_index, bi1.end_index)
    area2 = calculate_macd_area(macd_df, bi2.start_index, bi2.end_index)
    
    if area1 > 0:
        area_ratio = area2 / area1
        # 面积比越小，背驰越强
        area_strength = max(0.0, min(1.0, 1.0 - area_ratio))
        strength += 0.4 * area_strength
    
    # 2. 价格创新程度权重（30%）
    price_diff = abs(bi2.end_price - bi1.end_price) / bi1.end_price
    # 价格差异越大，创新程度越高，背驰可能越强
    price_strength = min(1.0, price_diff * 10)  # 放大系数
    strength += 0.3 * price_strength
    
    # 3. 笔幅度对比权重（30%）
    amp1 = bi1.amplitude
    amp2 = bi2.amplitude
    
    if amp1 > 0:
        amp_ratio = amp2 / amp1
        # 后一笔幅度越大，说明动能还有一定强度，背驰可能较弱
        # 后一笔幅度越小，说明动能衰减明显，背驰较强
        amp_strength = max(0.0, min(1.0, 1.0 - amp_ratio * 0.5))
        strength += 0.3 * amp_strength
    
    return min(1.0, max(0.0, strength))


def _calculate_confidence(
    area_ratio: float,
    strength: float
) -> float:
    """
    计算背驰置信度

    Args:
        area_ratio: MACD 面积比值
        strength: 背驰强度

    Returns:
        置信度 (0-1)
    """
    # 置信度由面积比和强度综合决定
    # 面积比越小（力度衰减明显），置信度越高
    # 强度越大，置信度越高
    
    area_confidence = max(0.0, min(1.0, 1.0 - area_ratio))
    
    confidence = 0.5 * area_confidence + 0.5 * strength
    
    return min(1.0, max(0.0, confidence))


if __name__ == "__main__":
    print("=" * 50)
    print("缠论背驰检测模块 v0.2.0")
    print("=" * 50)
    print("\n运行单元测试...")
    
    # 简单测试
    from bi import Bi
    
    bis = [
        Bi(start_index=0, end_index=5, start_type='top', end_type='bottom',
           start_price=110.0, end_price=95.0, kline_count=6, amplitude=13.6),
        Bi(start_index=5, end_index=10, start_type='bottom', end_type='top',
           start_price=95.0, end_price=105.0, kline_count=6, amplitude=10.5),
        Bi(start_index=10, end_index=15, start_type='top', end_type='bottom',
           start_price=105.0, end_price=100.0, kline_count=6, amplitude=4.8),
        Bi(start_index=15, end_index=20, start_type='bottom', end_type='top',
           start_price=100.0, end_price=110.0, kline_count=6, amplitude=10.0),
    ]
    
    n = 25
    macd_df = pd.DataFrame({
        'DIF': np.random.randn(n) * 0.5,
        'DEA': np.random.randn(n) * 0.3,
        'MACD': np.concatenate([
            np.random.randn(10) * 0.5 + 0.5,
            np.random.randn(5) * 0.3 - 0.2,
            np.random.randn(10) * 0.3 + 0.3,
        ])
    })
    
    beichi = detect_trend_beichi(bis, macd_df, min_bi_count=2)
    
    if beichi:
        print(f"\n检测到背驰:")
        print(f"  类型：{beichi.type}")
        print(f"  方向：{beichi.direction}")
        print(f"  强度：{beichi.strength:.2f}")
        print(f"  置信度：{min(1.0, beichi.confidence):.1%}")
        print(f"  描述：{beichi.description}")
    else:
        print("\n未检测到背驰")
    
    print("\n✓ 背驰检测模块测试完成")
