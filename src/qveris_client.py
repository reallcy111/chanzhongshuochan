'''qveris API client v1.7'''
import json, logging, os
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)
QVERIS_BASE = "https://qveris.ai/api/v1"
TOOL_REALTIME = "caidazi.get_real_time_record.execute.v1.7a43f96e"
TOOL_NEWS = "caidazi.news.query.v1.e76b9116"
TOOL_FINNEWS = "qveris_finance.finance_news_aggregation_v1"

def _load_key() -> str:
    with open(os.path.expanduser("~/.openclaw/openclaw.json")) as f:
        cfg = json.load(f)
    return cfg["plugins"]["entries"]["qveris"]["config"]["apiKey"]

def _post(tool_id: str, parameters: dict, search_id: str = "chanlun"):
    key = _load_key()
    if not key:
        return None
    try:
        import requests
        resp = requests.post(
            QVERIS_BASE + "/tools/execute",
            headers={"Authorization": "Bearer " + key},
            json={"tool_id": tool_id, "parameters": parameters, "search_id": search_id},
            timeout=20,
        )
        return resp.json().get("result", {}).get("data", {})
    except Exception as e:
        logger.warning("qveris execute failed: %s", e)
        return None

def _try_float(val: str) -> Optional[float]:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def _parse_quote_table(raw: str) -> Dict[str, str]:
    rows = [ln for ln in raw.split("\n") if ln.strip().startswith("|") and "---" not in ln]
    if len(rows) < 2:
        return {}
    hdr = [p.strip() for p in rows[0].split("|")[1:]]
    dat = [p.strip() for p in rows[-1].split("|")[1:]]
    result = {}
    for i in range(min(len(hdr), len(dat))):
        k, v = hdr[i], dat[i]
        if k and v and v != "---":
            result[k] = v
    return result

def get_realtime_quote(symbol: str) -> Optional[dict]:
    data = _post(TOOL_REALTIME, {"symbol": symbol})
    if not data:
        return None
    raw = data.get("result", "") or ""
    if not raw:
        return None
    t = _parse_quote_table(raw)
    if not t:
        return None
    def num(key):
        return _try_float(t.get(key, ""))
    def int_zero(key):
        v = t.get(key, "0") or "0"
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0
    return {
        "stock_code": t.get("股票代码", symbol),
        "stock_name": t.get("股票名称", ""),
        "trade_time": t.get("交易时间", ""),
        "latest_price": num("最新价（元）"),
        "price_change": num("涨跌额"),
        "pct_change": num("涨跌幅(%)"),
        "volume": int_zero("成交量(股）"),
        "amount": num("成交额（元）"),
        "open": num("开盘价（元）"),
        "high": num("最高价（元）"),
        "low": num("最低价（元）"),
        "total_market_cap": num("总市值（万元）"),
        "turnover_rate": num("换手率（%）"),
        "pe": num("市盈率(TTM)"),
        "pb": num("市净率"),
        "up_limit": num("涨停价"),
        "down_limit": num("跌停价"),
        "status": t.get("是否停牌（0：否，1：是）", "0"),
    }

def search_news(query: str, count: int = 5) -> List[dict]:
    results = []
    # finnews: _post 返回 data.result.data = {results: [...], total: N}
    data = _post(TOOL_FINNEWS, {"query": query, "limit": count})
    if data and isinstance(data, dict):
        items = data.get("results", []) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("title"):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "body": (item.get("body") or "")[:100],
                })
        if results:
            return results[:count]
    # caidazi.news: 返回 Markdown 表格
    data2 = _post(TOOL_NEWS, {"input": query, "size": count})
    if data2:
        raw2 = data2.get("result", "") or ""
        for line in raw2.split("\n"):
            line = line.strip()
            if line.startswith("|") and "---" not in line:
                parts = [p.strip() for p in line.split("|")[1:]]
                if len(parts) >= 2 and parts[1]:
                    results.append({
                        "title": parts[1],
                        "url": parts[2] if len(parts) > 2 else "",
                        "body": "",
                    })
    return results[:count]
