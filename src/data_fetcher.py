"""
缠中说禅技能 · 数据获取层 (v0.5.1 Nuwa)
==========================================

把 Nuwa 三阶段法需要的 5 个数据源的 fetcher 全部封装在此,
供 nuwa_pipeline.py 统一调度.

5 个数据源:
- Lane A (实时价): qveris.cn_financial_pro + qt.gtimg.cn 双源并行
- Lane B (消息面): tavily topic=finance + 新浪 vip 公告时间线
- Lane C (量化):  qveris 量/换手/委比 + 日K 派生
- Lane D (日K):   akshare 腾讯日K + 新浪日K fallback
- Lane E (跨源):  价格交叉验证 (在 nuwa_pipeline.validate_nuwa 里)
"""

import sys
import os
import json
import re
import time
import urllib.request
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ============================================================
# API key 加载 (从 openclaw.json 读)
# ============================================================

def _load_qveris_key() -> Optional[str]:
    try:
        with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
            cfg = json.load(f)
        return cfg.get('plugins', {}).get('entries', {}).get('qveris', {}).get('config', {}).get('apiKey')
    except Exception:
        return None


def _load_tavily_key() -> Optional[str]:
    try:
        with open(os.path.expanduser('~/.openclaw/openclaw.json')) as f:
            cfg = json.load(f)
        return cfg.get('plugins', {}).get('entries', {}).get('tavily', {}).get('config', {}).get('webSearch', {}).get('apiKey')
    except Exception:
        return None


# ============================================================
# Lane A: 实时价 (qveris 主源 + qt.gtimg.cn 备源)
# ============================================================

def fetch_quote_qveris(symbol: str) -> Optional[Dict]:
    """
    通过 qveris.cn_financial_pro.real_time_quotation 拿 A 股实时价

    symbol: 'sh600703' 或 '600703.SH'
    Returns: dict 或 None (失败)
    """
    api_key = _load_qveris_key()
    if not api_key:
        return None

    # 转换 symbol 格式
    raw = symbol.strip().lower()
    if raw.startswith('sh') or raw.startswith('sz'):
        qveris_code = raw[2:].upper() + ('.SH' if raw.startswith('sh') else '.SZ')
    elif raw.endswith('.sh') or raw.endswith('.sz'):
        qveris_code = raw.upper()
    else:
        qveris_code = raw.upper() + '.SH'  # 默认上海

    try:
        body = {
            'tool_id': 'cn_financial_pro.real_time_quotation.v1',
            'parameters': {'codes': qveris_code, 'indicators': 'common'},
            'search_id': 'chanlun-quote',
        }
        req = urllib.request.Request(
            'https://qveris.ai/api/v1/tools/execute',
            data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())

        # qveris 返回 [[{...}]] 双层 list
        data = result.get('result', {}).get('data', [])
        if not data or not data[0]:
            return None
        row = data[0][0] if isinstance(data[0], list) else data[0]

        price = float(row.get('latest', 0))
        pre_close = float(row.get('preClose', 0))
        if price <= 0 or pre_close <= 0:
            return None

        change = price - pre_close
        change_pct = (change / pre_close) * 100
        volume_hand = float(row.get('volume', 0))  # 手
        turnover_rate = float(row.get('turnoverRatio', 0))
        limit_up = pre_close * 1.10 if raw.startswith('sh6') or raw.endswith('.SH') else pre_close * 1.20

        return {
            'price': price,
            'prev_close': pre_close,
            'open': float(row.get('open', 0)),
            'high': float(row.get('high', 0)),
            'low': float(row.get('low', 0)),
            'volume_hand': volume_hand,
            'turnover_rate': turnover_rate,
            'change': round(change, 3),
            'change_pct': round(change_pct, 2),
            'limit_up': round(limit_up, 2),
            'time': str(row.get('time', '')),
            'is_limit_up': abs(price - limit_up) < 0.01 and change_pct > 9.0,
            'source': 'qveris:cn_financial_pro',
            # 扩展字段
            'total_mv': float(row.get('totalCapital', 0)) / 1e8,  # 元 → 亿元
            'turnover_value': f"{float(row.get('amount', 0))/1e8:.2f}亿元",
            'avg_price': float(row.get('amount', 0)) / (volume_hand * 100) if volume_hand else 0,
            # cn_financial_pro 不提供但接口保留
            'pb_ratio': 0.0,
            'volume_rate': 0.0,
            'entrust_rate': 0.0,
            'inner_disk': 0.0,
            'outer_disk': 0.0,
        }
    except Exception as e:
        print(f'[WARN] qveris 实时价 fail: {e}', file=sys.stderr)
        return None


