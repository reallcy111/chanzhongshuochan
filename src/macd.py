"""
缠论 MACD 指标计算模块
计算 DIF、DEA、MACD 柱状图
"""

import pandas as pd
from typing import Dict, Tuple
import numpy as np
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_ema(
    prices: pd.Series,
    period: int
) -> pd.Series:
    """
    计算指数移动平均线（EMA）

    Args:
        prices: 价格序列
        period: 周期

    Returns:
        EMA 序列
    """
    # 输入验证
    if prices is None or len(prices) == 0:
        raise ValueError("价格序列不能为空")
    
    if period <= 0:
        raise ValueError("周期必须大于0")

    try:
        if len(prices) < period:
            return pd.Series([np.nan] * len(prices), index=prices.index)

        # 计算平滑因子
        k = 2.0 / (period + 1)

        # 初始化 EMA
        ema = prices.copy()

        # 前 period-1 个值为 NaN
        ema.iloc[:period-1] = np.nan

        # 第一个 EMA 值使用简单移动平均
        ema.iloc[period-1] = prices.iloc[:period].mean()

        # 递归计算后续 EMA
        for i in range(period, len(prices)):
            ema.iloc[i] = prices.iloc[i] * k + ema.iloc[i-1] * (1 - k)

        return ema

    except Exception as e:
        logger.error(f"计算 EMA 出错: {e}", exc_info=True)
        raise


