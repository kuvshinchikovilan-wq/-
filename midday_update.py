import os
import base64
import requests
from datetime import datetime
import pytz
import yfinance as yf
from playwright.sync_api import sync_playwright

# משתמש באותו Webhook (או ב-DISCORD_WEBHOOK_MIDDAY אם תרצה ערוץ נפרד)
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_MIDDAY") or os.environ.get("DISCORD_WEBHOOK_MORNING")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

INDICES = [
    {"symbol": "^GSPC", "name": "S&P 500", "tag": "SPX"},
    {"symbol": "^IXIC", "name": "NASDAQ", "tag": "NDX"},
    {"symbol": "^DJI", "name": "DOW JONES", "tag": "DJI"},
    {"symbol": "^RUT", "name": "RUSSELL 2000", "tag": "RUT"},
]

MACRO_ASSETS = [
    {"symbol": "^VIX", "name": "VIX (FEAR INDEX)"},
    {"symbol": "^TNX", "name": "US 10Y YIELD"},
    {"symbol": "DX-Y.NYB", "name": "US DOLLAR (DXY)"},
    {"symbol": "GC=F", "name": "GOLD FUTURES"},
    {"symbol": "CL=F", "name": "CRUDE OIL (WTI)"},
    {"symbol": "BTC-USD", "name": "BITCOIN (BTC)"},
]

WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA", "GOOGL", "AMD", "NFLX", "AVGO",
    "PLTR", "SMCI", "COIN", "MSTR", "CRM", "ORCL", "INTC", "MU", "ARM", "PANW",
    "CRWD", "SNOW", "UBER", "SHOP", "JPM", "GS", "BAC", "V", "MA", "LLY",
    "UNH", "XOM", "CVX", "BA", "DIS", "PYPL", "SQ", "BABA", "NIO", "SOFI"
]

