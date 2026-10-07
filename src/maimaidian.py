"""
缠论买卖点识别模块 v0.2.0
基于缠论三类买卖点理论进行识别

买卖点定义（参考 czsc）：
- 一类买点：趋势背驰点（下跌趋势结束）
- 二类买点：回抽确认点（一类买点后的第一次回抽）
- 三类买点：中枢破坏点（突破中枢后的回抽不破中枢）

- 一类卖点：趋势背驰点（上涨趋势结束）
- 二类卖点：回抽确认点（一类卖点后的第一次回抽）
- 三类卖点：中枢破坏点（跌破中枢后的反弹不破中枢）

实现内容：
- identify_buy_sell_points: 识别买卖点
- classify_buy_sell_point: 分类买卖点
"""

import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np
import logging

# 导入依赖模块
from bi import Bi
from zhongshu import Zhongshu
from beichi import Beichi

logger = logging.getLogger(__name__)


@dataclass
class Maimaidian:
    """买卖点数据结构"""
    point_type: str  # 'buy1', 'buy2', 'buy3', 'sell1', 'sell2', 'sell3'
    index: int  # 买卖点位置（笔索引）
    price: float  # 买卖点价格
    confidence: float  # 置信度 (0-1)
    bi: Bi  # 相关笔
    zhongshu: Optional[Zhongshu]  # 相关中枢（二三类买卖点）
    beichi: Optional[Beichi]  # 相关背驰（一类买卖点）
    description: str  # 买卖点描述


def identify_buy_sell_points(
    bis: List[Bi],
    zhongshus: List[Zhongshu],
    beichis: List[Beichi],
    min_confidence: float = 0.3
) -> List[Maimaidian]:
    """
    识别买卖点

    Args:
        bis: 笔列表
        zhongshus: 中枢列表
        beichis: 背驰列表
        min_confidence: 最小置信度阈值

    Returns:
        买卖点列表
    """
    points = []
    
    # 一类买卖点：趋势背驰点
    type1_points = _identify_type1_points(bis, beichis)
    points.extend(type1_points)
    
    # 二类买卖点：回抽确认点
    type2_points = _identify_type2_points(bis, zhongshus, points)
    points.extend(type2_points)
    
    # 三类买卖点：中枢破坏点
    type3_points = _identify_type3_points(bis, zhongshus, points)
    points.extend(type3_points)
    
    # 过滤低置信度买卖点
    filtered = [p for p in points if p.confidence >= min_confidence]
    
    # 按时间排序
    sorted_points = sorted(filtered, key=lambda x: x.index)
    
    return sorted_points


def _identify_type1_points(
    bis: List[Bi],
    beichis: List[Beichi]
) -> List[Maimaidian]:
    """
    识别一类买卖点（趋势背驰点）

    一类买点：下跌趋势背驰（底背驰）
    一类卖点：上涨趋势背驰（顶背驰）
    """
    points = []
    
    # 只关注趋势背驰
    trend_beichis = [b for b in beichis if b.type == 'trend']
    
    for beichi in trend_beichis:
        # 获取相关笔
        if beichi.bi_index >= len(bis):
            continue
        
        bi = bis[beichi.bi_index]
        
        # 一类买点：底背驰（下跌趋势结束）
        if beichi.direction == 'bottom':
            point_type = 'buy1'
            confidence = min(1.0, beichi.confidence)  # 限制上限 100%
            
            points.append(Maimaidian(
                point_type=point_type,
                index=beichi.bi_index,
                price=beichi.price,
                confidence=confidence,
                bi=bi,
                zhongshu=None,
                beichi=beichi,
                description=f"一类买点：下跌趋势背驰，价格 {beichi.price:.2f}, "
                           f"置信度 {min(1.0, confidence):.1%}"
            ))
        
        # 一类卖点：顶背驰（上涨趋势结束）
        elif beichi.direction == 'top':
            point_type = 'sell1'
            confidence = min(1.0, beichi.confidence)  # 限制上限 100%
            
            points.append(Maimaidian(
                point_type=point_type,
                index=beichi.bi_index,
                price=beichi.price,
                confidence=confidence,
                bi=bi,
                zhongshu=None,
                beichi=beichi,
                description=f"一类卖点：上涨趋势背驰，价格 {beichi.price:.2f}, "
                           f"置信度 {min(1.0, confidence):.1%}"
            ))
    
    return points


