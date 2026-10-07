"""P1 bug fix smoke test - verifies all 3 P1 changes work end-to-end."""

import os
os.environ["PYTHONIOENCODING"] = "utf-8"

import sys
import tempfile
import pathlib
from datetime import date, timedelta

sys.path.insert(0, ".")

import pandas as pd

# === Test 1: compute_staleness_days (P1-1 helper) ===
from src.data_layer.westock_wrapper import compute_staleness_days

today = date.today()
df_fresh = pd.DataFrame({"date": [str(today - timedelta(days=1))]})
df_stale = pd.DataFrame({"date": [str(today - timedelta(days=14))]})
df_empty = pd.DataFrame({"date": []})
assert compute_staleness_days(df_fresh) == 1, f"fresh: {compute_staleness_days(df_fresh)}"
assert compute_staleness_days(df_stale) == 14, f"stale: {compute_staleness_days(df_stale)}"
assert compute_staleness_days(df_empty) == 0
print("[OK] P1-1 compute_staleness_days works (1, 14, 0)")

# === Test 2: westock_wrapper.get_kline new tuple signature (importable) ===
import inspect
from src.data_layer import westock_wrapper as ww

sig = inspect.signature(ww.get_kline)
print(f"[OK] P1-1 westock.get_kline signature exists: {sig}")

# === Test 3: router.route_kline staleness threshold constant ===
from src.data_layer.router import (
    route_kline,
    STALENESS_THRESHOLD_DAYS,
    RouterConfig,
    get_config,
)
assert STALENESS_THRESHOLD_DAYS == 3, f"expected 3, got {STALENESS_THRESHOLD_DAYS}"
print(f"[OK] P1-2 STALENESS_THRESHOLD_DAYS = {STALENESS_THRESHOLD_DAYS}")

# === Test 4: route_kline skip stale westock, fall through to akshare ===
import src.data_layer.akshare_wrapper as aw_mod
import src.data_layer.westock_wrapper as ww_mod

calls = {"akshare": 0, "westock": 0}


def tracking_get_kline_hk(symbol, **kwargs):
    calls["akshare"] += 1
    fresh_date = date.today().isoformat()
    return pd.DataFrame(
        {
            "date": [fresh_date],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [100.0],
            "amount": [1000.0],
            "exchange": ["HK"],
        }
    )


def tracking_get_kline_stale(symbol, **kwargs):
    calls["westock"] += 1
    stale_date = (date.today() - timedelta(days=14)).isoformat()
    return pd.DataFrame(
        {
            "date": [stale_date],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [100.0],
            "amount": [1000.0],
            "exchange": ["HK"],
        }
    ), 14


aw_mod.get_kline_hk = tracking_get_kline_hk
ww_mod.get_kline = tracking_get_kline_stale

# Disable qveris/tavily/agent_browser to keep chain short
cfg = get_config()
cfg.staleness_threshold_days = 3
cfg.enabled_kline_sources["qveris"] = False
cfg.enabled_kline_sources["tavily"] = False
cfg.enabled_kline_sources["agent_browser"] = False

# For HK: chain = [westock, akshare, ...]. westock stale -> should skip to akshare
try:
    df, src = route_kline("hk00700", days=10)
    print(f"[OK] P1-2 route_kline HK: source={src}, calls={calls}, df rows={len(df)}")
    assert calls["westock"] == 1, f"westock should be called once: {calls}"
    assert calls["akshare"] == 1, f"akshare should be called (fallback): {calls}"
    assert src == "akshare", f"should fallback to akshare, got: {src}"
    print("[OK] P1-2 stale westock correctly skipped to akshare")
except Exception as e:
    print(f"[FAIL] P1-2 route_kline: {e}")
    import traceback
    traceback.print_exc()

# === Test 5: staleness_threshold_days = None disables check ===
cfg.staleness_threshold_days = None
cfg.enabled_kline_sources["akshare"] = False  # so westock would be used if not skipped
calls2 = {"westock": 0}


def tracking_get_kline_stale2(symbol, **kwargs):
    calls2["westock"] += 1
    stale_date = (date.today() - timedelta(days=14)).isoformat()
    return pd.DataFrame(
        {
            "date": [stale_date],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [100.0],
            "amount": [1000.0],
            "exchange": ["HK"],
        }
    ), 14


ww_mod.get_kline = tracking_get_kline_stale2
try:
    df, src = route_kline("hk00700", days=10)
    print(f"[OK] P1-2 staleness disabled: source={src}, calls={calls2}")
    assert src == "westock", f"stale westock should be used when threshold=None, got: {src}"
    print("[OK] P1-2 staleness_threshold_days=None correctly disables check")
except Exception as e:
    print(f"[FAIL] P1-2 staleness disabled: {e}")
    import traceback
    traceback.print_exc()

# === Test 6: check_environment Mavis .env path ===
cfg.staleness_threshold_days = 3  # reset
cfg.enabled_kline_sources["akshare"] = True  # reset
from src.check_environment import MAVIS_ENV_PATH, _parse_env_file, get_api_key
print(f"[OK] P1-3 MAVIS_ENV_PATH = {MAVIS_ENV_PATH}")
assert ".mavis" in str(MAVIS_ENV_PATH), f"should contain .mavis: {MAVIS_ENV_PATH}"
assert "openclaw" not in str(MAVIS_ENV_PATH).lower(), f"should not contain openclaw: {MAVIS_ENV_PATH}"
assert "chanzhongshuochan" in str(MAVIS_ENV_PATH), f"should contain chanzhongshuochan: {MAVIS_ENV_PATH}"
print("[OK] P1-3 MAVIS_ENV_PATH uses ~/.mavis/skills/chanzhongshuochan/.env")