def get_logo_base64():
    for fname in ["logo.jpg", "logo.png", "logo.jpeg", "LOGO.jpg", "LOGO.png"]:
        if os.path.exists(fname):
            with open(fname, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                ext = "png" if fname.lower().endswith("png") else "jpeg"
                return f"data:image/{ext};base64,{encoded}"
    return ""

def fetch_quote(sym):
    try:
        t = yf.Ticker(sym)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            curr = float(hist["Close"].iloc[-1])
            pct = ((curr - prev) / prev) * 100
            return curr, pct
    except Exception as e:
        print(f"Quote error {sym}: {e}")
    return None, None

def get_market_data():
    indices_data = []
    for item in INDICES:
        price, pct = fetch_quote(item["symbol"])
        if price is not None:
            indices_data.append({
                "name": item["name"],
                "tag": item["tag"],
                "price": f"{price:,.2f}",
                "pct": pct
            })

    macro_data = []
    for item in MACRO_ASSETS:
        price, pct = fetch_quote(item["symbol"])
        if price is not None:
            p_str = f"{price:,.2f}%" if item["symbol"] == "^TNX" else (f"${price:,.0f}" if price > 1000 else f"{price:,.2f}")
            macro_data.append({
                "name": item["name"],
                "price": p_str,
                "pct": pct
            })

    movers = []
    try:
        data = yf.download(WATCHLIST, period="5d", progress=False, group_by="ticker")
        for sym in WATCHLIST:
            try:
                df = data[sym].dropna(subset=["Close"])
                if len(df) >= 2:
                    prev = float(df["Close"].iloc[-2])
                    curr = float(df["Close"].iloc[-1])
                    pct = ((curr - prev) / prev) * 100
                    movers.append({
                        "symbol": sym,
                        "price": f"${curr:,.2f}",
                        "pct": pct,
                        "logo": f"https://financialmodelingprep.com/image-stock/{sym}.png"
                    })
            except:
                continue
    except Exception as e:
        print(f"Error downloading movers: {e}")

    movers.sort(key=lambda x: x["pct"], reverse=True)
    gainers = [m for m in movers if m["pct"] > 0][:5]
    losers = sorted([m for m in movers if m["pct"] < 0], key=lambda x: x["pct"])[:5]

    return indices_data, macro_data, gainers, losers

def build_html(indices, macro, gainers, losers):
    now_il = datetime.now(ISRAEL_TZ)
    date_display = now_il.strftime("%d / %m / %Y")
    time_display = now_il.strftime("%H:%M")
    logo_src = get_logo_base64()
    logo_html = f'<img src="{logo_src}" class="brand-logo" />' if logo_src else '<div class="brand-fallback">IK</div>'

    # מדדים
    idx_cards = ""
    for idx in indices:
        is_up = idx["pct"] >= 0
        cls = "up" if is_up else "down"
        sign = "+" if is_up else ""
        arrow = "▲" if is_up else "▼"
        idx_cards += f"""
        <div class="idx-card {cls}-border">
            <div class="idx-top">
                <span class="idx-name">{idx['name']}</span>
                <span class="idx-tag">{idx['tag']}</span>
            </div>
            <div class="idx-price">{idx['price']}</div>
            <div class="idx-pct {cls}-badge">{arrow} {sign}{idx['pct']:.2f}%</div>
        </div>
        """

    # מאקרו
    macro_cards = ""
    for m in macro:
        is_up = m["pct"] >= 0
        cls = "up" if is_up else "down"
        sign = "+" if is_up else ""
        macro_cards += f"""
        <div class="macro-pill">
            <div class="mp-name">{m['name']}</div>
            <div class="mp-bottom">
                <span class="mp-price">{m['price']}</span>
                <span class="mp-pct {cls}-text">{sign}{m['pct']:.2f}%</span>
            </div>
        </div>
        """

    def render_movers(items, is_gainer=True):
        if not items:
            return '<div class="empty">No Data Available</div>'
        html = ""
        for it in items:
            cls = "up" if is_gainer else "down"
            sign = "+" if it["pct"] >= 0 else ""
            html += f"""
            <div class="mover-row">
                <div class="mover-left">
                    <div class="t-logo-wrap">
                        <img src="{it['logo']}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" class="t-logo" />
                        <div class="t-fallback" style="display:none;">{it['symbol'][0]}</div>
                    </div>
                    <div>
                        <div class="t-sym">${it['symbol']}</div>
                        <div class="t-price">{it['price']}</div>
                    </div>
                </div>
                <div class="mover-pct {cls}-badge">{sign}{it['pct']:.2f}%</div>
            </div>
            """
        return html

    gainers_html = render_movers(gainers, True)
    losers_html = render_movers(losers, False)

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800;900&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                width: 1200px;
                min-height: 1450px;
                font-family: 'Montserrat', sans-serif;
                background: radial-gradient(circle at 50% 0%, #162447 0%, #0a0f1d 55%, #050811 100%);
                color: #ffffff;
                padding: 45px;
                position: relative;
            }}
            .glow-top {{
                position: absolute; top: -180px; left: 50%; transform: translateX(-50%);
                width: 750px; height: 380px;
                background: radial-gradient(circle, rgba(212,175,55,0.22) 0%, rgba(0,0,0,0) 70%);
                pointer-events: none;
            }}
            .header {{
                display: flex; align-items: center; justify-content: space-between;
                background: linear-gradient(135deg, rgba(23,34,59,0.9) 0%, rgba(12,19,34,0.95) 100%);
                border: 2px solid rgba(212, 175, 55, 0.45);
                border-radius: 26px;
                padding: 28px 40px;
                box-shadow: 0 20px 50px rgba(0,0,0,0.6);
                margin-bottom: 32px;
            }}
            .header-left {{ display: flex; align-items: center; gap: 28px; }}
            .brand-logo {{
                width: 115px; height: 115px; border-radius: 22px;
                object-fit: cover; border: 2.5px solid #e5c158;
                box-shadow: 0 0 28px rgba(229, 193, 88, 0.35);
            }}
            .brand-fallback {{
                width: 115px; height: 115px; border-radius: 22px;
                background: linear-gradient(135deg, #d4af37, #aa7c11);
                display: flex; align-items: center; justify-content: center;
                font-size: 44px; font-weight: 900; color: #080d1a;
            }}
            .title-group h1 {{
                font-size: 42px; font-weight: 900; letter-spacing: 1.5px;
                background: linear-gradient(90deg, #fff6d6 0%, #e5c158 50%, #c59b27 100%);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            }}
            .title-group p {{
                font-size: 18px; font-weight: 700; color: #94a3b8;
                letter-spacing: 3px; margin-top: 8px;
            }}
            .date-box {{
                text-align: right;
                background: rgba(212, 175, 55, 0.1);
                border: 1px solid rgba(212, 175, 55, 0.35);
                padding: 16px 26px; border-radius: 18px;
            }}
            .date-day {{ font-size: 15px; font-weight: 800; color: #e5c158; letter-spacing: 2px; }}
            .date-str {{ font-size: 25px; font-weight: 800; color: #ffffff; margin-top: 4px; }}

            /* INDICES */
            .idx-grid {{
                display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px;
                margin-bottom: 32px;
            }}
            .idx-card {{
                background: linear-gradient(180deg, rgba(21, 31, 54, 0.9) 0%, rgba(12, 18, 32, 0.95) 100%);
                border-radius: 22px; padding: 24px 22px;
                box-shadow: 0 14px 30px rgba(0,0,0,0.45);
                border: 1px solid rgba(255,255,255,0.08);
            }}
            .up-border {{ border-top: 3px solid #10b981; }}
            .down-border {{ border-top: 3px solid #ef4444; }}
            .idx-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
            .idx-name {{ font-size: 16px; font-weight: 800; color: #cbd5e1; letter-spacing: 1px; }}
            .idx-tag {{ font-size: 12px; font-weight: 800; color: #e5c158; background: rgba(229,193,88,0.12); padding: 4px 8px; border-radius: 6px; }}
            .idx-price {{ font-size: 29px; font-weight: 900; color: #ffffff; margin-bottom: 14px; }}
            .idx-pct {{ display: inline-block; padding: 7px 14px; border-radius: 10px; font-size: 18px; font-weight: 800; }}

            .up-badge {{ background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
            .down-badge {{ background: rgba(239, 68, 68, 0.18); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
            .up-text {{ color: #34d399; }}
            .down-text {{ color: #f87171; }}

            /* CARD */
            .card {{
                background: linear-gradient(180deg, rgba(19, 28, 49, 0.88) 0%, rgba(11, 17, 30, 0.92) 100%);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-top: 2px solid rgba(229, 193, 88, 0.5);
                border-radius: 24px; padding: 28px 32px;
                box-shadow: 0 18px 40px rgba(0,0,0,0.5);
                margin-bottom: 32px;
            }}
            .card-header {{
                display: flex; align-items: center; justify-content: space-between;
                margin-bottom: 22px; padding-bottom: 14px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }}
            .card-title {{ font-size: 23px; font-weight: 800; display: flex; align-items: center; gap: 12px; }}
            .dot {{ width: 12px; height: 24px; border-radius: 6px; }}
            .gold-dot {{ background: linear-gradient(180deg, #fceabb, #d4af37); box-shadow: 0 0 12px rgba(212,175,55,0.6); }}
            .green-dot {{ background: linear-gradient(180deg, #6ee7b7, #10b981); box-shadow: 0 0 12px rgba(16,185,129,0.6); }}
            .red-dot {{ background: linear-gradient(180deg, #fca5a5, #ef4444); box-shadow: 0 0 12px rgba(239,68,68,0.6); }}

            /* MACRO PILLS */
            .macro-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
            .macro-pill {{
                background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.06);
                border-radius: 16px; padding: 18px 22px;
            }}
            .mp-name {{ font-size: 14px; font-weight: 800; color: #94a3b8; letter-spacing: 1px; margin-bottom: 10px; }}
            .mp-bottom {{ display: flex; justify-content: space-between; align-items: baseline; }}
            .mp-price {{ font-size: 24px; font-weight: 900; color: #ffffff; }}
            .mp-pct {{ font-size: 18px; font-weight: 800; }}

            /* MOVERS */
            .movers-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }}
            .mover-row {{
                display: flex; align-items: center; justify-content: space-between;
                background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.06);
                border-radius: 18px; padding: 14px 20px; margin-bottom: 14px;
            }}
            .mover-left {{ display: flex; align-items: center; gap: 16px; }}
            .t-logo-wrap {{
                width: 52px; height: 52px; border-radius: 50%; background: #ffffff; padding: 6px;
                display: flex; align-items: center; justify-content: center; overflow: hidden;
            }}
            .t-logo {{ width: 100%; height: 100%; object-fit: contain; }}
            .t-fallback {{
                width: 100%; height: 100%; border-radius: 50%; background: #1e293b; color: #e5c158;
                font-size: 22px; font-weight: 900; align-items: center; justify-content: center;
            }}
            .t-sym {{ font-size: 23px; font-weight: 900; color: #ffffff; }}
            .t-price {{ font-size: 16px; font-weight: 600; color: #94a3b8; margin-top: 2px; }}
            .mover-pct {{ padding: 8px 16px; border-radius: 12px; font-size: 20px; font-weight: 800; }}

            .footer {{
                text-align: center; margin-top: 8px;
                font-size: 15px; font-weight: 800; color: #64748b; letter-spacing: 3px;
            }}
            .footer span {{ color: #e5c158; }}
        </style>
    </head>
    <body>
        <div class="glow-top"></div>

        <div class="header">
            <div class="header-left">
                {logo_html}
                <div class="title-group">
                    <h1>ILAN.KUV VIP</h1>
                    <p>MID-DAY MARKET SNAPSHOT &bull; LIVE PULSE</p>
                </div>
            </div>
            <div class="date-box">
                <div class="date-day">ISRAEL TIME {time_display}</div>
                <div class="date-str">{date_display}</div>
            </div>
        </div>

        <div class="idx-grid">
            {idx_cards}
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title"><div class="dot gold-dot"></div> MACRO, YIELDS &amp; COMMODITIES</div>
                <div style="font-size:14px; font-weight:800; color:#e5c158; letter-spacing:1.5px;">REAL-TIME METRICS</div>
            </div>
            <div class="macro-grid">
                {macro_cards}
            </div>
        </div>

        <div class="movers-grid">
            <div class="card" style="margin-bottom:0; border-top-color: rgba(16, 185, 129, 0.5);">
                <div class="card-header">
                    <div class="card-title"><div class="dot green-dot"></div> TOP GAINERS (WATCHLIST)</div>
                </div>
                {gainers_html}
            </div>

            <div class="card" style="margin-bottom:0; border-top-color: rgba(239, 68, 68, 0.5);">
                <div class="card-header">
                    <div class="card-title"><div class="dot red-dot"></div> TOP LOSERS (WATCHLIST)</div>
                </div>
                {losers_html}
            </div>
        </div>

        <div class="footer">
            <span>ILAN.KUV</span> &bull; EXCLUSIVE TRADING COMMUNITY &bull; MARKET INTELLIGENCE
        </div>
    </body>
    </html>
    """

def generate_poster(html_content):
    output_path = "midday_update.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1450}, device_scale_factor=2)
        page.set_content(html_content, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path

def send_to_discord(image_path):
    if not WEBHOOK_URL:
        print("Error: Webhook URL not set!")
        return
    now_il = datetime.now(ISRAEL_TZ).strftime("%H:%M")
    payload = {
        "content": f"⚡ **עדכון אמצע יום המסחר בוול סטריט ({now_il}) – תמונת מצב מדדים, מאקרו והמניות הבולטות:**"
    }
    with open(image_path, "rb") as f:
        files = {"file": ("midday_update.png", f, "image/png")}
        requests.post(WEBHOOK_URL, data=payload, files=files)

if __name__ == "__main__":
    idx, macro, gainers, losers = get_market_data()
    html = build_html(idx, macro, gainers, losers)
    img_file = generate_poster(html)
    send_to_discord(img_file)
