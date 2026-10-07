"""
src/check_environment.py — 缠中说禅 skill 环境检查

两阶段检查:
  - check_light():  加载时 < 1s 轻量检查（Mavis 加载 skill 时调用）
  - check_full():   首次调用前 3-5s 完整检查（含网络、API key、数据源健康）

按 plan 决策:
  - 加载时轻量 + 首次调用前完整 (C 决策)
  - API key 缺失仅警告，不阻断 (B 决策)
  - env 文件不存在则智能创建 (C 决策)
  - 网络只 ping 一个关键域名 (B 决策)

v0.6.2 变更:
  - API key 读取路径: ~/.openclaw/openclaw.json → ~/.mavis/skills/chanzhongshuochan/.env
  - 提示文案: "在 MAVIS_ENV_PATH 配置"，不再提 OpenClaw

用法:
  from check_environment import check_light, check_full
  light = check_light()
  full = check_full()
  print(format_report(full))
"""

import os
import socket
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


# ============================================================
# API key 清单（统一处理：B 决策 — 缺失仅警告，不阻断）
#
# v0.6.2 读取优先级:
#   1. 环境变量
#   2. ~/.mavis/skills/chanzhongshuochan/.env 文件（KEY=VALUE 格式）
# ============================================================
REQUIRED_API_KEYS = {
    "QVERIS_API_KEY": {
        "purpose": "实时报价 + 财经新闻（qveris 2 级数据源）",
        "tier": "推荐",  # 缺失则降级到 tavily/agent-browser
        "obtain_url": "https://qveris.ai",
    },
    "TAVILY_API_KEY": {
        "purpose": "消息面兜底搜索（tavily 3 级数据源）",
        "tier": "推荐",
        "obtain_url": "https://tavily.com",
    },
}

# v0.6.2: Mavis skill 路径下的 .env 文件
MAVIS_ENV_PATH = Path.home() / ".mavis" / "skills" / "chanzhongshuochan" / ".env"
CACHE_DIR = Path.home() / ".cache" / "chanzhongshuochan"
NETWORK_TEST_DOMAIN = "qveris.ai"  # 关键域名（外网通则其他大概率通）


# ============================================================
# 数据类
# ============================================================
@dataclass
class CheckResult:
    name: str
    status: str  # "pass" | "fail" | "warn" | "skip"
    detail: str = ""
    error: str = ""

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v}


# ============================================================
# .env 文件解析（v0.6.2 — Mavis 路径）
# ============================================================
def _parse_env_file(path: Path) -> dict[str, str]:
    """解析 .env 文件，返回 {KEY: VALUE} 字典。

    支持格式:
        KEY=value
        KEY="value"
        KEY='value'
        # 注释行
        空行
    """
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def get_api_key(key_name: str) -> Optional[str]:
    """
    优先级 1: 环境变量（Mavis 注入）
    优先级 2: ~/.mavis/skills/chanzhongshuochan/.env 文件

    v0.6.2: 不再读 OpenClaw vault。
    """
    key = os.environ.get(key_name)
    if key:
        return key
    env_vars = _parse_env_file(MAVIS_ENV_PATH)
    return env_vars.get(key_name) or None


def save_api_keys_to_env(keys: dict) -> bool:
    """
    把 API key 写入 ~/.mavis/skills/chanzhongshuochan/.env
    （追加或更新，不覆盖其他变量）
    """
    try:
        env_vars = _parse_env_file(MAVIS_ENV_PATH)
        for k, v in keys.items():
            if v:
                env_vars[k] = v
        MAVIS_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        lines = [f'{k}="{v}"' for k, v in env_vars.items()]
        MAVIS_ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


