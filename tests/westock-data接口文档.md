# 腾讯自选股数据接口（westock-data）技术文档

> 本文档供 AI Agent 接入股票数据功能时参考
> 数据源：腾讯财经 / 腾讯自选股行情接口
> 调用方式：`npx westock-data-skillhub@1.0.3 <command> <args>`

---

## 一、接口调用方式

### 1.1 环境要求

- **运行时**：Node.js >= v18
- **调用方式**：`npx -y westock-data-skillhub@1.0.3 <命令> [参数]`
- **是否需要 Token**：❌ 完全不需要，无需注册账号
- **是否免费**：✅ 完全免费

### 1.2 调用格式

```bash
# 基本格式
npx -y westock-data-skillhub@1.0.3 <command> <code> [options]

# 参数格式
--period day|week|month|season|year  # K线周期
--limit N                              # 返回条数
--num N                                # 期数（财报等）
--start YYYY-MM-DD                     # 开始日期
--end YYYY-MM-DD                       # 结束日期
--fq qfq|hfq|bfq                      # 复权类型
```

### 1.3 股票代码格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 沪市 / 科创板 | `sh` + 6位数字 | `sh600519`（茅台）、`sh688981`（中芯） |
| 深市 | `sz` + 6位数字 | `sz000001`（平安银行）、`sz002714`（牧原） |
| 北交所 | `bj` + 6位数字 | `bj430047` |
| 港股 | `hk` + 5位数字 | `hk00700`（腾讯控股）、`hk03690`（美团） |
| 美股 | `us` + 代码 | `usAAPL`（苹果）、`usTSLA`（特斯拉） |
| 上证指数 | `sh` + 6位 `0` | `sh000001` |
| 板块 | `pt` + 板块ID | `pt01801081`（半导体） |

---

## 二、全部命令速查

| 命令 | 用途 | 批量 | 支持市场 |
|------|------|:----:|---------|
| `search` | 搜索股票/基金/板块名称 | ❌ | A股+港股+美股 |
| `quote` | 实时行情（价格/涨跌幅/PE/市值等） | ✅ | A股+港股+美股+指数+板块 |
| `kline` | K线数据（日/周/月/季/年） | ✅ | 个股+指数+板块+ETF |
| `minute` | 分时数据 | ❌ | 个股+指数+板块 |
| `finance` | 三大财务报表 | ✅ | A股+港股+美股 |
| `profile` | 公司简况 | ✅ | A股+港股+美股 |
| `asfund` | A股资金流向 | ✅ | 仅沪深 |
| `hkfund` | 港股资金流向 | ✅ | 仅港股 |
| `usfund` | 美股卖空数据 | ✅ | 仅美股 |
| `lhb` | 龙虎榜 | ✅ | 仅沪深 |
| `blocktrade` | 大宗交易 | ✅ | 仅沪深 |
| `margintrade` | 融资融券 | ✅ | 仅沪深 |
| `technical` | 技术指标 | ✅ | A股+港股+美股 |
| `chip` | 筹码成本 | ✅ | 仅沪深京A股 |
| `shareholder` | 股东结构 | ✅ | A股+港股 |
| `dividend` | 分红数据 | ✅ | A股+港股+美股 |
| `etf` | ETF详情 | ✅ | 仅A股ETF |
| `etf-holdings` | ETF持仓明细 | ✅ | 仅A股ETF |
| `etf-nav` | ETF净值历史 | ✅ | 仅A股ETF |
| `hot` | 热搜股票/ETF/板块 | ❌ | A股 |
| `board` | 板块行情 | ❌ | A股 |
| `calendar` | 投资日历 | ❌ | A股+港股+美股 |
| `ipo` | 新股日历 | ❌ | 沪深/港股/美股 |
| `exdiv` | 分红除权日历 | ✅ | A股+港股+美股 |
| `reserve` | 业绩预告 | ✅ | A股+港股+美股 |
| `suspension` | 停复牌信息 | ❌ | 仅沪深 |

---

## 三、各命令详解与返回字段

### 3.1 search — 股票搜索

