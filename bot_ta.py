import os, io, base64, requests
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

def calc_rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0.0).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    l = (-d.where(d < 0, 0.0)).ewm(alpha=1/p, min_periods=p, adjust=False).mean()
    return 100 - (100 / (1 + (g / l)))

def calc_mfi(df, p=14):
    tp = (df['High'] + df['Low'] + df['Close']) / 3.0
    rmf = tp * df['Volume']
    diff = tp.diff()
    pos = pd.Series(np.where(diff > 0, rmf, 0.0), index=df.index).rolling(p).sum()
    neg = pd.Series(np.where(diff < 0, rmf, 0.0), index=df.index).rolling(p).sum()
    return (100 - (100 / (1 + (pos / neg.replace(0, np.nan))))).fillna(50.0)

def get_sr(df, cp):
    rec = df.tail(120)
    h, l = rec['High'].values, rec['Low'].values
    sh = [float(h[i]) for i in range(3, len(rec)-3) if h[i] == max(h[i-3:i+4])]
    sl = [float(l[i]) for i in range(3, len(rec)-3) if l[i] == min(l[i-3:i+4])]
    rc = sorted([x for x in sh if x > cp * 1.003])
    sc = sorted([x for x in sl if x < cp * 0.997], reverse=True)
    r1 = rc[0] if rc else max(float(rec['High'].tail(30).max()), cp * 1.03)
    r2_l = [x for x in rc if x > r1 * 1.015]
    r2 = r2_l[0] if r2_l else max(float(rec['High'].max()), r1 * 1.04)
    s1 = sc[0] if sc else min(float(rec['Low'].tail(30).min()), cp * 0.97)
    s2_l = [x for x in sc if x < s1 * 0.985]
    s2 = s2_l[0] if s2_l else min(float(rec['Low'].min()), s1 * 0.96)
    return s1, s2, r1, r2

def make_chart(df_p, s1, s2, r1, r2, sym):
    fig = plt.figure(figsize=(11.5, 7.5), dpi=150, facecolor='#0b1120')
    gs = fig.add_gridspec(2, 1, height_ratios=[3.5, 1], hspace=0.06)
    ax1 = fig.add_subplot(gs[0], facecolor='#0b1120')
    ax2 = fig.add_subplot(gs[1], facecolor='#0b1120', sharex=ax1)
    x = np.arange(len(df_p))
    o, h, l, c, v = df_p['Open'].values, df_p['High'].values, df_p['Low'].values, df_p['Close'].values, df_p['Volume'].values
    for i in range(len(df_p)):
        col = '#10b981' if c[i] >= o[i] else '#ef4444'
        ax1.plot([i, i], [l[i], h[i]], color=col, linewidth=1.3, zorder=3)
        bh = max(abs(c[i] - o[i]), (h[i] - l[i]) * 0.04, 0.01)
        ax1.add_patch(Rectangle((i - 0.34, min(o[i], c[i])), 0.68, bh, facecolor=col, edgecolor=col, zorder=4))
        ax2.bar(i, v[i], width=0.68, color=col, alpha=0.65, zorder=3)
    for k, col, lb in [('SMA50','#38bdf8','SMA 50'), ('SMA100','#f59e0b','SMA 100'), ('SMA200','#a855f7','SMA 200')]:
        if not df_p[k].isna().all():
            ax1.plot(x, df_p[k].values, color=col, linewidth=2.0, label=lb, zorder=5)
    for val, col, lb in [(r2,'#f87171','R2'), (r1,'#ef4444','R1'), (s1,'#10b981','S1'), (s2,'#34d399','S2')]:
        ax1.axhline(val, color=col, linestyle='--', linewidth=1.3, alpha=0.8, zorder=2)
        ax1.text(len(df_p)+0.8, val, f" {lb}: ${val:,.2f} ", color='#fff', fontsize=9.5, fontweight='bold', va='center', bbox=dict(boxstyle='round,pad=0.2', facecolor=col, edgecolor='none', alpha=0.85))
    cp = c[-1]
    ax1.axhline(cp, color='#e5c158', linestyle=':', linewidth=1.2, zorder=6)
    ax1.text(len(df_p)+0.8, cp, f" LAST: ${cp:,.2f} ", color='#080d1a', fontsize=10, fontweight='bold', va='center', bbox=dict(boxstyle='round,pad=0.2', facecolor='#e5c158', edgecolor='none'))
    ax1.set_xlim(-1.5, len(df_p) + 15)
    ax1.set_ylim(min(float(df_p['Low'].min()), s1) * 0.985, max(float(df_p['High'].max()), r1) * 1.015)
    for ax in [ax1, ax2]:
        ax.grid(True, linestyle='--', alpha=0.12, color='#94a3b8')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#334155'); ax.spines['bottom'].set_color('#334155')
        ax.tick_params(colors='#94a3b8', labelsize=9.5)
    plt.setp(ax1.get_xticklabels(), visible=False)
    t_idx = np.linspace(0, len(df_p) - 1, 7, dtype=int)
    ax2.set_xticks(t_idx)
    ax2.set_xticklabels([df_p.index[i].strftime('%d %b') for i in t_idx], color='#cbd5e1', fontweight='bold')
    leg = ax1.legend(loc='upper left', facecolor='#111c33', edgecolor='#334155', fontsize=10, ncol=3)
    for t in leg.get_texts(): t.set_color('#fff'); t.set_weight('bold')
    ax1.set_title(f"{sym} • DAILY CHART (1D) • LAST 90 TRADING DAYS", color='#e5c158', fontsize=12, fontweight='bold', loc='right', pad=10)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#0b1120', bbox_inches='tight')
    plt.close(fig); buf.seek(0)
    return "data:image/png;base64," + base64.b64encode(buf.read()).decode('utf-8')

