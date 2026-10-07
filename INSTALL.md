# 缠中说禅 Skill 安装 / 恢复指南

> 📦 版本:v0.6.2(2026-06-24)
> 📅 文档:2026-06-25 GMT+8
> 🎯 用途:跨设备迁移 / 灾备恢复 / 重新部署

---

## 📋 系统要求

| 项 | 要求 |
|---|---|
| **操作系统** | Windows 10+ / macOS 12+ / Linux (Ubuntu 20.04+) |
| **Python** | 3.7+(必须,技能依赖) |
| **Mavis** | v2026.6+(推荐;OpenClaw v2026.5.18+ 兼容) |
| **Node.js** | **>= 18.0.0**(v0.6 新增 — westock-data CLI 依赖) |
| **npm / npx** | 随 Node.js 安装 |
| **磁盘空间** | ≥ 2 MB |
| **数据依赖** | akshare(必装)/ numpy / pandas(必装)/ tavily-python(可选)/ westock(npx 自动拉) |

---

## 🚀 安装步骤

### 步骤 1:解压备份包

```bash
# 假设备份包在 ~/Downloads/chanzhongshuochan-v0.6.2.zip
# Windows PowerShell
Expand-Archive -Path "$env:USERPROFILE\Downloads\chanzhongshuochan-v0.6.2.zip" -DestinationPath "$env:USERPROFILE\Downloads\chanzhongshuochan-extracted"

# macOS / Linux
unzip chanzhongshuochan-v0.6.2.zip -d ./chanzhongshuochan-extracted
```

### 步骤 2:复制到 Mavis skills 目录

```bash
# Windows
Copy-Item -Recurse "$env:USERPROFILE\Downloads\chanzhongshuochan-extracted\chanzhongshuochan" "$env:USERPROFILE\.mavis\skills\"

# macOS / Linux
cp -r ./chanzhongshuochan-extracted/chanzhongshuochan ~/.mavis/skills/
```

> 📝 **v0.6 路径变更**:从 `~/.openclaw/skills/` 迁移到 `~/.mavis/skills/chanzhongshuochan/`。OpenClaw 旧路径不再有效。

### 步骤 3:安装 Python 依赖(如未装)

```bash
# 必备
pip install numpy pandas

# v0.6 推荐
pip install akshare              # A股数据主源
pip install tavily-python       # 消息面兜底 (可选)

# westock-data 由 npx 自动拉,无需 pip install
# 首次调用 `python -m src.check_environment full` 会自动下载
```

### 步骤 4:配置 API key(可选)

```bash
# 创建 .env 文件
mkdir -p ~/.mavis/skills/chanzhongshuochan
cat > ~/.mavis/skills/chanzhongshuochan/.env <<'EOF'
QVERIS_API_KEY="your_qveris_key_here"
TAVILY_API_KEY="your_tavily_key_here"
EOF
chmod 600 ~/.mavis/skills/chanzhongshuochan/.env
```

> 📝 **v0.6.2 路径变更**:API key 读取从 `~/.openclaw/openclaw.json`(plugins.entries 路径)改为 `~/.mavis/skills/chanzhongshuochan/.env`(标准 KEY=VALUE 格式)。也支持环境变量直接注入。

### 步骤 5:验证安装

```bash
# 1. 检查目录结构
ls ~/.mavis/skills/chanzhongshuochan/

# 应该看到:
#   SKILL.md
#   INSTALL.md
#   CHANGELOG.md
#   docs/
#   src/
#   tests/

# 2. 验证 Python 可导入
PYTHONPATH=~/.mavis/skills/chanzhongshuochan python3 -c "
import sys
sys.path.insert(0, '~/.mavis/skills/chanzhongshuochan')
from src.main import analyze_symbol
print('✅ 入口 analyze_symbol 可导入')
"

# 3. 运行环境检查(含 westock Node/npx 检测)
python3 -m src.check_environment full
# 预期:westock_node / westock_npx / westock_package 显示 pass 或 warn
# DEGRADED 状态可接受(说明核心全通,部分可选数据源不可用)

# 4. 验证 Mavis 识别
mavis skills list | grep chanzhongshuochan
# 应该看到:✅ ready | 缠中说禅 | v0.6.2 | ...
```

---

## 🧪 快速测试

```bash
# 1. 跑分型单元测试 (8 个)
PYTHONPATH=. python3 tests/test_fenxing.py

# 2. 跑 P0/P1/P2 端到端 smoke test (14 个)
PYTHONPATH=. python3 tests/test_p1_smoke.py

# 3. 验证 analyze_symbol 入口可调
PYTHONPATH=. python3 -c "
import sys
sys.path.insert(0, '.')
from src.main import analyze_symbol
r = analyze_symbol('sh600519', days=120, with_quote=False)
print(f'status={r[\"status\"]}, K线来源={r.get(\"kline_source\")}, 行数={r.get(\"kline_rows\", 0)}')
print(f'kline_latest: close={r[\"kline_latest\"][\"close\"]}, date={r[\"kline_latest\"][\"date\"]}')
"

# 4. 验证 westock wrapper
python3 -m src.data_layer.westock_wrapper
# 预期:沪深/港股 K 线 + 报价测试全通
```