```bash
npx -y westock-data-skillhub@1.0.3 search 腾讯控股
npx -y westock-data-skillhub@1.0.3 search 半导体 --sector    # 搜索板块
```

返回：代码、名称、类型（GP-A / GP-HK / GP-US 等）

> ⚠️ 不支持批量搜索

---

### 3.2 quote — 实时行情

```bash
npx -y westock-data-skillhub@1.0.3 quote sh600519
npx -y westock-data-skillhub@1.0.3 quote sh600519,sz000001,hk00700,usAAPL  # 批量
npx -y westock-data-skillhub@1.0.3 quote sh000001,sz399001    # 指数行情
```

返回字段：最新价、涨跌额、涨跌幅、今开、昨收、最高、最低、成交量、成交额、换手率、市盈率、市值等

> ⚠️ 批量查询会返回每个股票独立表格

---

### 3.3 kline — K线数据

```bash
npx -y westock-data-skillhub@1.0.3 kline sh600519 --period day --limit 20
npx -y westock-data-skillhub@1.0.3 kline hk00700 --period week --limit 10
npx -y westock-data-skillhub@1.0.3 kline sz000001 --period day --limit 60 --fq qfq   # 前复权
npx -y westock-data-skillhub@1.0.3 kline sh000001 --period day --limit 20           # 指数K线
npx -y westock-data-skillhub@1.0.3 kline pt01801081 --period day --limit 5          # 板块K线
npx -y westock-data-skillhub@1.0.3 kline sh600000,sh600519 --period day --limit 20  # 批量
```

返回字段：`date | open | last | high | low | volume | amount | exchange`

- **周期**：`day` / `week` / `month` / `season` / `year`
  - ⚠️ 分钟K线不支持，请用 `minute` 命令
- **复权**：默认前复权，可选 `qfq`（前复权）、`hfq`（后复权）、`bfq`（不复权）
- **最大条数**：2000条

---

### 3.4 minute — 分时数据

```bash
npx -y westock-data-skillhub@1.0.3 minute sh600519        # 1日分时
npx -y westock-data-skillhub@1.0.3 minute sh600519 --days 5  # 5日分时
npx -y westock-data-skillhub@1.0.3 minute sh000001          # 指数分时
npx -y westock-data-skillhub@1.0.3 minute pt01801081       # 板块分时
```

> ⚠️ 不支持批量查询

---

### 3.5 finance — 财务报表

```bash
# A股
npx -y westock-data-skillhub@1.0.3 finance sh600519           # 完整财报，最新1期
npx -y westock-data-skillhub@1.0.3 finance sh600519 --num 4  # 最近4期
npx -y westock-data-skillhub@1.0.3 finance sh600519 --type lrb --num 8  # 利润表8期

# 港股
npx -y westock-data-skillhub@1.0.3 finance hk00700 --num 4

# 美股
npx -y westock-data-skillhub@1.0.3 finance usBABA --type income --num 4
```

报表类型：
- **A股**：`lrb`（利润表）、`zcfz`（资产负债表）、`xjll`（现金流量表），默认返回全部
- **港股**：`zhsy`（综合损益表）、`zcfz`、`xjll`
- **美股**：`income`、`balance`、`cashflow`

> ⚠️ **货币单位**：港股返回港元/美元，美股返回美元，**展示时必须标注正确货币单位**，禁止使用人民币符号

返回字段示例（利润表）：`_date | BasicEPS | DilutedEPS | EndDate | GrossProfitTTM | NPParentCompanyOwners | OperatingRevenue | TotalProfit | ...`

---

### 3.6 profile — 公司简况

```bash
npx -y westock-data-skillhub@1.0.3 profile sh600519
npx -y westock-data-skillhub@1.0.3 profile sh600519,hk00700,usAAPL  # 批量
```

---

### 3.7 技术指标（technical）

