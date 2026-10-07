"""
缠中说禅技能 · 高层入口 (v0.5.2)
====================================

低层: analyze_chanlun(klines_df, ...) - 纯算法, 接 DataFrame, 不联网
高层: analyze_symbol(symbol, name, ...) - 编排, 自动拉多源 + 跨源验证 + 跑分析

**命名约定**: 本模块完全不依赖 / 调用 nuwa 技能.
多源抓取 + 跨源验证是借鉴 nuwa 的设计, 但实现归 chanzhongshuochan 自己.
"""

import sys
import os
from datetime import datetime
from typing import Dict, Optional
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import (
    fetch_quote_qveris,
    fetch_quote_tx,
    fetch_klines_akshare,
    fetch_news_tavily,
    fetch_news_sina,
)
from main import analyze_chanlun
from quant_detect import detect_quant_features


# ============================================================
# 内部: 5 lane 并行抓取
# ============================================================

def _fetch_parallel(symbol: str, name: str, days: int, with_news: bool) -> Dict:
    """借鉴 nuwa 多源设计: 5 lane 并行抓 (chanzhongshuochan 自己实现, 不调 nuwa)"""
    results = {}

    lanes = {
        'quote_qveris': lambda: fetch_quote_qveris(symbol),
        'quote_tx':     lambda: fetch_quote_tx(symbol),
        'kline':        lambda: fetch_klines_akshare(symbol, days),
    }
    if with_news:
        lanes['news_tavily'] = lambda: fetch_news_tavily(f'{name} 公告 OR 异动')
        lanes['news_sina']   = lambda: fetch_news_sina(symbol)

    with ThreadPoolExecutor(max_workers=len(lanes)) as ex:
        futs = {k: ex.submit(fn) for k, fn in lanes.items()}
        for k, fut in futs.items():
            try:
                results[k] = fut.result(timeout=20)
            except Exception as e:
                print(f'[WARN] Lane {k} fail: {e}', file=sys.stderr)
                results[k] = None

    # 主价: qveris 优先 → qt 备选
    results['quote'] = results.get('quote_qveris') or results.get('quote_tx')

    # 日 K 解包
    kline_result = results.get('kline')
    if kline_result and isinstance(kline_result, tuple):
        results['kline_df'], results['kline_src'] = kline_result
    else:
        results['kline_df'] = results['kline_src'] = None

    return results


# ============================================================
# 内部: 跨源价格对比 (借鉴 nuwa 矛盾保留)
# ============================================================

def _validate_cross_source(results: Dict) -> Dict:
    """跨源价格对比, 借鉴 nuwa 矛盾保留规则 (chanzhongshuochan 自己实现)"""
    out = {
        'conflicts': [],
        'sources': {},
    }
    qveris_q = results.get('quote_qveris')
    qt_q = results.get('quote_tx')

    if qveris_q and qt_q:
        qveris_price = qveris_q.get('price', 0)
        qt_price = qt_q.get('price', 0)
        if qt_price > 0 and qveris_price > 0:
            diff_pct = abs(qveris_price - qt_price) / qt_price * 100
            out['sources']['quote_qveris_price'] = qveris_price
            out['sources']['quote_qt_price'] = qt_price
            out['sources']['quote_diff_pct'] = round(diff_pct, 3)
            if diff_pct > 1.0:
                out['conflicts'].append({
                    'type': 'price',
                    'qveris': qveris_price,
                    'qt': qt_price,
                    'diff_pct': round(diff_pct, 2),
                    'selected': 'qveris',
                })
    return out


# ============================================================
# 内部: 量化痕迹派生
# ============================================================

def _derive_quant(quote: Optional[Dict], df, lookback: int = 20) -> Dict:
    """从 quote + 日K 派生量化指标"""
    signals = {}
    if quote:
        if quote.get('turnover_rate') is not None:
            signals['turnover_rate'] = quote['turnover_rate']
            if quote['turnover_rate'] > 5:
                signals.setdefault('anomalies', []).append(
                    f"[ANOMALY:turnover={quote['turnover_rate']:.2f}% high > 5%]"
                )
        if quote.get('volume_rate'):
            signals['volume_rate'] = quote['volume_rate']
            if quote['volume_rate'] > 2:
                signals.setdefault('anomalies', []).append(
                    f"[ANOMALY:volume_rate={quote['volume_rate']:.2f} high > 2]"
                )
        if quote.get('entrust_rate'):
            signals['entrust_rate'] = quote['entrust_rate']
        if quote.get('inner_disk') and quote.get('outer_disk'):
            outer = quote['outer_disk']
            inner = quote['inner_disk']
            if outer > 0:
                signals['inner_outer_ratio'] = inner / outer
                if inner / outer > 3:
                    signals.setdefault('anomalies', []).append(
                        f"[ANOMALY:flow] 内/外盘比 {inner/outer:.2f} > 3"
                    )

    if df is not None and len(df) >= lookback:
        try:
            quant_features = detect_quant_features(df, lookback=lookback)
            signals['control_score'] = quant_features.get('control_score', 0)
            if 'volume' in df.columns:
                vol_recent = df['volume'].tail(5).mean()
                vol_baseline = df['volume'].tail(lookback).mean()
                vol_std = df['volume'].tail(lookback).std()
                if vol_std > 0:
                    zscore = (vol_recent - vol_baseline) / vol_std
                    signals['volume_anomaly_zscore'] = round(zscore, 2)
                    if abs(zscore) > 2:
                        signals.setdefault('anomalies', []).append(
                            f"[ANOMALY:volume_zscore={zscore:.2f} |z|>2]"
                        )
            for feat in ['volume_abnormal_count', 'price_volume_divergence_count',
                          'volume_concentration_count', 'large_flow_count']:
                if feat in quant_features:
                    signals[feat] = quant_features[feat]
        except Exception as e:
            print(f'[WARN] quant derive fail: {e}', file=sys.stderr)

    return signals


