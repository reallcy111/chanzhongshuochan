# chanzhongshuochan skill v0.6.0 — Bug 汇总与交接文档

> 给 Claude(原维护人)看
> 日期: 2026-06-24
> 操作人: Mavis(Mavis root session)
> 环境: Windows + Mavis(Mavis)

---

## 0. TL;DR

在 Windows + Mavis 环境重装 chanzhongshuochan v0.6.0 跑通,但**测试 sh600703 时发现 4 个 bug**(其中 1 个导致 Mavis 误读"当前位置")。文档已对齐到 v0.6.0,但 `main.py` 和 `check_environment.py` 里有 OpenClaw 时代的代码残留,**还没改**。

---

## 1. 本次会话完成的工作

### 1.1 安装
| 项 | 版本/路径 |
|---|---|
| Python | 3.13.7 → `C:\Python313\python.exe` |
| Node.js | 24.18.0 LTS → `C:\Program Files\nodejs\node.exe` |
| npm/npx | 11.16.0 |
| Python 依赖 | numpy 2.5.0 / pandas 3.0.3 / akshare 1.18.64 / matplotlib 3.11.0 |
| westock 包 | `westock-data-skillhub@1.0.3` (npx 首次自动拉,无需单独装) |
| Skill 安装路径 | `~/.mavis/skills/chanzhongshuochan/` |

### 1.2 文档对齐(Mavis 处理的)
- `SKILL.md` frontmatter `version: 0.5.1` → `0.6.0`
- `SKILL.md` 删"Nuwa 三阶段信息获取流程"整章,新增"数据获取层 (v0.6 westock-data 整合)" + "5 wrapper 表" + "5 级降级链" + "公共 API 一览"
- `CHANGELOG.md` 顶部加 v0.6.0 完整条目(westock 整合 / 5 wrapper / 5 级降级链 / 兼容性)
- `INSTALL.md` 整体重写:路径从 `~/.openclaw/skills/` 改为 `~/.mavis/skills/`,删不存在的 `config/` 段,加 v0.6 目录结构图 + westock 环境说明

### 1.3 端到端验证已通过
- ✅ `python -m src.check_environment full` → DEGRADED(核心全通)
- ✅ `python -m src.data_layer.westock_wrapper` → A 股/港股 K 线 + 报价全通
- ✅ `analyze_symbol('sh600519', days=120)` → status=ok,K 线 akshare / 报价 westock

---

## 2. 发现的 Bug 清单(按优先级)

### 🔴 P0 — `recent_fenxing/recent_bi/recent_maimaidian` 字段语义误导,直接导致误读

**位置**: `src/main.py:109-111`

```python
result["recent_fenxing"] = [_fenxing_to_dict(f) for f in fenxing_list[-5:]]
result["recent_bi"] = [_bi_to_dict(b) for b in bis[-5:]]
result["recent_maimaidian"] = [_maimaidian_to_dict(m) for m in maimaidians[-5:]]
```

**症状**:
- 字段名带 `recent_`,暗示"当前/最新"
- 实际是"**最近识别完成**的分型/笔/买卖点",时间戳可能停在几天前
- Mavis 拿到 `recent_fenxing[-1]` 的价格(底分型 13.89, 2026-06-12)当成"当前位置",实际 K 线最新已经涨到 21.81(2026-06-24)

**复现**:
```python
from src.main import analyze_symbol
r = analyze_symbol('sh600703', days=180)
# recent_fenxing[-1]['low'] = 13.89 (date=2026-06-12)
# 但 K 线最新 close=21.81 (date=2026-06-24)
# 真实"当前位置"是 21.81,不是 13.89
```

**根因**:
- K 线上涨段如果没出现新顶分型,就没形成新笔/分型
- `fenxing_list[-5:]` 只反映"历史最近完成的",不反映"实时位置"

**修复建议**(任选):
- **选项 A**: 重命名 `recent_*` → `latest_completed_*`(语义清晰,不破坏数据)
- **选项 B(推荐)**: `analyze_symbol` 加 3 个新字段,不改老字段名(向后兼容):
  ```python
  result["kline_latest"] = df.iloc[-1].to_dict()       # 最新一行 K 线完整 dict
  result["kline_latest_close"] = float(df.iloc[-1]["close"])
  result["kline_latest_date"] = str(df.iloc[-1]["date"])
  result["kline_range_30d"] = {                         # 30 天高低/起点/终点
      "high": float(df["high"].tail(30).max()),
      "low": float(df["low"].tail(30).min()),
      "start_close": float(df["close"].iloc[-30]),
      "end_close": float(df["close"].iloc[-1]),
      "change_pct": (df["close"].iloc[-1] / df["close"].iloc[-30] - 1) * 100,
  }
  ```