# ============================================================
# 0. 轻量检查（< 1s）
# ============================================================
def check_light() -> dict:
    """加载时轻量检查（不阻塞 Mavis skill 加载）"""
    results = []

    # Python 版本
    py_ok = sys.version_info >= (3, 7)
    results.append(CheckResult(
        "python_version",
        "pass" if py_ok else "fail",
        detail=f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        error="" if py_ok else "Python < 3.7 不支持",
    ))

    # 缓存目录可写
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        test_file = CACHE_DIR / ".test_write"
        test_file.write_text("ok")
        test_file.unlink()
        results.append(CheckResult("cache_dir_writable", "pass", detail=str(CACHE_DIR)))
    except OSError as e:
        results.append(CheckResult("cache_dir_writable", "fail", error=str(e)))

    # 必备依赖（核心计算）
    core_deps = ["numpy", "pandas"]
    for dep in core_deps:
        try:
            __import__(dep)
            results.append(CheckResult(f"dep_{dep}", "pass"))
        except ImportError:
            results.append(CheckResult(
                f"dep_{dep}", "fail",
                error=f"pip install {dep}",
            ))

    # 可选依赖（数据获取 + 走势图）
    optional_deps = {
        "akshare": "pip install akshare",
        "tavily": "pip install tavily-python",
        "mplfinance": "pip install mplfinance",
    }
    for dep, install_cmd in optional_deps.items():
        try:
            __import__(dep)
            results.append(CheckResult(f"dep_{dep}", "pass"))
        except ImportError:
            results.append(CheckResult(
                f"dep_{dep}", "warn",
                detail=f"缺失 — {install_cmd}",
            ))

    # 计算整体状态
    statuses = [r.status for r in results]
    if "fail" in statuses:
        overall = "broken"
    elif "warn" in statuses:
        overall = "degraded"
    else:
        overall = "ready"

    return {
        "overall": overall,
        "results": [r.to_dict() for r in results],
    }


# ============================================================
# 1. 完整检查（3-5s）
# ============================================================
def check_full() -> dict:
    """首次调用前完整检查（含网络、API key、数据源健康）"""
    light = check_light()
    # 把 dict 转回 CheckResult 列表（check_light 返回的是 dict 列表）
    results = [CheckResult(**r) for r in light["results"]]
    overall = light["overall"]

    # 1.1 API key 完整清单（B 决策 — 统一处理，缺失仅警告）
    for key_name, meta in REQUIRED_API_KEYS.items():
        value = get_api_key(key_name)
        if value:
            results.append(CheckResult(
                f"key_{key_name}",
                "pass",
                detail=f"长度 {len(value)}",
            ))
        else:
            results.append(CheckResult(
                f"key_{key_name}",
                "warn",
                detail=f"缺失（{meta['tier']}）— 用途: {meta['purpose']}，获取: {meta['obtain_url']}",
            ))

    # 1.2 网络测试（只 ping 一个关键域名 — B 决策）
    try:
        with socket.create_connection((NETWORK_TEST_DOMAIN, 443), timeout=5):
            results.append(CheckResult(
                f"network_{NETWORK_TEST_DOMAIN}",
                "pass",
                detail="TCP 443 可达",
            ))
    except Exception as e:
        results.append(CheckResult(
            f"network_{NETWORK_TEST_DOMAIN}",
            "warn",
            error=str(e),
            detail="外网可能不通，部分数据源会降级失败",
        ))

    # 1.3 数据源健康（akshare 拉一次确认）
    if _is_module_available("akshare"):
        try:
            import akshare as ak
            t0 = time.time()
            df = ak.stock_zh_a_hist_tx(
                symbol="sh600000",
                start_date="20240601",
                end_date="20240623",
                adjust="qfq",
                timeout=10,
            )
            elapsed = time.time() - t0
            results.append(CheckResult(
                "data_source_akshare",
                "pass" if len(df) > 0 else "warn",
                detail=f"响应 {elapsed:.2f}s, {len(df)} 行",
            ))
        except Exception as e:
            results.append(CheckResult(
                "data_source_akshare",
                "warn",
                error=f"{type(e).__name__}: {e}",
                detail="akshare 接口失败，将降级到 qveris/tavily",
            ))

    # 1.4 westock 环境检查（v0.6 新增）
    try:
        from data_layer.westock_wrapper import check_environment as westock_env
        env = westock_env()
        if env["node_available"]:
            ver = env.get("node_version")
            ver_str = ".".join(str(x) for x in ver) if ver else "未知"
            results.append(CheckResult(
                "westock_node",
                "pass",
                detail=f"v{ver_str} (>= 18 推荐)",
            ))
        else:
            results.append(CheckResult(
                "westock_node",
                "warn",
                error="Node.js 未安装",
                detail="westock-data 需 Node.js >= 18（缺失则港/美股 K 线降级到 akshare）",
            ))

        if env["npx_available"]:
            results.append(CheckResult("westock_npx", "pass", detail="npx 可用"))
        else:
            results.append(CheckResult(
                "westock_npx", "warn",
                error="npx 不可用",
                detail="重装 Node.js（含 npm）",
            ))

        if env["westock_package_available"]:
            results.append(CheckResult(
                "westock_package", "pass",
                detail="westock-data-skillhub@1.0.3 可调用",
            ))
        else:
            results.append(CheckResult(
                "westock_package", "warn",
                detail="首次调用会自动下载（需外网）",
            ))
    except ImportError as e:
        results.append(CheckResult(
            "westock_check", "warn",
            error=f"westock_wrapper 未加载: {e}",
            detail="data_layer 子模块未初始化",
        ))

    # 1.5 重新计算整体状态
    statuses = [r.status for r in results]
    if "fail" in statuses:
        overall = "broken"
    elif "warn" in statuses:
        overall = "degraded"
    else:
        overall = "ready"

    # 1.5 构建交互提示（C 决策 — 询问用户填入）
    prompt_for_fill = build_fill_prompt(results)

    return {
        "overall": overall,
        "results": [r.to_dict() for r in results],
        "missing_keys": [
            r.name.replace("key_", "")
            for r in results
            if r.name.startswith("key_") and r.status == "warn"
        ],
        "prompt_for_fill": prompt_for_fill,
    }


