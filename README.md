# 缠中说禅 · Chan Theory Skill

用**缠论**（缠中说禅理论）自动识别股票技术结构的 AI 技能包：自动算出**分型 → 笔 → 中枢 → 背驰 → 买卖点**，并出 K 线标注图。

支持 A 股 / 港股 / 美股。

```
输入: sh688411
输出: 9 笔 · 1 个中枢 · 1 处背驰 · 2 个买卖点  (+ 标注 K 线图)
```

---

## 这是什么

一个 **SKILL.md + Python 包**的混合技能：

- `SKILL.md` —— 给 AI 读的调用说明书（含大量踩坑记录，AI 照着做就不会错）
- `src/` —— 缠论计算内核，纯 Python 实现
- `tests/` —— 单元测试

换句话说：**它不是"让 AI 教你缠论"，而是"让 AI 调用一套跑通的缠论算法"。** AI 负责理解意图和解释结论，算法负责算数，两者不混在一起——这比让模型凭记忆口算分型可靠得多。

---

## 安装

### 1. 克隆到你的 skills 目录

```bash
# Mavis（默认）
git clone <this-repo> ~/.minimax/skills/chanzhongshuochan

# Claude Code
git clone <this-repo> ~/.claude/skills/chanzhongshuochan
```

### 2. 装依赖

```bash
pip install akshare numpy pandas mplfinance
# 可选，联网补数据用
pip install tavily-python
```

需要 Python 3.7+。行情源走 `npx westock-data`，还需 Node.js 18+。

### 3. 体检

```bash
cd <技能目录>
python -m src.check_environment full
```

输出 `READY` 即可用。

---

## 快速上手

### 当技能用（推荐）

跟 AI 说：

> 用缠论分析一下 sh688411

AI 会自动读 `SKILL.md` 并调用下面的代码。

### 当 Python 库用

```bash
cd <技能目录>
python -c "from src.main import analyze_symbol; r = analyze_symbol('sh688411', days=500); print(r['fenxing_count'], r['bi_count'], r['zhongshu_count'], r['maimaidian_count'])"
```

### 出图

```python
from src.plot_kline import draw_chanzhongshuochan_chart
path = draw_chanzhongshuochan_chart('sh688411', days=500)
```

PNG 默认落在 `MAVIS_WORKSPACE` 环境变量指向的目录，没设就存到当前目录。

---

## ⚠️ 三个必须知道的坑

**1. `days` 必须给 500，不要用默认 120。**
120 根 K 线通常只够识别出 2 笔，笔结构残缺，中枢和背驰全都识别不出来。实测同一只票：120 根 → 2 笔；500 根 → 9 笔 / 1 中枢 / 1 背驰。

**2. 不要手搓底层模块。**
直接调 `analyze_symbol()`。自己串底层模块如果漏掉 `simplify_klines`（缠论的「K 线包含关系合并」），会得出**完全相反**的结论——实测 124 个有效分型降到 55 个，9 笔变 10 笔，**1 个背驰凭空消失**，一类买点整个不见。

正确顺序：`route_kline → simplify_klines → identify_fenxing → identify_bis → identify_zhongshu → calculate_macd → detect_all_trend_beichis → identify_buy_sell_points`

**3. 图上的成交额不可信。**
akshare 在科创板上 `Volume` 恒为 0，`Amount` 同样失真（实测图上峰值 0.15 亿，真实约 40.5 亿，低估 270 倍）。
要做量能/成交额分析，改用东方财富 `push2his` 接口的 `f57` 字段。

---

## 已知限制

- 内置图表**不画中枢**（`zg`/`zd` 完全不出现），也只画最近 5 个分型标记，不画完整笔连线。要完整结构图请自行用 matplotlib 重绘。
- 纯技术分析，**不接基本面**。
- 不构成投资建议。

---

## 密钥

`.env.example` 里的两项 key 都是**可选**的，不配也能正常用。想开就复制成 `.env` 填值——`.env` 已在 `.gitignore` 里，不会被提交。

---

## 免责声明

本项目仅提供技术分析工具，**不构成任何投资建议**。市场有风险，投资需谨慎。