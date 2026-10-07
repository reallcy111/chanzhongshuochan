"""
src/data_layer/agent_browser.py — agent-browser 兜底层

按 plan 决策 (skills-fluttering-hinton.md):
- 5 级数据源最末位（兜底）
- 通过 subprocess 调用 agent-browser CLI（Vercel Labs）
- 爬公开页面: A 股新浪/东财、港股 aastocks、美股 yahoo finance

API: open → snapshot → action → close
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_NAME = "agent_browser"
AGENT_BROWSER_CMD = "agent-browser"
DEFAULT_TIMEOUT = 30


# ============================================================
# 异常类
# ============================================================
class AgentBrowserError(Exception):
    """agent-browser 所有异常的基类"""


class AgentBrowserEnvError(AgentBrowserError):
    """环境错误（agent-browser 未安装）"""


class AgentBrowserTransientError(AgentBrowserError):
    """可重试瞬时错误（超时）"""


class AgentBrowserPermanentError(AgentBrowserError):
    """永久错误（ref 失效、页面变更）"""


# ============================================================
# 工具：定位 CLI 路径
# ============================================================
def _is_agent_browser_available() -> bool:
    return shutil.which(AGENT_BROWSER_CMD) is not None


def _resolve_cmd() -> str:
    """解析 CLI 绝对路径（Windows PATHEXT 兼容）"""
    return shutil.which(AGENT_BROWSER_CMD) or AGENT_BROWSER_CMD


# ============================================================
# subprocess 封装
# ============================================================
@dataclass
class BrowserSnapshotItem:
    """snapshot 返回的单项"""
    ref: str
    role: str
    text: str


def _run_cmd(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> str:
    """执行 agent-browser 命令，返回 stdout。"""
    cmd = [_resolve_cmd()] + list(args)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as e:
        raise AgentBrowserEnvError(f"agent-browser 不可用: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise AgentBrowserTransientError(f"agent-browser 超时 ({timeout}s)") from e

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()[:300]
        raise AgentBrowserTransientError(
            f"agent-browser 退出码 {proc.returncode}: {stderr}"
        )
    return proc.stdout


# ============================================================
# 公开 API
# ============================================================
def open_page(url: str, timeout: int = 30) -> None:
    """打开 URL（新浏览器实例）"""
    _run_cmd(["open", url], timeout=timeout)


def snapshot_page(interactive_only: bool = True, timeout: int = 30) -> list[BrowserSnapshotItem]:
    """获取页面快照，返回可访问性树。"""
    cmd = ["snapshot"]
    if interactive_only:
        cmd.append("-i")
    out = _run_cmd(cmd, timeout=timeout)

    items: list[BrowserSnapshotItem] = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        m = re.match(r'^-\s+(\w+)\s+"([^"]*)"\[ref=(\w+)\]', line)
        if m:
            items.append(BrowserSnapshotItem(
                ref=m.group(3), role=m.group(1), text=m.group(2),
            ))
    return items


def get_text(ref: str, timeout: int = 10) -> str:
    """获取 ref 对应元素的文本"""
    return _run_cmd(["get", "text", f"@{ref}"], timeout=timeout).strip()


def take_screenshot(filename: str, timeout: int = 15) -> str:
    """截图，返回文件名"""
    _run_cmd(["screenshot", filename], timeout=timeout)
    return filename


def close_browser() -> None:
    """关闭浏览器"""
    try:
        _run_cmd(["close"], timeout=10)
    except AgentBrowserError as e:
        logger.warning("关闭浏览器失败: %s", e)


# ============================================================
# A 股 K 线兜底（爬新浪）
# ============================================================
def fetch_a_kline_via_sina(symbol: str, timeout: int = 60) -> Optional[str]:
    """agent-browser 爬新浪历史 K 线（兜底场景）

    Args:
        symbol: sh600519 / sz000001
    """
    if not _is_agent_browser_available():
        raise AgentBrowserEnvError("agent-browser 未安装")

    url = f"https://finance.sina.com.cn/realstock/company/{symbol}"
    try:
        open_page(url, timeout=timeout)
        snapshot = snapshot_page(interactive_only=False, timeout=timeout)
        for item in snapshot:
            if item.role == "table":
                return get_text(item.ref, timeout=15)
        return None
    finally:
        close_browser()


# ============================================================
# 自检
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    if not _is_agent_browser_available():
        print("[WARN] agent-browser CLI 未安装（兜底层不可用，其他源仍可用）")
    else:
        print("[OK] agent-browser 已安装")

    print()
    print("[OK] agent_browser.py self-check passed")