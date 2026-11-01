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
# הגדרות 2 החדרים בדיסקורד (Webhooks מעודכנים)
# ==========================================
DAILY_WEBHOOK_URL = "https://discord.com/api/webhooks/1566315887286296596/meUNLSkQiAd3QDPoB8NmbXQ5iy3wK23FqInNtNoaoQSIl7Co6Xuk7XlHsBCmnaG5Cs-w"
WEEKLY_WEBHOOK_URL = "https://discord.com/api/webhooks/1566319961473814690/AmghSzUjmGiRCXd-4QInHE3X8dwcAzRaqqMwAKRLdo3WCW0eSlP7hmZKbeAtQGP2pcG9"

# ==========================================
# יקום מניות מורחב (~170 מניות סחירות ומומנטום)
# ==========================================
WATCHLIST = [
    # Mega Caps & Tech Giants
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "NFLX", "AVGO", "ORCL", "CRM", "ADBE", "CSCO", "IBM", "INTU", "NOW",
    # Semiconductors & AI Hardware
    "AMD", "ARM", "SMCI", "MU", "TSM", "ASML", "QCOM", "INTC", "MRVL", "AMAT", "LRCX", "KLAC", "TXN", "ADI", "NXPI", "ON", "MPWR", "TER", "ENTG", "VRT", "DELL", "HPE", "ANET",
    # Cyber, Cloud & Software Momentum
    "PLTR", "CRWD", "PANW", "FTNT", "ZS", "OKTA", "S", "CYBR", "SNOW", "DDOG", "NET", "MDB", "TEAM", "HUBS", "WDAY", "TTD", "APP", "U", "IOT", "DUOL", "CFLT", "PATH", "DOCN", "GTLB",
    # Crypto, Fintech & High-Beta Growth
    "COIN", "MSTR", "MARA", "RIOT", "CLSK", "IREN", "CORZ", "WULF", "HOOD", "SOFI", "AFRM", "UPST", "XYZ", "PYPL", "NU", "MELI", "SE", "SHOP", "UBER", "LYFT", "ABNB", "DASH", "ROKU", "RBLX", "RDDT", "CVNA", "DKNG", "HIMS", "CELH", "ONON", "DECK",
    # EV, Space, Clean Energy & Next-Gen
    "RIVN", "LCID", "NIO", "XPEV", "LI", "RKLB", "ASTS", "LUNR", "JOBY", "ACHR", "IONQ", "RGTI", "QBTS", "SMR", "OKLO", "CEG", "VST", "FSLR", "ENPH", "SEDG", "ALB",
    # Financials & Wall Street
    "JPM", "GS", "MS", "BAC", "C", "WFC", "BLK", "BX", "KKR", "APO", "V", "MA", "AXP", "SPGI", "ICE", "CME",
    # Retail, Consumer & Entertainment
    "WMT", "COST", "TGT", "HD", "LOW", "NKE", "SBUX", "MCD", "CMG", "DIS", "SPOT", "LYV", "LULU", "CROX", "ELF",
    # Healthcare, Biotech & Pharma
    "LLY", "NVO", "UNH", "ISRG", "VRTX", "REGN", "AMGN", "GILD", "MRNA", "BNTX", "VKTX", "ABBV", "PFE", "MRK", "TMO", "DHR", "DXCM",
    # Industrials, Defense, Energy & Commodities
    "CAT", "DE", "GE", "BA", "LMT", "RTX", "NOC", "GD", "AXON", "URI", "PWR", "ETN", "PH", "XOM", "CVX", "COP", "SLB", "OXY", "HAL", "FCX", "NEM", "GOLD", "AA", "CCJ",
    # Key Market & Sector ETFs
    "SPY", "QQQ", "IWM", "DIA", "SOXX", "SMH", "IGV", "XLF", "XLE", "XLV", "XLI", "XBI", "ARKK", "GDX", "TAN", "URA", "IBIT"
]

# ==========================================
# מנגנון זיכרון למניעת כפילויות (יומי ושבועי)
# ==========================================
CACHE_FILE = "sent_breakouts.json"

def load_sent_cache():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_str = datetime.now(timezone.utc).strftime("%Y-W%W")
    
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                daily_sent = set(data.get("daily", [])) if data.get("date") == today_str else set()
                weekly_sent = set(data.get("weekly", [])) if data.get("week") == week_str else set()
                return daily_sent, weekly_sent
        except Exception:
            pass
    return set(), set()

def save_sent_cache(daily_set, weekly_set):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week_str = datetime.now(timezone.utc).strftime("%Y-W%W")
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({
                "date": today_str,
                "week": week_str,
                "daily": sorted(list(daily_set)),
                "weekly": sorted(list(weekly_set))
            }, f, indent=2)
    except Exception as e:
        print(f"Cache save error: {e}")

