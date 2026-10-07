"""
缠论量化资金检测模块 v0.2.0
基于成交量、换手率、资金流向等指标检测量化资金特征

量化资金特征：
1. 异常成交量（成交量突增）
2. 异常换手率（换手率激增）
3. 资金流向异常（大单流入/流出）
4. 成交量分布不均匀（集中放量）
5. 价格与成交量背离

量化控盘度评估：
- 基于多指标综合计算量化资金控盘程度
- 0-100 分制，分数越高表示量化资金参与度越高

实现内容：
- detect_quant_features: 检测量化资金特征
- calculate_control_score: 计算量化控盘度
- check_resonance: 检查缠论信号和量化信号共振
"""

import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class QuantFeature:
    """量化资金特征"""
    feature_type: str  # 特征类型
    value: float  # 特征值
    threshold: float  # 阈值
    score: float  # 该特征的贡献分数 (0-100)
    description: str  # 特征描述
    kline_index: int  # 发生的 K 线索引


@dataclass
class QuantSignal:
    """量化信号"""
    signal_type: str  # 'strong_buy', 'buy', 'hold', 'sell', 'strong_sell'
    control_score: float  # 量化控盘度 (0-100)
    features: List[QuantFeature]  # 检测到的特征列表
    confidence: float  # 置信度 (0-1)
    description: str  # 信号描述


def detect_quant_features(
    klines: pd.DataFrame,
    volume_threshold: float = 2.0,
    turnover_threshold: float = 3.0,
    window: int = 20
) -> Dict[str, List[QuantFeature]]:
    """
    检测量化资金特征

    Args:
        klines: K 线数据 DataFrame，需包含以下列：
            - 'close': 收盘价
            - 'high': 最高价
            - 'low': 最低价
            - 'volume': 成交量（可选）
            - 'turnover': 换手率（可选）
            - 'amount': 成交额（可选）
        volume_threshold: 成交量异常倍数阈值（相对于平均成交量）
        turnover_threshold: 换手率异常倍数阈值
        window: 计算平均值的时间窗口

    Returns:
        包含各类特征的字典
    """
    features = {
        'volume_abnormal': [],
        'turnover_abnormal': [],
        'price_volume_divergence': [],
        'volume_concentration': [],
        'large_flow': []
    }
    
    # 验证输入数据
    if len(klines) < window:
        logger.warning(f"K 线数据不足：{len(klines)} < {window}")
        return features
    
    required_columns = ['close', 'high', 'low']
    missing_cols = [col for col in required_columns if col not in klines.columns]
    if missing_cols:
        raise ValueError(f"K 线数据缺少必要列：{missing_cols}")
    
    # 1. 检测异常成交量
    if 'volume' in klines.columns:
        volume_features = _detect_volume_abnormal(
            klines, volume_threshold, window
        )
        features['volume_abnormal'] = volume_features
    
    # 2. 检测异常换手率
    if 'turnover' in klines.columns:
        turnover_features = _detect_turnover_abnormal(
            klines, turnover_threshold, window
        )
        features['turnover_abnormal'] = turnover_features
    
    # 3. 检测价格与成交量背离
    if 'volume' in klines.columns:
        divergence_features = _detect_price_volume_divergence(
            klines, window
        )
        features['price_volume_divergence'] = divergence_features
    
    # 4. 检测成交量集中度
    if 'volume' in klines.columns:
        concentration_features = _detect_volume_concentration(
            klines, window
        )
        features['volume_concentration'] = concentration_features
    
    # 5. 检测大单资金流向（如果有 amount 数据）
    if 'amount' in klines.columns:
        flow_features = _detect_large_flow(klines, window)
        features['large_flow'] = flow_features
    
    return features


def _detect_volume_abnormal(
    klines: pd.DataFrame,
    threshold: float,
    window: int
) -> List[QuantFeature]:
    """
    检测异常成交量

    条件：
    - 当前成交量 > 平均成交量 * threshold
    """
    features = []
    
    volume = klines['volume']
    
    # 计算滚动平均成交量
    avg_volume = volume.rolling(window=window, min_periods=1).mean()
    
    for i in range(window, len(klines)):
        curr_volume = volume.iloc[i]
        curr_avg = avg_volume.iloc[i]
        
        if curr_avg <= 0:
            continue
        
        ratio = curr_volume / curr_avg
        
        if ratio >= threshold:
            # 计算贡献分数
            # 倍数越大，分数越高
            score = min(100, (ratio - threshold) * 30 + 30)
            
            features.append(QuantFeature(
                feature_type='volume_abnormal',
                value=ratio,
                threshold=threshold,
                score=score,
                description=f"异常放量：成交量是平均的 {ratio:.1f} 倍",
                kline_index=i
            ))
    
    return features