- **选项 C**: SKILL.md 加一段"如何从 analyze_symbol 输出推导当前位置",教调用方正确解读

---

### 🟠 P1 — westock-data K 线数据滞后 2 周,无 staleness 告警

**位置**: `src/data_layer/westock_wrapper.py:262 (get_kline)`, `src/data_layer/reliability.py`(没做 staleness check)

**症状**:
- sh600703 akshare K 线最新: 2026-06-24
- sh600703 westock K 线最新: **2026-06-10(滞后 14 天)**
- router 在 akshare 失败时会降级到 westock,caller 拿到的"最新 K 线"可能是 2 周前的,但 wrapper 不告诉 caller

**复现**:
```python
from src.data_layer import route_kline
from src.data_layer.westock_wrapper import get_kline

df_a, _ = route_kline('sh600703', days=10)  # akshare
df_w = get_kline('sh600703', limit=10)      # westock
print(df_a.iloc[-1]['date'], 'vs', df_w.iloc[-1]['date'])
# 2026-06-24 vs 2026-06-10
```

**根因**:
- westock-data skillhub@1.0.3 后端腾讯自选股 API 本身延迟/缓存,不是 wrapper bug
- 但 wrapper 没暴露"数据是否新鲜"的状态

**影响**:
- A 股 K 线降级链: `akshare → westock → qveris → tavily → agent-browser`,akshare 挂了才会降级到 westock(本次没触发)
- 港美 K 线降级链: `westock → akshare → ...`,**第一级就是 westock**,港美股用户必然拿到 2 周前数据

**修复建议**:
- 选项 A: `westock_wrapper.get_kline` 返回值带 `staleness_days` 字段(末行日期 vs 今天)
  ```python
  def get_kline(symbol, limit=...) -> tuple[pd.DataFrame, int]:
      df = ...
      last_date = pd.to_datetime(df.iloc[-1]['date']).date()
      staleness_days = (date.today() - last_date).days
      return df, staleness_days
  ```
- 选项 B: `reliability.py` 加 staleness 检测函数,router 在 staleness > 3 时自动跳到下一级
- 选项 C: `docs/sdk-westock-data.md` "已知限制"段补一条 "数据可能滞后 1-2 周"
- **推荐**: A + C,马上能做,影响小

---

### 🟠 P1 — `check_environment.py` 提示用户去 OpenClaw 路径配 API key

**位置**: `src/check_environment.py:55-57`, `src/check_environment.py:380-385`

```python
OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"
# ...
"description": f"在 {OPENCLAW_CONFIG_PATH} 的 env 字段手动添加",
```

**症状**:
- `check_full()` 跑完提示:"API key 缺失,去 `~/.openclaw/openclaw.json` 配"
- 但 Mavis 没有 `~/.openclaw/` 这个目录,这条路在 Mavis 上是死路

**复现**:
```bash
python -m src.check_environment full
# 看输出末尾的 prompt_for_fill 部分
```

**根因**: v0.5.x 写给 OpenClaw 用,v0.6 集成 westock 时没重写 API key 管理这块

**修复建议**:
```python
# src/check_environment.py 改成:

# 1. 配置路径改成 Mavis
MAVIS_CONFIG_PATH = Path.home() / ".mavis" / "skills" / "chanzhongshuochan" / ".env"

# 2. 读取优先级: 环境变量 > .env 文件 (OpenClaw plugins.entries 路径删掉)
def get_api_key(key_name):
    key = os.environ.get(key_name)
    if key:
        return key
    # .env 文件 fallback
    env_file = MAVIS_CONFIG_PATH
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key_name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

# 3. prompt 提示改成 Mavis 路径
"description": f"在环境变量或 {MAVIS_CONFIG_PATH} 配置"
```

---

### 🟡 P2 — `main.py` analyze_symbol docstring 残留 OpenClaw

**位置**: `src/main.py:52`

```python
def analyze_symbol(
    symbol: str,
    name: str = "",
    days: int = 120,
    initial_trend: str = "up",
    with_quote: bool = True,
) -> dict:
    """分析一只股票，返回结构化结果（OpenClaw skill 渲染用）。
```

**修复**: 改 `"分析一只股票，返回结构化结果(Mavis skill 调用方使用)。"`

