import os
import io
import time
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import mplfinance as mpf
from datetime import datetime, timezone

# ==========================================
# הגדרת ה-Webhook של חדר תמיכות סווינג שבועי
# ==========================================
SUPPORT_WEBHOOK_URL = "https://discord.com/api/webhooks/1566348940167618631/ftzZ2uUKohQwpx10aNFbM2joMny_18jyOEJmp1oORIpGv2DPcVxCwP2Y5t6_Vrfao7_l"

# ==========================================
# יקום נכסים חזקים בלבד (Blue Chips, מובילות שוק, מדדים וסחורות)
# ==========================================
STRONG_ASSETS = [
    # Mega Caps & Market Leaders
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "NFLX", "AVGO", "ORCL", "CRM", "ADBE", "IBM", "INTU", "NOW", "ISRG",
    # Leading Semiconductors & Hardware
    "AMD", "ARM", "MU", "TSM", "ASML", "QCOM", "MRVL", "AMAT", "LRCX", "KLAC", "TXN", "ADI", "NXPI", "MPWR", "VRT", "DELL", "ANET",
    # Top Cyber, Cloud & FinTech Leaders
    "PLTR", "CRWD", "PANW", "FTNT", "ZS", "CYBR", "SNOW", "DDOG", "NET", "MDB", "WDAY", "TTD", "APP", "IOT", "SHOP", "UBER", "ABNB", "DASH", "SPOT", "MELI", "NU",
    # Financials, Industrials & Healthcare Giants
    "JPM", "GS", "MS", "BLK", "BX", "KKR", "V", "MA", "AXP", "SPGI", "CAT", "DE", "GE", "LMT", "RTX", "AXON", "URI", "ETN", "LLY", "NVO", "UNH", "VRTX", "REGN", "ABBV",
    # Consumer & Retail Titans
    "WMT", "COST", "HD", "LOW", "MCD", "CMG", "SBUX", "NKE", "LULU", "DECK", "ONON",
    # Energy, Crypto Proxies & Key ETFs
    "XOM", "CVX", "CEG", "VST", "CCJ", "COIN", "IBIT", "GLD", "SLV", "SPY", "QQQ", "IWM", "DIA", "SOXX", "SMH", "IGV", "XLF", "XLE", "XLI", "XLV"
]

# קובץ זיכרון למניעת שליחה כפולה של אותה מניה באותו שבוע
CACHE_FILE = "sent_weekly_supports.json"

def load_support_cache():
    week_str = datetime.now(timezone.utc).strftime("%Y-W%W")
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                if data.get("week") == week_str:
                    return set(data.get("sent", []))
        except Exception:
            pass
    return set()

def save_support_cache(sent_set):
    week_str = datetime.now(timezone.utc).strftime("%Y-W%W")
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({
                "week": week_str,
                "sent": sorted(list(sent_set))
            }, f, indent=2)
    except Exception as e:
        print(f"Cache save error: {e}")

# ==========================================
# חישוב אינדיקטורים טכניים בגרף השבועי
# ==========================================
def calculate_weekly_indicators(df):
    df = df.copy()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA100'] = df['Close'].rolling(window=100).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['Vol_SMA20'] = df['Volume'].rolling(window=20).mean()

    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    return df

