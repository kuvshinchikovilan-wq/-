import os
import io
import discord
from discord import app_commands
from discord.ext import commands
import numpy as np
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime

# ==========================================
# הגדרות בוט הדיסקורד
# ==========================================
# מושך את הטוקן ממשתני הסביבה ב-GitHub Actions / שרת
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN_HERE"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# חישוב אינדיקטורים טכניים ופרימרקט
# ==========================================
def fetch_and_prepare_data(ticker_symbol: str):
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="1y", interval="1d", auto_adjust=True)
    
    if df.empty or len(df) < 30:
        return None, None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # ממוצעים נעים
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['Vol_SMA20'] = df['Volume'].rolling(window=20).mean()

    # RSI (14)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI_SMA'] = df['RSI'].rolling(window=14).mean()

    # ATR (14) למדידת טווח תנועה הגיוני לטווח הקצר
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(14).mean()

    # בדיקת מחיר Pre/Post Market עדכני
    ext_info = {"has_ext": False, "ext_price": None, "ext_change_pct": 0.0, "label": ""}
    try:
        intraday = ticker.history(period="5d", interval="5m", prepost=True)
        if not intraday.empty:
            if isinstance(intraday.columns, pd.MultiIndex):
                intraday.columns = intraday.columns.get_level_values(0)
            last_ext_price = float(intraday['Close'].iloc[-1])
            reg_close = float(df['Close'].iloc[-1])
            diff_pct = ((last_ext_price - reg_close) / reg_close) * 100
            if abs(diff_pct) >= 0.15:
                ext_info = {
                    "has_ext": True,
                    "ext_price": last_ext_price,
                    "ext_change_pct": diff_pct,
                    "label": "Pre/Post Market"
                }
    except Exception:
        pass

    return df, ext_info

# ==========================================
# מנוע חכם לאיתור תמיכה והתנגדות לטווח הקצר
# (מונע קפיצה לרמות רחוקות כמו 600$ כשהמחיר ב-450$)
# ==========================================
def get_short_term_levels(df: pd.DataFrame, current_price: float):
    atr = float(df['ATR'].iloc[-1])
    if np.isnan(atr) or atr <= 0:
        atr = current_price * 0.025

    # מסתכלים רק על 55 ימי המסחר האחרונים לטווח הקצר
    recent_df = df.tail(55).copy()
    highs = recent_df['High'].values
    lows = recent_df['Low'].values

    swing_highs = []
    swing_lows = []

    # 1. איתור נקודות פיבוט מקומיות (Swing Highs / Lows)
    for i in range(2, len(recent_df) - 2):
        if highs[i] >= max(highs[i-2:i]) and highs[i] >= max(highs[i+1:i+3]):
            swing_highs.append(float(highs[i]))
        if lows[i] <= min(lows[i-2:i]) and lows[i] <= min(lows[i+1:i+3]):
            swing_lows.append(float(lows[i]))

    # 2. הוספת גבוה/נמוך של 10 ו-20 הימים האחרונים כעוגנים קרובים
    swing_highs.extend([
        float(recent_df['High'].tail(10).max()),
        float(recent_df['High'].tail(22).max())
    ])
    swing_lows.extend([
        float(recent_df['Low'].tail(10).min()),
        float(recent_df['Low'].tail(22).min())
    ])

    # 3. הוספת ממוצעים נעים כרמות תמיכה/התנגדות דינמיות
    for col in ['EMA20', 'SMA50', 'SMA100', 'SMA200']:
        if col in recent_df.columns and not np.isnan(recent_df[col].iloc[-1]):
            ma_val = float(recent_df[col].iloc[-1])
            swing_highs.append(ma_val)
            swing_lows.append(ma_val)

    # 4. הגבלת מרחק: בין 0.5 ATR לבין מקסימום 3.2 ATR (או גג 9% מהמחיר הנוכחי)
    min_dist = atr * 0.45
    max_dist = min(atr * 3.2, current_price * 0.09)

    valid_resistances = [
        r for r in swing_highs
        if (current_price + min_dist) <= r <= (current_price + max_dist)
    ]
    valid_supports = [
        s for s in swing_lows
        if (current_price - max_dist) <= s <= (current_price - min_dist)
    ]

    # בחירת ההתנגדות והתמיכה הקרובות והרלוונטיות ביותר למחיר הנוכחי
    if valid_resistances:
        resistance_1 = min(valid_resistances)
    else:
        resistance_1 = current_price + (1.8 * atr)

    if valid_supports:
        support_1 = max(valid_supports)
    else:
        support_1 = current_price - (1.8 * atr)

    # חישוב יעד פריצה קרוב (Resistance 2) ותמיכה שנייה (Support 2) במרחק הגיוני
    resistance_2 = resistance_1 + (1.5 * atr)
    support_2 = support_1 - (1.5 * atr)

    return {
        "support_1": round(support_1, 2),
        "support_2": round(support_2, 2),
        "resistance_1": round(resistance_1, 2),
        "resistance_2": round(resistance_2, 2),
        "atr": round(atr, 2)
    }

