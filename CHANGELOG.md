# Changelog

缠中说禅技能 (chanzhongshuochan) 版本变更记录。

## v0.6.3 (2026-06-25) — detect_trend_beichi list 化修复 (P3)

**核心改动**:龙研 (lobster) 反馈 v0.6.0 时代埋下的 `main.py:136` `len(Beichi)` TypeError —— `detect_trend_beichi` 实际返回 `Optional[Beichi]`(单对象),但 main.py 当 list 用,与 MEMORY 6/22 "maimaidian bug" 同源。

### 🐛 Bug 修复

- 🟠 **P3**:`detect_trend_beichi` 返回 `Optional[Beichi]` 单对象,`main.py:136` `or []` 兜底失败导致 `len(Beichi)` TypeError
  - **修复**:新增 `detect_all_trend_beichis(bis, macd_df) -> List[Beichi]`(同时返回顶背+底背,不丢弃次优的)
  - 改 `main.py:136` 用新函数:`beichis = detect_all_trend_beichis(...)`(直接 list,无需 `or []`)
  - 保留 `detect_trend_beichi` 单对象 API(向后兼容)
  - 见 [src/beichi.py](src/beichi.py) + [src/main.py:136](src/main.py#L136) + [src/__init__.py:35,75](src/__init__.py#L35)

### 💡 根因

- v0.6.0 时代埋下,与 MEMORY 6/22 "maimaidian bug" 同源:API 返回 `Optional[X]`(单),但 caller 当 `List[X]` 用
- `detect_trend_beichi` 检测顶+底两个背驰但只返回置信度高的一个(另一个被丢弃,信息损失)
- `main.py:136-139` 期望 list 做 `len()` 和 `identify_buy_sell_points(bis, zhongshus, beichis)` 输入

### ✅ 验证

- `tests/test_p1_smoke.py` 新增 P3-1 (detect_all_trend_beichis API) + P3-2 (main.py 无 TypeError 模式) 共 2 用例
- P0/P1/P2 行为无回归
- 总测试:14 (P1) + 2 (P3) + 8 (fenxing) = 24/24 通过

---

## v0.6.2 (2026-06-24) — Bug 修复 + 文档完善

**核心改动**:Mavis root session 复现 sh600703 时发现 4 个 bug(P0 误读"当前位置" + P1 westock 数据滞后无告警 + P1 OpenClaw 路径 Mavis 死路 + P2 docstring/quote 鲁棒性),全部修复并通过端到端测试。

### 🐛 Bug 修复

- 🔴 **P0**:`analyze_symbol` 输出加 `kline_latest` / `kline_range_30d` / `kline_latest_close` / `kline_latest_date` 字段(修复 `recent_*` 字段语义误导)
  - 见 [src/main.py:88-117](src/main.py#L88)
- 🟠 **P1-1**:westock `get_kline` 返回类型从 `pd.DataFrame` → `tuple[pd.DataFrame, int]` 含 `staleness_days`
  - 新增 `compute_staleness_days(df)` 和 `compute_staleness_minutes(df_minute)` helpers
  - 见 [src/data_layer/westock_wrapper.py:262-310](src/data_layer/westock_wrapper.py#L262)
- 🟠 **P1-2**:router `route_kline` 在 `staleness_days > 3` 时自动跳下一源(westock 数据过期 → akshare / qveris)
  - 新增 `STALENESS_THRESHOLD_DAYS = 3` 常量,`RouterConfig.staleness_threshold_days` 字段(`None` 禁用)
  - 见 [src/data_layer/router.py:113-200](src/data_layer/router.py#L113)
- 🟠 **P1-3**:`check_environment` 改用 `~/.mavis/skills/chanzhongshuochan/.env`(删 OpenClaw vault 路径)
  - `OPENCLAW_CONFIG_PATH` → `MAVIS_ENV_PATH`
  - `read_openclaw_config` / `save_api_keys_to_vault` 替换为 `_parse_env_file` / `save_api_keys_to_env`
  - 见 [src/check_environment.py](src/check_environment.py)
- 🟡 **P2**:`analyze_symbol` docstring "OpenClaw" → "Mavis"
- 🟡 **P2**:`QuoteResult` 加 `staleness_minutes: int | None` 字段(从 westock minute 末行 HHMM time 算)
- 🟡 **P2**:`tests/test_fenxing.py` 重写 — 删不存在的 `detect_top_fenxing/detect_bottom_fenxing` 引用,改用真实 `identify_fenxing` 函数
- 🟡 **P2**:`docs/sdk-westock-data.md` "已知限制" 补 "数据可能滞后 1-2 周"

### 📝 文档完善

- SKILL.md / CHANGELOG.md / INSTALL.md 对齐 v0.6.2(frontmatter `version: 0.6.2` + 删 Nuwa 章 + 加 v0.6 数据获取层 + 路径 `.openclaw` → `.mavis`)
- docs/sdk-westock-data.md 已知限制段加 1 行

### ✅ 验证

- `tests/test_p1_smoke.py`:**14/14 通过**(P1-1 staleness tuple / P1-2 跳源 / P1-3 Mavis .env)
- `tests/test_fenxing.py`:**8/8 通过**(P2 函数名修正)
- P0 + P1 + P2 行为无回归

---

## v0.6.0 (2026-06-24) — westock-data 整合 + 5 wrapper + router

**核心改动**:把 v0.5.x 单一的 `data_fetcher.py` 重构为 `src/data_layer/` 包,新增 5 个 wrapper + 数据契约 + 可靠性基础设施 + 按 market 降级的 router。westock-data 解决港美股数据断连痛点。

### ✨ 新增

- `src/data_layer/` 包:5 个数据源 wrapper
  - [`westock_wrapper.py`](src/data_layer/westock_wrapper.py) — `npx -y westock-data-skillhub@1.0.3`,腾讯自选股 API(免 Token,跨 A/HK/US/指数/板块/ETF)
  - [`akshare_wrapper.py`](src/data_layer/akshare_wrapper.py) — akshare 1.18+,A 股 K 线主源
  - [`qveris_wrapper.py`](src/data_layer/qveris_wrapper.py) — qveris.ai 实时价 + 财经新闻(L2)
  - [`tavily_wrapper.py`](src/data_layer/tavily_wrapper.py) — tavily 兜底搜索(L3)
  - [`agent_browser.py`](src/data_layer/agent_browser.py) — agent-browser 终极兜底(L4)
- [`src/data_layer/contracts.py`](src/data_layer/contracts.py) — `KlineRow` / `QuoteResult` / `FinanceRow` / `NewsItem`(frozen=True,含 `currency` 必填 CNY/HKD/USD)
- [`src/data_layer/reliability.py`](src/data_layer/reliability.py) — `with_retry`(指数退避) / `CircuitBreaker`(5min 熔断) / SQLite 当日缓存 + `WestockError` 映射
- [`src/data_layer/router.py`](src/data_layer/router.py) — `route_kline` / `route_quote` / `route_news`,按 market 5 级降级编排
- [`check_environment.py`](src/check_environment.py) 加 westock Node/npx/package 检查

### 🔧 降级链

| 数据类型 | 整合后降级链 |
|---|---|
| A 股 K 线 | akshare → westock → qveris → tavily → agent-browser |
| 港/美 K 线 | **westock** → akshare → qveris → tavily → agent-browser |
| 报价(全) | **westock** → qveris → akshare → tavily → agent-browser |
| 公告/新闻 | westock → qveris → akshare → tavily → agent-browser |
| 财报/资金/技术 | westock 单源(其余不覆盖) |

### 🗑️ 清理

- 归档 `quant_detect.py` / `qveris_client.py` / `data_fetcher.py` / `nuwa_pipeline.py` 到 `archive/v0.5.x/`
- 删 `config/default.json`(运行时引导式询问)
- 删 Nuwa 三阶段信息获取流程章
- 删 `~/.openclaw/openclaw.json` 依赖(Mavis 替代)

### ⚠️ 不兼容改动

- API 入口从 `from chanzhongshuochan import run_nuwa_analysis` → `from src.main import analyze_symbol`
- 数据源从 `qveris.cn_financial_pro` / `qt.gtimg.cn` → westock/akshare/qveris/tavily/agent-browser
- skill 路径从 `~/.openclaw/skills/chanzhongshuochan/` → `~/.mavis/skills/chanzhongshuochan/`
- `westock` 数据可能滞后 1-2 周(v0.6.2 router 已加 staleness 检测)

---

## v0.5.1 (2026-06-23) — Nuwa 三阶段法落地

**核心改动**：把数据获取层从 `/tmp/chan_600703_daily.py` standalone 脚本下沉到 skill, 让所有 cron 任务都能复用 Nuwa 三阶段流水线。

### 新增文件

- **`src/data_fetcher.py`** — 5 个数据源 fetcher
  - `fetch_quote_qveris(symbol)` — qveris.cn_financial_pro 实时价 (Lane A 主源)
  - `fetch_quote_tx(symbol)` — qt.gtimg.cn 腾讯实时价 (Lane A 备源)
  - `fetch_klines_akshare(symbol, days)` — akshare 日 K, 腾讯优先/新浪 fallback (Lane D)
  - `fetch_news_tavily(query)` — tavily topic=finance 搜索 (Lane B L2)
  - `fetch_news_sina(symbol)` — 新浪 vip 公告时间线 (Lane B L1 一手)

- **`src/nuwa_pipeline.py`** — Nuwa 三阶段编排器
  - `fetch_nuwa_parallel()` — 阶段 1, 5 Lane 并行 (ThreadPoolExecutor)
  - `validate_nuwa()` — 阶段 2, 反向验证 + 跨源价格冲突检测 (差 > 1% 标 [CONFLICT:price])
  - `combine_news()` — 消息面合并去重 (按 tier + title)
  - `fetch_quant_signals()` — 量化痕迹派生 (Lane C)
  - `run_nuwa_analysis()` — **统一入口**, 三阶段串联

### 修改文件

- **`src/__init__.py`** — 导出 v0.5.1 新接口
  - 新增: `fetch_quote_qveris, fetch_quote_tx, fetch_klines_akshare, fetch_news_tavily, fetch_news_sina`
  - 新增: `fetch_nuwa_parallel, validate_nuwa, combine_news, fetch_quant_signals, run_nuwa_analysis`
  - 版本号: `0.2.0` → `0.5.1`

### 解决的核心问题

| 问题 | 之前 | 之后 |
|---|---|---|
| 数据获取层 | 在 `/tmp/chan_600703_daily.py` 651 行里, 跟 skill 分离 | 在 skill 内, 任何调用方都能 import |
| 跨源验证 | 没有, 单源 fallback | 跨源价格对比, 差异 > 1% 显式 flag |
| 消息面 Nuwa 整合 | 委托给 search-anything subagent (5-15s 启动开销) | skill 内部多源抓取 (< 1s) |
| 信息溯源 | 简单 "数据源: X" | `{source, tier, time, confidence}` 全标注 |
| 复用方式 | 复制 651 行脚本改股票名 | `run_nuwa_analysis('sh000001', '平安银行')` 一行 |

### 不兼容改动

- 之前 standalone 脚本里直接 import 的内部函数 (fetch_quote_qveris 等) 现在在 skill 公共 API, **建议改用 `from chanzhongshuochan import ...`**
- standalone 脚本现在是 thin wrapper (242 行), 只做"格式化输出"

---

## v0.5.0 (2026-06-22) — Nuwa 设计文档

- SKILL.md 加入 Nuwa 三阶段法章节
- 新增 `references/nuwa-finance-workflow.md` (设计文档)
- 提案把 Nuwa 多智能体调研机制套用到金融数据获取

---

## v0.4.0 (2026-06-22) — 数据源调整

- 加 qveris.cn_financial_pro 实时价通道
- 修正 alphafeed/qveris 状态标注
- 沙箱白名单

---

## v0.3.0 (2026-06-14) — 行情补充

- 腾讯日K为主数据源
- 新浪期货/外盘期货/alphafeed 为行情补充
- akshare 集成

---

## v0.2.0 (2026-06-14) — 修复版

- 分型识别逻辑修复 (允许相邻 K 线高低点相等)
- 键名统一 (复数形式 fenxings/bis/zhongshus)
- 异常处理增强 + 输入验证 + 日志

---

## v0.1.0 (2026-06-13) — 初版

- 缠论核心模块: 分型/笔/中枢/背驰/买卖点
- 基于单股 K 线的全流程分析