def _identify_type2_points(
    bis: List[Bi],
    zhongshus: List[Zhongshu],
    existing_points: List[Maimaidian]
) -> List[Maimaidian]:
    """
    识别二类买卖点（回抽确认点）

    二类买点：一类买点后，第一次回抽不破前低
    二类卖点：一类卖点后，第一次反弹不破前高
    """
    points = []
    
    # 找到一类买点
    buy1_points = [p for p in existing_points if p.point_type == 'buy1']
    
    for buy1 in buy1_points:
        # 寻找一类买点后的回抽笔
        type2 = _find_type2_buy(bis, zhongshus, buy1)
        if type2:
            points.append(type2)
    
    # 找到一类卖点
    sell1_points = [p for p in existing_points if p.point_type == 'sell1']
    
    for sell1 in sell1_points:
        # 寻找一类卖点后的反弹笔
        type2 = _find_type2_sell(bis, zhongshus, sell1)
        if type2:
            points.append(type2)
    
    return points


def _find_type2_buy(
    bis: List[Bi],
    zhongshus: List[Zhongshu],
    buy1: Maimaidian
) -> Optional[Maimaidian]:
    """
    寻找二类买点

    条件：
    1. 一类买点后，出现第一次回抽（上涨笔 -> 下跌笔）
    2. 下跌笔的低点不破一类买点的价格
    3. 确认后出现上涨笔
    """
    # 一类买点索引
    buy1_index = buy1.index
    
    # 寻找一类买点后的笔
    if buy1_index >= len(bis) - 1:
        return None
    
    # 一类买点后应该有一段上涨笔
    # 然后出现回抽（下跌笔），回抽不破一类买点价格
    # 确认点在回抽后开始上涨的地方
    
    # 寻找上涨笔
    up_bi_index = None
    for i in range(buy1_index + 1, min(buy1_index + 5, len(bis))):
        bi = bis[i]
        if bi.end_price > bi.start_price and bi.start_type == 'bottom':
            up_bi_index = i
            break
    
    if up_bi_index is None:
        return None
    
    # 寻找回抽笔（下跌笔）
    pullback_bi_index = None
    for i in range(up_bi_index + 1, min(up_bi_index + 3, len(bis))):
        bi = bis[i]
        if bi.end_price < bi.start_price and bi.start_type == 'top':
            pullback_bi_index = i
            break
    
    if pullback_bi_index is None:
        return None
    
    pullback_bi = bis[pullback_bi_index]
    
    # 检查回抽是否不破一类买点价格
    if pullback_bi.end_price <= buy1.price:
        logger.debug(f"回抽破了一类买点：{pullback_bi.end_price:.2f} <= {buy1.price:.2f}")
        return None
    
    # 寻找确认笔（上涨笔）
    confirm_bi_index = None
    for i in range(pullback_bi_index + 1, min(pullback_bi_index + 3, len(bis))):
        bi = bis[i]
        if bi.end_price > bi.start_price and bi.start_type == 'bottom':
            confirm_bi_index = i
            break
    
    if confirm_bi_index is None:
        return None
    
    # 计算置信度
    pullback_depth = (buy1.bi.end_price - pullback_bi.end_price) / buy1.bi.end_price
    depth_factor = max(0.5, 1.0 - pullback_depth * 5)  # 回抽越深，置信度越低
    confidence = min(1.0, buy1.confidence * depth_factor)  # 限制上限 100%
    
    return Maimaidian(
        point_type='buy2',
        index=pullback_bi_index,
        price=pullback_bi.end_price,
        confidence=confidence,
        bi=pullback_bi,
        zhongshu=None,
        beichi=None,
        description=f"二类买点：回抽确认，价格 {pullback_bi.end_price:.2f}, "
                   f"回抽深度 {pullback_depth:.1%}, 置信度 {min(1.0, confidence):.1%}"
    )