# ==========================================
# חישוב קו מגמה אלכסוני (Linear Regression Channel / Trendline)
# ==========================================
def calculate_trendlines(plot_df: pd.DataFrame):
    x = np.arange(len(plot_df))
    closes = plot_df['Close'].values
    
    slope, intercept = np.polyfit(x, closes, 1)
    reg_line = slope * x + intercept
    std_dev = np.std(closes - reg_line)
    
    upper_channel = pd.Series(reg_line + (1.6 * std_dev), index=plot_df.index)
    lower_channel = pd.Series(reg_line - (1.6 * std_dev), index=plot_df.index)
    mid_channel = pd.Series(reg_line, index=plot_df.index)
    
    return upper_channel, mid_channel, lower_channel

# ==========================================
# בניית הגרף המעוצב (מותאם לטווח הקצר ללא עיוות ציר Y)
# ==========================================
def generate_ta_chart(df: pd.DataFrame, ticker: str, levels: dict, ext_info: dict):
    # מציגים 65 נרות אחרונים כדי שיראו ברור את הטווח הקצר
    plot_df = df.tail(65).copy()
    upper_ch, mid_ch, lower_ch = calculate_trendlines(plot_df)

    mc = mpf.make_marketcolors(
        up='#00E676', down='#FF1744',
        edge='inherit', wick='inherit',
        volume={'up': '#00E676', 'down': '#FF1744'}
    )

    style = mpf.make_mpf_style(
        base_mpf_style='nightclouds',
        marketcolors=mc,
        facecolor='#0B0E14',
        edgecolor='#1E222D',
        figcolor='#0B0E14',
        gridcolor='#1A1F2C',
        gridstyle='--',
        y_on_right=True,
        rc={
            'axes.labelcolor': '#B2B5BE',
            'xtick.color': '#B2B5BE',
            'ytick.color': '#B2B5BE',
            'font.size': 9
        }
    )

    apds = [
        # ממוצעים נעים
        mpf.make_addplot(plot_df['EMA20'], color='#2962FF', width=1.3, panel=0),
        mpf.make_addplot(plot_df['SMA50'], color='#FF9100', width=1.4, panel=0),
        # תעלת מגמה אלכסונית
        mpf.make_addplot(upper_ch, color='#00E5FF', linestyle=':', width=1.0, panel=0),
        mpf.make_addplot(lower_ch, color='#00E5FF', linestyle=':', width=1.0, panel=0),
        # ווליום ו-RSI
        mpf.make_addplot(plot_df['Vol_SMA20'], color='#FFD700', width=1.0, panel=1),
        mpf.make_addplot(plot_df['RSI'], panel=2, color='#E040FB', ylabel='RSI (14)', width=1.3, ylim=(20, 85)),
        mpf.make_addplot(plot_df['RSI_SMA'], panel=2, color='#FFD700', width=1.0)
    ]

    # מוסיפים את ממוצע 200 רק אם הוא נמצא בטווח קרוב (כדי שלא ימתח את הגרף ל-600$!)
    curr_price = float(plot_df['Close'].iloc[-1])
    if not plot_df['SMA200'].isna().all():
        last_sma200 = float(plot_df['SMA200'].iloc[-1])
        if abs(last_sma200 - curr_price) / curr_price <= 0.18:
            apds.append(mpf.make_addplot(plot_df['SMA200'], color='#FF1744', width=1.6, panel=0))

    rsi_70 = pd.Series(70, index=plot_df.index)
    rsi_30 = pd.Series(30, index=plot_df.index)
    apds.append(mpf.make_addplot(rsi_70, panel=2, color='#5D606B', linestyle=':', width=0.8))
    apds.append(mpf.make_addplot(rsi_30, panel=2, color='#5D606B', linestyle=':', width=0.8))

    hlines_list = [levels['resistance_1'], levels['support_1']]
    hlines_colors = ['#FFD700', '#00E676']
    hlines_styles = ['--', '--']

    if ext_info.get("has_ext") and ext_info.get("ext_price"):
        hlines_list.append(ext_info["ext_price"])
        hlines_colors.append('#E040FB')
        hlines_styles.append('-.')

    buf = io.BytesIO()
    fig, axes = mpf.plot(
        plot_df,
        type='candle',
        style=style,
        volume=True,
        volume_panel=1,
        addplot=apds,
        hlines=dict(
            hlines=hlines_list,
            colors=hlines_colors,
            linestyle=hlines_styles,
            linewidths=[1.8] * len(hlines_list)
        ),
        figsize=(13, 8),
        panel_ratios=(6, 1.8, 2),
        tight_layout=True,
        returnfig=True
    )

    prev_close = float(plot_df['Close'].iloc[-2])
    change_pct = ((curr_price - prev_close) / prev_close) * 100
    last_rsi = float(plot_df['RSI'].iloc[-1])

    axes[0].set_title(
        f"{ticker.upper()} • Short-Term Technical Setup  |  Close: ${curr_price:.2f} ({change_pct:+.2f}%)  |  RSI: {last_rsi:.1f}",
        color='white', fontsize=13, fontweight='bold', pad=14, loc='left'
    )

    legend_text = (
        f"── Immediate Resistance: ${levels['resistance_1']:.2f} (Gold)\n"
        f"── Immediate Support: ${levels['support_1']:.2f} (Green)\n"
        f"── EMA20 (Blue) | SMA50 (Orange) | Channel (Cyan)"
    )
    if ext_info.get("has_ext"):
        legend_text += f"\n── Pre/Post Market: ${ext_info['ext_price']:.2f} ({ext_info['ext_change_pct']:+.2f}%)"

    axes[0].text(
        0.02, 0.95, legend_text, transform=axes[0].transAxes,
        fontsize=8.5, color='#E0E3EB', verticalalignment='top',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='#131722', edgecolor='#2A2E39', alpha=0.88)
    )

    fig.text(
        0.5, 0.56, 'Ilan.Kuv  |  Quantum VIP',
        fontsize=30, color='white', ha='center', va='center', alpha=0.07, weight='bold'
    )

    fig.savefig(buf, format='png', dpi=160, bbox_inches='tight', facecolor='#0B0E14')
    buf.seek(0)
    return buf

