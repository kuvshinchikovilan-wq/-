import os
import io
import time
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime

# ==========================================
# הגדרות מערכת ו-Webhook
# ==========================================
# מושך את ה-Webhook מהגדרות ה-Secrets בגיטהאב (או שתדביק ישירות במירכאות לבדיקה)
DISCORD_WEBHOOK_URL = os.getenv("BREAKOUT_WEBHOOK_URL", "https://discord.com/api/webhooks/1566315887286296596/meUNLSkQiAd3QDPoB8NmbXQ5iy3wK23FqInNtNoaoQSIl7Co6Xuk7XlHsBCmnaG5Cs-w")

# יקום הסריקה: מניות מומנטום, שבבים, טכנולוגיה, פיננסים ומדדים מובילים
WATCHLIST = [
    # Mega Caps & Tech
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "NFLX", "AVGO", "ORCL",
    # Semiconductors & AI
    "AMD", "ARM", "SMCI", "MU", "TSM", "ASML", "QCOM", "INTC", "MRVL", "AMAT", "LRCX", "KLAC",
    # High-Beta Growth & Cyber & Crypto Proxies
    "PLTR", "CRWD", "PANW", "SNOW", "DDOG", "NET", "SHOP", "UBER", "COIN", "MSTR", "MARA", "HOOD", "SOFI", "AFRM", "UPST",
    # Financials, Industrials & Healthcare
    "JPM", "GS", "MS", "V", "MA", "AXP", "CAT", "GE", "LLY", "UNH", "ISRG", "XOM", "CVX",
    # Key ETFs
    "SPY", "QQQ", "IWM", "SOXX", "SMH", "XLF", "XLE", "ARKK", "IGV"
]

# ==========================================
# פונקציות חישוב אינדיקטורים טכניים
# ==========================================
def calculate_indicators(df):
    df = df.copy()
    # ממוצעים נעים (קומנדו + קצר טווח)
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()

    # ממוצע ווליום (20 נרות)
    df['Vol_SMA20'] = df['Volume'].rolling(window=20).mean()

    # חישוב RSI (Wilder's Smoothing - 14)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # חישוב ATR (14) למדידת תנודתיות ויעדים
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    return df

# ==========================================
# לוגיקת זיהוי פריצת התנגדות (יומי / שבועי)
# ==========================================
def detect_breakout(df, timeframe="1D", lookback=55):
    if len(df) < lookback + 10:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # חלון בדיקת ההתנגדות (ללא הנר האחרון שפורץ)
    window = df.iloc[-(lookback + 1):-1]
    resistance_price = float(window['High'].max())
    resistance_date = window['High'].idxmax()

    close_price = float(curr['Close'])
    prev_close = float(prev['Close'])
    open_price = float(curr['Open'])
    high_price = float(curr['High'])
    low_price = float(curr['Low'])
    
    curr_vol = float(curr['Volume'])
    avg_vol = float(curr['Vol_SMA20']) if curr['Vol_SMA20'] > 0 else 1.0
    rvol = (curr_vol / avg_vol) * 100

    rsi = float(curr['RSI'])
    atr = float(curr['ATR']) if not np.isnan(curr['ATR']) else (close_price * 0.025)
    ema20 = float(curr['EMA20'])
    sma50 = float(curr['SMA50'])
    sma200 = float(curr['SMA200']) if not np.isnan(curr['SMA200']) else sma50

    # בדיקת אחוז סגירה בחלק העליון של הנר (כדי לסנן פתילים עליונים / Fakeouts)
    candle_range = high_price - low_price
    close_strength = ((close_price - low_price) / candle_range) if candle_range > 0 else 0.5

    # תנאי סף לפריצה איכותית:
    # 1. הנר הנוכחי נסגר מעל ההתנגדות הקריטית
    # 2. הנר הקודם היה מתחת או בדיוק על ההתנגדות (פריצה טרייה היום!)
    # 3. נר ירוק (סגירה מעל פתיחה) שנסגר ב-40% העליונים של הטווח שלו
    # 4. נפח מסחר מעל 125% מהממוצע
    # 5. מחיר מעל ממוצע 20 ו-50, ו-RSI בטווח בריא (52 עד 82)
    is_fresh_breakout = (close_price > resistance_price * 1.001) and (prev_close <= resistance_price * 1.005)
    is_strong_candle = (close_price > open_price) and (close_strength >= 0.60)
    is_high_volume = rvol >= 125.0
    is_bullish_trend = (close_price > ema20) and (close_price > sma50) and (52 <= rsi <= 82)

    if is_fresh_breakout and is_strong_candle and is_high_volume and is_bullish_trend:
        change_pct = ((close_price - prev_close) / prev_close) * 100
        breakout_pct = ((close_price - resistance_price) / resistance_price) * 100
        
        # חישוב רמות ניהול סיכונים מבוסס ATR
        invalidation_level = min(low_price, resistance_price - (0.5 * atr))
        target_1 = close_price + (1.5 * atr)
        target_2 = close_price + (3.0 * atr)

        return {
            "timeframe": timeframe,
            "lookback": lookback,
            "close": close_price,
            "change_pct": change_pct,
            "resistance": resistance_price,
            "resistance_date": resistance_date.strftime("%d/%m/%Y"),
            "breakout_pct": breakout_pct,
            "rvol": rvol,
            "rsi": rsi,
            "atr": atr,
            "ema20": ema20,
            "sma50": sma50,
            "sma200": sma200,
            "invalidation": invalidation_level,
            "target_1": target_1,
            "target_2": target_2,
            "close_strength": close_strength * 100
        }
    return None