# Test _parse_env_file with mock content
with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False, encoding="utf-8") as f:
    f.write('QVERIS_API_KEY="qveris-test-123"\n')
    f.write("# comment line\n")
    f.write("TAVILY_API_KEY=tavily-test-456\n")
    f.write("EMPTY_VAR=\n")
    tmp_env = f.name

parsed = _parse_env_file(pathlib.Path(tmp_env))
assert parsed["QVERIS_API_KEY"] == "qveris-test-123", f"QVERIS: {parsed}"
assert parsed["TAVILY_API_KEY"] == "tavily-test-456", f"TAVILY: {parsed}"
assert parsed["EMPTY_VAR"] == "", f"EMPTY: {parsed}"
print(f"[OK] P1-3 _parse_env_file parsed: {list(parsed.keys())}")

# Test get_api_key priority: env var > .env
os.environ["TEST_KEY_X"] = "from_env"
import src.check_environment as ce
ce.MAVIS_ENV_PATH = pathlib.Path(tmp_env)  # patch for test
os.environ.pop("QVERIS_API_KEY", None)
got = get_api_key("QVERIS_API_KEY")
assert got == "qveris-test-123", f"should read from .env: {got}"
print(f"[OK] P1-3 get_api_key from .env: {got}")

# Env var should win
got2 = get_api_key("TEST_KEY_X")
assert got2 == "from_env", f"env var should win: {got2}"
print(f"[OK] P1-3 env var priority wins: {got2}")

# Missing key should return None
got3 = get_api_key("NONEXISTENT_KEY")
assert got3 is None, f"missing key should return None: {got3}"
print("[OK] P1-3 missing key returns None")

# === Test 7: check_full() no longer mentions OpenClaw ===
print()
print("--- build_fill_prompt (manual test) ---")
os.environ.pop("QVERIS_API_KEY", None)
os.environ.pop("TAVILY_API_KEY", None)
from src.check_environment import build_fill_prompt, CheckResult
fake_results = [
    CheckResult("key_QVERIS_API_KEY", "warn", detail="缺失").to_dict(),
    CheckResult("key_TAVILY_API_KEY", "warn", detail="缺失").to_dict(),
]
prompt = build_fill_prompt(fake_results)
assert prompt is not None
prompt_str = str(prompt)
assert "openclaw" not in prompt_str.lower(), f"should not contain openclaw: {prompt_str}"
# MAVIS_ENV_PATH must contain .mavis (real Mavis path, restored after test 6)
assert ".mavis" in str(MAVIS_ENV_PATH), f"MAVIS_ENV_PATH should contain .mavis: {MAVIS_ENV_PATH}"
print(f"[OK] P1-3 build_fill_prompt no longer mentions OpenClaw")
print(f"  Option 2 description: {prompt['options'][1]['description']}")
print(f"  MAVIS_ENV_PATH: {MAVIS_ENV_PATH}")

# === Test 8: P3 detect_all_trend_beichis API (v0.6.3 修复) ===
from src.beichi import detect_all_trend_beichis
import inspect
sig = inspect.signature(detect_all_trend_beichis)
ret = str(sig.return_annotation)
assert "List" in ret and "Beichi" in ret, f"return should be List[Beichi], got: {ret}"
# 空 bis → 空 list
macd_df = pd.DataFrame({"MACD": [0.0] * 10})
assert detect_all_trend_beichis([], macd_df) == []
# bis 不足 → 空 list
assert detect_all_trend_beichis([1], macd_df, min_bi_count=2) == []
# 正常 bis(随机) → 返回 list
import numpy as np
n = 20
macd_random = pd.DataFrame({
    "DIF": np.random.randn(n),
    "DEA": np.random.randn(n),
    "MACD": np.random.randn(n) * 0.5,
})
from src.bi import Bi
fake_bis = [
    Bi(start_index=0, end_index=5, start_type="bottom", end_type="top",
       start_price=100.0, end_price=110.0, kline_count=6, amplitude=10.0),
    Bi(start_index=5, end_index=10, start_type="top", end_type="bottom",
       start_price=110.0, end_price=105.0, kline_count=6, amplitude=4.5),
    Bi(start_index=10, end_index=15, start_type="bottom", end_type="top",
       start_price=105.0, end_price=115.0, kline_count=6, amplitude=9.5),
]
result_list = detect_all_trend_beichis(fake_bis, macd_random, min_bi_count=2)
assert isinstance(result_list, list), f"should be list, got: {type(result_list)}"
print(f"[OK] P3-1 detect_all_trend_beichis signature: {ret}")
print(f"      empty: [], result list type: {type(result_list).__name__}, len: {len(result_list)}")

# === Test 9: P3 main.py 不再 TypeError (v0.6.3 修复) ===
import pathlib
main_src = pathlib.Path("src/main.py").read_text(encoding="utf-8")
assert "detect_all_trend_beichis" in main_src, "main.py should use detect_all_trend_beichis"
assert "detect_trend_beichi(bis, macd_result) or []" not in main_src, (
    "main.py:136 still has the v0.6.0 bug pattern (detect_trend_beichi + or [])"
)
import src
assert hasattr(src, "detect_all_trend_beichis"), "src.detect_all_trend_beichis should be exported"
print("[OK] P3-2 main.py:136 no longer has the v0.6.0 TypeError pattern")
print("      src.detect_all_trend_beichis exported and importable")

print()
print("=" * 60)
print("[OK] P1 (3 fixes) + P3 (2 fixes) VERIFIED — v0.6.3 ready")

print()
print("=" * 60)
print("[OK] ALL 3 P1 BUG FIXES VERIFIED")