```bash
npx -y westock-data-skillhub@1.0.3 technical sh600519                              # 全部指标（最新）
npx -y westock-data-skillhub@1.0.3 technical sh600519 --group macd                  # MACD
npx -y westock-data-skillhub@1.0.3 technical sh600519 --group ma,rsi                # 均线+RSI
npx -y westock-data-skillhub@1.0.3 technical sh600519,hk00700 --group all            # 批量
npx -y westock-data-skillhub@1.0.3 technical sh600519 --group macd --start 2026-02-01 --end 2026-03-01  # 历史区间
```

**指标分组**：
- `ma` — 均线（MA5/10/20/30/60/120/250、EMA12/26/50）
- `macd` — DIF / DEA / MACD 柱
- `kdj` — K / D / J
- `rsi` — RSI_2 / RSI_6 / RSI_12 / RSI_24
- `boll` — 布林带上轨 / 中轨 / 下轨
- `bias` — 乖离率 BIAS_6 / 12 / 24
- `wr` — 威廉指标 WR_6 / WR_10
- `dmi` — SAR / PDI / MDI / ADX / ADXR
- `all` — 全部指标

返回格式：字段展平为 `分组.字段名`（如 `macd.DIF`、`rsi.RSI_6`）

---

### 3.8 筹码成本（chip）

```bash
npx -y westock-data-skillhub@1.0.3 chip sh600519
npx -y westock-data-skillhub@1.0.3 chip sh600519 --start 2026-02-01 --end 2026-03-01  # 历史区间
```

返回字段：`code | name | date | closePrice | chipProfitRate | chipAvgCost | chipConcentration90 | chipConcentration70`

- `chipProfitRate`：盈利率（>80% = 获利盘占优）
- `chipAvgCost`：平均成本
- `chipConcentration90/70`：集中度（越低 = 筹码越集中，主力控盘可能）

> ⚠️ 仅支持沪深京A股（`sh` / `sz` / `bj`）

---

### 3.9 资金流向

**A股资金**（`asfund`）：
```bash
npx -y westock-data-skillhub@1.0.3 asfund sh600519
npx -y westock-data-skillhub@1.0.3 asfund sh600519,sz000001 --date 2026-06-10  # 批量
```
返回字段：`MainNetFlow`（主力净流入，元）、`JumboNetFlow`（超大单）、`BlockNetFlow`（大单）、`MidNetFlow`（中单）、`SmallNetFlow`（小单）、`LgtHoldInfo`（北向资金）

**港股资金**（`hkfund`）：
```bash
npx -y westock-data-skillhub@1.0.3 hkfund hk00700
npx -y westock-data-skillhub@1.0.3 hkfund hk00700 --date 2026-03-10
```
返回字段：`TotalNetFlow`（总净流入，港元）、`MainNetFlow`（主力净流入）、`RetailNetFlow`（散户净流入）、`ShortRatio`（卖空比例）、`LgtHoldInfo`（南下资金）

**美股卖空**（`usfund`）：
```bash
npx -y westock-data-skillhub@1.0.3 usfund usAAPL
npx -y westock-data-skillhub@1.0.3 usfund usAAPL,usTSLA --date 2026-03-10
```
返回字段：`ShortRatio`（卖空比例 %）、`ShortShares`（卖空股数）、`ShortRecoverDays`（回补天数）

---

### 3.10 龙虎榜 / 大宗交易 / 融资融券

```bash
npx -y westock-data-skillhub@1.0.3 lhb sz000001             # 龙虎榜
npx -y westock-data-skillhub@1.0.3 lhb sz000001 --date 2026-03-20
npx -y westock-data-skillhub@1.0.3 blocktrade sz000001      # 大宗交易
npx -y westock-data-skillhub@1.0.3 margintrade sz000001     # 融资融券
```

> ⚠️ 仅支持沪深市场

---

### 3.11 股东结构（shareholder）

```bash
npx -y westock-data-skillhub@1.0.3 shareholder sh600519  # A股
npx -y westock-data-skillhub@1.0.3 shareholder hk00700   # 港股
```

返回：
- A股：`top10Shareholders`（十大股东）、`top10FloatShareholders`（十大流通股东）、`shareholderNum`（股东户数/环比/户均持股）
- 港股：`shareholderInfo`（主要股东持股）、`shareholderDist`（股东分布）、`instHoldingStats`（机构持仓统计）