# ==========================================
# בניית הניתוח הטכני המלא להודעת הדיסקורד
# ==========================================
def build_ta_embed(ticker: str, df: pd.DataFrame, levels: dict, ext_info: dict):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    close_price = float(curr['Close'])
    change_pct = ((close_price - float(prev['Close'])) / float(prev['Close'])) * 100
    ema20 = float(curr['EMA20'])
    sma50 = float(curr['SMA50'])
    sma200 = float(curr['SMA200']) if not np.isnan(curr['SMA200']) else sma50
    rsi = float(curr['RSI'])
    rvol = (float(curr['Volume']) / float(curr['Vol_SMA20'])) * 100 if curr['Vol_SMA20'] > 0 else 100.0

    # אבחון מגמה לטווח הקצר
    if close_price > ema20 and close_price > sma50:
        trend_str = "🟢 חיובית (נסחרת מעל ממוצעים 20 ו-50)"
        embed_color = 0x00E676
    elif close_price < ema20 and close_price < sma50:
        trend_str = "🔴 שלילית / בתיקון לטווח הקצר (מתחת לממוצעים 20 ו-50)"
        embed_color = 0xFF1744
    else:
        trend_str = "🟡 ניטרלית / התכנסות בין ממוצע 20 לממוצע 50"
        embed_color = 0xFFD700

    ext_line = ""
    if ext_info.get("has_ext"):
        ext_line = f"\n⚡ **מסחר מורחב (Pre/Post):** `${ext_info['ext_price']:.2f}` (`{ext_info['ext_change_pct']:+.2f}%`)"

    r1 = levels['resistance_1']
    r2 = levels['resistance_2']
    s1 = levels['support_1']
    s2 = levels['support_2']
    dist_to_r1 = ((r1 - close_price) / close_price) * 100
    dist_to_s1 = ((close_price - s1) / close_price) * 100

    description = (
        f"**מחיר נוכחי:** `${close_price:.2f}` (`{change_pct:+.2f}%`){ext_line}\n"
        f"**מגמת טווח קצר:** {trend_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**🎯 רמות מפתח קרובות (Short-Term Key Levels):**\n"
        f"• **התנגדות קרובה (קו זהב):** `${r1:.2f}` (במרחק `+{dist_to_r1:.1f}%`)\n"
        f"• **תמיכה קרובה (קו ירוק):** `${s1:.2f}` (במרחק `-{dist_to_s1:.1f}%`)\n"
        f"• **ממוצעים נעים:** EMA20: `${ema20:.2f}` | SMA50: `${sma50:.2f}` | SMA200: `${sma200:.2f}`\n"
        f"• **מומנטום ונפח:** RSI(14): `{rsi:.1f}` | נפח יחסי (RVOL): `{rvol:.0f}%` | ATR יומי: `${levels['atr']:.2f}`\n\n"
        f"**📐 תרחישי מסחר לטווח הקצר (Actionable Scenarios):**\n"
        f"🟢 **תרחיש חיובי (פריצה):** התבססות וסגירה מעל ההתנגדות הקרובה ב-**`${r1:.2f}`** תפתח מומנטום מיידי לכיוון היעד הבא ב-**`${r2:.2f}`**.\n"
        f"🔴 **תרחיש שלילי (שבירה):** אובדן רמת התמיכה הקרובה ב-**`${s1:.2f}`** יעיד על חולשה קצרת טווח ויוביל לבדיקת אזור התמיכה הבא ב-**`${s2:.2f}`**."
    )

    embed = discord.Embed(
        title=f"📊 ניתוח טכני ממוקד | ${ticker.upper()}",
        description=description,
        color=embed_color
    )
    embed.set_image(url=f"attachment://{ticker.upper()}_ta.png")
    embed.set_footer(text=f"Ilan VIP • Quantum TA Bot • {datetime.now().strftime('%d/%m/%Y %H:%M')} | אינו מהווה המלצה")
    return embed

