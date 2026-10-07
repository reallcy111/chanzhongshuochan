---
name: chanzhongshuochan
description: 缠中说禅技术分析技能,基于缠论自动识别分型笔中枢背驰买卖点,跨 A 股港股美股。触发词:缠中说禅、缠论、中枢、背驰、买卖点、技术分析、Chan theory。
---

# 缠中说禅 chanzhongshuochan Mavis Skill 调用指南

v0.6.3 westock-data 整合 + 5 wrapper + 5 级降级链
安装路径: `<你的 skills 目录>/chanzhongshuochan/`
  (Mavis 默认 `~/.minimax/skills/chanzhongshuochan/`;若你的宿主用 `.mavis` 目录,取实际生效的那份)
Python 包 + Skill hybrid

## 何时触发

- 分析 XXX 股票 缠论 技术形态 买卖点
- 看 XXX 是不是中枢 背驰 笔
- 用缠中说禅分析
- 缠论分析 加 量化共振

## 怎么调用

Skill 本身是 Python 包,不是 Mavis 工具函数。Mavis agent 加载本 SKILL.md 后,按下面方式帮用户调用。

### 方式 1: Mavis 跑 Python 端到端分析,推荐

```bash
cd <SKILL_DIR>   # 换成你实际的技能安装目录
python -c "from src.main import analyze_symbol; r = analyze_symbol('sh600519', days=500); print(r['status']); print('当前:', r['kline_latest']['date'], r['kline_latest']['close']); print('缠论:', r['fenxing_count'], r['bi_count'], r['zhongshu_count'], r['maimaidian_count'])"
```
⚠️ **days 必须给 500,不要用默认 120**。120 根通常只够识别出 2 笔,
笔结构残缺、中枢和背驰全识别不出来(2026-10-07 688411 实测:120 根→2 笔;500 根→9 笔 1 中枢 1 背驰)。

### 方式 2: 单模块调用

⚠️ **除非方式 1 拿不到某个字段,否则不要手搓底层**。自己串模块漏掉 `simplify_klines`
会得出与 `analyze_symbol` **完全相反**的结论(2026-10-07 688411 实测:
124 有效分型→55、9 笔→10、**1 个背驰→0 个**、一类买点凭空消失)。
`simplify_klines` 做的是缠论标准的「K 线包含关系合并」,是必需步骤,默认 `initial_trend='up'`。

正确顺序(与 `src/main.py:analyze_symbol` 一致):
route_kline → simplify_klines → identify_fenxing(simplified) → filter_valid_fenxing
→ identify_bis(fx, df) → validate_bis → identify_zhongshu → calculate_macd
→ detect_all_trend_beichis(bis, macd_df) → identify_buy_sell_points

易踩的签名(传错会静默返回空结果,不报错):
- `identify_bis(fenxing_list, klines, min_amplitude=0.5, min_klines=5)` — klines 必传
- `detect_all_trend_beichis(bis, macd_df, min_bi_count=2)` — 第二个是 MACD DataFrame
- `calculate_macd()` 返回 DataFrame;`result['macd_stats']` 恒为 `{}` 属正常
  (DataFrame 自带 `.get()`,没有 statistics 列就返回默认值),不是报错
- `analyze_symbol` **不返回 kline_df**,要 K 线明细必须自己 `route_kline(sym, days=500)`
- 中枢明细同理:`analyze_symbol` 只给 `zhongshu_count`,要 zg/zd 需自行调
  `identify_zhongshu(bis)` 并取 `.bi_indices / .zg / .zd`

```python
import sys, os
sys.path.insert(0, os.environ.get('SKILL_DIR', os.getcwd()))  # 换成你的技能安装目录
from src import (simplify_klines, identify_fenxing, filter_valid_fenxing,
                 identify_bis, validate_bis, identify_zhongshu,
                 calculate_macd, detect_all_trend_beichis, identify_buy_sell_points)
from src.data_layer import route_kline

df, _ = route_kline('sh688411', days=500)          # days 必须是 500
simp = simplify_klines(df, initial_trend='up')      # ← 漏这步结论全错
fx = filter_valid_fenxing(identify_fenxing(simp))   # ← 传 simp 不是 df
bis = validate_bis(identify_bis(fx, df))
zs = identify_zhongshu(bis)
macd = calculate_macd(df)
bc = detect_all_trend_beichis(bis, macd)            # ← 不是 (df, bis, zs)
ms = identify_buy_sell_points(bis, zs, bc) or []
```