def _detect_turnover_abnormal(
    klines: pd.DataFrame,
    threshold: float,
    window: int
) -> List[QuantFeature]:
    """
    检测异常换手率

    条件：
    - 当前换手率 > 平均换手率 * threshold
    """
    features = []
    
    turnover = klines['turnover']
    
    # 计算滚动平均换手率
    avg_turnover = turnover.rolling(window=window, min_periods=1).mean()
    
    for i in range(window, len(klines)):
        curr_turnover = turnover.iloc[i]
        curr_avg = avg_turnover.iloc[i]
        
        if curr_avg <= 0:
            continue
        
        ratio = curr_turnover / curr_avg
        
        if ratio >= threshold:
            score = min(100, (ratio - threshold) * 25 + 25)
            
            features.append(QuantFeature(
                feature_type='turnover_abnormal',
                value=ratio,
                threshold=threshold,
                score=score,
                description=f"异常换手率：换手率是平均的 {ratio:.1f} 倍",
                kline_index=i
            ))
    
    return features


def _detect_price_volume_divergence(
    klines: pd.DataFrame,
    window: int
) -> List[QuantFeature]:
    """
    检测价格与成交量背离

    背离类型：
    - 量价背离：价格上涨但成交量下降（上涨乏力）
    - 量价齐升：价格上涨且成交量放大（强势）
    - 量价齐跌：价格下跌且成交量放大（弱势）
    """
    features = []
    
    close = klines['close']
    volume = klines['volume']
    
    for i in range(window + 1, len(klines)):
        # 检查价格和成交量的变化方向
        prev_close = close.iloc[i - 1]
        curr_close = close.iloc[i]
        prev_volume = volume.iloc[i - 1]
        curr_volume = volume.iloc[i]
        
        price_change = (curr_close - prev_close) / prev_close
        volume_change = (curr_volume - prev_volume) / prev_volume
        
        # 量价背离：价格上涨但成交量下降
        if price_change > 0.02 and volume_change < -0.2:
            score = min(100, abs(price_change) * 500 + abs(volume_change) * 50)
            
            features.append(QuantFeature(
                feature_type='price_volume_divergence',
                value=price_change,
                threshold=0.02,
                score=score,
                description=f"量价背离：价格上涨 {price_change:.1%} 但成交量下降 {volume_change:.1%}",
                kline_index=i
            ))
        
        # 量价齐升：强势信号
        elif price_change > 0.02 and volume_change > 0.2:
            score = min(100, (price_change * 500 + volume_change * 50) / 2)
            
            features.append(QuantFeature(
                feature_type='price_volume_rise',
                value=price_change,
                threshold=0.02,
                score=score,
                description=f"量价齐升：价格上涨 {price_change:.1%} 且成交量放大 {volume_change:.1%}",
                kline_index=i
            ))
    
    return features


def _detect_volume_concentration(
    klines: pd.DataFrame,
    window: int
) -> List[QuantFeature]:
    """
    检测成交量集中度

    成交量集中度反映量化资金的操盘特征：
    - 成交量集中在少数 K 线（集中度高）
    - 成交量均匀分布（集中度低）
    """
    features = []
    
    volume = klines['volume']
    
    for i in range(window, len(klines)):
        window_volume = volume.iloc[i - window + 1:i + 1]
        
        if window_volume.sum() <= 0:
            continue
        
        # 计算集中度（基尼系数简化版）
        # 集中度 = 最大成交量 / 平均成交量
        max_vol = window_volume.max()
        avg_vol = window_volume.mean()
        
        concentration = max_vol / avg_vol if avg_vol > 0 else 0
        
        # 集中度超过 3 倍视为异常
        if concentration >= 3.0:
            score = min(100, (concentration - 3) * 20 + 40)
            
            features.append(QuantFeature(
                feature_type='volume_concentration',
                value=concentration,
                threshold=3.0,
                score=score,
                description=f"成交量集中：最大成交量是平均的 {concentration:.1f} 倍",
                kline_index=i
            ))
    
    return features


def _detect_large_flow(
    klines: pd.DataFrame,
    window: int
) -> List[QuantFeature]:
    """
    检测大单资金流向

    条件：
    - 成交额异常放大（可能为大单操作）
    """
    features = []
    
    amount = klines['amount']
    
    # 计算滚动平均成交额
    avg_amount = amount.rolling(window=window, min_periods=1).mean()
    
    for i in range(window, len(klines)):
        curr_amount = amount.iloc[i]
        curr_avg = avg_amount.iloc[i]
        
        if curr_avg <= 0:
            continue
        
        ratio = curr_amount / curr_avg
        
        # 成交额放大超过 2 倍视为大单操作
        if ratio >= 2.0:
            score = min(100, (ratio - 2) * 25 + 30)
            
            # 判断流向方向（价格上涨为流入，下跌为流出）
            close = klines['close']
            price_change = (close.iloc[i] - close.iloc[i - 1]) / close.iloc[i - 1]
            
            flow_direction = '流入' if price_change > 0 else '流出'
            
            features.append(QuantFeature(
                feature_type='large_flow',
                value=ratio,
                threshold=2.0,
                score=score,
                description=f"大单资金{flow_direction}：成交额是平均的 {ratio:.1f} 倍",
                kline_index=i
            ))
    
    return features


