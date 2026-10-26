import os
import base64
import requests
from datetime import datetime
import pytz
import yfinance as yf
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_MIDDAY") or os.environ.get("DISCORD_WEBHOOK_MORNING")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

INDICES = [
    {"symbol": "^GSPC", "name": "S&P 500", "tag": "SPX"},
    {"symbol": "^IXIC", "name": "NASDAQ", "tag": "NDX"},
    {"symbol": "^DJI", "name": "DOW JONES", "tag": "DJI"},
    {"symbol": "^RUT", "name": "RUSSELL 2K", "tag": "RUT"},
]

SECTORS = [
    {"symbol": "SMH", "name": "Semis"},
    {"symbol": "XLK", "name": "Tech"},
    {"symbol": "XLF", "name": "Financials"},
    {"symbol": "XLE", "name": "Energy"},
    {"symbol": "XLV", "name": "Health"},
    {"symbol": "XLY", "name": "Discret."},
    {"symbol": "XLC", "name": "Comm."},
    {"symbol": "XLI", "name": "Industrial"},
    {"symbol": "XLP", "name": "Staples"},
    {"symbol": "XLU", "name": "Utilities"},
    {"symbol": "XLRE", "name": "Real Est."},
    {"symbol": "XLB", "name": "Materials"},
]

MACRO_ASSETS = [
    {"symbol": "^VIX", "name": "VIX (FEAR)", "type": "num"},
    {"symbol": "DX-Y.NYB", "name": "DOLLAR (DXY)", "type": "num"},
    {"symbol": "^TNX", "name": "US 10Y YIELD", "type": "yield"},
    {"symbol": "^TYX", "name": "US 30Y YIELD", "type": "yield"},
    {"symbol": "TLT", "name": "TLT (20Y+ BOND)", "type": "price"},
    {"symbol": "GC=F", "name": "GOLD", "type": "price"},
    {"symbol": "SI=F", "name": "SILVER", "type": "price"},
    {"symbol": "CL=F", "name": "CRUDE OIL", "type": "price"},
    {"symbol": "HG=F", "name": "COPPER", "type": "price"},
    {"symbol": "NG=F", "name": "NAT. GAS", "type": "price"},
    {"symbol": "BTC-USD", "name": "BITCOIN", "type": "crypto"},
    {"symbol": "ETH-USD", "name": "ETHEREUM", "type": "crypto"},
]

WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA", "GOOGL", "AMD", "NFLX", "AVGO",
    "PLTR", "SMCI", "COIN", "MSTR", "CRM", "ORCL", "INTC", "MU", "ARM", "PANW",
    "CRWD", "SNOW", "UBER", "SHOP", "JPM", "GS", "BAC", "V", "MA", "LLY",
    "UNH", "XOM", "CVX", "BA", "DIS", "PYPL", "SQ", "BABA", "NIO", "SOFI",
    "ASML", "TSM", "QCOM", "AMAT", "LRCX", "NOW", "ADBE", "CAT", "DE", "GE",
    "CEG", "VST", "NEE", "COST", "WMT", "HD", "MCD", "NKE", "SBUX", "ABNB"
]