> ⚠️ 仅支持A股和港股

---

### 3.12 分红数据（dividend）

```bash
npx -y westock-data-skillhub@1.0.3 dividend sh600519                     # 最近分红
npx -y westock-data-skillhub@1.0.3 dividend sh600519 --years 5           # 近5年
npx -y westock-data-skillhub@1.0.3 dividend sh600519 --all               # 含未实施分红
npx -y westock-data-skillhub@1.0.3 dividend sh600519,hk00700,usAAPL     # 批量
npx -y westock-data-skillhub@1.0.3 dividend hk00700 --years 10
```

返回字段（因市场不同）：
- **A股**：`reportEndDate | dividendFlag | procedure | dividendType | rightRegDate | exDiviDate | bonusShareRatio | cashDiviRMB | ...`
- **港股**：`reportEndDate | exDiviDate | cashPayDate | cashDivPerShare | totalCashDivi | ...`
- **美股**：`exDivDate | regDate | payDate | dividend | dividendPlan`

---

### 3.13 ETF 数据

```bash
npx -y westock-data-skillhub@1.0.3 etf sh510300                  # ETF详情
npx -y westock-data-skillhub@1.0.3 etf-holdings sh510300        # 持仓明细
npx -y westock-data-skillhub@1.0.3 etf-nav sh510300 --start 2026-01-01 --end 2026-03-31  # 净值历史
npx -y westock-data-skillhub@1.0.3 etf-company sh510300         # 公司信息
npx -y westock-data-skillhub@1.0.3 etf-holders sh510300          # 持有人结构
npx -y westock-data-skillhub@1.0.3 etf-financial sh510300        # 财务指标
```

---

### 3.14 市场热度 / 板块

```bash
npx -y westock-data-skillhub@1.0.3 hot stock          # 热搜股票
npx -y westock-data-skillhub@1.0.3 hot board --limit 10  # 热门板块
npx -y westock-data-skillhub@1.0.3 hot etf            # 热搜ETF
npx -y westock-data-skillhub@1.0.3 board              # 板块行情首页
```

返回：`index | level | symbol | rank | rankdelta | date | stock_type | name | zdf | zxj`

---

### 3.15 投资日历 / 新股 / 停复牌

```bash
# 投资日历
npx -y westock-data-skillhub@1.0.3 calendar                           # 查看有事件的日期
npx -y westock-data-skillhub@1.0.3 calendar 2026-06-10 --limit 30    # 指定日期详情
npx -y westock-data-skillhub@1.0.3 calendar 2026-06-10 --country 1 --indicator 1  # 仅中国经济数据

# 新股
npx -y westock-data-skillhub@1.0.3 ipo hs     # 沪深新股
npx -y westock-data-skillhub@1.0.3 ipo hk     # 港股新股
npx -y westock-data-skillhub@1.0.3 ipo us     # 美股新股

# 分红除权日历
npx -y westock-data-skillhub@1.0.3 exdiv sh600519

# 业绩预告
npx -y westock-data-skillhub@1.0.3 reserve sh600519

# 停复牌
npx -y westock-data-skillhub@1.0.3 suspension hs
```

---

## 四、能力边界与已知限制

| 限制项 | 说明 |
|--------|------|
| **龙虎榜** | 仅支持沪深市场（`sh` / `sz`） |
| **大宗交易** | 仅支持沪深市场 |
| **融资融券** | 仅支持沪深市场 |
| **筹码成本** | 仅支持沪深京A股（`sh` / `sz` / `bj`） |
| **股东结构** | 仅支持A股和港股 |
| **搜索和分时** | 不支持批量查询 |
| **K线** | 分钟级别不支持，需用 `minute` |
| **复权** | 默认前复权，需指定 `--fq` 参数切换 |
| **K线最大条数** | 2000条 |
| **港股/美股金额** | 返回港元/美元，**展示时必须标注货币单位**，禁止用人民币符号 |
| **频次限制** | 无公开明确限制，但过多请求可能触发腾讯侧风控 |
| **接口稳定性** | 腾讯接口可能被动变更，无 SLA 保证 |

