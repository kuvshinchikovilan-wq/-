import os
import json
import datetime
import requests
import yfinance as yf
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
WHATSAPP_WEBHOOK = os.environ.get("WHATSAPP_WEBHOOK_URL", "")

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
        price_fmt = f"{last_close:,.3f}" if is_yield else f"{last_close:,.2f}"
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
    indices_cfg = [
        ("S&P 500", "^GSPC", False),
        ("NASDAQ 100", "^NDX", False),
        ("DOW JONES", "^DJI", False),
        ("QQQ", "QQQ", False),
        ("SPY", "SPY", False),
        ("RSP (S&P EW)", "RSP", False),
        ("IWM (Russell)", "IWM", False),
        ("VIX", "^VIX", False),
        ("DXY", "DX-Y.NYB", False),
        ("US 10Y", "^TNX", True),
    ]
    top_indices = []
    for name, sym, is_y in indices_cfg:
        q = fetch_quote(sym, is_y)
        q["name"] = name
        top_indices.append(q)

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

    comm_cfg = [
        ("🛢️ נפט WTI", "CL=F"),
        ("🪙 זהב (Gold)", "GC=F"),
        ("₿ ביטקוין (BTC)", "BTC-USD"),
        ("💎 אתריום (ETH)", "ETH-USD"),
    ]
    commodities = []
    for name, sym in comm_cfg:
        q = fetch_quote(sym)
        q["name"] = name
        commodities.append(q)

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
        f"הסקטור המוביל היום: {best_sec['name']} ({best_sec['pct']}), בעוד {worst_sec['name']} סגר ב-{worst_sec['pct']}.",
        f"מניות בולטות: {top_g['sym']} קפצה ב-{top_g['pct']}, ומנגד {top_l['sym']} ירדה ב-{top_l['pct']}.",
        f"מדד הפחד (VIX) ננעל על {vix['price']} ({vix['pct']}), ותשואת האג״ח ל-10 שנים על {top_indices[9]['price']}%."
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
      <div style="background:rgba(11,22,41,0.95);border:1.5px solid rgba(56,189,248,0.35);border-radius:14px;padding:12px 14px;text-align:left;" dir="ltr">
        <div style="font-size:18px;color:#e2e8f0;font-weight:800;">{i['name']}</div>
        <div style="font-size:34px;color:#ffffff;font-weight:900;margin:4px 0;letter-spacing:-0.5px;">{i['price']}</div>
        <div style="font-size:20px;font-weight:800;color:{color_cls(i['up'])};">{i['pct']} <span style="opacity:0.85;font-size:17px;margin-left:4px;">{i['chg']}</span></div>
      </div>
    """ for i in data["top_indices"]])

    gainers_html = "".join([f"""
      <div style="display:grid;grid-template-columns:1.1fr 1.1fr 1.2fr;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.08);font-family:'JetBrains Mono',monospace;font-size:22px;align-items:center;">
        <span style="font-weight:900;color:#fff;text-align:right;">{g['sym']}</span>
        <span style="color:#e2e8f0;font-weight:700;text-align:center;">{g['price']}</span>
        <span dir="ltr" style="color:#10b981;font-weight:900;text-align:left;">{g['pct']}</span>
      </div>
    """ for g in data["gainers"]])

    losers_html = "".join([f"""
      <div style="display:grid;grid-template-columns:1.1fr 1.1fr 1.2fr;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.08);font-family:'JetBrains Mono',monospace;font-size:22px;align-items:center;">
        <span style="font-weight:900;color:#fff;text-align:right;">{l['sym']}</span>
        <span style="color:#e2e8f0;font-weight:700;text-align:center;">{l['price']}</span>
        <span dir="ltr" style="color:#f43f5e;font-weight:900;text-align:left;">{l['pct']}</span>
      </div>
    """ for l in data["losers"]])

    sectors_html = "".join([f"""
      <div style="display:flex;justify-content:space-between;align-items:center;padding:5.5px 0;border-bottom:1px solid rgba(255,255,255,0.06);font-size:19px;">
        <span style="color:#f1f5f9;font-weight:700;">{s['name']}</span>
        <span dir="ltr" style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:900;color:{color_cls(s['up'])};">{s['pct']}</span>
      </div>
    """ for s in data["sectors"]])

    comm_html = "".join([f"""
      <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.08);font-size:21px;">
        <span style="color:#f1f5f9;font-weight:800;">{c['name']}</span>
        <span dir="ltr" style="font-family:'JetBrains Mono',monospace;color:#fff;font-weight:800;">{c['price']}</span>
        <span dir="ltr" style="font-family:'JetBrains Mono',monospace;font-weight:900;color:{color_cls(c['up'])};">{c['pct']}</span>
      </div>
    """ for c in data["commodities"]])

    bonds_html = "".join([f"""
      <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.08);font-size:21px;" dir="ltr">
        <span style="color:#cbd5e1;font-weight:900;">{b['name']}</span>
        <span style="font-family:'JetBrains Mono',monospace;color:#fff;font-weight:800;">{b['price']}%</span>
        <span style="font-family:'JetBrains Mono',monospace;font-weight:900;color:{color_cls(b['up'])};">{b['pct']}</span>
      </div>
    """ for b in data["bonds"]])

    bullets_html = "".join([f"""
      <li style="margin-bottom:12px;display:flex;align-items:flex-start;gap:12px;font-size:23px;line-height:1.35;color:#f8fafc;font-weight:700;">
        <span style="color:#38bdf8;font-size:24px;line-height:1.2;">●</span> <span>{b}</span>
      </li>
    """ for b in data["bullets"]])

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@500;700;800;900&family=JetBrains+Mono:wght@700;800;900&display=swap" rel="stylesheet">
<style>
  body {{ margin:0; padding:0; background:#040914; font-family:'Heebo',sans-serif; color:#fff; }}
  #poster {{
    width: 1120px;
    padding: 26px;
    box-sizing: border-box;
    background: linear-gradient(180deg, #061224 0%, #040914 100%);
  }}
</style>
</head>
<body>
  <div id="poster">
    <!-- Header -->
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid rgba(56,189,248,0.3);padding-bottom:16px;margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:16px;">
        <img src="https://ilankuv.netlify.app/assets/logo.jpg" style="width:86px;height:86px;border-radius:18px;border:2px solid #10b981;object-fit:cover;">
        <div>
          <div dir="ltr" style="font-family:'JetBrains Mono',monospace;font-size:38px;font-weight:900;">ILAN<span style="color:#10b981;">.KUV</span></div>
          <div style="font-size:15px;color:#38bdf8;letter-spacing:2px;font-weight:800;">MARKETVIEW</div>
        </div>
      </div>
      <div style="text-align:center;">
        <div style="font-size:56px;font-weight:900;line-height:1.05;">סיכום מסחר בארה״ב</div>
        <div style="font-size:28px;color:#cbd5e1;font-weight:800;margin-top:4px;">{data['date_he']}</div>
      </div>
      <div style="text-align:left;font-family:'JetBrains Mono',monospace;font-size:16px;font-weight:800;color:#10b981;background:rgba(16,185,129,0.14);border:1.5px solid rgba(16,185,129,0.4);padding:10px 16px;border-radius:14px;">
        WALL STREET CLOSE
      </div>
    </div>

    <!-- Top 10 Indices Grid -->
    <div style="display:grid;grid-template-columns:repeat(5, 1fr);gap:10px;margin-bottom:16px;">
      {indices_html}
    </div>

    <!-- Middle Row: Gainers | Losers | Sectors -->
    <div style="display:grid;grid-template-columns:1fr 1fr 1.05fr;gap:12px;margin-bottom:16px;">
      <div style="background:rgba(6,34,29,0.92);border:1.5px solid rgba(16,185,129,0.5);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:25px;font-weight:900;border-bottom:1.5px solid rgba(16,185,129,0.35);padding-bottom:8px;margin-bottom:8px;color:#10b981;">↗ מניות בולטות – עולות</div>
        {gainers_html}
      </div>
      <div style="background:rgba(43,12,22,0.92);border:1.5px solid rgba(244,63,94,0.5);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:25px;font-weight:900;border-bottom:1.5px solid rgba(244,63,94,0.35);padding-bottom:8px;margin-bottom:8px;color:#f43f5e;">↘ מניות בולטות – יורדות</div>
        {losers_html}
      </div>
      <div style="background:rgba(11,22,41,0.95);border:1.5px solid rgba(56,189,248,0.35);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:24px;font-weight:900;border-bottom:1.5px solid rgba(56,189,248,0.3);padding-bottom:8px;margin-bottom:8px;">סקטורים (S&P 500)</div>
        {sectors_html}
      </div>
    </div>

    <!-- Commodities & Bonds -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
      <div style="background:rgba(11,22,41,0.95);border:1.5px solid rgba(56,189,248,0.35);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:24px;font-weight:900;border-bottom:1.5px solid rgba(56,189,248,0.25);padding-bottom:8px;margin-bottom:8px;">סחורות וקריפטו</div>
        {comm_html}
      </div>
      <div style="background:rgba(11,22,41,0.95);border:1.5px solid rgba(56,189,248,0.35);border-radius:16px;padding:16px;">
        <div style="text-align:center;font-size:24px;font-weight:900;border-bottom:1.5px solid rgba(56,189,248,0.25);padding-bottom:8px;margin-bottom:8px;">אג״ח אמריקאי (תשואות)</div>
        {bonds_html}
      </div>
    </div>

    <!-- Bottom Summary Box -->
    <div style="background:rgba(11,22,41,0.96);border:1.5px solid rgba(56,189,248,0.4);border-radius:16px;padding:20px;">
      <div style="font-size:26px;font-weight:900;margin-bottom:12px;color:#38bdf8;">📋 תמונת מצב | ILAN.KUV</div>
      <ul style="list-style:none;padding:0;margin:0;">
        {bullets_html}
      </ul>
    </div>

    <!-- Footer -->
    <div style="display:flex;justify-content:space-between;margin-top:14px;padding-top:10px;border-top:1px solid rgba(255,255,255,0.15);font-size:15px;font-weight:700;color:#cbd5e1;">
      <span dir="ltr" style="font-family:'JetBrains Mono',monospace;font-weight:900;color:#fff;">ILAN.KUV MARKETVIEW</span>
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

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1120, "height": 1500}, device_scale_factor=2)
        page.goto(f"file://{os.path.abspath('poster.html')}", wait_until="networkidle")
        poster_el = page.locator("#poster")
        poster_el.screenshot(path="market_close.png")
        browser.close()

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

    if WHATSAPP_WEBHOOK:
        with open("market_close.png", "rb") as img:
            requests.post(
                WHATSAPP_WEBHOOK,
                data={"caption": f"סיכום מסחר בארה״ב – {data['date_he']} | ILAN.KUV"},
                files={"file": ("market_close.png", img, "image/png")}
            )

if __name__ == "__main__":
    main()
