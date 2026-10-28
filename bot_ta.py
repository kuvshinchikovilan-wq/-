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
        df = t.history(period="6mo")
        if df.empty or len(df) < 50:
            return None
        
        curr_price = float(df["Close"].iloc[-1])
        prev_price = float(df["Close"].iloc[-2])
        pct_change = ((curr_price - prev_price) / prev_price) * 100
        
        sma_50 = float(df["Close"].rolling(50).mean().iloc[-1])
        
        # חישוב RSI
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])
        
        # חישוב רמות תמיכה והתנגדות דינמיות מתוך 3 חודשים האחרונים
        recent_df = df.tail(60)
        resistance = float(recent_df["High"].max())
        support = float(recent_df["Low"].min())
        
        # התאמת תמיכה והתנגדות קרובות יותר למחיר הנוכחי
        highs_near = recent_df[recent_df["High"] > curr_price]["High"]
        lows_near = recent_df[recent_df["Low"] < curr_price]["Low"]
        
        near_resistance = float(highs_near.min()) if not highs_near.empty else resistance
        near_support = float(lows_near.max()) if not lows_near.empty else support

        trend = "BULLISH (Uptrend)" if curr_price > sma_50 else "BEARISH (Downtrend)"
        
        return {
            "symbol": symbol,
            "price": f"${curr_price:,.2f}",
            "pct": pct_change,
            "sma50": f"${sma_50:,.2f}",
            "rsi": f"{rsi:.1f}",
            "support": f"${near_support:,.2f}",
            "resistance": f"${near_resistance:,.2f}",
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
                width: 1000px; height: 700px;
                font-family: 'Montserrat', sans-serif;
                background: radial-gradient(circle at 50% 0%, #162447 0%, #0a0f1d 60%, #050811 100%);
                color: #ffffff; padding: 35px; overflow: hidden;
            }}
            .header {{
                display: flex; align-items: center; justify-content: space-between;
                background: linear-gradient(135deg, rgba(23,34,59,0.95) 0%, rgba(12,19,34,0.98) 100%);
                border: 2px solid rgba(212, 175, 55, 0.5);
                border-radius: 20px; padding: 20px 30px; margin-bottom: 22px;
            }}
            .header-left {{ display: flex; align-items: center; gap: 20px; }}
            .t-logo-wrap {{ width: 75px; height: 75px; border-radius: 50%; background: #fff; padding: 5px; display: flex; align-items: center; justify-content: center; }}
            .t-logo {{ width: 100%; height: 100%; object-fit: contain; }}
            .title-group h1 {{ font-size: 34px; font-weight: 900; color: #ffffff; }}
            .title-group p {{ font-size: 15px; font-weight: 800; color: #e5c158; letter-spacing: 2px; margin-top: 4px; }}
            
            .price-box {{ text-align: right; }}
            .price {{ font-size: 36px; font-weight: 900; color: #ffffff; }}
            .pct {{ font-size: 19px; font-weight: 900; padding: 4px 12px; border-radius: 8px; display: inline-block; margin-top: 4px; }}
            .up {{ background: rgba(16,185,129,0.2); color: #34d399; border: 1px solid rgba(16,185,129,0.4); }}
            .down {{ background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid rgba(239,68,68,0.4); }}

            .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 16px; }}
            .card {{
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px; padding: 18px 22px; display: flex; justify-content: space-between; align-items: center;
            }}
            .card-label {{ font-size: 15px; font-weight: 800; color: #94a3b8; letter-spacing: 1.5px; }}
            .card-val {{ font-size: 24px; font-weight: 900; color: #ffffff; }}
            
            .levels-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 16px; }}
            .level-card {{
                background: rgba(212,175,55,0.05); border: 1.5px solid rgba(212,175,55,0.3);
                border-radius: 16px; padding: 16px 22px; display: flex; justify-content: space-between; align-items: center;
            }}

            .trend-card {{
                background: linear-gradient(135deg, rgba(56,189,248,0.15) 0%, rgba(255,255,255,0.02) 100%);
                border: 1.5px solid rgba(56,189,248,0.4);
                border-radius: 16px; padding: 16px 22px; display: flex; justify-content: space-between; align-items: center;
            }}
            .trend-title {{ font-size: 15px; font-weight: 800; color: #38bdf8; letter-spacing: 2px; }}
            .trend-val {{ font-size: 20px; font-weight: 900; color: #ffffff; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-left">
                <div class="t-logo-wrap">
                    <img src="{data['logo']}" onerror="this.style.display='none'" class="t-logo" />
