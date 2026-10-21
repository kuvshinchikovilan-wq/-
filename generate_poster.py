import os
import json
import datetime
import requests
import yfinance as yf
from playwright.sync_api import sync_playwright

# כתובות ה-Webhook (נמשכות אוטומטית מהגדרות האבטחה של גיטהאב)
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
WHATSAPP_WEBHOOK = os.environ.get("WHATSAPP_WEBHOOK_URL", "")

# תרגום תאריך לעברית
DAYS_HE = {
    0: "יום שני", 1: "יום שלישי", 2: "יום רביעי",
    3: "יום חמישי", 4: "יום שישי", 5: "יום שבת", 6: "יום ראשון"
}
MONTHS_HE = {
    1: "בינואר", 2: "בפברואר", 3: "במרץ", 4: "באפריל",
    5: "במאי", 6: "ביוני", 7: "ביולי", 8: "באוגוסט",
    9: "בספטמבר", 10: "באוקטובר", 11: "בנובמבר", 12: "בדצמבר"
}

def get_hebrew_date():
    now = datetime.datetime.now()
    return f"{DAYS_HE[now.weekday()]}, {now.day} {MONTHS_HE[now.month]} {now.year}"

def fetch_quote(ticker, is_yield=False):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) < 2:
            return {"price": "N/A", "pct": "0.00%", "chg": "0.00", "raw_pct": 0.0, "up": True}
        last_close = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2])
        diff = last_close - prev_close
        pct = (diff / prev_close) * 100
        up = diff >= 0
        sign = "+" if up else ""
        price_fmt = f"{last_close:,.3f}" if is_yield else (f"{last_close:,.2f}" if last_close < 10000 else f"{last_close:,.2f}")
        return {
            "price": price_fmt,
            "pct": f"{sign}{pct:.2f}%",
            "chg": f"{sign}{diff:.2f}",
            "raw_pct": pct,
            "up": up
        }
    except Exception:
        return {"price": "0.00", "pct": "0.00%", "chg": "0.00", "raw_pct": 0.0, "up": True}