def _find_type2_sell(
    bis: List[Bi],
    zhongshus: List[Zhongshu],
    sell1: Maimaidian
) -> Optional[Maimaidian]:
    """
    寻找二类卖点

    条件：
    1. 一类卖点后，出现第一次反弹（下跌笔 -> 上涨笔）
    2. 上涨笔的高点不破一类卖点的价格
    3. 确认后出现下跌笔
    """
    sell1_index = sell1.index
    
    if sell1_index >= len(bis) - 1:
        return None
    
    # 寻找下跌笔
    down_bi_index = None
    for i in range(sell1_index + 1, min(sell1_index + 5, len(bis))):
        bi = bis[i]
        if bi.end_price < bi.start_price and bi.start_type == 'top':
            down_bi_index = i
            break
    
    if down_bi_index is None:
        return None
    
    # 寻找反弹笔（上涨笔）
    rebound_bi_index = None
    for i in range(down_bi_index + 1, min(down_bi_index + 3, len(bis))):
        bi = bis[i]
        if bi.end_price > bi.start_price and bi.start_type == 'bottom':
            rebound_bi_index = i
            break
    
    if rebound_bi_index is None:
        return None
    
    rebound_bi = bis[rebound_bi_index]
    
    # 检查反弹是否不破一类卖点价格
    if rebound_bi.end_price >= sell1.price:
        logger.debug(f"反弹破了一类卖点：{rebound_bi.end_price:.2f} >= {sell1.price:.2f}")
        return None
    
    # 计算置信度
    rebound_height = (sell1.bi.end_price - rebound_bi.end_price) / sell1.bi.end_price
    height_factor = max(0.5, 1.0 - rebound_height * 5)
    confidence = min(1.0, sell1.confidence * height_factor)  # 限制上限 100%
    
    return Maimaidian(
        point_type='sell2',
        index=rebound_bi_index,
        price=rebound_bi.end_price,
        confidence=confidence,
        bi=rebound_bi,
        zhongshu=None,
        beichi=None,
        description=f"二类卖点：反弹确认，价格 {rebound_bi.end_price:.2f}, "
                   f"反弹高度 {rebound_height:.1%}, 置信度 {min(1.0, confidence):.1%}"
    )


def _identify_type3_points(
    bis: List[Bi],
    zhongshus: List[Zhongshu],
    existing_points: List[Maimaidian]
) -> List[Maimaidian]:
    """
    识别三类买卖点（中枢破坏点）

    三类买点：突破中枢后，回抽不破中枢
    三类卖点：跌破中枢后，反弹不破中枢
    """
    points = []
    
    if len(zhongshus) == 0:
        return points
    
    # 对每个中枢检查三类买卖点
    for zs in zhongshus:
        # 检查中枢突破后的三类买点
        type3_buy = _find_type3_buy(bis, zs)
        if type3_buy:
            points.append(type3_buy)
        
        # 检查中枢跌破后的三类卖点
        type3_sell = _find_type3_sell(bis, zs)
        if type3_sell:
            points.append(type3_sell)
    
    return points


def _find_type3_buy(
    bis: List[Bi],
    zs: Zhongshu
) -> Optional[Maimaidian]:
    """
    寻找三类买点

    条件：
    1. 有笔突破中枢上沿（zg）
    2. 突破后出现回抽
    3. 回抽的低点不破中枢下沿（zd）
    4. 确认后继续上涨
    """
    # 检查中枢后是否有突破笔
    if zs.end_index >= len(bis) - 1:
        return None
    
    # 寻找突破中枢上沿的笔
    breakout_bi_index = None
    for i in range(zs.end_index + 1, len(bis)):
        bi = bis[i]
        bi_high = max(bi.start_price, bi.end_price)
        
        if bi_high > zs.zg:
            breakout_bi_index = i
            break
    
    if breakout_bi_index is None:
        return None
    
    # 确认突破方向是向上
    breakout_bi = bis[breakout_bi_index]
    if breakout_bi.end_price <= breakout_bi.start_price:
        return None
    
    # 寻找回抽笔（下跌笔）
    if breakout_bi_index >= len(bis) - 1:
        return None
    
    pullback_bi_index = None
    for i in range(breakout_bi_index + 1, min(breakout_bi_index + 3, len(bis))):
        bi = bis[i]
        if bi.end_price < bi.start_price:
            pullback_bi_index = i
            break
    
    if pullback_bi_index is None:
        return None
    
    pullback_bi = bis[pullback_bi_index]
    pullback_low = min(pullback_bi.start_price, pullback_bi.end_price)
    
    # 检查回抽是否不破中枢下沿
    if pullback_low < zs.zd:
        logger.debug(f"回抽破了中枢下沿：{pullback_low:.2f} < {zs.zd:.2f}")
        return None
    
    # 计算置信度
    pullback_depth = (zs.zg - pullback_low) / zs.zg
    depth_factor = max(0.3, 1.0 - pullback_depth * 3)
    
    # 中枢强度：延伸次数越多，中枢越强，突破越可信
    zs_strength = min(1.0, zs.extend_count / 10 + 0.5)
    
    confidence = min(1.0, depth_factor * zs_strength)  # 限制上限 100%
    
    return Maimaidian(
        point_type='buy3',
        index=pullback_bi_index,
        price=pullback_low,
        confidence=confidence,
        bi=pullback_bi,
        zhongshu=zs,
        beichi=None,
        description=f"三类买点：中枢突破回抽，价格 {pullback_low:.2f}, "
                   f"中枢 [{zs.zd:.2f}, {zs.zg:.2f}], 置信度 {min(1.0, confidence):.1%}"
    )