# ==========================================
# יצירת גרף מעוצב (Ilan VIP Dark Theme)
# ==========================================
def generate_breakout_chart(df, ticker, info):
    plot_bars = 75 if info["timeframe"] == "1D" else 52
    plot_df = df.tail(plot_bars).copy()

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

    # הוספת סימון חץ ירוק מתחת לנר הפריצה האחרון
    marker_series = pd.Series(np.nan, index=plot_df.index)
    marker_series.iloc[-1] = plot_df['Low'].iloc[-1] * 0.975

    apds = [
        mpf.make_addplot(plot_df['EMA20'], color='#2962FF', width=1.3, panel=0),
        mpf.make_addplot(plot_df['SMA50'], color='#FF9100', width=1.4, panel=0),
        mpf.make_addplot(marker_series, type='scatter', markersize=140, marker='^', color='#00E676', panel=0),
        mpf.make_addplot(plot_df['Vol_SMA20'], color='#FFD700', width=1.0, panel=1),
        mpf.make_addplot(plot_df['RSI'], panel=2, color='#E040FB', ylabel='RSI (14)', width=1.3, ylim=(20, 88))
    ]

    if not plot_df['SMA200'].isna().all():
        apds.append(mpf.make_addplot(plot_df['SMA200'], color='#FF1744', width=1.6, panel=0))

    # קווי RSI (30/70)
    rsi_70 = pd.Series(70, index=plot_df.index)
    rsi_30 = pd.Series(30, index=plot_df.index)
    apds.append(mpf.make_addplot(rsi_70, panel=2, color='#5D606B', linestyle=':', width=0.8))
    apds.append(mpf.make_addplot(rsi_30, panel=2, color='#5D606B', linestyle=':', width=0.8))

    tf_label = "Daily (1D)" if info["timeframe"] == "1D" else "Weekly (1W)"
    
    buf = io.BytesIO()
    fig, axes = mpf.plot(
        plot_df,
        type='candle',
        style=style,
        volume=True,
        volume_panel=1,
        addplot=apds,
        hlines=dict(
            hlines=[info["resistance"], info["invalidation"], info["target_1"]],
            colors=['#FFD700', '#FF5252', '#00E5FF'],
            linestyle=['--', ':', '-.'],
            linewidths=[2.0, 1.3, 1.3]
        ),
        figsize=(13, 8),
        panel_ratios=(6, 1.8, 2),
        tight_layout=True,
        returnfig=True
    )

    # כותרת עליונה מקצועית
    axes[0].set_title(
        f"{ticker} • {tf_label} Breakout Alert  |  Close: ${info['close']:.2f} (+{info['change_pct']:.2f}%)  |  RVOL: {info['rvol']:.0f}%",
        color='white', fontsize=13, fontweight='bold', pad=14, loc='left'
    )

    # מקרא קווים בפינה השמאלית העליונה
    legend_text = (
        f"── Resistance Broken: ${info['resistance']:.2f} (Gold)\n"
        f"── Target 1: ${info['target_1']:.2f} (Cyan)\n"
        f"── Invalidation: ${info['invalidation']:.2f} (Red)\n"
        f"── EMA20 (Blue) | SMA50 (Orange) | SMA200 (Red)"
    )
    axes[0].text(
        0.02, 0.95, legend_text, transform=axes[0].transAxes,
        fontsize=8.5, color='#E0E3EB', verticalalignment='top',
        bbox=dict(boxstyle='round,pad=0.5', facecolor='#131722', edgecolor='#2A2E39', alpha=0.88)
    )

    # חותמת מים במרכז הגרף
    fig.text(
        0.5, 0.56, 'Ilan.Kuv  |  Quantum VIP',
        fontsize=30, color='white', ha='center', va='center', alpha=0.07, weight='bold'
    )

    fig.savefig(buf, format='png', dpi=160, bbox_inches='tight', facecolor='#0B0E14')
    buf.seek(0)
    return buf