def calculate_control_score(
    features: Dict[str, List[QuantFeature]]
) -> float:
    """
    计算量化控盘度 (0-100)

    综合各特征的贡献分数，计算量化资金的整体控盘程度
    
    Args:
        features: 特征字典

    Returns:
        量化控盘度 (0-100)
    """
    # 各特征的权重
    weights = {
        'volume_abnormal': 0.25,      # 异常成交量权重
        'turnover_abnormal': 0.20,    # 异常换手率权重
        'price_volume_divergence': 0.15,  # 量价背离权重
        'volume_concentration': 0.20,     # 成交量集中度权重
        'large_flow': 0.20           # 大单流向权重
    }
    
    total_score = 0.0
    total_weight = 0.0
    
    for feature_type, feature_list in features.items():
        if len(feature_list) == 0:
            continue
        
        weight = weights.get(feature_type, 0.1)
        
        # 取该类型特征的最高分数
        max_score = max(f.score for f in feature_list)
        
        total_score += max_score * weight
        total_weight += weight
    
    if total_weight == 0:
        return 0.0
    
    # 计算加权平均分数
    control_score = total_score / total_weight
    
    return min(100, max(0, control_score))


def generate_quant_signal(
    features: Dict[str, List[QuantFeature]],
    control_score: float
) -> QuantSignal:
    """
    生成量化信号

    根据控盘度和特征生成买卖信号
    
    Args:
        features: 特征字典
        control_score: 量化控盘度

    Returns:
        量化信号对象
    """
    # 汇总所有特征
    all_features = []
    for feature_list in features.values():
        all_features.extend(feature_list)
    
    # 判断信号类型
    signal_type = 'hold'
    confidence = 0.0
    description = '无明显量化信号'
    
    if control_score >= 70:
        # 高控盘度：量化资金高度参与
        
        # 检查量价齐升特征
        rise_features = features.get('price_volume_rise', [])
        if len(rise_features) > 0:
            signal_type = 'strong_buy'
            confidence = 0.8
            description = '量化资金强势介入，量价齐升'
        
        # 检查大单流入
        flow_features = features.get('large_flow', [])
        inflow = [f for f in flow_features if '流入' in f.description]
        if len(inflow) > 0:
            signal_type = 'buy'
            confidence = 0.7
            description = '大单资金流入，量化参与度高'
    
    elif control_score >= 50:
        # 中等控盘度
        
        # 检查量价背离
        divergence = features.get('price_volume_divergence', [])
        if len(divergence) > 0:
            signal_type = 'sell'
            confidence = 0.6
            description = '量价背离，上涨乏力'
        
        # 检查大单流出
        flow_features = features.get('large_flow', [])
        outflow = [f for f in flow_features if '流出' in f.description]
        if len(outflow) > 0:
            signal_type = 'sell'
            confidence = 0.65
            description = '大单资金流出'
        
        else:
            signal_type = 'hold'
            confidence = 0.5
            description = '量化资金适度参与'
    
    elif control_score >= 30:
        # 低控盘度
        
        # 检查成交量集中
        concentration = features.get('volume_concentration', [])
        if len(concentration) > 0:
            signal_type = 'hold'
            confidence = 0.4
            description = '成交量集中，需关注后续走势'
    
    else:
        # 极低控盘度：量化资金参与度低
        signal_type = 'hold'
        confidence = 0.3
        description = '量化资金参与度低，走势自然'
    
    return QuantSignal(
        signal_type=signal_type,
        control_score=control_score,
        features=all_features,
        confidence=confidence,
        description=description
    )


def check_resonance(
    chanlun_signal: str,
    quant_signal: str
) -> bool:
    """
    检查缠论信号和量化信号共振

    共振定义：
    - 缠论买点 + 量化买入信号 = 共振（强买）
    - 缠论卖点 + 量化卖出信号 = 共振（强卖）
    - 其他情况 = 不共振
    
    Args:
        chanlun_signal: 缠论信号 ('buy1', 'buy2', 'buy3', 'sell1', 'sell2', 'sell3', 'hold')
        quant_signal: 量化信号 ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')

    Returns:
        是否共振
    """
    # 缠论买点
    chanlun_buy = chanlun_signal.startswith('buy')
    
    # 量化买入信号
    quant_buy = quant_signal in ('strong_buy', 'buy')
    
    # 缠论卖点
    chanlun_sell = chanlun_signal.startswith('sell')
    
    # 量化卖出信号
    quant_sell = quant_signal in ('sell', 'strong_sell')
    
    # 共振判断
    if chanlun_buy and quant_buy:
        return True
    elif chanlun_sell and quant_sell:
        return True
    
    return False


if __name__ == "__main__":
    print("=" * 50)
    print("缠论量化资金检测模块 v0.2.0")
    print("=" * 50)
    print("\n✓ 模块加载成功")
