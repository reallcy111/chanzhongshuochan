"""
src/data_layer/westock_wrapper.py — 腾讯 westock-data skill 封装

按 plan 决策 (skills-fluttering-hinton.md):
- 免 Token，subprocess 调 npx westock-data-skillhub@1.0.3
- Markdown 表格解析（自写，无依赖）
- 数据契约转换:
  - last → close
  - volume 手 → 股（×100）
  - exchange 字段在 westock kline 中实际是换手率，重命名后丢弃
- currency 按 market 自动推断
- 报价从 minute 末行 + kline 末行获取（westock 没有 quote 命令）
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .contracts import (
    KlineRow,
    QuoteResult,
    FinanceRow,
    NewsItem,
    Market,
    Currency,
    detect_market,
    detect_currency,
)

logger = logging.getLogger(__name__)


# ============================================================
# 异常类（与 reliability.classify_westock_error 映射）
# ============================================================
class WestockError(Exception):
    """westock-data 所有异常的基类"""


class WestockEnvError(WestockError):
    """环境错误（Node 未装、npx 不可用）"""


class WestockTransientError(WestockError):
    """可重试的瞬时错误（subprocess 退出码非 0、超时）"""


class WestockPermanentError(WestockError):
    """永久错误（股票代码不存在、westock 不支持该市场）"""


class WestockParseError(WestockError):
    """Markdown 解析失败（westock 输出格式变更）"""


# ============================================================
# 常量
# ============================================================
NPX_CMD = "npx"
WESTOCK_PKG = "westock-data-skillhub@1.0.3"
NODE_MIN_VERSION = (18, 0, 0)
MAX_LIMIT = 2000
DEFAULT_TIMEOUT = 30  # 秒
SOURCE_NAME = "westock"


# ============================================================
# 配置
# ============================================================
@dataclass
class WestockConfig:
    """westock wrapper 运行配置"""
    npx_cmd: str = NPX_CMD
    package: str = WESTOCK_PKG
    timeout: int = DEFAULT_TIMEOUT
    npm_cache: Optional[Path] = None


_default_config: Optional[WestockConfig] = None


def get_config() -> WestockConfig:
    """获取默认配置（单例）"""
    global _default_config
    if _default_config is None:
        _default_config = WestockConfig()
    return _default_config


def set_config(config: WestockConfig) -> None:
    """设置默认配置（测试用）"""
    global _default_config
    _default_config = config


# ============================================================
# subprocess 封装（统一入口）
# ============================================================
def _run_westock(
    args: list[str], config: Optional[WestockConfig] = None
) -> str:
    """调 npx westock-data-skillhub <args>，返回 stdout 字符串。

    Raises:
        WestockEnvError: Node/npx 不可用、包未找到
        WestockTransientError: subprocess 失败（非 0 退出码、超时）
        WestockPermanentError: 命令错误（如未知命令）
    """
    cfg = config or get_config()
    # Windows 兼容: 解析 npx 绝对路径（PATHEXT .cmd/.bat）
    npx_path = cfg.npx_cmd
    if npx_path == "npx":
        resolved = shutil.which("npx")
        if resolved:
            npx_path = resolved
    cmd = [npx_path, "-y", cfg.package] + list(args)

    # Windows 兼容: 设置 UTF-8 编码避免 GBK 解码错误
    env = None
    if os.name == "nt":
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except FileNotFoundError as e:
        raise WestockEnvError(f"npx 不可用: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise WestockTransientError(f"westock 超时 ({cfg.timeout}s)") from e

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:300]
        if "not found" in stderr.lower() or "command not found" in stderr.lower():
            raise WestockEnvError(f"westock 包未找到: {stderr}")
        if "未知命令" in stderr or "unknown command" in stderr.lower():
            raise WestockPermanentError(f"westock 命令错误: {stderr}")
        raise WestockTransientError(
            f"westock 退出码 {proc.returncode}: {stderr}"
        )

    return proc.stdout


# ============================================================
# Markdown 表格解析
# ============================================================
_NON_NUMERIC_COLS = frozenset({
    "date", "time", "code", "name", "exchange", "type",
    "industry", "website", "business", "chairman",
    "regAddress", "officeAddress", "tel", "email",
    "EndDate", "InfoPublDate", "EnterpriseType", "SecuCode",
    "EstablishDate", "listedDate", "IssuePrice", "regCapital",
})


def _parse_markdown_table(md: str) -> pd.DataFrame:
    """把 Markdown 表格解析成 DataFrame。

    支持空表（仅表头无数据行），返回空 DataFrame（列存在但无行）。

    Raises:
        WestockParseError: 无法识别 Markdown 格式
    """
    if not md or not md.strip():
        raise WestockParseError("输出为空")

    lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        raise WestockParseError(f"未找到 Markdown 表格: {md[:200]}")

    header = [c.strip() for c in lines[0].strip("|").split("|")]
    rows: list[list[str]] = []
    for ln in lines[1:]:
        if re.match(r"^\|\s*[-:]+\s*\|", ln):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) != len(header):
            logger.warning(
                "列数不匹配: expected %d, got %d (行: %s)",
                len(header), len(cells), ln[:100],
            )
            continue
        rows.append(cells)

    if not rows:
        return pd.DataFrame(columns=header)

    df = pd.DataFrame(rows, columns=header)

    for col in df.columns:
        if col in _NON_NUMERIC_COLS:
            continue
        try:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", ""), errors="coerce"
            )
        except Exception:  # pylint: disable=broad-except
            pass

    return df


# ============================================================
# 数据契约转换
# ============================================================
def _normalize_symbol(symbol: str) -> str:
    """归一化 symbol（小写）"""
    return symbol.lower().strip()


def _westock_kline_to_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """把 westock kline 输出转换为标准 DataFrame。

    westock kline 字段: date | open | last | high | low | volume | amount | exchange
    - last → close
    - volume: 手 → 股（×100）
    - exchange 字段在 westock 中实际是换手率，记录到 attrs 后丢弃
    - 新增 exchange 列 = 交易所代码（"SH"/"SZ"/"HK"/"US"）
    """
    df = df.copy()

    if "last" in df.columns:
        df = df.rename(columns={"last": "close"})

    # volume 单位转换:
    # - A 股 westock 返回"手" → ×100 转"股"
    # - 港/美股 westock 已是"股"，无需转换
    market = detect_market(symbol)
    if "volume" in df.columns and market in (Market.A_SH, Market.A_SZ, Market.A_BJ):
        df["volume"] = df["volume"] * 100

    if "exchange" in df.columns:
        df.attrs["turnover_rate_raw"] = df["exchange"].tolist()
        df = df.drop(columns=["exchange"])

    df["exchange"] = market.value.upper()

    desired = ["date", "open", "high", "low", "close", "volume", "amount", "exchange"]
    df = df[[c for c in desired if c in df.columns]]
    return df


def compute_staleness_days(df: pd.DataFrame) -> int:
    """根据 DataFrame 末行 date 计算 staleness_days（距今天数）。

    用途：westock-data 后端腾讯自选股 API 数据可能滞后 1-2 周，
    router 在 staleness > 3 时自动跳下一源。

    Args:
        df: 标准 K 线 DataFrame（含 date 列）

    Returns:
        staleness_days（int）。df 为空时返回 0；date 解析失败时返回极大值（999）
    """
    if df.empty or "date" not in df.columns:
        return 0
    try:
        last_date = pd.to_datetime(df.iloc[-1]["date"]).date()
    except (ValueError, TypeError):
        return 999  # 解析失败 → 视为极旧
    return (date.today() - last_date).days


def compute_staleness_minutes(df_minute: pd.DataFrame, now: Optional[datetime] = None) -> int:
    """根据分钟行情 DataFrame 末行 time 计算 staleness_minutes。

    westock minute 命令的 time 列是 HHMM 格式（如 "0930", "1459"）。
    A 股交易时段: 09:30-11:30 + 13:00-15:00；港股 09:30-16:00；美股 21:30-04:00。
    本函数做简化处理：直接计算 (now - last_minute_time) 的分钟差，跨午夜/跨日返回负数时取绝对值。

    Args:
        df_minute: 含 'time' 列的分钟行情 DataFrame
        now: 当前时间（默认 datetime.now()，测试用可注入）

    Returns:
        staleness_minutes（int）。df 为空 / time 缺失 / 解析失败时返回 0
    """
    from datetime import datetime  # 局部导入避免顶层依赖扩大

    if df_minute.empty or "time" not in df_minute.columns:
        return 0
    try:
        time_str = str(df_minute.iloc[-1]["time"]).strip()
        if len(time_str) != 4 or not time_str.isdigit():
            return 0
        hh, mm = int(time_str[:2]), int(time_str[2:])
        now = now or datetime.now()
        last_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        delta = (now - last_dt).total_seconds() / 60
        # 跨日（昨夜的分钟行）时 delta 为负，取绝对值
        return abs(int(delta))
    except (ValueError, TypeError, AttributeError):
        return 0


# ============================================================
# 公开 API
# ============================================================
def get_kline(
    symbol: str,
    period: str = "day",
    limit: int = 120,
    fq: str = "qfq",
    start: Optional[str] = None,
    end: Optional[str] = None,
    config: Optional[WestockConfig] = None,
) -> tuple[pd.DataFrame, int]:
    """获取 K 线（westock kline 命令）。

    Args:
        symbol: westock 格式代码 (sh600519 / hk00700 / usAAPL / sh510300)
        period: day / week / month / season / year
        limit: 返回条数（最大 2000）
        fq: qfq / hfq / bfq（前复权/后复权/不复权）
        start: YYYY-MM-DD（可选）
        end: YYYY-MM-DD（可选）

    Returns:
        (DataFrame, staleness_days):
        - DataFrame 列: date / open / high / low / close / volume / amount / exchange
        - staleness_days: 末行日期距今天数（> 3 时建议走其他源）

    Raises:
        WestockEnvError / WestockTransientError / WestockPermanentError / WestockParseError
    """
    cfg = config or get_config()
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT
    symbol = _normalize_symbol(symbol)

    args = ["kline", symbol, "--period", period, "--limit", str(limit), "--fq", fq]
    if start:
        args += ["--start", start]
    if end:
        args += ["--end", end]

    md = _run_westock(args, cfg)
    df = _parse_markdown_table(md)
    if df.empty:
        raise WestockPermanentError(f"{symbol} K 线为空")

    df = _westock_kline_to_df(df, symbol)
    staleness_days = compute_staleness_days(df)
    return df, staleness_days


def get_quote(
    symbol: str,
    config: Optional[WestockConfig] = None,
) -> QuoteResult:
    """获取实时报价（从 minute 末行 + kline 末行组装）。

    westock 没有 quote 命令。降级策略:
    1. minute --days 1 末行 → 最新价 + 成交量 + 成交额
    2. kline 末行 close → 昨收

    Args:
        symbol: westock 格式代码

    Returns:
        QuoteResult（currency 必填: CNY/HKD/USD）
    """
    cfg = config or get_config()
    symbol = _normalize_symbol(symbol)

    md_minute = _run_westock(["minute", symbol, "--days", "1"], cfg)
    df_minute = _parse_markdown_table(md_minute)
    if df_minute.empty:
        raise WestockPermanentError(f"{symbol} 分时数据为空")
    last_minute = df_minute.iloc[-1]
    latest_price = float(last_minute["price"])
    # volume/amount 在不同市场/时间可能缺失，缺失则填 0
    latest_volume_hand = float(last_minute.get("volume", 0) or 0)
    latest_amount = float(last_minute.get("amount", 0) or 0)
    # v0.6.2: 计算 staleness_minutes（从末行 HHMM time 算）
    staleness_minutes = compute_staleness_minutes(df_minute)

    md_kline = _run_westock(
        ["kline", symbol, "--period", "day", "--limit", "2"], cfg
    )
    df_kline = _parse_markdown_table(md_kline)
    if len(df_kline) < 2:
        prev_close = latest_price
    else:
        prev_close = float(df_kline.iloc[-2]["last"])

    market = detect_market(symbol)
    currency = Currency.for_market(market)
    change = latest_price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    return QuoteResult(
        symbol=symbol,
        name="",
        price=latest_price,
        prev_close=prev_close,
        open=latest_price,
        high=latest_price,
        low=latest_price,
        change=change,
        change_pct=change_pct,
        volume=latest_volume_hand * 100,
        turnover_value=latest_amount,
        currency=currency,
        staleness_minutes=staleness_minutes,
    )


def get_minute(
    symbol: str,
    days: int = 1,
    config: Optional[WestockConfig] = None,
) -> pd.DataFrame:
    """分时数据（westock minute 命令）。"""
    cfg = config or get_config()
    symbol = _normalize_symbol(symbol)
    md = _run_westock(["minute", symbol, "--days", str(days)], cfg)
    return _parse_markdown_table(md)


def get_finance(
    symbol: str,
    num: int = 1,
    type_: Optional[str] = None,
    config: Optional[WestockConfig] = None,
) -> dict[str, pd.DataFrame]:
    """财务报表（westock finance 命令，返回多子表）。

    westock finance 输出按 **lrb** / **zcfz** / **xjll** 分段。

    Args:
        symbol: westock 格式代码
        num: 最近期数
        type_: A 股 lrb/zcfz/xjll；港股 zhsy/zcfz/xjll；美股 income/balance/cashflow
              （None = 默认全部）

    Returns:
        dict[报表名 → DataFrame]，例如 {"lrb": df, "zcfz": df, "xjll": df}
    """
    cfg = config or get_config()
    symbol = _normalize_symbol(symbol)
    args = ["finance", symbol, "--num", str(num)]
    if type_:
        args += ["--type", type_]
    md = _run_westock(args, cfg)

    sections: dict[str, pd.DataFrame] = {}
    current_name = "default"
    current_lines: list[str] = []
    for line in md.splitlines():
        m = re.match(r"\*\*(\w+)\*\*", line.strip())
        if m:
            if current_lines:
                df = _parse_markdown_table("\n".join(current_lines))
                if not df.empty:
                    sections[current_name] = df
            current_name = m.group(1)
            current_lines = []
        elif line.strip().startswith("|"):
            current_lines.append(line)
    if current_lines:
        df = _parse_markdown_table("\n".join(current_lines))
        if not df.empty:
            sections[current_name] = df

    if not sections:
        raise WestockPermanentError(f"{symbol} 财务数据为空")
    return sections


def get_chip(
    symbol: str,
    config: Optional[WestockConfig] = None,
) -> dict:
    """筹码成本（仅沪深京 A 股）。

    Returns:
        dict 含 code/name/date/close_price/profit_rate/avg_cost/
        concentration_90/concentration_70
    """
    cfg = config or get_config()
    symbol = _normalize_symbol(symbol)
    md = _run_westock(["chip", symbol], cfg)
    df = _parse_markdown_table(md)
    if df.empty:
        raise WestockPermanentError(f"{symbol} 筹码数据为空")
    row = df.iloc[0]
    return {
        "code": str(row.get("code", symbol)),
        "name": str(row.get("name", "")),
        "date": str(row.get("date", "")),
        "close_price": float(row.get("closePrice", 0)),
        "profit_rate": float(row.get("chipProfitRate", 0)),
        "avg_cost": float(row.get("chipAvgCost", 0)),
        "concentration_90": float(row.get("chipConcentration90", 0)),
        "concentration_70": float(row.get("chipConcentration70", 0)),
    }


def get_fund_flow(
    symbol: str,
    date: Optional[str] = None,
    config: Optional[WestockConfig] = None,
) -> pd.DataFrame:
    """资金流向（按 market 自动选 asfund/hkfund/usfund）。"""
    cfg = config or get_config()
    symbol = _normalize_symbol(symbol)
    market = detect_market(symbol)
    cmd_map = {
        Market.A_SH: "asfund",
        Market.A_SZ: "asfund",
        Market.A_BJ: "asfund",
        Market.HK: "hkfund",
        Market.US: "usfund",
    }
    cmd = cmd_map.get(market, "asfund")
    args = [cmd, symbol]
    if date:
        args += ["--date", date]
    md = _run_westock(args, cfg)
    df = _parse_markdown_table(md)
    df.attrs["currency"] = Currency.for_market(market).value
    return df


def search(
    query: str,
    sector: bool = False,
    config: Optional[WestockConfig] = None,
) -> pd.DataFrame:
    """搜索股票/板块。"""
    cfg = config or get_config()
    args = ["search", query]
    if sector:
        args.append("--sector")
    md = _run_westock(args, cfg)
    return _parse_markdown_table(md)


def get_technical(
    symbol: str,
    group: str = "all",
    config: Optional[WestockConfig] = None,
) -> pd.DataFrame:
    """技术指标（westock technical 命令，仅作对账/参考，缠论自算）。"""
    cfg = config or get_config()
    symbol = _normalize_symbol(symbol)
    md = _run_westock(["technical", symbol, "--group", group], cfg)
    return _parse_markdown_table(md)


def get_profile(
    symbol: str,
    config: Optional[WestockConfig] = None,
) -> dict:
    """公司简况（westock profile 命令）。"""
    cfg = config or get_config()
    symbol = _normalize_symbol(symbol)
    md = _run_westock(["profile", symbol], cfg)
    df = _parse_markdown_table(md)
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


# ============================================================
# 环境检查
# ============================================================
def check_environment() -> dict:
    """检查 westock 运行环境（被 check_environment.py 调用）。

    Returns:
        dict:
            - node_available: bool
            - node_version: tuple | None
            - npx_available: bool
            - westock_package_available: bool
    """
    result: dict = {
        "node_available": False,
        "node_version": None,
        "npx_available": False,
        "westock_package_available": False,
    }

    if shutil.which("node"):
        result["node_available"] = True
        try:
            proc = subprocess.run(
                ["node", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            ver_str = proc.stdout.strip().lstrip("v").split(".")
            if len(ver_str) >= 2:
                result["node_version"] = (
                    int(ver_str[0]),
                    int(ver_str[1]),
                    int(ver_str[2]) if len(ver_str) > 2 else 0,
                )
        except Exception:  # pylint: disable=broad-except
            pass

    if shutil.which("npx"):
        result["npx_available"] = True

    if result["npx_available"]:
        # Windows 兼容: 用绝对路径（subprocess 不会自动解析 PATHEXT .cmd/.bat）
        npx_path = shutil.which("npx") or "npx"
        try:
            subprocess.run(
                [npx_path, "-y", WESTOCK_PKG, "--help"],
                capture_output=True, text=True, timeout=60,
            )
            result["westock_package_available"] = True
        except Exception:  # pylint: disable=broad-except
            result["westock_package_available"] = False

    return result


# ============================================================
# 自检
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    print("=== westock 环境检查 ===")
    env = check_environment()
    print(f"node: {env['node_available']} (版本 {env['node_version']})")
    print(f"npx: {env['npx_available']}")
    print(f"westock 包: {env['westock_package_available']}")

    if env["westock_package_available"]:
        print()
        print("=== 沪深 K 线测试 ===")
        df, staleness = get_kline("sh600519", limit=3)
        print(f"列: {list(df.columns)}")
        print(f"行数: {len(df)}")
        print(f"换手率 attrs: {df.attrs.get('turnover_rate_raw')}")
        print(f"staleness: {staleness} 天")
        print(df.head())

        print()
        print("=== 港股 K 线测试 ===")
        df, staleness = get_kline("hk00700", limit=2)
        print(f"列: {list(df.columns)}")
        print(f"staleness: {staleness} 天")
        print(df.head())

        print()
        print("=== 报价测试（从 minute 组装）===")
        q = get_quote("sh600519")
        print(f"symbol: {q.symbol}")
        print(f"价格: {q.currency} {q.price}")
        print(f"昨收: {q.currency} {q.prev_close}")
        print(f"涨跌: {q.change} ({q.change_pct:.2f}%)")
        print(f"成交量: {q.volume} 股")

        print()
        print("=== 港股报价 ===")
        q = get_quote("hk00700")
        print(f"价格: {q.currency} {q.price}")

    print()
    print("[OK] westock_wrapper.py self-check passed")