def fetch_quote_tx(symbol: str) -> Optional[Dict]:
    """
    通过 qt.gtimg.cn 拿 A 股实时价 (腾讯, 沙箱通, GBK 编码)

    symbol: 'sh600703'
    Returns: dict 或 None
    """
    raw = symbol.strip().lower()
    if not raw.startswith(('sh', 'sz')):
        return None
    try:
        with urllib.request.urlopen(f'https://qt.gtimg.cn/q={raw}', timeout=5) as r:
            content = r.read().decode('gbk', errors='ignore')
        # 格式: v_sh600703="1~三安光电~600703~19.83~19.29~19.50~..."
        m = re.search(r'="([^"]+)"', content)
        if not m:
            return None
        parts = m.group(1).split('~')
        if len(parts) < 36:
            return None

        price = float(parts[3] or 0)
        prev_close = float(parts[4] or 0)
        if price <= 0 or prev_close <= 0:
            return None

        change = price - prev_close
        change_pct = (change / prev_close) * 100
        limit_up = float(parts[47] or 0)
        volume_hand = float(parts[6] or 0) / 100  # 腾讯返回手数(单位:手) → 转换为万手需要 *10000? 实际 parts[6] 是"手"
        turnover_rate = float(parts[38] or 0)
        time_str = parts[30]  # YYYYMMDDHHMMSS

        return {
            'price': price,
            'prev_close': prev_close,
            'open': float(parts[5] or 0),
            'high': float(parts[33] or 0),
            'low': float(parts[34] or 0),
            'volume_hand': volume_hand,
            'turnover_rate': turnover_rate,
            'change': round(change, 3),
            'change_pct': round(change_pct, 2),
            'limit_up': limit_up,
            'time': time_str,
            'is_limit_up': abs(price - limit_up) < 0.01 and change_pct > 9.0,
            'source': 'qt.gtimg.cn',
            # 腾讯不提供
            'total_mv': 0.0,
            'turnover_value': '',
            'avg_price': 0.0,
            'pb_ratio': 0.0,
            'volume_rate': 0.0,
            'entrust_rate': 0.0,
            'inner_disk': 0.0,
            'outer_disk': 0.0,
        }
    except Exception as e:
        print(f'[WARN] 腾讯实时价 fail: {e}', file=sys.stderr)
        return None


# ============================================================
# Lane D: 日 K (akshare 腾讯日K + 新浪日K fallback)
# ============================================================

def fetch_klines_akshare(symbol: str, days: int = 180) -> Tuple[Optional[object], str]:
    """
    从 akshare 拉日 K, 优先腾讯日K, fallback 新浪日K

    symbol: 'sh600703' 或 'sz000001'
    Returns: (DataFrame, source_label) 或 (None, 'N/A')
    """
    import akshare as ak
    import pandas as pd

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

    # L1: 腾讯日K
    try:
        df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            if 'volume' not in df.columns:
                df['volume'] = df.get('amount', 0)
            return df.tail(120).reset_index(drop=True), '腾讯日K'
    except Exception as e:
        print(f"[WARN] 腾讯日K fail: {e}", file=sys.stderr)

    # L2: 新浪日K
    try:
        df = ak.stock_zh_a_daily(symbol=symbol, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            return df.tail(120).reset_index(drop=True), '新浪日K'
    except Exception as e:
        print(f"[WARN] 新浪日K fail: {e}", file=sys.stderr)

    return None, 'N/A'


# ============================================================
# Lane B: 消息面 (tavily + 新浪 vip 双源)
# ============================================================

def fetch_news_tavily(query: str, max_results: int = 5) -> List[Dict]:
    """
    通过 tavily topic=finance 抓消息面

    query: 中文搜索词, e.g. "600703 三安光电 公告"
    Returns: list of {title, url, date, source, tier, snippet}
    """
    api_key = _load_tavily_key()
    if not api_key:
        return []

    try:
        body = {
            'query': query,
            'topic': 'finance',
            'max_results': max_results,
            'time_range': 'week',
            'search_depth': 'basic',
            'api_key': api_key,
        }
        req = urllib.request.Request(
            'https://api.tavily.com/search',
            data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read().decode())
        items = []
        for hit in result.get('results', []):
            items.append({
                'title': hit.get('title', '').strip(),
                'url': hit.get('url', ''),
                'date': hit.get('published_date', ''),
                'source': 'tavily',
                'tier': 5,  # tavily 二手
                'snippet': hit.get('content', '')[:150],
            })
        return items
    except Exception as e:
        print(f"[WARN] tavily 抓公告 fail: {e}", file=sys.stderr)
        return []


def fetch_news_sina(symbol: str) -> List[Dict]:
    """
    通过新浪 vip 抓公告时间线 (一手 tier 1)

    symbol: 'sh600703' → 自动转换 '600703'
    Returns: list of {title, date, source, tier, url}
    """
    raw = symbol.strip().lower()
    # sh600703 → 600703
    code = re.sub(r'^(sh|sz)', '', raw)
    url = f'https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/{code}.phtml'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode('gbk', errors='ignore')
        pattern = re.compile(r'(20\d{2}-\d{2}-\d{2})[^>]*>\s*([^<]{5,80})')
        items = []
        seen = set()
        for m in pattern.finditer(html):
            date, title = m.group(1), m.group(2).strip()
            if any(k in title for k in ['登录', '找回', '新浪', '会员', '快速通道']):
                continue
            key = f"{date}|{title}"
            if key in seen:
                continue
            seen.add(key)
            items.append({
                'title': title,
                'date': date,
                'source': 'sina.vip',
                'tier': 1,  # 一手
                'url': url,
            })
        return items[:10]
    except Exception as e:
        print(f"[WARN] 新浪 vip 抓公告 fail: {e}", file=sys.stderr)
        return []
