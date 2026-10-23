import os
import base64
import requests
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_MORNING")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

MAJOR_TICKERS = {
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AMD", 
    "NFLX", "INTC", "JPM", "BAC", "GS", "MS", "V", "MA", "DIS", "PYPL", 
    "CRM", "AVGO", "ORCL", "PLTR", "COIN", "UBER", "SHOP", "PANW", "SMCI",
    "LLY", "UNH", "XOM", "CVX", "WMT", "COST", "HD", "PG", "JNJ", "ABBV",
    "BA", "CAT", "GE", "GM", "F", "IBM", "MCD", "NKE", "PEP", "KO"
}

def get_logo_base64():
    for fname in ["logo.jpg", "logo.png", "logo.jpeg", "LOGO.jpg", "LOGO.png"]:
        if os.path.exists(fname):
            with open(fname, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                ext = "png" if fname.lower().endswith("png") else "jpeg"
                return f"data:image/{ext};base64,{encoded}"
    return ""

def get_macro_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    events = []
    now_il = datetime.now(ISRAEL_TZ)
    today_str = now_il.strftime("%Y-%m-%d")
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get("country") == "USD" and item.get("impact") in ["High", "Medium"]:
                    raw_date = item.get("date", "")
                    if raw_date.startswith(today_str):
                        dt = datetime.fromisoformat(raw_date).astimezone(ISRAEL_TZ)
                        events.append({
                            "time": dt.strftime("%H:%M"),
                            "title": item.get("title", ""),
                            "impact": item.get("impact", ""),
                            "forecast": item.get("forecast", "-") or "-",
                            "previous": item.get("previous", "-") or "-"
                        })
    except Exception as e:
        print(f"Error fetching macro: {e}")
    return events[:6]

def get_earnings():
    now_il = datetime.now(ISRAEL_TZ)
    today_str = now_il.strftime("%Y-%m-%d")
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={today_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    bmo, amc = [], []
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            rows = r.json().get("data", {}).get("rows", []) or []
            rows.sort(key=lambda x: (x.get("symbol") not in MAJOR_TICKERS))
            for row in rows:
                sym = row.get("symbol", "").strip()
                time_type = row.get("time", "")
                eps_est = row.get("epsForecast", "-") or "-"
                name = row.get("name", "")[:22]
                entry = {
                    "symbol": sym,
                    "name": name,
                    "eps": eps_est,
                    "is_major": sym in MAJOR_TICKERS,
                    "logo": f"https://financialmodelingprep.com/image-stock/{sym}.png"
                }
                if "pre-market" in time_type:
                    bmo.append(entry)
                elif "after-hours" in time_type:
                    amc.append(entry)
    except Exception as e:
        print(f"Error fetching earnings: {e}")
    return bmo[:6], amc[:6]

def build_html(macro_events, bmo, amc):
    now_il = datetime.now(ISRAEL_TZ)
    date_display = now_il.strftime("%d / %m / %Y")
    day_name = now_il.strftime("%A").upper()
    logo_src = get_logo_base64()

    logo_html = f'<img src="{logo_src}" class="brand-logo" />' if logo_src else '<div class="brand-fallback">IK</div>'

    # בניית שורות מאקרו
    if not macro_events:
        macro_rows = '<div class="empty-state">No High or Medium Impact US Macro Events Scheduled Today</div>'
    else:
        macro_rows = ""
        for ev in macro_events:
            badge_cls = "badge-high" if ev["impact"] == "High" else "badge-med"
            macro_rows += f"""
            <div class="macro-row">
                <div class="m-time">{ev['time']}</div>
                <div class="m-impact"><span class="badge {badge_cls}">{ev['impact'].upper()}</span></div>
                <div class="m-title">{ev['title']}</div>
                <div class="m-forecast">{ev['forecast']}</div>
                <div class="m-prev">{ev['previous']}</div>
            </div>
            """

    # פונקציה לבניית כרטיסיות דוחות
    def render_earnings(items):
        if not items:
            return '<div class="empty-state">No Notable Earnings Scheduled</div>'
        html = ""
        for it in items:
            star_cls = "major-card" if it["is_major"] else ""
            html += f"""
            <div class="earn-row {star_cls}">
                <div class="earn-left">
                    <div class="ticker-logo-wrap">
                        <img src="{it['logo']}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" class="ticker-logo" />
                        <div class="ticker-fallback" style="display:none;">{it['symbol'][0]}</div>
                    </div>
                    <div class="ticker-info">
                        <div class="ticker-sym">${it['symbol']} {'<span class="star">★</span>' if it['is_major'] else ''}</div>
                        <div class="ticker-name">{it['name']}</div>
                    </div>
                </div>
                <div class="earn-eps">
                    <span class="eps-label">EST EPS</span>
                    <span class="eps-val">{it['eps']}</span>
                </div>
            </div>
            """
        return html

    bmo_html = render_earnings(bmo)
    amc_html = render_earnings(amc)

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@500;600;700;800;900&family=Rubik:wght@500;700;800&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                width: 1200px;
                min-height: 1450px;
                font-family: 'Montserrat', 'Rubik', sans-serif;
                background: radial-gradient(circle at 50% 0%, #162447 0%, #0a0f1d 55%, #050811 100%);
                color: #ffffff;
                padding: 45px;
                position: relative;
                overflow: hidden;
            }}
            /* אפקטים של תאורת רקע יוקרתית */
            .glow-top {{
                position: absolute; top: -180px; left: 50%; transform: translateX(-50%);
                width: 750px; height: 380px;
                background: radial-gradient(circle, rgba(212,175,55,0.22) 0%, rgba(0,0,0,0) 70%);
                pointer-events: none;
            }}
            /* HEADER */
            .header {{
                display: flex; align-items: center; justify-content: space-between;
                background: linear-gradient(135deg, rgba(23,34,59,0.9) 0%, rgba(12,19,34,0.95) 100%);
                border: 2px solid rgba(212, 175, 55, 0.45);
                border-radius: 26px;
                padding: 28px 40px;
                box-shadow: 0 20px 50px rgba(0,0,0,0.6), inset 0 1px 2px rgba(255,255,255,0.15);
                margin-bottom: 35px;
                position: relative;
            }}
            .header-left {{ display: flex; align-items: center; gap: 28px; }}
            .brand-logo {{
                width: 115px; height: 115px; border-radius: 22px;
                object-fit: cover;
                border: 2.5px solid #e5c158;
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
                text-transform: uppercase;
            }}
            .title-group p {{
                font-size: 18px; font-weight: 600; color: #94a3b8;
                letter-spacing: 3px; margin-top: 8px; text-transform: uppercase;
            }}
            .date-box {{
                text-align: right;
                background: rgba(212, 175, 55, 0.1);
                border: 1px solid rgba(212, 175, 55, 0.35);
                padding: 16px 26px; border-radius: 18px;
            }}
            .date-day {{ font-size: 15px; font-weight: 800; color: #e5c158; letter-spacing: 2.5px; }}
            .date-str {{ font-size: 26px; font-weight: 800; color: #ffffff; margin-top: 4px; }}

            /* SECTION CARD */
            .card {{
                background: linear-gradient(180deg, rgba(19, 28, 49, 0.88) 0%, rgba(11, 17, 30, 0.92) 100%);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-top: 2px solid rgba(229, 193, 88, 0.5);
                border-radius: 24px;
                padding: 30px 35px;
                box-shadow: 0 18px 40px rgba(0,0,0,0.5);
                margin-bottom: 35px;
            }}
            .card-header {{
                display: flex; align-items: center; justify-content: space-between;
                margin-bottom: 24px; padding-bottom: 16px;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }}
            .card-title {{
                font-size: 25px; font-weight: 800; letter-spacing: 1px;
                display: flex; align-items: center; gap: 12px; color: #f8fafc;
            }}
            .gold-dot {{
                width: 12px; height: 26px; border-radius: 6px;
                background: linear-gradient(180deg, #fceabb 0%, #d4af37 100%);
                box-shadow: 0 0 12px rgba(212, 175, 55, 0.6);
            }}
            .blue-dot {{
                width: 12px; height: 26px; border-radius: 6px;
                background: linear-gradient(180deg, #7dd3fc 0%, #0284c7 100%);
                box-shadow: 0 0 12px rgba(56, 189, 248, 0.6);
            }}
            .card-sub {{ font-size: 15px; font-weight: 700; color: #e5c158; letter-spacing: 1.5px; }}

            /* MACRO TABLE */
            .macro-cols {{
                display: grid; grid-template-columns: 110px 140px 1fr 140px 140px;
                padding: 0 22px 12px 22px;
                font-size: 14px; font-weight: 800; color: #64748b; letter-spacing: 1.5px;
            }}
            .macro-row {{
                display: grid; grid-template-columns: 110px 140px 1fr 140px 140px;
                align-items: center;
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
                padding: 18px 22px;
                margin-bottom: 12px;
            }}
            .m-time {{ font-size: 22px; font-weight: 800; color: #f8fafc; }}
            .badge {{
                padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 800; letter-spacing: 1px;
            }}
            .badge-high {{
                background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.5);
            }}
            .badge-med {{
                background: rgba(245, 158, 11, 0.2); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.5);
            }}
            .m-title {{ font-size: 21px; font-weight: 700; color: #ffffff; padding-right: 15px; }}
            .m-forecast {{ font-size: 22px; font-weight: 800; color: #e5c158; text-align: center; }}
            .m-prev {{ font-size: 20px; font-weight: 600; color: #94a3b8; text-align: center; }}

            /* EARNINGS GRID */
            .earnings-grid {{
                display: grid; grid-template-columns: 1fr 1fr; gap: 30px;
            }}
            .earn-row {{
                display: flex; align-items: center; justify-content: space-between;
                background: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 18px;
                padding: 14px 20px;
                margin-bottom: 14px;
            }}
            .major-card {{
                background: linear-gradient(90deg, rgba(212, 175, 55, 0.12) 0%, rgba(255, 255, 255, 0.03) 100%);
                border: 1px solid rgba(212, 175, 55, 0.4);
            }}
            .earn-left {{ display: flex; align-items: center; gap: 16px; }}
            .ticker-logo-wrap {{
                width: 54px; height: 54px; border-radius: 50%;
                background: #ffffff; padding: 6px;
                display: flex; align-items: center; justify-content: center;
                box-shadow: 0 4px 12px rgba(0,0,0,0.4);
                overflow: hidden;
            }}
            .ticker-logo {{ width: 100%; height: 100%; object-fit: contain; }}
            .ticker-fallback {{
                width: 100%; height: 100%; border-radius: 50%;
                background: #1e293b; color: #e5c158;
                font-size: 24px; font-weight: 900;
                align-items: center; justify-content: center;
            }}
            .ticker-sym {{ font-size: 24px; font-weight: 900; color: #ffffff; letter-spacing: 0.5px; }}
            .star {{ color: #e5c158; font-size: 20px; }}
            .ticker-name {{ font-size: 15px; font-weight: 600; color: #94a3b8; margin-top: 2px; }}
            .earn-eps {{
                text-align: right;
                background: rgba(0, 0, 0, 0.3);
                padding: 8px 16px; border-radius: 12px;
                border: 1px solid rgba(255,255,255,0.06);
            }}
            .eps-label {{ display: block; font-size: 11px; font-weight: 800; color: #64748b; letter-spacing: 1px; }}
            .eps-val {{ font-size: 20px; font-weight: 800; color: #f8fafc; }}

            .empty-state {{
                text-align: center; padding: 55px 20px;
                font-size: 20px; font-weight: 600; color: #64748b;
                background: rgba(255,255,255,0.015); border-radius: 16px;
            }}
            .footer {{
                text-align: center; margin-top: 10px;
                font-size: 15px; font-weight: 800; color: #64748b; letter-spacing: 3px;
            }}
            .footer span {{ color: #e5c158; }}
        </style>
    </head>
    <body>
        <div class="glow-top"></div>

        <!-- HEADER -->
        <div class="header">
            <div class="header-left">
                {logo_html}
                <div class="title-group">
                    <h1>ILAN.KUV VIP</h1>
                    <p>Wall Street Daily Briefing &bull; Macro &amp; Earnings</p>
                </div>
            </div>
            <div class="date-box">
                <div class="date-day">{day_name}</div>
                <div class="date-str">{date_display}</div>
            </div>
        </div>

        <!-- MACRO CALENDAR -->
        <div class="card">
            <div class="card-header">
                <div class="card-title"><div class="gold-dot"></div> US ECONOMIC CALENDAR</div>
                <div class="card-sub">ISRAEL TIME (GMT+2/3)</div>
            </div>
            <div class="macro-cols">
                <div>TIME</div>
                <div>IMPACT</div>
                <div>EVENT</div>
                <div style="text-align:center;">FORECAST</div>
                <div style="text-align:center;">PREVIOUS</div>
            </div>
            {macro_rows}
        </div>

        <!-- EARNINGS -->
        <div class="earnings-grid">
            <div class="card" style="margin-bottom:0;">
                <div class="card-header">
                    <div class="card-title"><div class="gold-dot"></div> BEFORE OPEN (BMO)</div>
                    <div class="card-sub">PRE-MARKET</div>
                </div>
                {bmo_html}
            </div>

            <div class="card" style="margin-bottom:0; border-top-color: rgba(56, 189, 248, 0.5);">
                <div class="card-header">
                    <div class="card-title"><div class="blue-dot"></div> AFTER CLOSE (AMC)</div>
                    <div class="card-sub" style="color:#38bdf8;">AFTER-HOURS</div>
                </div>
                {amc_html}
            </div>
        </div>

        <div class="footer">
            <span>ILAN.KUV</span> &bull; EXCLUSIVE TRADING COMMUNITY &bull; MARKET INTELLIGENCE
        </div>
    </body>
    </html>
    """

def generate_poster(html_content):
    output_path = "morning_brief.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1450}, device_scale_factor=2)
        page.set_content(html_content, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path

def send_to_discord(image_path):
    if not WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_MORNING not set!")
        return
    now_il = datetime.now(ISRAEL_TZ).strftime("%d/%m/%Y")
    payload = {
        "content": f"📊 **בוקר טוב קהילה! להלן היומן הכלכלי והחברות המדווחות להיום ({now_il}):**"
    }
    with open(image_path, "rb") as f:
        files = {"file": ("morning_brief.png", f, "image/png")}
        requests.post(WEBHOOK_URL, data=payload, files=files)

if __name__ == "__main__":
    macro = get_macro_events()
    bmo, amc = get_earnings()
    html = build_html(macro, bmo, amc)
    img_file = generate_poster(html)
    send_to_discord(img_file)