# ============================================================
# 2. 交互提示构建（C 决策）
# ============================================================
def build_fill_prompt(results: list) -> Optional[dict]:
    """
    询问用户是否填入缺失的 API key。
    返回结构化 dict，Mavis skill prompt 可直接渲染。
    """
    # 兼容 CheckResult 实例和 dict 两种输入
    items = [r.to_dict() if hasattr(r, "to_dict") else r for r in results]
    missing = [
        r for r in items
        if r["name"].startswith("key_") and r["status"] == "warn"
    ]
    if not missing:
        return None

    return {
        "question": f"检测到 {len(missing)} 个 API key 缺失，是否现在填入？",
        "options": [
            {
                "label": "是，逐个填入",
                "description": "进入交互式输入，每项问一次（Mavis skill prompt 调用）",
            },
            {
                "label": "否，稍后手动配",
                "description": f"在环境变量或 {MAVIS_ENV_PATH} 配置（KEY=VALUE 格式）",
            },
            {
                "label": "跳过，仅用可选数据源",
                "description": "只用 akshare（已验证），不依赖 qveris/tavily",
            },
        ],
        "missing_keys": [
            {
                "name": r["name"].replace("key_", ""),
                "purpose": REQUIRED_API_KEYS.get(r["name"].replace("key_", ""), {}).get("purpose", ""),
                "obtain_url": REQUIRED_API_KEYS.get(r["name"].replace("key_", ""), {}).get("obtain_url", ""),
            }
            for r in missing
        ],
    }


# ============================================================
# 3. 报告格式化
# ============================================================
def format_report(report: dict) -> str:
    """人类可读的报告"""
    lines = []
    emoji = {"ready": "✅", "degraded": "⚠️ ", "broken": "❌"}
    lines.append(f"{emoji.get(report['overall'], '?')} 缠中说禅 skill 环境检查: {report['overall'].upper()}")
    lines.append("")
    for r in report.get("results", []):
        status_emoji = {"pass": "✅", "warn": "⚠️ ", "fail": "❌", "skip": "⏭ "}.get(r["status"], "?")
        name = r["name"]
        if r.get("detail"):
            lines.append(f"  {status_emoji} {name}: {r['detail']}")
        elif r.get("error"):
            lines.append(f"  {status_emoji} {name}: {r['error']}")
        else:
            lines.append(f"  {status_emoji} {name}")

    if report.get("prompt_for_fill"):
        pf = report["prompt_for_fill"]
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"❓ {pf['question']}")
        for i, opt in enumerate(pf["options"], 1):
            lines.append(f"  {i}. {opt['label']} — {opt['description']}")
        for mk in pf["missing_keys"]:
            lines.append(f"  • {mk['name']}: {mk['purpose']} (获取: {mk['obtain_url']})")

    return "\n".join(lines)


# ============================================================
# 辅助
# ============================================================
def _is_module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


# ============================================================
# CLI 入口（直接跑）
# ============================================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode == "light":
        report = check_light()
    else:
        report = check_full()
    print(format_report(report))
    sys.exit(0 if report["overall"] != "broken" else 1)
