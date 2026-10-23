import os
import requests
from datetime import datetime
import pytz
from PIL import Image, ImageDraw, ImageFont

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_MORNING")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

MAJOR_TICKERS = {
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AMD", 
    "NFLX", "INTC", "JPM", "BAC", "GS", "MS", "V", "MA", "DIS", "PYPL", 
    "CRM", "AVGO", "ORCL", "PLTR", "COIN", "UBER", "SHOP", "PANW", "SMCI",
    "LLY", "UNH", "XOM", "CVX", "WMT", "COST", "HD", "PG", "JNJ", "ABBV"
}

def get_macro_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    events = []
    now_il = datetime.now(ISRAEL_TZ)
    today_str = now_il.strftime("%Y-%m-%d")
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data:
                if item.get("country") == "USD" and item.get("impact") in ["High", "Medium"]:
                    raw_date = item.get("date", "")
                    if raw_date.startswith(today_str):
                        dt = datetime.fromisoformat(raw_date).astimezone(ISRAEL_TZ)
                        time_str = dt.strftime("%H:%M")
                        events.append({
                            "time": time_str,
                            "title": item.get("title", ""),
                            "impact": item.get("impact", ""),
                            "forecast": item.get("forecast", "-") or "-",
                            "previous": item.get("previous", "-") or "-"
                        })
    except Exception as e:
        print(f"Error fetching macro: {e}")
    return events[:8]

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
                sym = row.get("symbol", "")
                time_type = row.get("time", "")
                eps_est = row.get("epsForecast", "-") or "-"
                name = row.get("name", "")[:18]
                
                entry = {"symbol": sym, "name": name, "eps": eps_est, "is_major": sym in MAJOR_TICKERS}
                if "pre-market" in time_type:
                    bmo.append(entry)
                elif "after-hours" in time_type:
                    amc.append(entry)
    except Exception as e:
        print(f"Error fetching earnings: {e}")
    return bmo[:8], amc[:8]

def create_image(macro_events, bmo, amc):
    width, height = 1080, 1150
    bg_color = (13, 17, 23)
    card_bg = (22, 27, 34)
    gold = (240, 185, 11)
    white = (255, 255, 255)
    gray = (139, 148, 158)
    red_high = (248, 81, 73)
    orange_med = (210, 153, 34)
    blue_accent = (88, 166, 255)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_sec = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_item_b = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 21)
        font_item = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
    except:
        font_title = font_sub = font_sec = font_item_b = font_item = font_small = ImageFont.load_default()

    now_il = datetime.now(ISRAEL_TZ)
    date_display = now_il.strftime("%d/%m/%Y")

    draw.rectangle([(0, 0), (width, 110)], fill=(18, 23, 31))
    draw.line([(0, 110), (width, 110)], fill=gold, width=3)
    draw.text((40, 28), "ILAN VIP | MORNING BRIEFING", fill=gold, font=font_title)
    draw.text((40, 72), f"Macro Calendar & Earnings Report  •  {date_display} (Israel Time)", fill=gray, font=font_sub)

    y_cursor = 140
    draw.rounded_rectangle([(40, y_cursor), (width - 40, y_cursor + 440)], radius=12, fill=card_bg, outline=(48, 54, 61), width=1)
    draw.text((65, y_cursor + 20), "US ECONOMIC CALENDAR (TODAY)", fill=blue_accent, font=font_sec)
    draw.line([(65, y_cursor + 60), (width - 65, y_cursor + 60)], fill=(48, 54, 61), width=1)

    draw.text((65, y_cursor + 72), "TIME", fill=gray, font=font_small)
    draw.text((160, y_cursor + 72), "IMPACT", fill=gray, font=font_small)
    draw.text((275, y_cursor + 72), "EVENT", fill=gray, font=font_small)
    draw.text((760, y_cursor + 72), "FORECAST", fill=gray, font=font_small)
    draw.text((900, y_cursor + 72), "PREVIOUS", fill=gray, font=font_small)

    row_y = y_cursor + 105
    if not macro_events:
        draw.text((65, row_y + 20), "No High/Medium Impact US Macro Events Scheduled For Today.", fill=gray, font=font_item)
    else:
        for ev in macro_events:
            imp_color = red_high if ev["impact"] == "High" else orange_med
            draw.text((65, row_y), ev["time"], fill=white, font=font_item_b)
            draw.rounded_rectangle([(160, row_y + 2), (245, row_y + 26)], radius=5, fill=imp_color)
            draw.text((172, row_y + 4), ev["impact"].upper(), fill=white, font=font_small)
            draw.text((275, row_y), ev["title"][:38], fill=white, font=font_item)
            draw.text((760, row_y), str(ev["forecast"]), fill=gold, font=font_item_b)
            draw.text((900, row_y), str(ev["previous"]), fill=gray, font=font_item)
            row_y += 40

    y_earn = 610
    col_w = (width - 100) // 2

    draw.rounded_rectangle([(40, y_earn), (40 + col_w, y_earn + 460)], radius=12, fill=card_bg, outline=(48, 54, 61), width=1)
    draw.text((65, y_earn + 20), "BEFORE OPEN (BMO)", fill=gold, font=font_sec)
    draw.line([(65, y_earn + 60), (40 + col_w - 25, y_earn + 60)], fill=(48, 54, 61), width=1)
    
    ey = y_earn + 80
    if not bmo:
        draw.text((65, ey), "No Notable BMO Earnings", fill=gray, font=font_item)
    else:
        for item in bmo:
            sym_color = gold if item["is_major"] else white
            prefix = "★ " if item["is_major"] else "• "
            draw.text((65, ey), f"{prefix}${item['symbol']}", fill=sym_color, font=font_item_b)
            draw.text((195, ey + 2), item["name"], fill=gray, font=font_small)
            draw.text((40 + col_w - 135, ey), f"Est: {item['eps']}", fill=white, font=font_small)
            ey += 44

    x_amc = 60 + col_w
    draw.rounded_rectangle([(x_amc, y_earn), (width - 40, y_earn + 460)], radius=12, fill=card_bg, outline=(48, 54, 61), width=1)
    draw.text((x_amc + 25, y_earn + 20), "AFTER CLOSE (AMC)", fill=blue_accent, font=font_sec)
    draw.line([(x_amc + 25, y_earn + 60), (width - 65, y_earn + 60)], fill=(48, 54, 61), width=1)

    ey = y_earn + 80
    if not amc:
        draw.text((x_amc + 25, ey), "No Notable AMC Earnings", fill=gray, font=font_item)
    else:
        for item in amc:
            sym_color = gold if item["is_major"] else white
            prefix = "★ " if item["is_major"] else "• "
            draw.text((x_amc + 25, ey), f"{prefix}${item['symbol']}", fill=sym_color, font=font_item_b)
            draw.text((x_amc + 155, ey + 2), item["name"], fill=gray, font=font_small)
            draw.text((width - 175, ey), f"Est: {item['eps']}", fill=white, font=font_small)
            ey += 44

    draw.text((40, height - 45), "ilan.kuv  •  Ilan VIP Financial Community", fill=gray, font=font_small)

    output_path = "morning_brief.png"
    img.save(output_path)
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
    img_file = create_image(macro, bmo, amc)
    send_to_discord(img_file)