def run_bot(sym):
    sym = sym.upper().strip()
    df = yf.Ticker(sym).history(period="1y")
    if df.empty or len(df) < 30: return None
    df['SMA50'] = df['Close'].rolling(50).mean()
    df['SMA100'] = df['Close'].rolling(100).mean()
    df['SMA200'] = df['Close'].rolling(200).mean()
    df['RSI'] = calc_rsi(df['Close'], 14)
    df['MFI'] = calc_mfi(df, 14)
    cp = float(df['Close'].iloc[-1])
    pp = float(df['Close'].iloc[-2]) if len(df) >= 2 else cp
    pct = ((cp - pp) / pp) * 100 if pp > 0 else 0.0
    s50 = float(df['SMA50'].iloc[-1]) if not np.isnan(df['SMA50'].iloc[-1]) else cp
    s100 = float(df['SMA100'].iloc[-1]) if not np.isnan(df['SMA100'].iloc[-1]) else cp
    s200 = float(df['SMA200'].iloc[-1]) if not np.isnan(df['SMA200'].iloc[-1]) else cp
    rsi = float(df['RSI'].iloc[-1]) if not np.isnan(df['RSI'].iloc[-1]) else 50.0
    mfi = float(df['MFI'].iloc[-1]) if not np.isnan(df['MFI'].iloc[-1]) else 50.0
    rvol = float(df['Volume'].iloc[-1]) / max(float(df['Volume'].tail(20).mean()), 1.0)
    s1, s2, r1, r2 = get_sr(df, cp)
    chart = make_chart(df.tail(90).copy(), s1, s2, r1, r2, sym)
    if cp > s50 > s200: tr, tc = "STRONG BULLISH (Above 50 & 200 SMA)", "#34d399"
    elif cp < s50 < s200: tr, tc = "BEARISH DOWNTREND (Below 50 & 200 SMA)", "#f87171"
    elif cp > s200: tr, tc = "PULLBACK IN UPTREND (Above 200 SMA)", "#fbbf24"
    else: tr, tc = "RECOVERY / TRANSITION (Above 50 SMA)", "#38bdf8"
    now_il = datetime.now(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")
    p_col = "#34d399" if pct >= 0 else "#f87171"
    p_sgn = "+" if pct >= 0 else ""
    logo = f"https://financialmodelingprep.com/image-stock/{sym}.png"

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ width: 1920px; height: 1080px; font-family: 'Montserrat', sans-serif; background: #070b16; color: #fff; padding: 28px 36px; overflow: hidden; }}
        .hdr {{ display: flex; align-items: center; justify-content: space-between; background: #111a2e; border: 2px solid rgba(212,175,55,0.5); border-radius: 20px; padding: 16px 30px; margin-bottom: 22px; }}
        .h-left {{ display: flex; align-items: center; gap: 20px; }}
        .logo {{ width: 74px; height: 74px; border-radius: 50%; background: #fff; padding: 6px; object-fit: contain; border: 2px solid #e5c158; }}
        .tf {{ background: rgba(56,189,248,0.2); border: 1.5px solid #38bdf8; color: #38bdf8; font-size: 15px; font-weight: 900; padding: 4px 12px; border-radius: 8px; margin-left: 12px; }}
        .main {{ display: grid; grid-template-columns: 1.48fr 0.52fr; gap: 24px; height: 890px; }}
        .c-card {{ background: #0b1120; border: 1.5px solid rgba(255,255,255,0.1); border-top: 3px solid #e5c158; border-radius: 20px; padding: 12px; display: flex; align-items: center; justify-content: center; }}
        .side {{ display: flex; flex-direction: column; gap: 16px; }}
        .box {{ background: #111a2e; border: 1px solid rgba(255,255,255,0.09); border-radius: 18px; padding: 18px 22px; }}
        .b-title {{ font-size: 15px; font-weight: 900; color: #e5c158; letter-spacing: 1.5px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.08); }}
        .row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 18px; font-weight: 800; }}
        .sr-g {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
        .pill {{ padding: 12px; border-radius: 12px; text-align: center; font-weight: 900; }}
    </style></head><body>
        <div class="hdr">
            <div class="h-left">
                <img src="{logo}" onerror="this.style.display='none'" class="logo" />
                <div>
                    <h1 style="font-size:36px; font-weight:900;">${sym} TECHNICAL CHART <span class="tf">DAILY • 1D TIMEFRAME</span></h1>
                    <p style="font-size:15px; font-weight:800; color:#e5c158; letter-spacing:2px; margin-top:4px;">ILAN.KUV VIP QUANT TERMINAL • {now_il}</p>
                </div>
            </div>
            <div style="text-align:right;">
                <span style="font-size:42px; font-weight:900;">${cp:,.2f}</span>
                <span style="font-size:24px; font-weight:900; color:{p_col}; margin-left:14px;">{p_sgn}{pct:.2f}%</span>
            </div>
        </div>
        <div class="main">
            <div class="c-card"><img src="{chart}" style="width:100%; height:100%; object-fit:contain;" /></div>
            <div class="side">
                <div class="box" style="border-top: 3px solid {tc};">
                    <div class="b-title">MARKET STRUCTURE (DAILY 1D)</div>
                    <div style="font-size:20px; font-weight:900; color:{tc};">{tr}</div>
                </div>
                <div class="box" style="border-top: 3px solid #10b981;">
                    <div class="b-title">KEY SUPPORT & RESISTANCE (PIVOTS)</div>
                    <div class="sr-g">
                        <div class="pill" style="background:rgba(239,68,68,0.15); border:1px solid #ef4444; color:#f87171;"><div style="font-size:12px;">R1 (NEAR RES)</div><div style="font-size:22px;">${r1:,.2f}</div></div>
                        <div class="pill" style="background:rgba(239,68,68,0.15); border:1px solid #ef4444; color:#f87171;"><div style="font-size:12px;">R2 (MAJOR RES)</div><div style="font-size:22px;">${r2:,.2f}</div></div>
                        <div class="pill" style="background:rgba(16,185,129,0.15); border:1px solid #10b981; color:#34d399;"><div style="font-size:12px;">S1 (NEAR SUP)</div><div style="font-size:22px;">${s1:,.2f}</div></div>
                        <div class="pill" style="background:rgba(16,185,129,0.15); border:1px solid #10b981; color:#34d399;"><div style="font-size:12px;">S2 (MAJOR SUP)</div><div style="font-size:22px;">${s2:,.2f}</div></div>
                    </div>
                </div>
                <div class="box" style="border-top: 3px solid #38bdf8;">
                    <div class="b-title">MOVING AVERAGES (DAILY SMAs)</div>
                    <div class="row"><span style="color:#38bdf8;">50 SMA</span><span>${s50:,.2f}</span></div>
                    <div class="row"><span style="color:#f59e0b;">100 SMA</span><span>${s100:,.2f}</span></div>
                    <div class="row"><span style="color:#a855f7;">200 SMA</span><span>${s200:,.2f}</span></div>
                </div>
                <div class="box" style="border-top: 3px solid #e5c158;">
                    <div class="b-title">MOMENTUM & MONEY FLOW</div>
                    <div class="row"><span>RSI (14 Daily)</span><span>{rsi:.1f}</span></div>
                    <div class="row"><span>MFI (14 Money Flow)</span><span>{mfi:.1f}</span></div>
                    <div class="row"><span>Relative Volume (RVOL)</span><span style="color:#38bdf8;">{rvol:.2f}x</span></div>
                    <div class="row"><span>52W High / Low</span><span style="font-size:16px;">${ float(df['Low'].min()):,.2f} - ${float(df['High'].max()):,.2f}</span></div>
                </div>
            </div>
        </div>
    </body></html>"""
    out = f"ta_{sym}.png"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=2)
        pg.set_content(html, wait_until="networkidle")
        pg.screenshot(path=out)
        b.close()
    return out

if __name__ == "__main__":
    tk = os.environ.get("TARGET_TICKER", "NVDA")
    img = run_bot(tk)
    if img and WEBHOOK_URL:
        with open(img, "rb") as f:
            requests.post(WEBHOOK_URL, data={"content": f"📊 **ניתוח טכני מלא (גרף נרות יומי 1D, ממוצעי 50/100/200, תמיכה/התנגדות ו-MFI) עבור ${tk.upper()}:**"}, files={"file": (img, f, "image/png")})
# END OF FILE
