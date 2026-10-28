import os
import io
import base64
import requests
from datetime import datetime
import pytz
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_TA") or os.environ.get("DISCORD_WEBHOOK_MIDDAY")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

def get_logo_base64():
    for fname in ["logo.jpg", "logo.png", "logo.jpeg", "LOGO.jpg", "LOGO.png"]:
        if os.path.exists(fname):
            with open(fname, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                ext = "png" if fname.lower().endswith("png") else "jpeg"
                return f"data:image/{ext};base64,{encoded}"
    return ""

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_mfi(df, period=14):
    tp = (df['High'] + df['Low'] + df['Close']) / 3.0
    rmf = tp * df['Volume']
    diff = tp.diff()
    pos_mf = pd.Series(np.where(diff > 0, rmf, 0.0), index=df.index)
    neg_mf = pd.Series(np.where(diff < 0, rmf, 0.0), index=df.index)
    pos_sum = pos_mf.rolling(period).sum()
    neg_sum = neg_mf.rolling(period).sum()
    mfr = pos_sum / neg_sum.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mfr))
    return mfi.fillna(50.0)

def find_sr_levels(df, curr_price):
    recent = df.tail(120)
    highs = recent['High'].values
    lows = recent['Low'].values
    
    swing_highs = []
    swing_lows = []
    for i in range(3, len(recent) - 3):
        if highs[i] == max(highs[i-3:i+4]):
            swing_highs.append(float(highs[i]))
        if lows[i] == min(lows[i-3:i+4]):
            swing_lows.append(float(lows[i]))

    res_candidates = sorted([h for h in swing_highs if h > curr_price * 1.003])
    sup_candidates = sorted([l for l in swing_lows if l < curr_price * 0.997], reverse=True)

    r1 = res_candidates[0] if len(res_candidates) > 0 else float(recent['High'].tail(30).max())
    if r1 <= curr_price:
        r1 = curr_price * 1.03

    r2_list = [h for h in res_candidates if h > r1 * 1.015]
    r2 = r2_list[0] if len(r2_list) > 0 else max(float(recent['High'].max()), r1 * 1.04)

    s1 = sup_candidates[0] if len(sup_candidates) > 0 else float(recent['Low'].tail(30).min())
    if s1 >= curr_price:
        s1 = curr_price * 0.97

    s2_list = [l for l in sup_candidates if l < s1 * 0.985]
    s2 = s2_list[0] if len(s2_list) > 0 else min(float(recent['Low'].min()), s1 * 0.96)

    return s1, s2, r1, r2

def render_candlestick_chart(df_plot, s1, s2, r1, r2, symbol):
    fig = plt.figure(figsize=(11.5, 7.6), dpi=160, facecolor='#0b1120')
    gs = fig.add_gridspec(2, 1, height_ratios=[3.6, 1], hspace=0.06)
    ax1 = fig.add_subplot(gs[0], facecolor='#0b1120')
    ax2 = fig.add_subplot(gs[1], facecolor='#0b1120', sharex=ax1)

    x = np.arange(len(df_plot))
    opens = df_plot['Open'].values
    highs = df_plot['High'].values
    lows = df_plot['Low'].values
    closes = df_plot['Close'].values
    vols = df_plot['Volume'].values

    for i in range(len(df_plot)):
        is_bull = closes[i] >= opens[i]
        color = '#10b981' if is_bull else '#ef4444'
        ax1.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1.3, zorder=3)
        body_bottom = min(opens[i], closes[i])
        body_height = max(abs(closes[i] - opens[i]), (highs[i] - lows[i]) * 0.04, 0.01)
        rect = Rectangle((i - 0.34, body_bottom), 0.68, body_height, facecolor=color, edgecolor=color, zorder=4)
        ax1.add_patch(rect)
        ax2.bar(i, vols[i], width=0.68, color=color, alpha=0.65, zorder=3)

    # ממוצעים נעים 50 / 100 / 200
    if 'SMA50' in df_plot and not df_plot['SMA50'].isna().all():
        ax1.plot(x, df_plot['SMA50'].values, color='#38bdf8', linewidth=2.0, label='SMA 50', zorder=5)
    if 'SMA100' in df_plot and not df_plot['SMA100'].isna().all():
        ax1.plot(x, df_plot['SMA100'].values, color='#f59e0b', linewidth=2.0, label='SMA 100', zorder=5)
    if 'SMA200' in df_plot and not df_plot['SMA200'].isna().all():
        ax1.plot(x, df_plot['SMA200'].values, color='#a855f7', linewidth=2.2, label='SMA 200', zorder=5)

    # קווי תמיכה והתנגדות על הגרף
    levels = [
        (r2, '#f87171', 'R2 (Major Res)', '--'),
        (r1, '#ef4444', 'R1 (Resistance)', '--'),
        (s1, '#10b981', 'S1 (Support)', '--'),
        (s2, '#34d399', 'S2 (Major Sup)', '--'),
    ]
    for val, col, lbl, style in levels:
        ax1.axhline(val, color=col, linestyle=style, linewidth=1.4, alpha=0.8, zorder=2)
        ax1.text(len(df_plot) + 0.8, val, f" {lbl}: ${val:,.2f} ", color='#ffffff',
                 fontsize=9.5, fontweight='bold', va='center',
                 bbox=dict(boxstyle='round,pad=0.25', facecolor=col, edgecolor='none', alpha=0.85))

    curr_p = closes[-1]
    ax1.axhline(curr_p, color='#e5c158', linestyle=':', linewidth=1.2, alpha=0.9, zorder=6)
    ax1.text(len(df_plot) + 0.8, curr_p, f" LAST: ${curr_p:,.2f} ", color='#080d1a',
             fontsize=10, fontweight='bold', va='center',
             bbox=dict(boxstyle='round,pad=0.25', facecolor='#e5c158', edgecolor='none'))

    ax1.set_xlim(-1.5, len(df_plot) + 18)
    y_min = min(float(df_plot['Low'].min()), s1) * 0.985
    y_max = max(float(df_plot['High'].max()), r1) * 1.015
    ax1.set_ylim(y_min, y_max)

    for ax in [ax1, ax2]:
        ax.grid(True, linestyle='--', alpha=0.12, color='#94a3b8')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#334155')
        ax.spines['bottom'].set_color('#334155')
        ax.tick_params(colors='#94a3b8', labelsize=9.5)

    plt.setp(ax1.get_xticklabels(), visible=False)
    ax1.set_ylabel("Price (USD)", color='#94a3b8', fontsize=10, fontweight='bold')
    ax2.set_ylabel("Volume", color='#94a3b8', fontsize=9.5, fontweight='bold')

    tick_idx = np.linspace(0, len(df_plot) - 1, 7, dtype=int)
    tick_labels = [df_plot.index[i].strftime('%d %b') for i in tick_idx]
    ax2.set_xticks(tick_idx)
    ax2.set_xticklabels(tick_labels, color='#cbd5e1', fontweight='bold')

    leg = ax1.legend(loc='upper left', facecolor='#111c33', edgecolor='#334155', fontsize=10, ncol=3)
    for text in leg.get_texts():
        text.set_color('#ffffff')
        text.set_weight('bold')

    ax1.set_title(f"{symbol} • DAILY CHART (1D) • LAST 90 TRADING DAYS", color='#e5c158',
                  fontsize=12, fontweight='bold', loc='right', pad=10)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=160, facecolor='#0b1120', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode('utf-8')