## 关键事实

- 当前价 不等于 recent_fenxing: 永远从 result kline_latest 拿当前位置,不要用 recent_fenxing 末尾
- 30天区间: 从 result kline_range_30d 拿
- K 线数据源: akshare / westock 自动 5 级降级
- 报价数据源: 默认 westock, v0.6 主行情源
- 依赖: Python 3.13 + Node.js 24 + akshare / numpy / pandas / mplfinance / tavily-python
- API key: QVERIS_API_KEY / TAVILY_API_KEY 为**可选**,用于联网搜索补数据。
  未配置时自动降级到本地数据源,不影响主流程。配置方式见 `.env.example`。

## 强制出图规范

每次分析完成后,**必须输出 mplfinance K 线图**,不允许用 ASCII / Unicode 字符画替代。

### 调用方式

```python
from src.plot_kline import draw_chanzhongshuochan_chart
path = draw_chanzhongshuochan_chart('sh688820', days=500)
# 返回 PNG 绝对路径,直接用 <media src=...> 交付给用户
```

或 CLI:

```bash
python -m src.plot_kline sh688820 500
```

### 硬性要求(用户明确指定)

1. **中文不乱码**:`matplotlib` 必须在 `import mplfinance` **之前**设
   `plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']`
   且 `plt.rcParams['axes.unicode_minus'] = False`。
   `style` 的 `rc` 参数也要传同配置(否则 mplfinance 内部 axes 不继承)。

2. **关键水平位虚线必须明显**:`axhline` 必须用 `linestyle='--'` + `linewidth>=1.5`,
   推荐 `dashes=(6, 4)`,`alpha=0.85`,右侧配 `bbox` 文字标签。
   **关键位语义固定**:
   - 前高 = K线 High 最大值
   - 最近一笔的两端(start_price + end_price)
   - 上一个反向笔的终点
   - 最多 4 条,标签含笔号+顶/底+价格(如 "笔3顶 213.35")

3. **成交额不可信,必须外部兜底**:akshare 科创板 `Volume` 恒为 0 已是已知问题,
   **但 `Amount` 同样失真**——内置的 `Amount/1e8` 兜底会产出错误数量级的数字
   (2026-10-07 688411 实测:图上成交额峰值 0.150 亿元,真实峰值(2026-03-11)约 40.5 亿元,
   低估约 270 倍;2026-09-30 图上 0.0215 亿 vs 真实 3.3879 亿,低估约 158 倍)。
   **要做量能/成交额分析,改用东方财富 `push2his` 的 f57 字段**:
   `https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.688411&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=400`
   第 7 列(f57)是成交额,除以 1e8 得亿元,按日期与 akshare 的 OHLC 合并。
   两源收盘价可对齐,已验证。⚠️ 该接口对 urllib 会限流,取数用 PowerShell `Invoke-RestMethod`
   并落盘缓存,不要在绘图脚本里循环重试。

4. **分型标记**:顶分型 `marker='v'` 红、底分型 `marker='^'` 绿,
   `markersize>=140`,通过 `addplot` 叠加。

5. **输出文件命名**:`{symbol}_kline.png`。默认落在宿主注入的 workspace 目录
   (环境变量 `MAVIS_WORKSPACE`);未设置时退回**当前工作目录**。
   想指定别处:`os.environ['MAVIS_WORKSPACE'] = <目标目录>` 或直接传 `out_path=`。

## 已知限制(出图前先看)

- **不画中枢**:`draw_chanzhongshuochan_chart` 只画关键水平位,中枢 zg/zd 完全不出现在图上。
  交付前若结论涉及中枢,必须自行 `identify_zhongshu` 取值并补 `axhspan`。
- **只画最近 5 个分型标记**,不画完整笔连线。结构叙事要靠 `recent_bi` / 底层重算。
- **成交额错**(见硬性要求 3),量能结论不能直接引用这张图。
- 需要完整结构图时,建议自行用 matplotlib 重绘:OHLC 取 akshare、成交额取东财、
  笔连线 + 中枢带 + 买卖点标注一并画出。

## 故障排查

跑 python -m src.check_environment full 看环境状态 应输出 READY

## 注意事项

本技能仅提供技术分析,不构成投资建议。市场有风险,投资需谨慎。