# ==========================================
# שליחת הניתוח המלא והגרף לדיסקורד
# ==========================================
def send_discord_alert(ticker, info, chart_buf):
    tf_heb = "גרף יומי (1D)" if info["timeframe"] == "1D" else "גרף שבועי (1W)"
    period_heb = f"{info['lookback']} ימי המסחר" if info["timeframe"] == "1D" else f"{info['lookback']} השבועות"

    trend_status = "מעל כל הממוצעים המרכזיים (20, 50, 200) - מבנה שורי מלא" if info['close'] > info['sma200'] else "מעל ממוצעים 20 ו-50 (בבניית מומנטום)"

    description = (
        f"**מחיר סגירה:** `${info['close']:.2f}` (`+{info['change_pct']:.2f}%`)  •  **טווח זמן:** `{tf_heb}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**📐 הסטאפ הטכני (The Setup):**\n"
        f"המניה פרצה וסגרה מעל רמת ההתנגדות הקריטית ב-**`${info['resistance']:.2f}`** "
        f"(שיא מאז `{info['resistance_date']}` - {period_heb} האחרונים). "
        f"נר הפריצה נסגר ב-`{info['close_strength']:.0f}%` העליונים של הטווח שלו, מה שמעיד על שליטה של קונים ללא היצע משמעותי בסגירה.\n\n"
        f"**📊 אינדיקטורים ואישורי כסף חכם:**\n"
        f"• **נפח מסחר יחסי (RVOL):** `{info['rvol']:.0f}%` ביחס לממוצע 20 ימים (כניסת ווליום מוסדי)\n"
        f"• **מדד עוצמה יחסית (RSI 14):** `{info['rsi']:.1f}` (מומנטום חיובי חזק)\n"
        f"• **מבנה ממוצעים:** {trend_status}\n"
        f"• **תנודתיות יומית ממוצעת (ATR):** `${info['atr']:.2f}`\n\n"
        f"**🎯 רמות מפתח למעקב (Key Levels):**\n"
        f"• **אזור הפריצה (הופך לתמיכה - קו זהב):** `${info['resistance']:.2f}`\n"
        f"• **אזור שלילת הסטאפ (Invalidation - קו אדום):** סגירה מתחת ל-`${info['invalidation']:.2f}`\n"
        f"• **יעד טכני 1 (1.5x ATR - קו תכלת):** `${info['target_1']:.2f}`\n"
        f"• **יעד טכני 2 (3.0x ATR):** `${info['target_2']:.2f}`"
    )

    embed = {
        "title": f"🚀 התראת פריצת התנגדות קריטית | ${ticker} ({tf_heb})",
        "color": 59766,  # ירוק אזמרגד יוקרתי
        "description": description,
        "image": {"url": f"attachment://{ticker}_breakout.png"},
        "footer": {
            "text": f"Ilan VIP • Quantum Breakout Scanner • {datetime.now().strftime('%d/%m/%Y %H:%M')} | סקירה טכנית בלבד ואינה המלצה"
        }
    }

    payload = {
        "username": "Quantum Breakout Bot | Ilan VIP",
        "embeds": [embed]
    }

    files = {
        "file": (f"{ticker}_breakout.png", chart_buf, "image/png")
    }

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        data={"payload_json": json.dumps(payload)},
        files=files,
        timeout=30
    )
    return response.status_code

# ==========================================
# פונקציית הרצה ראשית (סריקת יומי + שבועי)
# ==========================================
def run_scanner():
    print(f"Starting Quantum Breakout Scanner on {len(WATCHLIST)} tickers...")
    alerts_sent = 0

    for ticker in WATCHLIST:
        try:
            # 1. בדיקת גרף יומי (1D)
            df_daily = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
            if isinstance(df_daily.columns, pd.MultiIndex):
                df_daily.columns = df_daily.columns.get_level_values(0)

            if not df_daily.empty:
                df_daily = calculate_indicators(df_daily)
                daily_breakout = detect_breakout(df_daily, timeframe="1D", lookback=50)
                if daily_breakout:
                    print(f"[!] Daily Breakout detected: {ticker}")
                    chart = generate_breakout_chart(df_daily, ticker, daily_breakout)
                    send_discord_alert(ticker, daily_breakout, chart)
                    alerts_sent += 1
                    time.sleep(2)

            # 2. בדיקת גרף שבועי (1W) - רק בימי שישי/סופ"ש או פריצה שבועית
            df_weekly = yf.download(ticker, period="3y", interval="1wk", progress=False, auto_adjust=True)
            if isinstance(df_weekly.columns, pd.MultiIndex):
                df_weekly.columns = df_weekly.columns.get_level_values(0)

            if not df_weekly.empty:
                df_weekly = calculate_indicators(df_weekly)
                weekly_breakout = detect_breakout(df_weekly, timeframe="1W", lookback=26)
                if weekly_breakout:
                    print(f"[!] Weekly Breakout detected: {ticker}")
                    chart = generate_breakout_chart(df_weekly, ticker, weekly_breakout)
                    send_discord_alert(ticker, weekly_breakout, chart)
                    alerts_sent += 1
                    time.sleep(2)

        except Exception as e:
            print(f"Error scanning {ticker}: {e}")

    print(f"Scan complete. Total breakout alerts sent: {alerts_sent}")

if __name__ == "__main__":
    run_scanner()