---

## 📂 目录结构(恢复后应一致)

```
~/.mavis/skills/chanzhongshuochan/
├── SKILL.md                                技能主文档(v0.6.2)
├── INSTALL.md                              ← 本文件
├── CHANGELOG.md                            变更记录(v0.6.2 / v0.6.0 / v0.5.x)
├── src/
│   ├── __init__.py                         公共 API 导出
│   ├── main.py                             高层入口 (analyze_symbol)
│   ├── check_environment.py                环境检查 (Node/npx/westock/API key)
│   ├── kline.py                            K线处理
│   ├── fenxing.py                          分型识别
│   ├── bi.py                               笔划分
│   ├── zhongshu.py                         中枢
│   ├── beichi.py                           背驰
│   ├── maimaidian.py                       买卖点
│   ├── macd.py                             MACD
│   └── data_layer/                         v0.6 数据获取层(核心)
│       ├── __init__.py                     统一导出 (KlineRow/QuoteResult/route_*)
│       ├── contracts.py                    数据契约 (frozen=True + currency 必填)
│       ├── reliability.py                  重试/熔断/SQLite 缓存
│       ├── router.py                       5 级降级编排
│       ├── westock_wrapper.py              npx 腾讯自选股 (Markdown 解析)
│       ├── akshare_wrapper.py              akshare A股/港/美 K线 + 公告
│       ├── qveris_wrapper.py               qveris.ai 实时价 + 财经新闻
│       ├── tavily_wrapper.py               tavily 兜底搜索
│       └── agent_browser.py                agent-browser 终极兜底
├── docs/                                   SDK 文档
│   ├── sdk-westock-data.md                 westock 使用 + 已知限制
│   ├── sdk-akshare.md                      akshare 字段约定
│   ├── sdk-qveris.md                       qveris API key 获取
│   ├── sdk-tavily.md                       tavily topic=finance
│   ├── sdk-mplfinance.md                   走势图
│   └── sdk-agent-browser.md                agent-browser 兜底
└── tests/
    ├── test_fenxing.py                     分型单元测试 (8 个, v0.6.2 重写)
    └── test_p1_smoke.py                    P0+P1+P2 端到端 (14 个)
```

> 📝 **v0.6 变更**:`quant_detect.py` / `qveris_client.py` / `data_fetcher.py` / `nuwa_pipeline.py` 已归档到 `archive/v0.5.x/`(如需旧版,见归档)。`config/default.json` 已删除(运行时引导式询问)。

---

## 🔄 卸载

```bash
# 直接删除目录
rm -rf ~/.mavis/skills/chanzhongshuochan

# Windows
Remove-Item -Recurse -Force "$env:USERPROFILE\.mavis\skills\chanzhongshuochan"
```

**不会影响**:
- Python 依赖包(`pip install` 装的)
- Node.js / npm / westock-data(全局安装,其他 skill 共享)
- 主公的其他 Mavis skills

---

## 🛠️ 故障排查

### Q1: Mavis 不识别 skill(状态 `needs setup`)

**原因**:skill 目录不在 `~/.mavis/skills/chanzhongshuochan/` 标准位置

**修复**:
```bash
# 确认路径
ls ~/.mavis/skills/chanzhongshuochan/SKILL.md

# 如果不在,复制过去
# 重新加载
mavis skills list
```

### Q2: westock K 线滞后 / 港美股报 stale 错

**原因**:westock-data 腾讯自选股 API 数据可能滞后 1-2 周

**修复**:
- v0.6.2 router 已自动检测 staleness > 3 天并跳下一源,无需手动处理
- 港美股第一级源是 westock,若 westock 整体故障会降到 akshare(但 akshare 港美不稳定)
- 极端情况:设 `RouterConfig.staleness_threshold_days = None` 禁用 staleness 检查(不推荐)

### Q3: Python 导入失败

**错误**:`ModuleNotFoundError: No module named 'xxx'`

**修复**:
```bash
pip install xxx
# 或用虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt  # 如有
```

### Q4: westock npx 报"westock 包未找到"

**原因**:首次调用需外网下载 `westock-data-skillhub@1.0.3`,网络问题导致失败

**修复**:
- 检查网络: `npm ping` / `curl https://registry.npmjs.org/`
- 重装 Node.js(含 npm)
- 极端情况:设 `RouterConfig.enabled_kline_sources['westock'] = False` 禁用 westock

### Q5: API key 缺失警告

**修复**:
- 在 `~/.mavis/skills/chanzhongshuochan/.env` 写入 `QVERIS_API_KEY=xxx` / `TAVILY_API_KEY=xxx`
- 或设环境变量 `export QVERIS_API_KEY=xxx`
- 缺失仅警告(DEGRADED),不阻断核心功能(akshare 可独立工作)

---

## 🔐 建议

1. **建议**用加密压缩包(如 7-Zip AES-256)保护备份
2. **建议**把备份同步到云盘(OneDrive / 坚果云 / NAS)
3. **建议**每 90 天重新打包一次
4. **建议**记录每次大改动的 CHANGELOG

---

_最后更新:2026-06-25 GMT+8_
_维护人:Mavis root session / 贾维斯 🫡_