def _find_type3_sell(
    bis: List[Bi],
    zs: Zhongshu
) -> Optional[Maimaidian]:
    """
    寻找三类卖点

    条件：
    1. 有笔跌破中枢下沿（zd）
    2. 跌破后出现反弹
    3. 反弹的高点不破中枢上沿（zg）
    4. 确认后继续下跌
    """
    # 检查中枢后是否有跌破笔
    if zs.end_index >= len(bis) - 1:
        return None
    
    # 寻找跌破中枢下沿的笔
    breakdown_bi_index = None
    for i in range(zs.end_index + 1, len(bis)):
        bi = bis[i]
        bi_low = min(bi.start_price, bi.end_price)
        
        if bi_low < zs.zd:
            breakdown_bi_index = i
            break
    
    if breakdown_bi_index is None:
        return None
    
    # 确认跌破方向是向下
    breakdown_bi = bis[breakdown_bi_index]
    if breakdown_bi.end_price >= breakdown_bi.start_price:
        return None
    
    # 寻找反弹笔（上涨笔）
    if breakdown_bi_index >= len(bis) - 1:
        return None
    
    rebound_bi_index = None
    for i in range(breakdown_bi_index + 1, min(breakdown_bi_index + 3, len(bis))):
        bi = bis[i]
        if bi.end_price > bi.start_price:
            rebound_bi_index = i
            break
    
    if rebound_bi_index is None:
        return None
    
    rebound_bi = bis[rebound_bi_index]
    rebound_high = max(rebound_bi.start_price, rebound_bi.end_price)
    
    # 检查反弹是否不破中枢上沿
    if rebound_high > zs.zg:
        logger.debug(f"反弹破了中枢上沿：{rebound_high:.2f} > {zs.zg:.2f}")
        return None
    
    # 计算置信度
    rebound_height = (rebound_high - zs.zd) / zs.zd
    height_factor = max(0.3, 1.0 - rebound_height * 3)
    
    zs_strength = min(1.0, zs.extend_count / 10 + 0.5)
    
    confidence = min(1.0, height_factor * zs_strength)  # 限制上限 100%
    
    return Maimaidian(
        point_type='sell3',
        index=rebound_bi_index,
        price=rebound_high,
        confidence=confidence,
        bi=rebound_bi,
        zhongshu=zs,
        beichi=None,
        description=f"三类卖点：中枢跌破反弹，价格 {rebound_high:.2f}, "
                   f"中枢 [{zs.zd:.2f}, {zs.zg:.2f}], 置信度 {min(1.0, confidence):.1%}"
    )


def classify_buy_sell_point(point: Maimaidian) -> str:
    """
    分类买卖点

    Args:
        point: 买卖点对象

    Returns:
        分类字符串：'1 买'、'2 买'、'3 买'、'1 卖'、'2 卖'、'3 卖'
    """
    type_mapping = {
        'buy1': '1 买',
        'buy2': '2 买',
        'buy3': '3 买',
        'sell1': '1 卖',
        'sell2': '2 卖',
        'sell3': '3 卖'
    }
    
    return type_mapping.get(point.point_type, '未知')


def get_maimaidian_statistics(points: List[Maimaidian]) -> Dict[str, float]:
    """
    获取买卖点统计信息
    """
    if len(points) == 0:
        return {
            'total_count': 0,
            'buy_count': 0,
            'sell_count': 0,
            'type1_count': 0,
            'type2_count': 0,
            'type3_count': 0,
            'avg_confidence': 0.0
        }
    
    buy_count = sum(1 for p in points if p.point_type.startswith('buy'))
    sell_count = sum(1 for p in points if p.point_type.startswith('sell'))
    
    type1_count = sum(1 for p in points if p.point_type.endswith('1'))
    type2_count = sum(1 for p in points if p.point_type.endswith('2'))
    type3_count = sum(1 for p in points if p.point_type.endswith('3'))
    
    confidences = [p.confidence for p in points]
    
    return {
        'total_count': len(points),
        'buy_count': buy_count,
        'sell_count': sell_count,
        'type1_count': type1_count,
        'type2_count': type2_count,
        'type3_count': type3_count,
        'avg_confidence': np.mean(confidences),
        'max_confidence': np.max(confidences),
        'min_confidence': np.min(confidences)
    }


if __name__ == "__main__":
    print("=" * 50)
    print("缠论买卖点识别模块 v0.2.0")
    print("=" * 50)
    print("\n✓ 模块加载成功")