def gather_all_market_data():
    # 1. Top 10 Indices
    indices_cfg = [
        ("S&P 500", "^GSPC", False),
        ("NASDAQ 100", "^NDX", False),
        ("DOW JONES", "^DJI", False),
        ("QQQ", "QQQ", False),
        ("SPY", "SPY", False),
        ("RSP (S&P 500 EW)", "RSP", False),
        ("IWM (Russell 2000)", "IWM", False),
        ("VIX", "^VIX", False),
        ("DXY", "DX-Y.NYB", False),
        ("US 10Y", "^TNX", True),
    ]
    top_indices = []
    for name, sym, is_y in indices_cfg:
        q = fetch_quote(sym, is_y)
        q["name"] = name
        top_indices.append(q)

    # 2. Sectors (11 S&P 500 Sectors)
    sectors_cfg = [
        ("טכנולוגיה (XLK)", "XLK"),
        ("פיננסים (XLF)", "XLF"),
        ("בריאות (XLV)", "XLV"),
        ("צריכה מחזורית (XLY)", "XLY"),
        ("צריכה בסיסית (XLP)", "XLP"),
        ("אנרגיה (XLE)", "XLE"),
        ("תעשייה (XLI)", "XLI"),
        ("תשתיות (XLU)", "XLU"),
        ("נדל״ן (XLRE)", "XLRE"),
        ("חומרים (XLB)", "XLB"),
        ("תקשורת (XLC)", "XLC"),
    ]
    sectors = []
    for name, sym in sectors_cfg:
        q = fetch_quote(sym)
        q["name"] = name
        sectors.append(q)
    sectors.sort(key=lambda x: x["raw_pct"], reverse=True)

    # 3. Watchlist for Top Gainers & Losers
    watchlist = [
        "NVDA", "AAPL", "MSFT", "AMZN", "META", "TSLA", "GOOGL", "AMD",
        "AVGO", "NFLX", "PLTR", "SMCI", "CRWD", "PANW", "SNOW", "COIN",
        "MU", "INTC", "ORCL", "CRM", "ADBE", "NOW", "ARM", "TSM", "DELL", "ESLT"
    ]
    stocks_data = []
    for sym in watchlist:
        q = fetch_quote(sym)
        q["sym"] = sym
        stocks_data.append(q)

    stocks_sorted = sorted(stocks_data, key=lambda x: x["raw_pct"], reverse=True)
    gainers = stocks_sorted[:6]
    losers = sorted(stocks_data, key=lambda x: x["raw_pct"])[:6]

    # 4. Commodities & Crypto
    comm_cfg = [
        ("🛢️ נפט WTI", "CL=F"),
        ("🪙 זהב (US$/oz)", "GC=F"),
        ("₿ ביטקוין (USD)", "BTC-USD"),
        ("💎 אתריום (USD)", "ETH-USD"),
    ]
    commodities = []
    for name, sym in comm_cfg:
        q = fetch_quote(sym)
        q["name"] = name
        commodities.append(q)

    # 5. US Treasury Yields
    bonds_cfg = [
        ("3M", "^IRX"),
        ("5Y", "^FVX"),
        ("10Y", "^TNX"),
        ("30Y", "^TYX"),
    ]
    bonds = []
    for name, sym in bonds_cfg:
        q = fetch_quote(sym, is_yield=True)
        q["name"] = name
        bonds.append(q)

    # 6. Auto-generated Hebrew Market Summary Bullets
    sp = top_indices[0]
    ndx = top_indices[1]
    vix = top_indices[7]
    best_sec = sectors[0]
    worst_sec = sectors[-1]
    top_g = gainers[0]
    top_l = losers[0]

    market_dir = "בעליות שערים" if sp["up"] else "בירידות שערים"
    bullets = [
        f"וול סטריט ננעלה {market_dir}: מדד S&P 500 סגר ב-{sp['pct']} ומדד נאסד״ק 100 ב-{ndx['pct']}.",
        f"הסקטור החזק ביותר היום: {best_sec['name']} ({best_sec['pct']}), בעוד {worst_sec['name']} סגר ב-{worst_sec['pct']}.",
        f"מניות בולטות: {top_g['sym']} זינקה ב-{top_g['pct']}, ומנגד {top_l['sym']} נחלשה ב-{top_l['pct']}.",
        f"מדד הפחד (VIX) ננעל ברמה של {vix['price']} ({vix['pct']}), ותשואת האג״ח ל-10 שנים עומדת על {top_indices[9]['price']}%."
    ]

    return {
        "date_he": get_hebrew_date(),
        "top_indices": top_indices,
        "gainers": gainers,
        "losers": losers,
        "sectors": sectors,
        "commodities": commodities,
        "bonds": bonds,
        "bullets": bullets
    }

