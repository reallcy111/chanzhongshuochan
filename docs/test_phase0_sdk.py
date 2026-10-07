#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 0 SDK 标准调用验证脚本

用法:
  python docs/test_phase0_sdk.py

输出:
  - 5 个 SDK 的可用性 + 标准调用结果
  - 测试报告保存到 docs/test_phase0_report.json

需要先装依赖:
  pip install akshare tavily-python mplfinance
"""

import json
import sys
import time
import os
import socket
import traceback
from datetime import datetime
from pathlib import Path

REPORT = {
    "timestamp": datetime.now().isoformat(),
    "python_version": sys.version,
    "platform": sys.platform,
    "tests": {},
    "summary": {"pass": 0, "fail": 0, "skip": 0},
}


def record(name, status, **kwargs):
    """记录测试结果"""
    REPORT["tests"][name] = {"status": status, **kwargs}
    if status == "pass":
        REPORT["summary"]["pass"] += 1
        print(f"✅ {name}: PASS — {kwargs.get('detail', '')}")
    elif status == "fail":
        REPORT["summary"]["fail"] += 1
        print(f"❌ {name}: FAIL — {kwargs.get('error', '')}")
    elif status == "skip":
        REPORT["summary"]["skip"] += 1
        print(f"⏭  {name}: SKIP — {kwargs.get('reason', '')}")


def section(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


# ============================================================
# 0. 环境检查
# ============================================================
section("0. 环境检查")

# Python 版本
py_ok = sys.version_info >= (3, 7)
record("python_version", "pass" if py_ok else "fail",
       version=sys.version, detail=f">= 3.7 required")

# 缓存目录
cache_dir = Path.home() / ".cache" / "chanzhongshuochan"
try:
    cache_dir.mkdir(parents=True, exist_ok=True)
    test_file = cache_dir / ".test_write"
    test_file.write_text("ok")
    test_file.unlink()
    record("cache_dir_writable", "pass", path=str(cache_dir))
except Exception as e:
    record("cache_dir_writable", "fail", error=str(e))


# ============================================================
# 1. akshare — A 股/港股/美股 K 线 + 实时报价
# ============================================================
section("1. akshare")

try:
    import akshare as ak
    record("akshare_import", "pass", version=getattr(ak, "__version__", "unknown"))
except ImportError as e:
    record("akshare_import", "fail", error=str(e))
    record("akshare_a_kline", "skip", reason="akshare 未安装")
    record("akshare_hk_kline", "skip", reason="akshare 未安装")
    record("akshare_us_kline", "skip", reason="akshare 未安装")
    record("akshare_a_spot", "skip", reason="akshare 未安装")
else:
    # A 股 K 线（腾讯源）
    try:
        df = ak.stock_zh_a_hist_tx(
            symbol="sh600000",
            start_date="20240101",
            end_date="20240623",
            adjust="qfq",
            timeout=10,
        )
        record("akshare_a_kline", "pass",
               detail=f"获取 {len(df)} 行 A 股 K 线",
               columns=list(df.columns))
    except Exception as e:
        record("akshare_a_kline", "fail", error=f"{type(e).__name__}: {e}")

    # 港股 K 线
    try:
        df = ak.stock_hk_hist(
            symbol="00700",
            period="daily",
            start_date="20240101",
            end_date="20240623",
            adjust="qfq",
        )
        record("akshare_hk_kline", "pass",
               detail=f"获取 {len(df)} 行港股 K 线",
               columns=list(df.columns))
    except Exception as e:
        record("akshare_hk_kline", "fail", error=f"{type(e).__name__}: {e}")

    # 美股 K 线
    try:
        df = ak.stock_us_hist(
            symbol="105.MSFT",
            period="daily",
            start_date="20240101",
            end_date="20240623",
            adjust="qfq",
        )
        record("akshare_us_kline", "pass",
               detail=f"获取 {len(df)} 行美股 K 线",
               columns=list(df.columns))
    except Exception as e:
        record("akshare_us_kline", "fail", error=f"{type(e).__name__}: {e}")

    # A 股实时报价
    try:
        df = ak.stock_zh_a_spot_em()
        record("akshare_a_spot", "pass",
               detail=f"获取 {len(df)} 行 A 股实时报价",
               columns=list(df.columns)[:5])
    except Exception as e:
        record("akshare_a_spot", "fail", error=f"{type(e).__name__}: {e}")


# ============================================================
# 2. qveris — 实时报价 + 财经新闻
# ============================================================
section("2. qveris")

# 读 OpenClaw vault（plugins.entries.qveris.config.apiKey，不是 env 字段）
def get_qveris_key():
    key = os.environ.get("QVERIS_API_KEY")
    if key:
        return key
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        return cfg.get("plugins", {}).get("entries", {}).get("qveris", {}).get("config", {}).get("apiKey")
    return None

qveris_key = get_qveris_key()
if not qveris_key:
    record("qveris_key_present", "fail",
           error="QVERIS_API_KEY 未配置（env 环境变量或 ~/.openclaw/openclaw.json env 字段）")
    record("qveris_realtime_quote", "skip", reason="API key 缺失")
    record("qveris_news", "skip", reason="API key 缺失")
else:
    record("qveris_key_present", "pass", detail=f"key 长度 {len(qveris_key)}")

    # 实时报价
    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        url = "https://qveris.ai/api/v1/tools/execute"
        payload = json.dumps({
            "tool_id": "caidazi.get_real_time_record.execute.v1.7a43f96e",
            "tool_input": {"symbol": "sh600000"},
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={
                "Authorization": f"Bearer {qveris_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        record("qveris_realtime_quote", "pass",
               detail=f"响应时间 {elapsed:.2f}s",
               sample_keys=list(result.keys())[:5] if isinstance(result, dict) else None)
    except Exception as e:
        record("qveris_realtime_quote", "fail", error=f"{type(e).__name__}: {e}")

    # 财经新闻
    try:
        payload = json.dumps({
            "tool_id": "qveris_finance.finance_news_aggregation_v1",
            "tool_input": {"query": "浦发银行", "limit": 5},
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={
                "Authorization": f"Bearer {qveris_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        n_results = len(result.get("results", []))
        record("qveris_news", "pass",
               detail=f"返回 {n_results} 条新闻",
               sample_keys=list(result.keys())[:5] if isinstance(result, dict) else None)
    except Exception as e:
        record("qveris_news", "fail", error=f"{type(e).__name__}: {e}")


# ============================================================
# 3. tavily — 消息面兜底
# ============================================================
section("3. tavily")

def get_tavily_key():
    key = os.environ.get("TAVILY_API_KEY")
    if key:
        return key
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        return cfg.get("plugins", {}).get("entries", {}).get("tavily", {}).get("config", {}).get("webSearch", {}).get("apiKey")
    return None

tavily_key = get_tavily_key()
if not tavily_key:
    record("tavily_key_present", "fail",
           error="TAVILY_API_KEY 未配置")
    record("tavily_search_finance", "skip", reason="API key 缺失")
else:
    record("tavily_key_present", "pass", detail=f"key 长度 {len(tavily_key)}")
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        t0 = time.time()
        result = client.search(
            query="浦发银行 600000 公告",
            topic="finance",
            max_results=3,
            timeout=30,
        )
        elapsed = time.time() - t0
        n_results = len(result.get("results", []))
        record("tavily_search_finance", "pass",
               detail=f"topic=finance, 返回 {n_results} 条, 响应 {elapsed:.2f}s")
    except ImportError as e:
        record("tavily_search_finance", "fail", error=f"tavily-python 未安装: {e}")
    except Exception as e:
        record("tavily_search_finance", "fail", error=f"{type(e).__name__}: {e}")


# ============================================================
# 4. mplfinance — 走势图
# ============================================================
section("4. mplfinance")

try:
    import mplfinance as mpf
    import pandas as pd
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")  # 无 GUI 后端

    # 构造示例数据
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(30))
    df = pd.DataFrame({
        "open": close + np.random.randn(30) * 0.5,
        "high": close + abs(np.random.randn(30)) * 0.5,
        "low":  close - abs(np.random.randn(30)) * 0.5,
        "close": close,
        "volume": np.random.randint(1000000, 5000000, 30),
    }, index=dates)

    # 测试 addplot + scatter
    ap = mpf.make_addplot(
        [df["high"].iloc[5]] * len(df),
        type="scatter", marker="$T$", markersize=100, color="red",
    )
    test_chart = cache_dir / "test_chart.png"
    mpf.plot(df, type="candle", addplot=ap, savefig=str(test_chart))

    if test_chart.exists():
        size_kb = test_chart.stat().st_size / 1024
        record("mplfinance_plot", "pass",
               detail=f"保存 {test_chart.name} ({size_kb:.1f} KB)")
    else:
        record("mplfinance_plot", "fail", error="savefig 后文件未生成")
except ImportError as e:
    record("mplfinance_plot", "fail", error=f"依赖未安装: {e}")
except Exception as e:
    record("mplfinance_plot", "fail", error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[:500]}")


# ============================================================
# 5. agent-browser — 公开页面爬取
# ============================================================
section("5. agent-browser")

try:
    import subprocess
    result = subprocess.run(
        ["agent-browser", "--version"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        version = result.stdout.strip() or result.stderr.strip()
        record("agent_browser_version", "pass", detail=f"版本: {version[:100]}")
    else:
        record("agent_browser_version", "fail",
               error=f"returncode={result.returncode}, stderr={result.stderr[:200]}")
except FileNotFoundError:
    record("agent_browser_version", "fail",
           error="agent-browser 未安装（npm i -g @vercel-labs/agent-browser）")
except Exception as e:
    record("agent_browser_version", "fail", error=f"{type(e).__name__}: {e}")


# ============================================================
# 6. 网络测试 — qveris.ai 可达性
# ============================================================
section("6. 网络测试（关键域名）")

def check_domain(host, port=443, timeout=5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except Exception as e:
        return False, str(e)

for host in ["qveris.ai", "api.tavily.com", "qt.gtimg.cn"]:
    ok, err = check_domain(host)
    record(f"network_{host}", "pass" if ok else "fail",
           error=err if not ok else None)


# ============================================================
# 输出报告
# ============================================================
section("测试报告汇总")

print(f"\n✅ PASS: {REPORT['summary']['pass']}")
print(f"❌ FAIL: {REPORT['summary']['fail']}")
print(f"⏭  SKIP: {REPORT['summary']['skip']}")

# 写报告
report_path = Path("docs/test_phase0_report.json")
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2))
print(f"\n📄 报告已保存: {report_path}")

# 退出码
sys.exit(0 if REPORT["summary"]["fail"] == 0 else 1)