def get_logo_base64():
    for fname in ["logo.jpg", "logo.png", "logo.jpeg", "LOGO.jpg", "LOGO.png"]:
        if os.path.exists(fname):
            with open(fname, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                ext = "png" if fname.lower().endswith("png") else "jpeg"
                return f"data:image/{ext};base64,{encoded}"
    return ""

def get_all_market_data():
    all_symbols = (
        [x["symbol"] for x in INDICES] +
        [x["symbol"] for x in SECTORS] +
        [x["symbol"] for x in MACRO_ASSETS] +
        WATCHLIST
    )
    data = yf.download(all_symbols, period="5d", progress=False, group_by="ticker")

    def extract_quote(sym):
        try:
            df = data[sym].dropna(subset=["Close"])
            if len(df) >= 2:
                prev = float(df["Close"].iloc[-2])
                curr = float(df["Close"].iloc[-1])
                pct = ((curr - prev) / prev) * 100
                return curr, pct
        except:
            pass
        return None, None

    indices_data = []
    for item in INDICES:
        price, pct = extract_quote(item["symbol"])
        if price is not None:
            indices_data.append({
                "name": item["name"],
                "tag": item["tag"],
                "price": f"{price:,.2f}",
                "pct": pct
            })

    sectors_data = []
    for item in SECTORS:
        price, pct = extract_quote(item["symbol"])
        if price is not None:
            sectors_data.append({
                "symbol": item["symbol"],
                "name": item["name"],
                "pct": pct
            })
    sectors_data.sort(key=lambda x: x["pct"], reverse=True)

    macro_data = []
    for item in MACRO_ASSETS:
        price, pct = extract_quote(item["symbol"])
        if price is not None:
            if item["type"] == "yield":
                p_str = f"{price:,.2f}%"
            elif item["type"] == "crypto":
                p_str = f"${price:,.0f}"
            elif item["type"] == "price":
                p_str = f"${price:,.2f}"
            else:
                p_str = f"{price:,.2f}"
            macro_data.append({
                "name": item["name"],
                "price": p_str,
                "pct": pct
            })

    movers = []
    for sym in WATCHLIST:
        price, pct = extract_quote(sym)
        if price is not None:
            movers.append({
                "symbol": sym,
                "price": f"${price:,.2f}",
                "pct": pct,
                "logo": f"https://financialmodelingprep.com/image-stock/{sym}.png"
            })

    movers.sort(key=lambda x: x["pct"], reverse=True)
    gainers = [m for m in movers if m["pct"] > 0][:5]
    losers = sorted([m for m in movers if m["pct"] < 0], key=lambda x: x["pct"])[:5]

    return indices_data, sectors_data, macro_data, gainers, losers

def build_html(indices, sectors, macro, gainers, losers):
    now_il = datetime.now(ISRAEL_TZ)
    date_display = now_il.strftime("%d/%m/%Y")
    time_display = now_il.strftime("%H:%M")
    logo_src = get_logo_base64()
    logo_html = f'<img src="{logo_src}" class="brand-logo" />' if logo_src else '<div class="brand-fallback">IK</div>'

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
                <span class="idx-pct {cls}-badge">{arrow} {sign}{idx['pct']:.2f}%</span>
            </div>
            <div class="idx-price">{idx['price']}</div>
        </div>
        """

    sec_cards = ""
    max_abs_sec = max([abs(s["pct"]) for s in sectors] + [1.5])
    for s in sectors:
        is_up = s["pct"] >= 0
        cls = "up" if is_up else "down"
        sign = "+" if is_up else ""
        bar_w = min(100, int((abs(s["pct"]) / max_abs_sec) * 100))
        sec_cards += f"""
        <div class="sec-box">
            <div class="sec-top">
                <div>
                    <span class="sec-sym">{s['symbol']}</span>
                    <span class="sec-name">{s['name']}</span>
                </div>
                <span class="sec-pct {cls}-text">{sign}{s['pct']:.2f}%</span>
            </div>
            <div class="sec-bar-bg">
                <div class="sec-bar-fill {cls}-fill" style="width: {bar_w}%;"></div>
            </div>
        </div>
        """

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
                <span class="mp-pct {cls}-badge-sm">{sign}{m['pct']:.2f}%</span>
            </div>
        </div>
        """

    def render_movers(items, is_gainer=True):
        if not items:
            return '<div class="empty">No Data</div>'
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
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800;900&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                width: 1920px;
                height: 1180px;
                font-family: 'Montserrat', sans-serif;
                background: radial-gradient(circle at 50% 0%, #162447 0%, #0a0f1d 60%, #050811 100%);
                color: #ffffff;
                padding: 32px 40px;
                overflow: hidden;
            }}
            /* HEADER */
            .header {{
                display: flex; align-items: center; justify-content: space-between;
                background: linear-gradient(135deg, rgba(23,34,59,0.95) 0%, rgba(12,19,34,0.98) 100%);
                border: 2px solid rgba(212, 175, 55, 0.5);
                border-radius: 22px;
                padding: 18px 32px;
                margin-bottom: 22px;
                box-shadow: 0 15px 35px rgba(0,0,0,0.5);
            }}
            .header-left {{ display: flex; align-items: center; gap: 24px; }}
            .brand-logo {{
                width: 88px; height: 88px; border-radius: 18px;
                object-fit: cover; border: 2.5px solid #e5c158;
            }}
            .brand-fallback {{
                width: 88px; height: 88px; border-radius: 18px;
                background: linear-gradient(135deg, #d4af37, #aa7c11);
                display: flex; align-items: center; justify-content: center;
                font-size: 38px; font-weight: 900; color: #080d1a;
            }}
            .title-group h1 {{
                font-size: 44px; font-weight: 900; letter-spacing: 1.5px;
                background: linear-gradient(90deg, #fff6d6 0%, #e5c158 55%, #c59b27 100%);
                -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            }}
            .title-group p {{
                font-size: 19px; font-weight: 800; color: #94a3b8;
                letter-spacing: 3px; margin-top: 4px;
            }}
            .date-box {{
                text-align: right;
                background: rgba(212, 175, 55, 0.12);
                border: 2px solid rgba(212, 175, 55, 0.4);
                padding: 12px 26px; border-radius: 16px;
            }}
            .date-day {{ font-size: 17px; font-weight: 800; color: #e5c158; letter-spacing: 2px; }}
            .date-str {{ font-size: 28px; font-weight: 900; color: #ffffff; margin-top: 2px; }}

            /* INDICES TOP ROW */
            .idx-grid {{
                display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px;
                margin-bottom: 22px;
            }}
            .idx-card {{
                background: linear-gradient(180deg, rgba(22, 33, 58, 0.95) 0%, rgba(12, 18, 32, 0.98) 100%);
                border-radius: 18px; padding: 18px 24px;
                border: 1px solid rgba(255,255,255,0.1);
                box-shadow: 0 10px 25px rgba(0,0,0,0.4);
            }}
            .up-border {{ border-left: 6px solid #10b981; }}
            .down-border {{ border-left: 6px solid #ef4444; }}
            .idx-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
            .idx-name {{ font-size: 22px; font-weight: 900; color: #e2e8f0; }}
            .idx-price {{ font-size: 36px; font-weight: 900; color: #ffffff; }}
            .idx-pct {{ padding: 6px 14px; border-radius: 10px; font-size: 22px; font-weight: 900; }}

            .up-badge {{ background: rgba(16, 185, 129, 0.22); color: #34d399; border: 1.5px solid rgba(16, 185, 129, 0.5); }}
            .down-badge {{ background: rgba(239, 68, 68, 0.22); color: #f87171; border: 1.5px solid rgba(239, 68, 68, 0.5); }}
            .up-badge-sm {{ background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 4px 10px; border-radius: 8px; font-size: 19px; font-weight: 900; }}
            .down-badge-sm {{ background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 4px 10px; border-radius: 8px; font-size: 19px; font-weight: 900; }}
            .up-text {{ color: #34d399; }}
            .down-text {{ color: #f87171; }}

            /* MAIN 2-COLUMN DASHBOARD */
            .main-grid {{
                display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 24px;
            }}
            .left-col {{ display: flex; flex-direction: column; gap: 22px; }}
            .right-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}

            .card {{
                background: linear-gradient(180deg, rgba(19, 28, 49, 0.92) 0%, rgba(11, 17, 30, 0.96) 100%);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-top: 3px solid rgba(229, 193, 88, 0.6);
                border-radius: 20px; padding: 20px 24px;
                box-shadow: 0 14px 35px rgba(0,0,0,0.5);
            }}
            .card-header {{
                display: flex; align-items: center; justify-content: space-between;
                margin-bottom: 16px; padding-bottom: 10px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .card-title {{ font-size: 24px; font-weight: 900; display: flex; align-items: center; gap: 10px; }}
            .dot {{ width: 12px; height: 24px; border-radius: 6px; }}
            .gold-dot {{ background: #e5c158; }}
            .blue-dot {{ background: #38bdf8; }}
            .green-dot {{ background: #10b981; }}
            .red-dot {{ background: #ef4444; }}

            /* SECTORS (4x3) */
            .sec-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
            .sec-box {{
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px; padding: 12px 14px;
            }}
            .sec-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
            .sec-sym {{ font-size: 20px; font-weight: 900; color: #e5c158; display: block; }}
            .sec-name {{ font-size: 15px; font-weight: 700; color: #cbd5e1; }}
            .sec-pct {{ font-size: 21px; font-weight: 900; }}
            .sec-bar-bg {{ width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; }}
            .sec-bar-fill {{ height: 100%; border-radius: 4px; }}
            .up-fill {{ background: linear-gradient(90deg, #059669, #34d399); }}
            .down-fill {{ background: linear-gradient(90deg, #dc2626, #f87171); }}

            /* MACRO (4x3) */
            .macro-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
            .macro-pill {{
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px; padding: 12px 16px;
            }}
            .mp-name {{ font-size: 16px; font-weight: 800; color: #94a3b8; margin-bottom: 8px; }}
            .mp-bottom {{ display: flex; justify-content: space-between; align-items: center; }}
            .mp-price {{ font-size: 24px; font-weight: 900; color: #ffffff; }}

            /* MOVERS */
            .mover-row {{
                display: flex; align-items: center; justify-content: space-between;
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px; padding: 14px 16px; margin-bottom: 14px;
            }}
            .mover-left {{ display: flex; align-items: center; gap: 14px; }}
            .t-logo-wrap {{
                width: 56px; height: 56px; border-radius: 50%; background: #ffffff; padding: 5px;
                display: flex; align-items: center; justify-content: center; overflow: hidden;
            }}
            .t-logo {{ width: 100%; height: 100%; object-fit: contain; }}
            .t-fallback {{
                width: 100%; height: 100%; border-radius: 50%; background: #1e293b; color: #e5c158;
                font-size: 24px; font-weight: 900; align-items: center; justify-content: center;
            }}
            .t-sym {{ font-size: 26px; font-weight: 900; color: #ffffff; }}
            .t-price {{ font-size: 19px; font-weight: 700; color: #94a3b8; margin-top: 2px; }}
            .mover-pct {{ padding: 8px 14px; border-radius: 10px; font-size: 22px; font-weight: 900; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-left">
                {logo_html}
                <div class="title-group">
                    <h1>ILAN.KUV VIP TERMINAL</h1>
                    <p>MID-DAY MARKET SNAPSHOT &bull; SECTORS &amp; MACRO PULSE</p>
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

        <div class="main-grid">
            <div class="left-col">
                <div class="card" style="border-top-color: #38bdf8;">
                    <div class="card-header">
                        <div class="card-title"><div class="dot blue-dot"></div> SECTOR ROTATION (RANKED)</div>
                    </div>
                    <div class="sec-grid">
                        {sec_cards}
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-title"><div class="dot gold-dot"></div> MACRO, YIELDS, COMMODITIES &amp; CRYPTO</div>
                    </div>
                    <div class="macro-grid">
                        {macro_cards}
                    </div>
                </div>
            </div>

            <div class="right-col">
                <div class="card" style="border-top-color: #10b981;">
                    <div class="card-header">
                        <div class="card-title"><div class="dot green-dot"></div> TOP GAINERS</div>
                    </div>
                    {gainers_html}
                </div>

                <div class="card" style="border-top-color: #ef4444;">
                    <div class="card-header">
                        <div class="card-title"><div class="dot red-dot"></div> TOP LOSERS</div>
                    </div>
                    {losers_html}
                </div>
            </div>
        </div>
    </body>
    </html>
    """

def generate_poster(html_content):
    output_path = "midday_update.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1180}, device_scale_factor=2)
        page.set_content(html_content, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=False)
        browser.close()
    return output_path

def send_to_discord(image_path):
    if not WEBHOOK_URL:
        print("Error: Webhook URL not set!")
        return
    now_il = datetime.now(ISRAEL_TZ).strftime("%H:%M")
    payload = {
        "content": f"⚡ **עדכון אמצע יום המסחר בוול סטריט ({now_il}) – מדדים, מפת סקטורים, מאקרו והמניות הבולטות:**"
    }
    with open(image_path, "rb") as f:
        files = {"file": ("midday_update.png", f, "image/png")}
        requests.post(WEBHOOK_URL, data=payload, files=files)

if __name__ == "__main__":
    idx, sectors, macro, gainers, losers = get_all_market_data()
    html = build_html(idx, sectors, macro, gainers, losers)
    img_file = generate_poster(html)
    send_to_discord(img_file)