---

## 五、输出格式规范

1. **所有查询命令**输出 Markdown 表格，AI 直接从表格读取数据
2. **查询结果应转为表格展示**，禁止直接输出原始 JSON
3. **不创建临时脚本文件**，不将数据分析逻辑写成独立脚本
4. **金额换算**：
   - 成交量：手 → ÷10000 = 万手
   - 成交额/市值：元 → ÷1亿 = 亿元
   - 港股金额：港元 → ÷1亿 = 亿港元
   - 美股金额：美元 → ÷1亿 = 亿美元
   - 卖空数量：股 → ÷100万 = 百万股
5. **数据为空时**说明"暂无数据"，**不可伪造数据**

---

## 六、货币单位处理（重要）

> ⚠️ 港股财报返回港元/美元，美股返回美元，展示时**必须标注正确货币单位**

| 市场 | 货币 | 正确示例 | 错误示例 |
|------|------|---------|---------|
| A股 | 人民币（元） | 营业收入：832.3亿元 | 营业收入：832.3亿美元 |
| 港股 | 港元或美元 | 营业收入：832.3亿港元 | 营业收入：832.3亿元 |
| 美股 | 美元 | 营业收入：832.3亿美元 | 营业收入：832.3亿元 |

---

## 七、典型调用流程示例

### 示例 1：分析茅台近期走势

```bash
# 1. 搜索股票代码
npx -y westock-data-skillhub@1.0.3 search 贵州茅台
→ sh600519

# 2. 查看K线
npx -y westock-data-skillhub@1.0.3 kline sh600519 --period day --limit 20

# 3. 查看技术指标
npx -y westock-data-skillhub@1.0.3 technical sh600519 --group macd,rsi,boll

# 4. 查看筹码
npx -y westock-data-skillhub@1.0.3 chip sh600519

# 5. 查看资金流向
npx -y westock-data-skillhub@1.0.3 asfund sh600519
```

### 示例 2：跨市场对比腾讯和苹果

```bash
# 搜索
npx -y westock-data-skillhub@1.0.3 search 腾讯控股   → hk00700
npx -y westock-data-skillhub@1.0.3 search 苹果       → usAAPL

# 批量K线
npx -y westock-data-skillhub@1.0.3 kline hk00700,usAAPL --period day --limit 30

# 批量财报
npx -y westock-data-skillhub@1.0.3 finance hk00700,usAAPL --num 4

# 批量分红
npx -y westock-data-skillhub@1.0.3 dividend hk00700,usAAPL --years 3
```

### 示例 3：板块资金分析

```bash
# 搜索板块
npx -y westock-data-skillhub@1.0.3 search 半导体 --sector
→ pt01801081

# 查看板块行情
npx -y westock-data-skillhub@1.0.3 quote pt01801081

# 查看热门板块排行
npx -y westock-data-skillhub@1.0.3 hot board --limit 10
```

---

## 八、与其他数据接口的对比

| 对比维度 | westock-data（腾讯） | Tushare Pro |
|---------|-------------------|-------------|
| **Token** | ❌ 不需要 | ✅ 需要（积分制） |
| **费用** | 完全免费 | 部分免费，深度数据需付费 |
| **数据源** | 腾讯财经 | 交易所授权数据商 |
| **实时性** | 准实时，免费 | 日线T+1；实时需付费 |
| **A股基本面** | ✅ 有 | ✅ 深度（需积分） |
| **港股数据** | ✅ 日线/资金/股东 | ❌ 需单独付费 |
| **美股数据** | ✅ 日线/资金/财报 | ❌ 需单独付费 |
| **分钟数据** | ✅ 分时免费，K线分钟不支持 | ❌ 需付费 |
| **稳定性** | 依赖腾讯接口，无SLA | 官方维护，100+服务器 |
| **适用场景** | 盘中快速查询、跨市场对比 | 量化回测、深度财务分析 |
