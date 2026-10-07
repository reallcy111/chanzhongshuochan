# Agent-Browser SDK 标准调用规范

> 来源：Context7 /vercel-labs/agent-browser（2026-06-23 验证）
> 用途：缠中说禅 skill 数据获取层 4 级数据源（公开页面爬取兜底）

## 简介

agent-browser 是 Vercel Labs 出的 headless 浏览器自动化 CLI，专为 AI agent 设计：
- Rust 实现 + Node.js fallback
- 通过 `@ref` 引用元素（不用 selector）
- 输出可访问性树快照（AI 友好）

## 安装

```bash
# 用户已装在 OpenClaw 里（npm 全局）
# 验证: agent-browser --version
# 应该返回版本号

# 如果需要重新装:
npm install -g @vercel-labs/agent-browser
```

## 基本命令

```bash
# 打开网页
agent-browser open https://finance.sina.com.cn/realstock/company/sh600000

# 获取可访问性树快照（含 ref）
agent-browser snapshot
# 输出示例:
# - heading "浦发银行" [ref=e1]
# - text "8.50" [ref=e2]
# - link "详情" [ref=e3]

# 只输出 interactive 元素（推荐用于 AI）
agent-browser snapshot -i

# 通过 ref 点击
agent-browser click @e3

# 通过 ref 填表
agent-browser fill @e10 "user@example.com"

# 截图
agent-browser screenshot page.png

# 获取元素文本
agent-browser get text @e1

# 关闭浏览器
agent-browser close
```

## 在 Python 中调用

```python
import subprocess
import json

def agent_browser_snapshot(url: str, interactive_only: bool = True) -> list[dict]:
    """获取页面快照，返回 [{ref, role, text}, ...]"""
    # 1. open
    subprocess.run(["agent-browser", "open", url], check=True, capture_output=True)
    # 2. snapshot
    cmd = ["agent-browser", "snapshot"]
    if interactive_only:
        cmd.append("-i")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    # 3. 解析输出（每行格式: "- {role} \"{text}\" [ref={ref}]"）
    items = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        # 简化解析
        import re
        match = re.match(r'^-\s+(\w+)\s+"([^"]*)"\[ref=(\w+)\]', line)
        if match:
            items.append({
                "role": match.group(1),
                "text": match.group(2),
                "ref": match.group(3),
            })
    return items

def agent_browser_get_text(ref: str) -> str:
    """获取 ref 对应元素的文本"""
    result = subprocess.run(
        ["agent-browser", "get", "text", f"@{ref}"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()

def agent_browser_close():
    """关闭浏览器"""
    subprocess.run(["agent-browser", "close"], check=False, capture_output=True)
```

## A 股 K 线兜底场景（爬新浪）

```python
def fetch_a_klines_via_browser(symbol: str, days: int) -> pd.DataFrame:
    """agent-browser 爬新浪历史 K 线"""
    url = f"https://finance.sina.com.cn/realstock/company/{symbol}"
    snapshot = agent_browser_snapshot(url, interactive_only=False)
    
    # 找到 K 线表格的 ref
    table_ref = next(
        (s["ref"] for s in snapshot if s["role"] == "table" and "K线" in s["text"]),
        None,
    )
    if not table_ref:
        raise RuntimeError("K线表格未找到")
    
    # 获取表格内容（简化）
    raw_text = agent_browser_get_text(table_ref)
    # ... 解析为 DataFrame ...
    return df
```

## 已知陷阱

1. **每次 open 会启动新浏览器实例**：多次爬取要复用
2. **ref 在每次 snapshot 后失效**：重新 snapshot 拿新 ref
3. **JS 渲染需要时间**：snapshot 前可加 `time.sleep(2)`
4. **新浪 vip 需登录或 IP 白名单**：失败时降级到 agent-browser 通用搜索
5. **关闭浏览器很关键**：不 close 会一直占资源

## 完整生命周期

```python
def browser_workflow(url: str, actions: list[dict]) -> dict:
    """标准工作流: open → snapshot → actions → close"""
    try:
        subprocess.run(["agent-browser", "open", url], check=True, capture_output=True, timeout=30)
        snapshot = agent_browser_snapshot(url, interactive_only=True)
        results = {}
        for action in actions:
            ref = action["ref"]
            cmd = action["cmd"]  # "click" | "fill" | "get text" | "screenshot"
            if cmd == "click":
                subprocess.run(["agent-browser", "click", f"@{ref}"], check=True, timeout=10)
            elif cmd == "get text":
                results[ref] = agent_browser_get_text(ref)
            elif cmd == "screenshot":
                subprocess.run(["agent-browser", "screenshot", action["file"]], check=True, timeout=10)
                results[ref] = action["file"]
        return results
    finally:
        agent_browser_close()
```

## 内联测试

```python
if __name__ == '__main__':
    # 简单测试
    snapshot = agent_browser_snapshot("https://example.com", interactive_only=True)
    print(f"找到 {len(snapshot)} 个 interactive 元素")
    for item in snapshot[:5]:
        print(f"  [{item['ref']}] {item['role']}: {item['text']}")
    agent_browser_close()
```

## 异常处理

```python
import subprocess

class AgentBrowserError(Exception):
    pass

def safe_run(cmd: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout
    except subprocess.TimeoutExpired:
        raise AgentBrowserError(f"agent-browser 超时: {' '.join(cmd)}")
    except subprocess.CalledProcessError as e:
        raise AgentBrowserError(f"agent-browser 失败: {e.stderr}")
```

## 替代方案

如果 agent-browser 不可用，备选：
- **Playwright MCP**（`mcp__plugin_ecc_playwright__*`）— 已在我环境
- **Exa MCP**（`mcp__plugin_ecc_exa__web_fetch_exa`）— 抓静态页面
- **WebFetch / WebSearch**（通用工具）— 兜底