# ==========================================
# פקודת הסלאש /ta בדיסקורד
# ==========================================
@bot.tree.command(name="ta", description="שליפת גרף וניתוח טכני ממוקד לטווח הקצר עבור מניה")
@app_commands.describe(ticker="סימול המניה באנגלית (למשל NVDA, TSLA, SPY)")
async def ta_command(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer(thinking=True)
    clean_ticker = ticker.strip().upper().replace("$", "")

    try:
        df, ext_info = fetch_and_prepare_data(clean_ticker)
        if df is None:
            await interaction.followup.send(f"❌ לא נמצאו מספיק נתונים עבור הסימול **{clean_ticker}**. ודא שהטיקר תקין.")
            return

        current_price = float(df['Close'].iloc[-1])
        levels = get_short_term_levels(df, current_price)
        chart_buf = generate_ta_chart(df, clean_ticker, levels, ext_info)
        embed = build_ta_embed(clean_ticker, df, levels, ext_info)

        file = discord.File(fp=chart_buf, filename=f"{clean_ticker}_ta.png")
        
        # שליחה בפרטי (DM) או בחדר בהתאם להגדרת השרת
        try:
            await interaction.user.send(embed=embed, file=file)
            if interaction.guild is not None:
                await interaction.followup.send(f"✅ הניתוח הטכני עבור **${clean_ticker}** נשלח אליך בפרטי (DM)!", ephemeral=True)
        except discord.Forbidden:
            # אם למשתמש סגור ה-DM, שולח כתגובה ישירה
            chart_buf.seek(0)
            file_fallback = discord.File(fp=chart_buf, filename=f"{clean_ticker}_ta.png")
            await interaction.followup.send(embed=embed, file=file_fallback)

    except Exception as e:
        await interaction.followup.send(f"⚠️ אירעה שגיאה בניתוח המניה **{clean_ticker}**: `{str(e)}`")

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s). Quantum TA Bot is online as {bot.user}!")
    except Exception as e:
        print(f"Error syncing commands: {e}")

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