# ==========================================
# לוגיקת זיהוי הגעה לתמיכה משמעותית בגרף שבועי
# ==========================================
def detect_weekly_support_setup(df):
    if len(df) < 60:
        return None

    curr = df.iloc[-1]
    close_price = float(curr['Close'])
    low_price = float(curr['Low'])

    sma20 = float(curr['SMA20']) if not np.isnan(curr['SMA20']) else None
    sma50 = float(curr['SMA50']) if not np.isnan(curr['SMA50']) else None
    sma100 = float(curr['SMA100']) if not np.isnan(curr['SMA100']) else None
    sma200 = float(curr['SMA200']) if not np.isnan(curr['SMA200']) else None
    rsi = float(curr['RSI']) if not np.isnan(curr['RSI']) else 50.0
    atr = float(curr['ATR']) if not np.isnan(curr['ATR']) else (close_price * 0.04)

    # 1. סינון "נכס חזק": חייב להיות במגמה ראשית עולה
    if sma200 and close_price < sma200 * 0.96:
        return None
    if sma50 and sma200 and sma50 < sma200:
        return None

    # 2. חישוב השיא של 26 השבועות האחרונים (חצי שנה) כדי לוודא שיש תיקון אמיתי (Pullback)
    recent_high = float(df['High'].iloc[-26:].max())
    pullback_pct = ((recent_high - close_price) / recent_high) * 100

    # מניה שירדה בין 6% ל-28% מהשיא שלה (תיקון בריא לסווינג)
    if not (6.0 <= pullback_pct <= 28.0):
        return None

    # 3. בדיקת RSI שבועי - התקררות לאזור איסוף (34 עד 58)
    if not (34.0 <= rsi <= 58.0):
        return None

    # 4. איתור רמת התמיכה המשמעותית שהמניה בודקת כרגע
    prev_pivot_support = float(df['Low'].iloc[-20:-3].min())
    
    candidates = []
    if sma50:
        candidates.append(("ממוצע נע 50 שבועי (SMA 50 - תמיכה מוסדית)", sma50))
    if sma100:
        candidates.append(("ממוצע נע 100 שבועי (SMA 100 - תמיכת מאקרו)", sma100))
    if sma200:
        candidates.append(("ממוצע נע 200 שבועי (SMA 200 - רצפת ברזל ארוכת טווח)", sma200))
    if sma20 and pullback_pct >= 7.5 and (sma50 and sma20 > sma50):
        candidates.append(("ממוצע נע 20 שבועי (SMA 20 - תמיכת מומנטום)", sma20))
    if prev_pivot_support > 0:
        candidates.append(("רמת תמיכה אופקית שבועית (Weekly Demand Zone)", prev_pivot_support))

    matched_support_name = None
    matched_support_price = None

    for name, level in candidates:
        dist_from_close = ((close_price - level) / level) * 100
        dist_from_low = ((low_price - level) / level) * 100

        if (-1.0 <= dist_from_close <= 2.3) or (-1.5 <= dist_from_low <= 1.2 and close_price >= level * 0.99):
            matched_support_name = name
            matched_support_price = level
            break

    if not matched_support_name:
        return None

    # חישוב רמות לעסקת הסווינג (יחס סיכוי/סיכון)
    invalidation_level = min(low_price * 0.97, matched_support_price - (0.85 * atr))
    target_1 = close_price + (recent_high - close_price) * 0.6
    target_2 = recent_high

    risk_pct = ((close_price - invalidation_level) / close_price) * 100
    reward_pct = ((target_2 - close_price) / close_price) * 100
    rr_ratio = (reward_pct / risk_pct) if risk_pct > 0 else 2.0

    return {
        "close": close_price,
        "recent_high": recent_high,
        "pullback_pct": pullback_pct,
        "support_name": matched_support_name,
        "support_price": matched_support_price,
        "rsi": rsi,
        "atr": atr,
        "sma20": sma20,
        "sma50": sma50,
        "sma100": sma100,
        "sma200": sma200,
        "invalidation": invalidation_level,
        "target_1": target_1,
        "target_2": target_2,
        "reward_pct": reward_pct,
        "rr_ratio": rr_ratio
    }