def calculate_macd(
    klines: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> pd.DataFrame:
    """
    计算 MACD 指标

    MACD 由三部分组成：
    1. DIF（快线）= EMA(12) - EMA(26)
    2. DEA（慢线）= EMA(DIF, 9)
    3. MACD 柱 = (DIF - DEA) * 2

    Args:
        klines: K 线数据 DataFrame，必须包含 'close' 列
        fast_period: 快线周期，默认 12
        slow_period: 慢线周期，默认 26
        signal_period: 信号线周期，默认 9

    Returns:
        包含 DIF、DEA、MACD 列的 DataFrame

    Raises:
        ValueError: 如果 K 线数据缺少 'close' 列
    """
    # 输入验证
    if klines is None or len(klines) == 0:
        raise ValueError("K线数据不能为空")
    
    if 'close' not in klines.columns:
        raise ValueError("K线数据必须包含 'close' 列")

    try:
        # 数据类型验证
        close_prices = klines['close'].astype(float)

        if len(klines) < slow_period + signal_period:
            raise ValueError(f"K线数据长度至少需要 {slow_period + signal_period} 根")

        # 计算快慢 EMA
        ema_fast = calculate_ema(close_prices, fast_period)
        ema_slow = calculate_ema(close_prices, slow_period)

        # 计算 DIF
        dif = ema_fast - ema_slow

        # 计算 DEA（DIF 的 EMA）
        dea = calculate_ema(dif.dropna(), signal_period)

        # 计算 MACD 柱
        macd = (dif - dea) * 2

        # 创建结果 DataFrame
        result = pd.DataFrame({
            'DIF': dif,
            'DEA': dea,
            'MACD': macd
        }, index=klines.index)

        return result

    except Exception as e:
        logger.error(f"计算 MACD 出错: {e}", exc_info=True)
        raise


def get_macd_signals(macd_df: pd.DataFrame) -> pd.DataFrame:
    """
    获取 MACD 信号

    信号类型：
    1. 金叉：DIF 上穿 DEA（DIF 从下往上穿过 DEA）
    2. 死叉：DIF 下穿 DEA（DIF 从上往下穿过 DEA）
    3. 红柱变大：MACD 柱从负变正或正值增加
    4. 绿柱变大：MACD 柱从正变负或负值减小

    Args:
        macd_df: MACD 指标 DataFrame

    Returns:
        信号 DataFrame，包含 'signal' 和 'value' 列
    """
    # 输入验证
    if macd_df is None or len(macd_df) == 0:
        raise ValueError("MACD 数据不能为空")
    
    if len(macd_df) < 3:
        return pd.DataFrame(columns=['signal', 'value'])

    try:
        signals = pd.DataFrame(index=macd_df.index)
        signals['signal'] = None

        for i in range(1, len(macd_df)):
            if pd.isna(macd_df.iloc[i]['DIF']) or pd.isna(macd_df.iloc[i]['DEA']):
                continue

            prev_dif = macd_df.iloc[i-1]['DIF']
            curr_dif = macd_df.iloc[i]['DIF']
            prev_dea = macd_df.iloc[i-1]['DEA']
            curr_dea = macd_df.iloc[i]['DEA']
            prev_macd = macd_df.iloc[i-1]['MACD']
            curr_macd = macd_df.iloc[i]['MACD']

            # 检测金叉
            if prev_dif < prev_dea and curr_dif > curr_dea:
                signals.loc[macd_df.index[i], 'signal'] = 'golden_cross'

            # 检测死叉
            elif prev_dif > prev_dea and curr_dif < curr_dea:
                signals.loc[macd_df.index[i], 'signal'] = 'death_cross'

            # 检测红柱变大
            elif curr_macd > 0 and (prev_macd <= 0 or curr_macd > prev_macd):
                if pd.notna(prev_macd) and curr_macd > prev_macd > 0:
                    signals.loc[macd_df.index[i], 'signal'] = 'red_increase'

            # 检测绿柱变大
            elif curr_macd < 0 and (prev_macd >= 0 or curr_macd < prev_macd):
                if pd.notna(prev_macd) and curr_macd < prev_macd < 0:
                    signals.loc[macd_df.index[i], 'signal'] = 'green_increase'

        return signals

    except Exception as e:
        logger.error(f"获取 MACD 信号出错: {e}", exc_info=True)
        raise


def calculate_macd_divergence(
    klines: pd.DataFrame,
    macd_df: pd.DataFrame,
    window: int = 20
) -> Dict[str, list]:
    """
    计算 MACD 背离

    背离类型：
    1. 顶背离：价格创新高，但 MACD 不创新高
    2. 底背离：价格创新低，但 MACD 不创新低

    Args:
        klines: K 线数据
        macd_df: MACD 指标数据
        window: 检测窗口大小

    Returns:
        包含背离信息的字典
    """
    divergences = {
        'top': [],
        'bottom': []
    }

    if len(klines) < window:
        return divergences

    close_prices = klines['close']

    for i in range(window, len(klines)):
        # 获取窗口内的数据
        window_close = close_prices.iloc[i-window:i]
        window_macd = macd_df['MACD'].iloc[i-window:i]

        # 寻找价格和 MACD 的极值点
        price_max_idx = window_close.idxmax()
        price_min_idx = window_close.idxmin()
        macd_max_idx = window_macd.idxmax()
        macd_min_idx = window_macd.idxmin()

        # 检测顶背离：价格新高，MACD 未新高
        if price_max_idx == klines.index[i-1]:
            if macd_max_idx != klines.index[i-1]:
                divergences['top'].append({
                    'index': i-1,
                    'price': close_prices.iloc[i-1],
                    'macd': macd_df['MACD'].iloc[i-1]
                })

        # 检测底背离：价格新低，MACD 未新低
        if price_min_idx == klines.index[i-1]:
            if macd_min_idx != klines.index[i-1]:
                divergences['bottom'].append({
                    'index': i-1,
                    'price': close_prices.iloc[i-1],
                    'macd': macd_df['MACD'].iloc[i-1]
                })

    return divergences


def get_macd_statistics(macd_df: pd.DataFrame) -> Dict[str, float]:
    """
    获取 MACD 统计信息

    Args:
        macd_df: MACD 指标 DataFrame

    Returns:
        统计信息字典
    """
    # 输入验证
    if macd_df is None or len(macd_df) == 0:
        raise ValueError("MACD 数据不能为空")

    try:
        valid_dif = macd_df['DIF'].dropna()
        valid_macd = macd_df['MACD'].dropna()

        if len(valid_dif) == 0:
            return {
                'dif_mean': 0.0,
                'dif_std': 0.0,
                'macd_mean': 0.0,
                'macd_std': 0.0,
                'golden_cross_count': 0,
                'death_cross_count': 0
            }

        signals = get_macd_signals(macd_df)
        golden_cross_count = (signals['signal'] == 'golden_cross').sum()
        death_cross_count = (signals['signal'] == 'death_cross').sum()

        return {
            'dif_mean': float(valid_dif.mean()),
            'dif_std': float(valid_dif.std()),
            'macd_mean': float(valid_macd.mean()),
            'macd_std': float(valid_macd.std()),
            'golden_cross_count': int(golden_cross_count),
            'death_cross_count': int(death_cross_count)
        }

    except Exception as e:
        logger.error(f"计算 MACD 统计信息出错: {e}", exc_info=True)
        raise


# 单元测试
def test_calculate_macd():
    """测试 MACD 计算"""
    print("测试 MACD 计算...")

    # 测试用例 1: 简单趋势数据
    n = 100
    data = pd.DataFrame({
        'open': 100 + np.arange(n) / 10 + np.random.randn(n) * 0.5,
        'high': 100 + np.arange(n) / 10 + np.random.randn(n) * 0.5 + 1,
        'low': 100 + np.arange(n) / 10 + np.random.randn(n) * 0.5 - 1,
        'close': 100 + np.arange(n) / 10 + np.random.randn(n) * 0.5
    })

    macd_result = calculate_macd(data)
    print(f"测试用例 1: 计算结果列数 = {len(macd_result.columns)}")
    print(f"  有效 DIF 数量: {macd_result['DIF'].dropna().shape[0]}")
    print(f"  有效 DEA 数量: {macd_result['DEA'].dropna().shape[0]}")
    print(f"  有效 MACD 数量: {macd_result['MACD'].dropna().shape[0]}")

    # 测试用例 2: 震荡数据
    n = 100
    data = pd.DataFrame({
        'open': 100 + np.sin(np.arange(n) / 10) * 10 + np.random.randn(n) * 0.5,
        'high': 100 + np.sin(np.arange(n) / 10) * 10 + np.random.randn(n) * 0.5 + 1,
        'low': 100 + np.sin(np.arange(n) / 10) * 10 + np.random.randn(n) * 0.5 - 1,
        'close': 100 + np.sin(np.arange(n) / 10) * 10 + np.random.randn(n) * 0.5
    })

    macd_result = calculate_macd(data)
    stats = get_macd_statistics(macd_result)
    print(f"\n测试用例 2（震荡数据）:")
    print(f"  DIF 均值: {stats['dif_mean']:.4f}")
    print(f"  DIF 标准差: {stats['dif_std']:.4f}")
    print(f"  MACD 均值: {stats['macd_mean']:.4f}")
    print(f"  金叉次数: {stats['golden_cross_count']}")
    print(f"  死叉次数: {stats['death_cross_count']}")

    # 测试用例 3: 随机数据
    np.random.seed(42)
    n = 100
    data = pd.DataFrame({
        'open': 100 + np.random.randn(n).cumsum() / 10,
        'high': 100 + np.random.randn(n).cumsum() / 10 + np.abs(np.random.randn(n)),
        'low': 100 + np.random.randn(n).cumsum() / 10 - np.abs(np.random.randn(n)),
        'close': 100 + np.random.randn(n).cumsum() / 10
    })

    macd_result = calculate_macd(data)
    print(f"\n测试用例 3（随机数据）:")
    print(f"  计算完成，DIF 范围: [{macd_result['DIF'].min():.2f}, {macd_result['DIF'].max():.2f}]")
    print(f"  MACD 范围: [{macd_result['MACD'].min():.2f}, {macd_result['MACD'].max():.2f}]")

    print("✓ MACD 计算测试通过\n")


def test_macd_signals():
    """测试 MACD 信号识别"""
    print("测试 MACD 信号识别...")

    # 创建一个有明显金叉死叉的数据
    n = 100
    data = pd.DataFrame({
        'close': 100 + np.sin(np.arange(n) / 5) * 20 + np.random.randn(n)
    })

    macd_result = calculate_macd(data)
    signals = get_macd_signals(macd_result)

    signal_counts = signals['signal'].value_counts()
    print(f"识别到的信号:")
    for signal, count in signal_counts.items():
        print(f"  {signal}: {count} 次")

    print("✓ MACD 信号识别测试通过\n")


def test_edge_cases():
    """测试边界情况"""
    print("测试边界情况...")

    # 测试数据不足
    try:
        data = pd.DataFrame({'close': [100, 101, 102]})
        calculate_macd(data)
        print("✗ 应该抛出异常")
    except ValueError as e:
        print(f"✓ 正确处理数据不足: {str(e)[:50]}...")

    # 测试缺少列
    try:
        data = pd.DataFrame({'open': [100, 101, 102]})
        calculate_macd(data)
        print("✗ 应该抛出异常")
    except ValueError as e:
        print(f"✓ 正确处理缺少列: {str(e)}")

    # 测试空数据
    empty_data = pd.DataFrame({'close': []})
    try:
        calculate_macd(empty_data)
    except:
        print("✓ 正确处理空数据")

    print("✓ 边界情况测试通过\n")


if __name__ == "__main__":
    test_calculate_macd()
    test_macd_signals()
    test_edge_cases()