# ==========================================
# חישוב אינדיקטורים טכניים
# ==========================================
def calculate_indicators(df):
    df = df.copy()
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
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
# לוגיקת זיהוי פריצה חיה (Live Intraday & Weekly)
# ==========================================
def detect_live_breakout(df, timeframe="1D", lookback=25):
    if len(df) < lookback + 5:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # רמת ההתנגדות של X הנרות הקודמים (ללא הנר הנוכחי)
    window = df.iloc[-(lookback + 1):-1]
    resistance_price = float(window['High'].max())
    resistance_date = window['High'].idxmax()

    current_price = float(curr['Close'])
    current_high = float(curr['High'])
    prev_close = float(prev['Close'])
    open_price = float(curr['Open'])
    low_price = float(curr['Low'])

    curr_vol = float(curr['Volume'])
    avg_vol = float(curr['Vol_SMA20']) if curr['Vol_SMA20'] > 0 else 1.0
    rvol = (curr_vol / avg_vol) * 100

    rsi = float(curr['RSI']) if not np.isnan(curr['RSI']) else 55.0
    atr = float(curr['ATR']) if not np.isnan(curr['ATR']) else (current_price * 0.025)
    ema20 = float(curr['EMA20'])
    sma50 = float(curr['SMA50']) if not np.isnan(curr['SMA50']) else ema20
    sma200 = float(curr['SMA200']) if not np.isnan(curr['SMA200']) else sma50

    change_pct = ((current_price - prev_close) / prev_close) * 100
    
    # תנאי פריצה בזמן אמת:
    # 1. המחיר נסחר כעת מעל רמת ההתנגדות הקריטית
    # 2. הנר הקודם סגר מתחת להתנגדות (פריצה טרייה שמתרחשת עכשיו)
    # 3. נר ירוק בעלייה של לפחות 1.0%
    is_breaking_now = (current_price > resistance_price) and (prev_close <= resistance_price * 1.004)
    is_green_momentum = (current_price > open_price) and (change_pct >= 1.0)

    if is_breaking_now and is_green_momentum:
        breakout_pct = ((current_price - resistance_price) / resistance_price) * 100
        invalidation_level = min(low_price, resistance_price - (0.6 * atr))
        target_1 = current_price + (1.5 * atr)
        target_2 = current_price + (3.0 * atr)

        return {
            "timeframe": timeframe,
            "lookback": lookback,
            "close": current_price,
            "high": current_high,
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
            "target_2": target_2
        }
    return None

# ==========================================
# יצירת גרף מעוצב (Ilan VIP Dark Theme)
# ==========================================
def generate_breakout_chart(df, ticker, info):
    plot_bars = 65 if info["timeframe"] == "1D" else 52
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

    # חץ ירוק בולט מתחת לנר הפורץ
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

    rsi_70 = pd.Series(70, index=plot_df.index)
    rsi_30 = pd.Series(30, index=plot_df.index)
    apds.append(mpf.make_addplot(rsi_70, panel=2, color='#5D606B', linestyle=':', width=0.8))
    apds.append(mpf.make_addplot(rsi_30, panel=2, color='#5D606B', linestyle=':', width=0.8))

    tf_label = "DAILY (1D) LIVE BREAKOUT" if info["timeframe"] == "1D" else "WEEKLY (1W) MACRO BREAKOUT"

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

    axes[0].set_title(
        f"{ticker} • {tf_label}  |  Price: ${info['close']:.2f} (+{info['change_pct']:.2f}%)  |  RSI: {info['rsi']:.1f}",
        color='white', fontsize=13, fontweight='bold', pad=14, loc='left'
    )

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

    fig.text(
        0.5, 0.56, 'Ilan.Kuv  |  Quantum VIP',
        fontsize=30, color='white', ha='center', va='center', alpha=0.07, weight='bold'
    )

    fig.savefig(buf, format='png', dpi=160, bbox_inches='tight', facecolor='#0B0E14')
    buf.seek(0)
    return buf