# ============================================================
# 内部: 消息面合并去重
# ============================================================

def _combine_news(news_tavily, news_sina) -> list:
    """合并 tavily + 新浪 vip, 按 tier + 去重"""
    items = []
    items.extend(news_sina or [])
    items.extend(news_tavily or [])
    seen = set()
    deduped = []
    for it in items:
        key = it.get('title', '')[:30]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    deduped.sort(key=lambda x: x.get('date', ''), reverse=True)
    return deduped[:15]


# ============================================================
# 公开 API: analyze_symbol (高层入口)
# ============================================================

def analyze_symbol(
    symbol: str,
    name: str = '',
    days: int = 180,
    with_news: bool = True,
    initial_trend: str = 'up',
) -> Dict:
    """
    chanzhongshuochan 高层入口: 拉多源数据 + 跨源验证 + 跑缠论分析

    与 analyze_chanlun 区别:
      - analyze_chanlun(klines_df) - 纯算法, 不联网
      - analyze_symbol(symbol) - 编排, 自动拉数据 + 验证 + 分析

    借鉴 nuwa 设计 (多源 + 跨源验证), 实现归 chanzhongshuochan 自己, 不调 nuwa 技能.

    Args:
        symbol: 'sh600703' 或 'sz000001' (akshare 格式)
        name: 股票名称 (用于 tavily 搜索词), 默认 ''
        days: 日 K 历史天数 (默认 180)
        with_news: 是否抓消息面
        initial_trend: 缠论初始趋势 ('up' or 'down')

    Returns:
        dict: {
            'status': 'ok' | 'fail',
            'symbol': 'sh600703',
            'name': '...',
            'generated_at': ISO timestamp,
            'quote': 主价 dict 或 None,
            'kline_df': 日 K DataFrame 或 None,
            'kline_src': '腾讯日K' / '新浪日K' / 'N/A',
            'chanlun': analyze_chanlun 的输出 (分型/笔/中枢/MACD),
            'quant': 量化痕迹 dict,
            'news': 消息面列表 (合并去重),
            'validation': {conflicts, sources},
            'total_seconds': 总耗时,
        }
    """
    name = name or symbol
    out = {
        'status': 'ok',
        'symbol': symbol,
        'name': name,
        'generated_at': datetime.now().isoformat(),
    }

    # === 阶段 1: 多源并行抓取 ===
    t0 = datetime.now()
    fetch_results = _fetch_parallel(symbol, name, days, with_news)
    t1 = datetime.now()

    quote = fetch_results.get('quote')
    df = fetch_results.get('kline_df')
    kline_src = fetch_results.get('kline_src', 'N/A')

    if df is None and quote is None:
        out['status'] = 'fail'
        out['fail_reason'] = 'all data sources unavailable'
        return out

    # === 量化派生 ===
    quant = _derive_quant(quote, df)

    # === 阶段 2: 跨源验证 ===
    validation = _validate_cross_source(fetch_results)
    news = _combine_news(fetch_results.get('news_tavily'), fetch_results.get('news_sina'))
    t2 = datetime.now()

    # === 阶段 3: 缠论分析 (用验证后数据) ===
    if df is not None:
        chanlun_result = analyze_chanlun(df, initial_trend=initial_trend)
    else:
        chanlun_result = {'fenxings': [], 'valid_fenxing': [], 'bis': [],
                          'validated_bis': [], 'zhongshus': [], 'statistics': {}}
    t3 = datetime.now()

    out.update({
        'quote': quote,
        'kline_df': df,
        'kline_src': kline_src,
        'chanlun': chanlun_result,
        'quant': quant,
        'news': news,
        'validation': validation,
        'total_seconds': round((t3 - t0).total_seconds(), 1),
    })
    return out
