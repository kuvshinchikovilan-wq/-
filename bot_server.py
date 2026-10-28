import os
import io
import discord
from discord.ext import commands
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# הגדרת הרשאות הבוט
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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
    ax1.set_title(f"{sym} • DAILY CHART (1D)", color='#e5c158', fontsize=12, fontweight='bold', loc='right', pad=10)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#0b1120', bbox_inches='tight')
    plt.close(fig); buf.seek(0)
    return buf

@bot.event
async def on_ready():
    print(f'Bot is online as {bot.user}')

@bot.command(name='ta')
async def ta_command(ctx, symbol: str = "NVDA"):
    symbol = symbol.upper().strip()
    async with ctx.typing():
        try:
            df = yf.Ticker(symbol).history(period="1y")
            if df.empty or len(df) < 30:
                await ctx.send(f"❌ לא נמצאו נתונים מספיקים עבור הטיקר `{symbol}`.")
                return
            
            df['SMA50'] = df['Close'].rolling(50).mean()
            df['SMA100'] = df['Close'].rolling(100).mean()
            df['SMA200'] = df['Close'].rolling(200).mean()
            
            cp = float(df['Close'].iloc[-1])
            pp = float(df['Close'].iloc[-2]) if len(df) >= 2 else cp
            pct = ((cp - pp) / pp) * 100 if pp > 0 else 0.0
            
            s1, s2, r1, r2 = get_sr(df, cp)
            chart_buf = make_chart(df.tail(90).copy(), s1, s2, r1, r2, symbol)
            
            file = discord.File(chart_buf, filename=f"ta_{symbol}.png")
            p_sgn = "+" if pct >= 0 else ""
            msg = f"📊 **ניתוח טכני לבקשתך עבור ${symbol}** | מחיר: **${cp:,.2f}** ({p_sgn}{pct:.2f}%)"
            await ctx.send(content=msg, file=file)
        except Exception as e:
            await ctx.send(f"⚠️ אגיד שגיאה בעיבוד הנתונים עבור `{symbol}`: {str(e)}")

# הרצת הבוט עם הטוקן
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("Error: DISCORD_BOT_TOKEN environment variable not set!")