# ==========================================
# שליחת ההתראה לחדר המתאים בדיסקורד
# ==========================================
def send_discord_alert(ticker, info, chart_buf, webhook_url):
    is_daily = info["timeframe"] == "1D"
    tf_heb = "גרף יומי (1D)" if is_daily else "גרף שבועי (1W)"
    period_heb = f"{info['lookback']} ימי המסחר" if is_daily else f"{info['lookback']} השבועות"
    embed_color = 65416 if is_daily else 16766720  # ירוק זוהר ליומי, זהב יוקרתי לשבועי
    icon = "🚀" if is_daily else "💎"

    trend_status = "מעל הממוצעים המרכזיים (20, 50, 200) - מגמה שורית" if info['close'] > info['sma200'] else "מומנטום חיובי מעל ממוצע 20"

    description = (
        f"**מחיר בזמן אמת:** `${info['close']:.2f}` (`+{info['change_pct']:.2f}%`)  •  **טווח:** `{tf_heb}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**📐 הסטאפ הטכני (Live Breakout Setup):**\n"
        f"המניה פורצת כעת בזמן אמת את רמת ההתנגדות הקריטית ב-**`${info['resistance']:.2f}`** "
        f"(שיא של {period_heb} האחרונים מאז `{info['resistance_date']}`). "
        f"המחיר נסחר כעת ב-`+{info['breakout_pct']:.2f}%` מעל נקודת הפריצה.\n\n"
        f"**📊 נתוני מומנטום ואינדיקטורים:**\n"
        f"• **מדד עוצמה (RSI 14):** `{info['rsi']:.1f}`\n"
        f"• **קצב נפח מסחר (RVOL):** `{info['rvol']:.0f}%` ביחס לממוצע\n"
        f"• **מיקום ממוצעים:** {trend_status}\n"
        f"• **טווח תנועה ממוצע (ATR):** `${info['atr']:.2f}`\n\n"
        f"**🎯 רמות מפתח על הגרף:**\n"
        f"• **קו הפריצה (הופך לתמיכה - זהב):** `${info['resistance']:.2f}`\n"
        f"• **רמת שלילת הסטאפ (Invalidation - אדום):** `${info['invalidation']:.2f}`\n"
        f"• **יעד טכני 1 (תכלת):** `${info['target_1']:.2f}`\n"
        f"• **יעד טכני 2:** `${info['target_2']:.2f}`"
    )

    embed = {
        "title": f"{icon} פריצת התנגדות בזמן אמת | ${ticker} ({tf_heb})",
        "color": embed_color,
        "description": description,
        "image": {"url": f"attachment://{ticker}_{info['timeframe']}.png"},
        "footer": {
            "text": f"Ilan VIP • Quantum Breakout Live • {datetime.now().strftime('%d/%m/%Y %H:%M')} | אינו מהווה המלצה"
        }
    }

    payload = {
        "username": "Quantum Breakout Scanner | Ilan VIP",
        "embeds": [embed]
    }

    files = {
        "file": (f"{ticker}_{info['timeframe']}.png", chart_buf, "image/png")
    }

    requests.post(webhook_url, data={"payload_json": json.dumps(payload)}, files=files, timeout=30)

# ==========================================
# פונקציית הרצה ראשית (מפוצלת ל-2 החדרים)
# ==========================================
def run_scanner():
    print(f"Starting Live Breakout Scanner on {len(WATCHLIST)} stocks...")
    daily_sent, weekly_sent = load_sent_cache()
    daily_count = 0
    weekly_count = 0

    for ticker in WATCHLIST:
        try:
            # --- 1. סריקת גרף יומי (לחדר פריצות יומי) ---
            if ticker not in daily_sent and daily_count < 6:
                df_d = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
                if isinstance(df_d.columns, pd.MultiIndex):
                    df_d.columns = df_d.columns.get_level_values(0)

                if not df_d.empty:
                    df_d = calculate_indicators(df_d)
                    b_daily = detect_live_breakout(df_d, timeframe="1D", lookback=25)
                    if b_daily:
                        print(f"[!] LIVE DAILY Breakout: {ticker}")
                        chart = generate_breakout_chart(df_d, ticker, b_daily)
                        send_discord_alert(ticker, b_daily, chart, DAILY_WEBHOOK_URL)
                        daily_sent.add(ticker)
                        daily_count += 1
                        time.sleep(2)

            # --- 2. סריקת גרף שבועי (לחדר פריצות שבועי) ---
            if ticker not in weekly_sent and weekly_count < 4:
                df_w = yf.download(ticker, period="3y", interval="1wk", progress=False, auto_adjust=True)
                if isinstance(df_w.columns, pd.MultiIndex):
                    df_w.columns = df_w.columns.get_level_values(0)

                if not df_w.empty:
                    df_w = calculate_indicators(df_w)
                    b_weekly = detect_live_breakout(df_w, timeframe="1W", lookback=16)
                    if b_weekly:
                        print(f"[!] LIVE WEEKLY Breakout: {ticker}")
                        chart = generate_breakout_chart(df_w, ticker, b_weekly)
                        send_discord_alert(ticker, b_weekly, chart, WEEKLY_WEBHOOK_URL)
                        weekly_sent.add(ticker)
                        weekly_count += 1
                        time.sleep(2)

        except Exception as e:
            print(f"Error on {ticker}: {e}")

    save_sent_cache(daily_sent, weekly_sent)
    print(f"Scan finished. Sent {daily_count} Daily alerts and {weekly_count} Weekly alerts.")

if __name__ == "__main__":
    run_scanner()