---

### 🟡 P2 — westock quote 鲁棒性(K 线滞后时仍返回价格)

**位置**: `src/data_layer/westock_wrapper.py:306 (get_quote)`

**症状**: 本次 sh600703 测试时,westock K 线滞后 2 周,但 quote 仍返回 21.81(碰巧跟 akshare 6-24 收盘一致)。可能是 `get_quote` 用 minute 命令拿到了当天实时分时数据,但**没标 staleness**。

**修复**: 跟 P1 westock staleness 一起处理。`QuoteResult` 加 `staleness_minutes` 字段(从 minute 末行时间算),> 60 分钟时标 stale。

---

## 3. 缺失的可选依赖(不影响核心,可后续补)

| 依赖 | 缺失影响 | 修复命令 |
|---|---|---|
| `tavily-python` | 消息面兜底搜索用,跳过 tavily 直接走 agent-browser | `pip install tavily-python` |
| `mplfinance` | 画 K 线图用,dict 输出不受影响 | `pip install mplfinance` |
| `QVERIS_API_KEY` | 实时报价/财经新闻 2 级源 | https://qveris.ai 申请 |
| `TAVILY_API_KEY` | 消息面兜底 3 级源,装 tavily-python 后还要 token | https://tavily.com 申请 |

**当前 `check_full()` 状态**: DEGRADED(8 项 pass, 4 项 warn,0 项 fail)

---

## 4. 复现步骤清单(给 Claude 验证)

```bash
# 1. 环境检查(看 DEGRADED + OpenClaw 路径提示)
python -m src.check_environment full

# 2. 复现 P0 语义 bug
python -c "
import sys
sys.path.insert(0, r'~/.mavis/skills/chanzhongshuochan')
from src.main import analyze_symbol
r = analyze_symbol('sh600703', days=180, with_quote=False)
print('recent_fenxing 最后:', r['recent_fenxing'][-1])
print('  ↑ 这是 2026-06-12 的底分型 13.89')
print('  但 K 线最新 close 已经是 21.81 (2026-06-24)')
print('  analyze_symbol 没暴露 kline_latest 字段,caller 没法直接知道当前位置')
"

# 3. 复现 P1 westock 滞后
python -c "
import sys
sys.path.insert(0, r'~/.mavis/skills/chanzhongshuochan/src')
from data_layer import route_kline
from data_layer.westock_wrapper import get_kline
df_a, _ = route_kline('sh600703', days=10)
df_w = get_kline('sh600703', limit=10)
print(f'akshare 最新: {df_a.iloc[-1][\"date\"]}')
print(f'westock 最新: {df_w.iloc[-1][\"date\"]}')
print(f'westock 滞后 {(df_a.iloc[-1][\"date\"] - df_w.iloc[-1][\"date\"]).days} 天')
"
```

---

## 5. 关键文件路径

| 类型 | 路径 |
|---|---|
| Skill 根目录 | `~/.mavis/skills/chanzhongshuochan/` |
| `main.py` | `…\src\main.py` |
| `westock_wrapper.py` | `…\src\data_layer\westock_wrapper.py` |
| `reliability.py` | `…\src\data_layer\reliability.py` |
| `check_environment.py` | `…\src\check_environment.py` |
| `router.py` | `…\src\data_layer\router.py` |
| `SKILL.md` | `…\SKILL.md` |
| `CHANGELOG.md` | `…\CHANGELOG.md` |
| `INSTALL.md` | `…\INSTALL.md` |
| 备份 zip | `<备份包路径>/chanzhongshuochan-v0.6.0.zip` |

---

## 6. 建议下一步

按优先级:
1. **修 P0**(`main.py` 加 `kline_latest` / `kline_range_30d` 字段)— 影响所有 caller 解读
2. **修 P1 westock staleness**(wrapper 加 staleness 检测 + reliability 集成)— 影响港美股 K 线准确性
3. **修 P1 OpenClaw 路径**(`check_environment.py` 改 Mavis)— 影响 API key 配置流程
4. 修 P2(docstring + quote 鲁棒性)— 小修
5. 补齐可选依赖(用户已问,等拍板)

需要 Claude 拍板的:
- P0 选项 A/B/C 哪个?
- P1 staleness 阈值定几天?3 天?7 天?
- P1 Mavis `.env` 路径用哪个?(`~/.mavis/skills/chanzhongshuochan/.env` 还是别处?)

---

_Mavis root session 整理 / 2026-06-24 22:10 GMT+8_