def build_html(data):
    def color_cls(up):
        return "#10b981" if up else "#f43f5e"

    indices_html = "".join([f"""
      <div style="background:rgba(11,22,41,0.92);border:1px solid rgba(56,189,248,0.28);border-radius:14px;padding:14px;text-align:left;" dir="ltr">
        <div style="font-size:13px;color:#cbd5e1;font-weight:700;">{i['name']}</div>
        <div style="font-size:26px;color:#ffffff;font-weight:900;margin:4px 0;">{i['price']}</div>
        <div style="font-size:14px;font-weight:800;color:{color_cls(i['up'])};">{i['pct']} <span style="opacity:0.8;margin-left:6px;">{i['chg']}</span></div>
      </div>
    """ for i in data["top_indices"]])

    gainers_html = "".join([f"""
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-family:'JetBrains Mono',monospace;font-size:15px;">
        <span style="font-weight:800;color:#fff;text-align:right;">{g['sym']}</span>
        <span style="color:#e2e8f0;text-align:center;">{g['price']}</span>
        <span dir="ltr" style="color:#10b981;font-weight:800;text-align:left;">{g['pct']}</span>
      </div>
    """ for g in data["gainers"]])

    losers_html = "".join([f"""
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-family:'JetBrains Mono',monospace;font-size:15px;">
        <span style="font-weight:800;color:#fff;text-align:right;">{l['sym']}</span>
        <span style="color:#e2e8f0;text-align:center;">{l['price']}</span>
        <span dir="ltr" style="color:#f43f5e;font-weight:800;text-align:left;">{l['pct']}</span>
      </div>
    """ for l in data["losers"]])

    sectors_html = "".join([f"""
      <div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:13px;">
        <span style="color:#e2e8f0;font-weight:600;">{s['name']}</span>
        <span dir="ltr" style="font-family:'JetBrains Mono',monospace;font-weight:800;color:{color_cls(s['up'])};">{s['pct']}</span>
      </div>
    """ for s in data["sectors"]])

    comm_html = "".join([f"""
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-size:14px;">
        <span style="color:#e2e8f0;font-weight:700;">{c['name']}</span>
        <span dir="ltr" style="font-family:'JetBrains Mono',monospace;color:#fff;font-weight:700;">{c['price']}</span>
        <span dir="ltr" style="font-family:'JetBrains Mono',monospace;font-weight:800;color:{color_cls(c['up'])};">{c['pct']}</span>
      </div>
    """ for c in data["commodities"]])

    bonds_html = "".join([f"""
      <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-size:14px;" dir="ltr">
        <span style="color:#94a3b8;font-weight:800;">{b['name']}</span>
        <span style="font-family:'JetBrains Mono',monospace;color:#fff;font-weight:700;">{b['price']}%</span>
        <span style="font-family:'JetBrains Mono',monospace;font-weight:800;color:{color_cls(b['up'])};">{b['pct']}</span>
      </div>
    """ for b in data["bonds"]])

    bullets_html = "".join([f"""
      <li style="margin-bottom:10px;display:flex;align-items:center;gap:10px;font-size:16px;color:#f1f5f9;">
        <span style="color:#38bdf8;font-size:18px;">●</span> <span>{b}</span>
      </li>
    """ for b in data["bullets"]])

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;700;800;900&family=JetBrains+Mono:wght@600;700;800&display=swap" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; background:#040914; font-family:'Heebo',sans-serif; color:#fff; }}
  #poster {{
    width: 1080px;
    padding: 32px;
    box-sizing: border-box;
    background: linear-gradient(180deg, #061224 0%, #040914 100%);
  }}