# ==========================================
# יצירת גרף שבועי מעוצב עם סימון אזור התמיכה
# ==========================================
def generate_support_chart(df, ticker, info):
    plot_df = df.tail(65).copy()

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

    marker_series = pd.Series(np.nan, index=plot_df.index)
    marker_series.iloc[-1] = plot_df['Low'].iloc[-1] * 0.965

    apds = [
        mpf.make_addplot(marker_series, type='scatter', markersize=150, marker='^', color='#00E5FF', panel=0),
        mpf.make_addplot(plot_df['RSI'], panel=2, color='#E040FB', ylabel='Weekly RSI', width=1.3, ylim=(20, 85))
    ]

    if not plot_df['SMA20'].isna().all():
        apds.append(mpf.make_addplot(plot_df['SMA20'], color='#2962FF', width=1.2, panel=0))
    if not plot_df['SMA50'].isna().all():
        apds.append(mpf.make_addplot(plot_df['SMA50'], color='#FF9100', width=1.6, panel=0))
    if not plot_df['SMA100'].isna().all():
        apds.append(mpf.make_addplot(plot_df['SMA100'], color='#00E676', width=1.4, panel=0))
    if not plot_df['SMA200'].isna().all():
        apds.append(mpf.make_addplot(plot_df['SMA200'], color='#FF1744', width=1.8, panel=0))

    rsi_70 = pd.Series(70, index=plot_df.index)
    rsi_30 = pd.Series(30, index=plot_df.index)
    apds.append(mpf.make_addplot(rsi_70, panel=2, color='#5D606B', linestyle=':', width=0.8))
    apds.append(mpf.make_addplot(rsi_30, panel=2, color='#5D606B', linestyle=':', width=0.8))

    buf = io.BytesIO()
    fig, axes = mpf.plot(
        plot_df,
        type='candle',
        style=style,
        volume=True,
        volume_panel=1,
        addplot=apds,
        hlines=dict(
            hlines=[info["support_price"], info["invalidation"], info["target_2"]],
            colors=['#00E5FF', '#FF5252', '#FFD700'],
            linestyle=['--', ':', '-.'],
            linewidths=[2.2, 1.3, 1.5]
        ),
        figsize=(13, 8),
        panel_ratios=(6, 1.8, 2),
        tight_layout=True,
        returnfig=True
    )

    axes[0].set_title(
        f"{ticker} • WEEKLY (1W) SWING SUPPORT  |  Price: ${info['close']:.2f} (-{info['pullback_pct']:.1f}% from High)  |  RSI: {info['rsi']:.1f}",
        color='white', fontsize=13, fontweight='bold', pad=14, loc='left'
    )

    legend_text = (
        f"── Key Support Zone: ${info['support_price']:.2f} (Cyan)\n"
        f"── Swing Target (Recent High): ${info['target_2']:.2f} (Gold)\n"
        f"── Invalidation (Stop Zone): ${info['invalidation']:.2f} (Red)\n"
        f"── SMA20 (Blue) | SMA50 (Orange) | SMA100 (Green) | SMA200 (Red)"
    )
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
# שליחת כרטיסיית הניתוח לחדר הסווינג בדיסקורד
# ==========================================
def send_support_alert(ticker, info, chart_buf):
    description = (
        f"**מחיר נוכחי:** `${info['close']:.2f}`  •  **תיקון מהשיא:** `-{info['pullback_pct']:.1f}%`  •  **טווח:** `גרף שבועי (1W)`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**🛡️ הסטאפ הטכני לסווינג (Weekly Pullback to Support):**\n"
        f"נכס מוביל במגמה חיובית ראשית שהשלים תיקון בריא מהשיא האחרון (`${info['recent_high']:.2f}`) "
        f"והגיע כעת אל **{info['support_name']}** באזור **`${info['support_price']:.2f}`**.\n\n"
        f"**📊 נתוני מומנטום ומבנה מחיר:**\n"
        f"• **מדד עוצמה שבועי (Weekly RSI):** `{info['rsi']:.1f}` (התקררות אידיאלית לאיסוף סווינג)\n"
        f"• **פוטנציאל חזרה לשיא האחרון:** `+{info['reward_pct']:.1f}%`\n"
        f"• **יחס סיכוי/סיכון משוער (R:R):** `1:{info['rr_ratio']:.1f}`\n\n"
        f"**🎯 רמות מפתח לתכנון העסקה (Key Swing Levels):**\n"
        f"• **אזור תמיכה מרכזי (קו תכלת):** `${info['support_price']:.2f}`\n"
        f"• **שלילת הסטאפ / שבירת תמיכה (קו אדום):** סגירה שבועית מתחת ל-`${info['invalidation']:.2f}`\n"
        f"• **יעד סווינג 1 (אזור התנגדות ביניים):** `${info['target_1']:.2f}`\n"
        f"• **יעד סווינג 2 (בדיקת השיא השבועי - קו זהב):** `${info['target_2']:.2f}`"
    )

    embed = {
        "title": f"🛡️ נכס חזק בתמיכה שבועית (סטאפ סווינג) | ${ticker}",
        "color": 58879,
        "description": description,
        "image": {"url": f"attachment://{ticker}_weekly_support.png"},
        "footer": {
            "text": f"Ilan VIP • Quantum Swing Support Scanner • {datetime.now().strftime('%d/%m/%Y %H:%M')} | אינו מהווה המלצה"
        }
    }

    payload = {
        "username": "Quantum Swing Scanner | Ilan VIP",
        "embeds": [embed]
    }

    files = {
        "file": (f"{ticker}_weekly_support.png", chart_buf, "image/png")
    }

    requests.post(SUPPORT_WEBHOOK_URL, data={"payload_json": json.dumps(payload)}, files=files, timeout=30)

# ==========================================
# פונקציית הרצה ראשית
# ==========================================
def run_support_scanner():
    print(f"Scanning {len(STRONG_ASSETS)} strong assets for Weekly Support pullbacks...")
    sent_this_week = load_support_cache()
    alerts_sent = 0

    for ticker in STRONG_ASSETS:
        try:
            if ticker in sent_this_week or alerts_sent >= 5:
                continue

            df_w = yf.download(ticker, period="5y", interval="1wk", progress=False, auto_adjust=True)
            if isinstance(df_w.columns, pd.MultiIndex):
                df_w.columns = df_w.columns.get_level_values(0)

            if not df_w.empty:
                df_w = calculate_weekly_indicators(df_w)
                setup = detect_weekly_support_setup(df_w)
                if setup:
                    print(f"[!] Weekly Support Setup Found: {ticker} at {setup['support_name']}")
                    chart = generate_support_chart(df_w, ticker, setup)
                    send_support_alert(ticker, setup, chart)
                    sent_this_week.add(ticker)
                    alerts_sent += 1
                    time.sleep(2)

        except Exception as e:
            print(f"Error scanning {ticker}: {e}")

    save_support_cache(sent_this_week)
    print(f"Weekly Support scan complete. Sent {alerts_sent} setups.")

if __name__ == "__main__":
    run_support_scanner()
