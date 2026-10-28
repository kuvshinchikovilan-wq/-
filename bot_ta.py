import os
import base64
import requests
from datetime import datetime
import pytz
import yfinance as yf
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_TA") or os.environ.get("DISCORD_WEBHOOK_MIDDAY")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

def get_logo_base64():
    for fname in ["logo.jpg", "logo.png", "logo.jpeg", "LOGO.jpg", "LOGO.png"]:
        if os.path.exists(fname):
            with open(fname, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                ext = "png" if fname.lower().endswith("png") else "jpeg"
                return f"data:image/{ext};base64,{encoded}"
    return ""

def analyze_ticker(symbol):
    symbol = symbol.upper().strip()
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="1y")
        if df.empty or len(df) < 200:
            return None
        
        curr_price = float(df["Close"].iloc[-1])
        prev_price = float(df["Close"].iloc[-2])
        pct_change = ((curr_price - prev_price) / prev_price) * 100
        
        sma_50 = float(df["Close"].rolling(50).mean().iloc[-1])
        sma_200 = float(df["Close"].rolling(200).mean().iloc[-1])
        
        # חישוב RSI פשוט
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])
        
        high_52 = float(df["High"].max())
        low_52 = float(df["Low"].min())
        
        # סטטוס טכני
        trend = "BULLISH (Uptrend)" if curr_price > sma_50 > sma_200 else ("BEARISH (Downtrend)" if curr_price < sma_50 < sma_200 else "CONSOLIDATION / MIXED")
        
        return {
            "symbol": symbol,
            "price": f"${curr_price:,.2f}",
            "pct": pct_change,
            "sma50": f"${sma_50:,.2f}",
            "sma200": f"${sma_200:,.2f}",
            "rsi": f"{rsi:.1f}",
            "high52": f"${high_52:,.2f}",
            "low52": f"${low_52:,.2f}",
            "trend": trend,
            "logo": f"https://financialmodelingprep.com/image-stock/{symbol}.png"
        }
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None

def build_ta_html(data):
    logo_src = get_logo_base64()
    logo_html = f'<img src="{logo_src}" class="brand-logo" />' if logo_src else '<div class="brand-fallback">IK</div>'
    
    is_up = data["pct"] >= 0
    cls = "up" if is_up else "down"
    sign = "+" if is_up else ""
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800;900&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                width: 1000px; height: 650px;
                font-family: 'Montserrat', sans-serif;
                background: radial-gradient(circle at 50% 0%, #162447 0%, #0a0f1d 60%, #050811 100%);
                color: #ffffff; padding: 35px; overflow: hidden;
            }}
            .header {{
                display: flex; align-items: center; justify-content: space-between;
                background: linear-gradient(135deg, rgba(23,34,59,0.95) 0%, rgba(12,19,34,0.98) 100%);
                border: 2px solid rgba(212, 175, 55, 0.5);
                border-radius: 20px; padding: 20px 30px; margin-bottom: 25px;
            }}
            .header-left {{ display: flex; align-items: center; gap: 20px; }}
            .brand-logo {{ width: 75px; height: 75px; border-radius: 16px; object-fit: cover; border: 2px solid #e5c158; }}
            .t-logo-wrap {{ width: 75px; height: 75px; border-radius: 50%; background: #fff; padding: 5px; display: flex; align-items: center; justify-content: center; }}
            .t-logo {{ width: 100%; height: 100%; object-fit: contain; }}
            .title-group h1 {{ font-size: 36px; font-weight: 900; color: #ffffff; }}
            .title-group p {{ font-size: 16px; font-weight: 800; color: #e5c158; letter-spacing: 2px; margin-top: 4px; }}
            
            .price-box {{ text-align: right; }}
            .price {{ font-size: 38px; font-weight: 900; color: #ffffff; }}
            .pct {{ font-size: 20px; font-weight: 900; padding: 4px 12px; border-radius: 8px; display: inline-block; margin-top: 4px; }}
            .up {{ background: rgba(16,185,129,0.2); color: #34d399; border: 1px solid rgba(16,185,129,0.4); }}
            .down {{ background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid rgba(239,68,68,0.4); }}

            .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
            .card {{
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 18px; padding: 20px; text-align: center;
            }}
            .card-label {{ font-size: 14px; font-weight: 800; color: #94a3b8; letter-spacing: 1.5px; margin-bottom: 8px; }}
            .card-val {{ font-size: 26px; font-weight: 900; color: #ffffff; }}
            
            .trend-card {{
                grid-column: span 3;
                background: linear-gradient(135deg, rgba(212,175,55,0.15) 0%, rgba(255,255,255,0.02) 100%);
                border: 1.5px solid rgba(212,175,55,0.4);
                border-radius: 18px; padding: 18px; display: flex; justify-content: space-between; align-items: center;
            }}
            .trend-title {{ font-size: 16px; font-weight: 800; color: #e5c158; letter-spacing: 2px; }}
            .trend-val {{ font-size: 22px; font-weight: 900; color: #ffffff; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-left">
                <div class="t-logo-wrap">
                    <img src="{data['logo']}" onerror="this.style.display='none'" class="t-logo" />
                </div>
                <div class="title-group">
                    <h1>${data['symbol']} TECHNICAL ANALYSIS</h1>
                    <p>ILAN.KUV VIP QUANT TERMINAL</p>
                </div>
            </div>
            <div class="price-box">
                <div class="price">{data['price']}</div>
                <div class="pct {cls}">{sign}{data['pct']:.2f}%</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-label">50 SMA</div>
                <div class="card-val">{data['sma50']}</div>
            </div>
            <div class="card">
                <div class="card-label">200 SMA</div>
                <div class="card-val">{data['sma200']}</div>
            </div>
            <div class="card">
                <div class="card-label">RSI (14)</div>
                <div class="card-val">{data['rsi']}</div>
            </div>
            <div class="card">
                <div class="card-label">52W HIGH</div>
                <div class="card-val" style="color:#34d399;">{data['high52']}</div>
            </div>
            <div class="card">
                <div class="card-label">52W LOW</div>
                <div class="card-val" style="color:#f87171;">{data['low52']}</div>
            </div>
            <div class="card">
                <div class="card-label">MOMENTUM</div>
                <div class="card-val" style="color:#38bdf8;">ACTIVE</div>
            </div>

            <div class="trend-card">
                <div class="trend-title">PRIMARY MARKET STRUCTURE</div>
                <div class="trend-val">{data['trend']}</div>
            </div>
        </div>
    </body>
    </html>
    """

def generate_ta_poster(symbol):
    data = analyze_ticker(symbol)
    if not data:
        return None
    html = build_ta_html(data)
    output_path = f"ta_{symbol}.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 650}, device_scale_factor=2)
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=False)
        browser.close()
    return output_path

def send_to_discord(symbol, image_path):
    if not WEBHOOK_URL:
        return
    payload = {"content": f"📊 **ניתוח טכני לבקשתך עבור מניית ${symbol.upper()}:**"}
    with open(image_path, "rb") as f:
        files = {"file": (image_path, f, "image/png")}
        requests.post(WEBHOOK_URL, data=payload, files=files)

if __name__ == "__main__":
    # אפשר להגדיר טיקר ברירת מחדל או לקרוא מאינפוט
    target_ticker = os.environ.get("TARGET_TICKER", "NVDA")
    img = generate_ta_poster(target_ticker)
    if img:
        send_to_discord(target_ticker, img)