</style>
</head>
<body>
  <div id="poster">
    <!-- Header -->
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(56,189,248,0.25);padding-bottom:18px;margin-bottom:20px;">
      <div style="display:flex;align-items:center;gap:16px;">
        <img src="https://ilankuv.netlify.app/assets/logo.jpg" style="width:76px;height:76px;border-radius:16px;border:2px solid #10b981;object-fit:cover;">
        <div>
          <div dir="ltr" style="font-family:'JetBrains Mono',monospace;font-size:30px;font-weight:900;">ILAN<span style="color:#10b981;">.KUV</span></div>
          <div style="font-size:12px;color:#38bdf8;letter-spacing:2px;font-weight:700;">MARKETVIEW</div>
        </div>
      </div>
      <div style="text-align:center;">
        <div style="font-size:46px;font-weight:900;line-height:1.1;">סיכום מסחר בארה״ב</div>
        <div style="font-size:22px;color:#cbd5e1;font-weight:700;margin-top:4px;">{data['date_he']}</div>
      </div>
      <div style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:13px;color:#10b981;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.35);padding:8px 14px;border-radius:12px;">
        WALL STREET CLOSE
      </div>
    </div>

    <!-- Top 10 Indices Grid -->
    <div style="display:grid;grid-template-columns:repeat(5, 1fr);gap:12px;margin-bottom:20px;">
      {indices_html}
    </div>

    <!-- Middle Row: Gainers | Losers | Sectors -->
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:20px;">
      <div style="background:rgba(6,34,29,0.9);border:1px solid rgba(16,185,129,0.45);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:20px;font-weight:900;border-bottom:1px solid rgba(16,185,129,0.3);padding-bottom:10px;margin-bottom:10px;color:#10b981;">↗ מניות בולטות – עולות</div>
        {gainers_html}
      </div>
      <div style="background:rgba(43,12,22,0.9);border:1px solid rgba(244,63,94,0.45);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:20px;font-weight:900;border-bottom:1px solid rgba(244,63,94,0.3);padding-bottom:10px;margin-bottom:10px;color:#f43f5e;">↘ מניות בולטות – יורדות</div>
        {losers_html}
      </div>
      <div style="background:rgba(11,22,41,0.92);border:1px solid rgba(56,189,248,0.28);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:20px;font-weight:900;border-bottom:1px solid rgba(56,189,248,0.25);padding-bottom:10px;margin-bottom:10px;">סקטורים מרכזיים (S&P 500)</div>
        {sectors_html}
      </div>
    </div>

    <!-- Commodities & Bonds -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px;">
      <div style="background:rgba(11,22,41,0.92);border:1px solid rgba(56,189,248,0.28);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:19px;font-weight:900;border-bottom:1px solid rgba(56,189,248,0.2);padding-bottom:8px;margin-bottom:10px;">סחורות וקריפטו</div>
        {comm_html}
      </div>
      <div style="background:rgba(11,22,41,0.92);border:1px solid rgba(56,189,248,0.28);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:19px;font-weight:900;border-bottom:1px solid rgba(56,189,248,0.2);padding-bottom:8px;margin-bottom:10px;">אג״ח אמריקאי</div>
        {bonds_html}
      </div>
    </div>

    <!-- Bottom Summary Box -->
    <div style="background:rgba(11,22,41,0.95);border:1px solid rgba(56,189,248,0.35);border-radius:16px;padding:20px;">
      <div style="font-size:20px;font-weight:900;margin-bottom:12px;color:#38bdf8;">📋 תמונת מצב | ILAN.KUV</div>
      <ul style="list-style:none;padding:0;margin:0;">
        {bullets_html}
      </ul>
    </div>

    <!-- Footer -->
    <div style="display:flex;justify-content:space-between;margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.1);font-size:12px;color:#94a3b8;">
      <span dir="ltr" style="font-family:'JetBrains Mono',monospace;font-weight:800;color:#fff;">ILAN.KUV MARKETVIEW</span>
      <span>הנתונים נכונים לסיום המסחר בוול סטריט | אין באמור המלצה או ייעוץ השקעות.</span>
    </div>
  </div>
</body>
</html>"""

def main():
    data = gather_all_market_data()
    html_content = build_html(data)

    with open("poster.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # צילום הפוסטר לקובץ PNG חד באמצעות Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=2)
        page.goto(f"file://{os.path.abspath('poster.html')}", wait_until="networkidle")
        poster_el = page.locator("#poster")
        poster_el.screenshot(path="market_close.png")
        browser.close()

    # 1. שיגור אוטומטי לדיסקורד
    if DISCORD_WEBHOOK:
        with open("market_close.png", "rb") as img:
            payload = {
                "username": "ILAN.KUV // סיכום מסחר",
                "avatar_url": "https://ilankuv.netlify.app/assets/logo.jpg",
                "content": f"📊 **סיכום מסחר בארה״ב – {data['date_he']} | קהילת ILAN.KUV**"
            }
            requests.post(
                DISCORD_WEBHOOK,
                data={"payload_json": json.dumps(payload)},
                files={"file": ("market_close.png", img, "image/png")}
            )

    # 2. שיגור אוטומטי לוואטסאפ (דרך Webhook של Make / Green-API)
    if WHATSAPP_WEBHOOK:
        with open("market_close.png", "rb") as img:
            requests.post(
                WHATSAPP_WEBHOOK,
                data={"caption": f"סיכום מסחר בארה״ב – {data['date_he']} | ILAN.KUV"},
                files={"file": ("market_close.png", img, "image/png")}
            )

if __name__ == "__main__":
    main()
