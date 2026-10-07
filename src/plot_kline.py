"""chanzhongshuochan 标准 K 线图模块 - 强制出图规范

要求:
1. 中文不乱码 (Microsoft YaHei / SimHei)
2. 关键位虚线 (前高 / 笔顶 / 笔底)
3. 分型点标记 (顶红 V / 底绿 ^)
4. 成交额自动兜底 (akshare 科创板 volume=0 时用 amount/1e8)
5. 保存为 PNG,返回绝对路径

调用:
    from src.plot_kline import draw_chanzhongshuochan_chart
    path = draw_chanzhongshuochan_chart('sh688820', days=120)
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 必须在 import mplfinance 之前设置
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

import mplfinance as mpf
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from src.data_layer import route_kline


def draw_chanzhongshuochan_chart(
    symbol: str,
    days: int = 120,
    out_path: str = None,
    fenxing_marks: list = None,
    key_levels: list = None,
    figsize: tuple = (14, 8),
    dpi: int = 130,
) -> str:
    """画 chanzhongshuochan 标准 K 线图(强制出图规范)

    Args:
        symbol: 股票代码(如 'sh688820')
        days: 回看天数
        out_path: 输出路径,默认 workspace 下 {symbol}_kline.png
        fenxing_marks: 分型标记 [(idx, 'top'|'bottom', price), ...]
        key_levels: 关键水平位 [(price, color, label), ...]
            默认: 前高 + 最近一笔两端 + 上一个反向笔终点(最多 4 条)
        figsize: 图大小
        dpi: 输出分辨率

    Returns:
        绝对路径
    """
    # 1) 取数据
    df, source = route_kline(symbol, days=days)

    df_idx = df.copy()
    df_idx['date'] = pd.to_datetime(df_idx['date'])
    df_idx = df_idx.set_index('date')
    df_idx = df_idx.rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
        'volume': 'Volume', 'amount': 'Amount',
    })
    # 只保留 OHLCV,mplfinance 不接受多余列(如 exchange)
    keep = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount'] if c in df_idx.columns]
    df_idx = df_idx[keep]

    # 2) Volume 兜底(akshare 科创板经常返回 0 或缺列)
    vol_label = '成交量'
    if 'Volume' not in df_idx.columns or df_idx['Volume'].fillna(0).sum() == 0:
        if 'Amount' in df_idx.columns:
            df_idx['Volume'] = (df_idx['Amount'] / 1e8).round(2)
            vol_label = '成交额 (亿元)'
        else:
            df_idx['Volume'] = 0

    # 3) 跑一次完整分析,拿分型和笔
    from src.main import analyze_symbol
    r = analyze_symbol(symbol, days=days)

    if fenxing_marks is None:
        fenxing_marks = [
            (fx['kline_index'], fx['type'], fx.get('high', fx.get('low', 0)))
            for fx in r.get('recent_fenxing', [])
            if fx.get('kline_index', -1) < len(df_idx)
        ]

    # 4) 默认关键水平位:从 recent_bi 提取缠论笔端点
    #    规范: 前高 + 最近一笔的两端 + 上一个反向笔终点(最多 4 条)
    if key_levels is None:
        bis = r.get('recent_bi', [])
        kline_high = float(df_idx['High'].max())

        levels = [(kline_high, '#1f77b4', f'前高 {kline_high:.2f}')]

        if bis:
            # recent_bi 只返回最近 5 笔,笔号必须按总笔数 bi_count 回推,
            # 否则总笔数>5 时会把 笔9 标成 笔5(2026-10-07 688411 实测)
            bi_total = int(r.get('bi_count') or len(bis))
            first_n = bi_total - len(bis) + 1
            last_bi = bis[-1]
            n = first_n + len(bis) - 1
            if last_bi['end_type'] == 'top':
                levels.append((last_bi['end_price'], '#9467bd',
                               f'笔{n}顶 {last_bi["end_price"]:.2f}'))
                levels.append((last_bi['start_price'], '#d62728',
                               f'笔{n}底 {last_bi["start_price"]:.2f}'))
            else:
                levels.append((last_bi['end_price'], '#d62728',
                               f'笔{n}底 {last_bi["end_price"]:.2f}'))
                levels.append((last_bi['start_price'], '#9467bd',
                               f'笔{n}顶 {last_bi["start_price"]:.2f}'))

            if len(bis) >= 2:
                prev = bis[-2]
                prev_n = n - 1
                prev_label = f'笔{prev_n}{"底" if prev["end_type"]=="bottom" else "顶"}'
                levels.append((prev['end_price'], '#ff7f0e',
                               f'{prev_label} {prev["end_price"]:.2f}'))

        key_levels = levels

    # 5) style(只画 K 线,不传 addplot — 分型点用主图 ax.scatter 标)
    mc = mpf.make_marketcolors(up='r', down='g', edge='inherit',
                               wick='inherit', volume='inherit')
    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle=':',
        gridcolor='#cccccc',
        gridaxis='both',
        rc={'font.family': 'sans-serif',
            'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans'],
            'axes.unicode_minus': False},
        figcolor='white',
    )

    # 6) 出图
    title = f'{symbol} 日K线 · 缠论分析 ({source}, {len(df)}根)'
    if out_path is None:
        # 优先用宿主会话注入的 workspace，其次退回当前工作目录。
        # 不要在此硬编码任何绝对路径，否则换机器/换用户会写到不存在的目录。
        workspace = os.environ.get('MAVIS_WORKSPACE') or os.getcwd()
        os.makedirs(workspace, exist_ok=True)
        out_path = os.path.join(workspace, f'{symbol}_kline.png')

    fig, axes = mpf.plot(
        df_idx,
        type='candle',
        style=style,
        volume=True,
        title=title,
        ylabel='价格 (元)',
        ylabel_lower=vol_label,
        figsize=figsize,
        tight_layout=True,
        returnfig=True,
    )
    ax_main = axes[0]

    # 7) 关键水平位 — 粗虚线 + 文字标签
    last_date = df_idx.index[-1]
    for price, color, label in key_levels:
        ax_main.axhline(price, color=color, linestyle='--', linewidth=1.6,
                        dashes=(6, 4), alpha=0.85, zorder=1)
        ax_main.annotate(
            f' {label}', xy=(last_date, price),
            xytext=(8, 0), textcoords='offset points',
            color=color, fontsize=9, fontweight='bold',
            va='center', ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='white',
                      ec=color, lw=0.8, alpha=0.85),
        )

    # 8) 分型点 — 用 ax.plot 标(mplfinance addplot 在 NaN 多时报错)
    #    注意:mplfinance 内部把 x 轴转成整数索引(0..N-1),不能用 Timestamp
    date_list = list(df_idx.index)
    for idx, typ, price in fenxing_marks:
        if 0 <= idx < len(date_list) and price:
            x = idx  # mplfinance 用整数索引
            color = 'red' if typ == 'top' else 'limegreen'
            marker = 'v' if typ == 'top' else '^'
            ax_main.plot(x, price, marker=marker, markersize=14,
                         color=color, markeredgecolor='black',
                         markeredgewidth=0.8, linestyle='None',
                         zorder=10)
            # 价格标注
            offset = 22 if typ == 'top' else -28
            ax_main.annotate(f'{price:.2f}', xy=(x, price),
                             xytext=(0, offset), textcoords='offset points',
                             ha='center', fontsize=8, color=color,
                             fontweight='bold', zorder=11,
                             bbox=dict(boxstyle='round,pad=0.15', fc='white',
                                       ec=color, lw=0.5, alpha=0.85))

    # 9) 图例
    legend_items = [
        Line2D([0], [0], marker='v', color='w', markerfacecolor='red',
               markersize=10, label='顶分型'),
        Line2D([0], [0], marker='^', color='w', markerfacecolor='limegreen',
               markersize=10, label='底分型'),
    ]
    for price, color, label in key_levels:
        legend_items.append(
            Line2D([0], [0], color=color, linestyle='--',
                   linewidth=1.6, label=label),
        )
    ax_main.legend(handles=legend_items, loc='upper left',
                   fontsize=8, framealpha=0.9)

    fig.savefig(out_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return os.path.abspath(out_path)


if __name__ == '__main__':
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else 'sh688820'
    d = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    p = draw_chanzhongshuochan_chart(sym, days=d)
    print(f'OK: {p}')