def analyze_ticker(symbol):
    symbol = symbol.upper().strip()
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty or len(df) < 30:
            return None

        df['SMA50'] = df['Close'].rolling(50).mean()
        df['SMA100'] = df['Close'].rolling(100).mean()
        df['SMA200'] = df['Close'].rolling(200).mean()
        df['RSI'] = calculate_rsi(df['Close'], 14)
        df['MFI'] = calculate_mfi(df, 14)

        curr_price = float(df['Close'].iloc[-1])
        prev_price = float(df['Close'].iloc[-2]) if len(df) >= 2 else curr_price
        pct_change = ((curr_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0.0

        sma50 = float(df['SMA50'].iloc[-1]) if not np.isnan(df['SMA50'].iloc[-1]) else curr_price
        sma100 = float(df['SMA100'].iloc[-1]) if not np.isnan(df['SMA100'].iloc[-1]) else curr_price
        sma200 = float(df['SMA200'].iloc[-1]) if not np.isnan(df['SMA200'].iloc[-1]) else curr_price

        dist_50 = ((curr_price - sma50) / sma50) * 100
        dist_100 = ((curr_price - sma100) / sma100) * 100
        dist_200 = ((curr_price - sma200) / sma200) * 100

        rsi_val = float(df['RSI'].iloc[-1]) if not np.isnan(df['RSI'].iloc[-1]) else 50.0
        mfi_val = float(df['MFI'].iloc[-1]) if not np.isnan(df['MFI'].iloc[-1]) else 50.0

        vol_curr = float(df['Volume'].iloc[-1])
        vol_avg20 = float(df['Volume'].tail(20).mean())
        rvol = vol_curr / vol_avg20 if vol_avg20 > 0 else 1.0

        high_52 = float(df['High'].max())
        low_52 = float(df['Low'].min())

        s1, s2, r1, r2 = find_sr_levels(df, curr_price)
        df_plot = df.tail(90).copy()
        chart_b64 = render_candlestick_chart(df_plot, s1, s2, r1, r2, symbol)

        if curr_price > sma50 > sma200:
            trend = "STRONG BULLISH (Above 50 & 200 SMA)"
            trend_col = "#34d399"
        elif curr_price < sma50 < sma200:
            trend = "BEARISH DOWNTREND (Below 50 & 200 SMA)"
            trend_col = "#f87171"
        elif curr_price > sma200 and curr_price < sma50:
            trend = "PULLBACK IN UPTREND (Below 50 / Above 200)"
            trend_col = "#fbbf24"
        else:
            trend = "RECOVERY / TRANSITION (Above 50 / Below 200)"
            trend_col = "#38bdf8"

        return {
            "symbol": symbol,
            "price": f"${curr_price:,.2f}",
            "pct": pct_change,
            "sma50": f"${sma50:,.2f}",
            "sma100": f"${sma100:,.2f}",
            "sma200": f"${sma200:,.2f}",
            "dist50": dist_50,
            "dist100": dist_100,
            "dist200": dist_200,
            "rsi": rsi_val,
            "mfi": mfi_val,
            "rvol": f"{rvol:.2f}x",
            "high52": f"${high_52:,.2f}",
            "low52": f"${low_52:,.2f}",
            "s1": f"${s1:,.2f}",
            "s2": f"${s2:,.2f}",
            "r1": f"${r1:,.2f}",
            "r2": f"${r2:,.2f}",
            "trend": trend,
            "trend_col": trend_col,
            "chart_b64": chart_b64,
            "logo": f"https://financialmodelingprep.com/image-stock/{symbol}.png"
        }
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None

def build_ta_html(data):
    now_il = datetime.now(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")
    is_up = data["pct"] >= 0
    cls = "up" if is_up else "down"
    sign = "+" if is_up else ""

    def fmt_dist(val):
        s = "+" if val >= 0 else ""
        c = "#34d399" if val >=
