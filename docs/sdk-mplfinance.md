# mplfinance SDK 标准调用规范

> 来源：Context7 /matplotlib/mplfinance（2026-06-23 验证）
> 用途：缠中说禅 skill 报告生成（走势图，含分型/笔/中枢/买卖点标注）

## 安装

```bash
pip install mplfinance
# 依赖: matplotlib, pandas, numpy
```

## 基础 K 线图

```python
import mplfinance as mpf
import pandas as pd

# df 列: date, open, high, low, close, volume
df = pd.read_csv("klines.csv", parse_dates=["date"], index_col="date")
df = df[["open", "high", "low", "close", "volume"]]  # 必须按这个顺序

mpf.plot(
    df,
    type="candle",      # "candle" | "ohlc" | "line" | "renko" | "pnf"
    style="charles",    # "charles" | "yahoo" | "binance" | ... 内置样式
    title="缠论走势图",
    ylabel="价格",
    volume=True,        # 是否画成交量
    figsize=(16, 9),
    savefig="chart.png", # 或 "chart.svg"
)
```

## 自定义 Marker（关键：分型/买卖点标注）

```python
# 准备分型/买卖点的 y 坐标和 marker
fenxing_indices = [...]   # 在 df 中的 index
fenxing_prices = [...]    # 对应价格
markers = ['$T$' if is_top else '$B$' for is_top in is_top_list]
colors = ['red' if is_top else 'green' for is_top in is_top_list]

# 用 make_addplot 创建 addplot 层
ap = mpf.make_addplot(
    fenxing_prices,
    type="scatter",
    marker=markers,            # 支持 LaTeX '$...$'、字母 'D'、符号 'v' '^' 等
    markersize=200,
    color=colors,
)

# 叠加到主图
mpf.plot(df, type="candle", addplot=ap)
```

## 多层 addplot（笔/中枢/买卖点）

```python
# 笔：折线
bi_y = [...]   # 笔端点价格
bi_x = [...]   # 笔端点 index

# 中枢：矩形阴影（mplfinance 通过 fill_between 实现）
zs_high = [...]  # 中枢上沿
zs_low = [...]   # 中枢下沿

# 买卖点：1/2/3 类用不同颜色
buy_points_1 = [...]  # 1 类买点价格
buy_points_2 = [...]
buy_points_3 = [...]

ap_bi = mpf.make_addplot(bi_y, type="line", color="blue", linewidth=1.5)
ap_buy1 = mpf.make_addplot(buy_points_1, type="scatter", marker='$1$', markersize=300, color="lime")
ap_buy2 = mpf.make_addplot(buy_points_2, type="scatter", marker='$2$', markersize=300, color="cyan")
ap_buy3 = mpf.make_addplot(buy_points_3, type="scatter", marker='$3$', markersize=300, color="magenta")

mpf.plot(
    df,
    type="candle",
    addplot=[ap_bi, ap_buy1, ap_buy2, ap_buy3],
    fill_between=dict(y1=zs_low, y2=zs_high, color="gray", alpha=0.2),
)
```

## 中文字体

```python
import matplotlib.pyplot as plt

# macOS
plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB"]
# Windows
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
# Linux
plt.rcParams["font.sans-serif"] = ["WenQuanYi Micro Hei", "Noto Sans CJK SC"]
plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题
```

**注意**：mplfinance 使用 matplotlib 字体系统，必须在 import 后立即设字体。

## 手动添加图层（高级）

```python
# 拿到 figure 和 axes 自行操作
fig, axlist = mpf.plot(df, type="candle", returnfig=True)
ax = axlist[0]  # 主图
ax.scatter(x, y, s=200, marker="D", color="red")
# axlist[1] 是成交量图（如果 volume=True）
mpf.show()
```

## 输出到文件

```python
mpf.plot(
    df,
    type="candle",
    savefig=dict(fname="chart.png", dpi=150, bbox_inches="tight"),
)
# 或
mpf.plot(df, type="candle", savefig="chart.png")
```

## 已知陷阱

1. **DataFrame 列必须按 `open, high, low, close, volume` 顺序**，多余列会被忽略
2. **Index 必须是 DatetimeIndex**（不是字符串）
3. **marker 长度必须等于 df 行数**（或用 `None` 跳过）
4. **中文字体在每台机器上路径不同**，需运行时探测
5. **savefig 不支持交互**，如果想看效果先用 `mpf.show()` 再保存

## 内联测试

```python
if __name__ == '__main__':
    import pandas as pd
    import numpy as np

    # 构造示例数据
    dates = pd.date_range("2024-01-01", periods=60, freq="D")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(60))
    df = pd.DataFrame({
        "open": close + np.random.randn(60) * 0.5,
        "high": close + abs(np.random.randn(60)) * 0.5,
        "low":  close - abs(np.random.randn(60)) * 0.5,
        "close": close,
        "volume": np.random.randint(1000000, 5000000, 60),
    }, index=dates)

    ap = mpf.make_addplot(
        [df["high"].iloc[10]] * len(df),  # 简化：第 10 天高点点
        type="scatter", marker='$T$', markersize=200, color="red"
    )
    mpf.plot(df, type="candle", addplot=ap, savefig="test_chart.png")
    print("Saved test_chart.png")
```

## 在 OpenClaw skill 中输出到缓存目录

```python
from pathlib import Path
import os

CACHE_DIR = Path(os.environ.get("CHANZHONGSHUOCHAN_CACHE", "~/.cache/chanzhongshuochan/charts")).expanduser()
CACHE_DIR.mkdir(parents=True, exist_ok=True)

output_path = CACHE_DIR / f"{symbol}_{date}_{level}.png"
mpf.plot(df, type="candle", addplot=ap, savefig=str(output_path))
```
