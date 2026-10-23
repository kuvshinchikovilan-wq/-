import os
import io
import requests
from datetime import datetime
import pytz
from PIL import Image, ImageDraw, ImageFont, ImageOps
from bidi.algorithm import get_display
import arabic_reshaper

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_MORNING")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

MAJOR_TICKERS = {
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AMD", 
    "NFLX", "INTC", "JPM", "BAC", "GS", "MS", "V", "MA", "DIS", "PYPL", 
    "CRM", "AVGO", "ORCL", "PLTR", "COIN", "UBER", "SHOP", "PANW", "SMCI",
    "LLY", "UNH", "XOM", "CVX", "WMT", "COST", "HD", "PG", "JNJ", "ABBV",
    "BA", "CAT", "GE", "GM", "F", "IBM", "MCD", "NKE", "PEP", "KO"
}

# מילון תרגום אוטומטי של דוחות מאקרו לעברית
MACRO_TRANSLATIONS = {
    "CPI m/m": "מדד המחירים לצרכן (חודשי)",
    "CPI y/y": "מדד המחירים לצרכן (שנתי)",
    "Core CPI m/m": "מדד הליבה לצרכן (חודשי)",
    "Core CPI y/y": "מדד הליבה לצרכן (שנתי)",
    "Core PCE Price Index m/m": "מדד האינפלציה של הפד (Core PCE)",
    "PPI m/m": "מדד המחירים ליצרן (חודשי)",
    "Core PPI m/m": "מדד הליבה ליצרן (חודשי)",
    "Unemployment Claims": "תביעות ראשוניות לדמי אבטלה",
    "Non-Farm Employment Change": "דוח תעסוקה - משרות חדשות (NFP)",
    "Unemployment Rate": "שיעור האבטלה",
    "Average Hourly Earnings m/m": "שכר ממוצע לשעה (חודשי)",
    "Advance GDP q/q": "תוצר מקומי גולמי (GDP ראשוני)",
    "Prelim GDP q/q": "תוצר מקומי גולמי (GDP מעודכן)",
    "Final GDP q/q": "תוצר מקומי גולמי (GDP סופי)",
    "Federal Funds Rate": "החלטת הריבית של הפד (FOMC)",
    "FOMC Statement": "הצהרת מדיניות הפד (FOMC)",
    "FOMC Press Conference": "מסיבת העיתונאים של יו״ר הפד פאוול",
    "Fed Chair Powell Speaks": "נאום יו״ר הפד ג׳רום פאוול",
    "FOMC Meeting Minutes": "פרוטוקול ישיבת הפד",
    "Retail Sales m/m": "מכירות קמעונאיות (חודשי)",
    "Core Retail Sales m/m": "מכירות קמעונאיות - ליבה",
    "ISM Manufacturing PMI": "מדד מנהלי הרכש בתעשייה (ISM)",
    "ISM Services PMI": "מדד מנהלי הרכש בשירותים (ISM)",
    "Flash Manufacturing PMI": "מדד מנהלי הרכש בתעשייה (Flash)",
    "Flash Services PMI": "מדד מנהלי הרכש בשירותים (Flash)",
    "CB Consumer Confidence": "מדד אמון הצרכנים (CB)",
    "Prelim UoM Consumer Sentiment": "סנטימנט הצרכנים של אונ׳ מישיגן",
    "Revised UoM Consumer Sentiment": "סנטימנט הצרכנים של מישיגן (סופי)",
    "JOLTS Job Openings": "סקר משרות פנויות (JOLTS)",
    "ADP Non-Farm Employment Change": "סקר תעסוקה במגזר הפרטי (ADP)",
    "Crude Oil Inventories": "מלאי הנפט הגולמי בארה״ב",
    "Existing Home Sales": "מכירות בתים קיימים",
    "New Home Sales": "מכירות בתים חדשים",
    "Building Permits": "אישורי בנייה",
    "Durable Goods Orders m/m": "הזמנות מוצרים בני קיימא",
    "Core Durable Goods Orders m/m": "הזמנות מוצרים בני קיימא (ליבה)",
    "Empire State Manufacturing Index": "מדד הייצור של ניו יורק (Empire State)",
    "Philly Fed Manufacturing Index": "מדד הייצור של פילדלפיה"
}

def heb(text):
    """סידור טקסט בעברית שיוצג בכיוון הנכון בתמונה"""
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)

def translate_macro(eng_title):
    if eng_title in MACRO_TRANSLATIONS:
        return MACRO_TRANSLATIONS[eng_title]
    # תרגום חלקי חכם אם השם מעט שונה
    for k, v in MACRO_TRANSLATIONS.items():
        if k.lower() in eng_title.lower():
            return v
    if "Speaks" in eng_title and "FOMC" in eng_title:
        return "נאום חבר פד (FOMC)"
    return "נתון מאקרו ארה״ב"

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
                        eng_title = item.get("title", "")
                        events.append({
                            "time": time_str,
                            "title_en": eng_title,
                            "title_he": translate_macro(eng_title),
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
                name = row.get("name", "")[:16]
                
                entry = {"symbol": sym, "name": name, "eps": eps_est, "is_major": sym in MAJOR_TICKERS}
                if "pre-market" in time_type:
                    bmo.append(entry)
                elif "after-hours" in time_type:
                    amc.append(entry)
    except Exception as e:
        print(f"Error fetching earnings: {e}")
    return bmo[:6], amc[:6]

def fetch_ticker_logo(symbol, size=56):
    """שליפת לוגו של מניה מהאינטרנט וחיתוך לעיגול יוקרתי"""
    urls = [
        f"https://financialmodelingprep.com/image-stock/{symbol}.png",
        f"https://storage.googleapis.com/iex/api/logos/{symbol}.png"
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=4)
            if r.status_code == 200 and len(r.content) > 500:
                logo_img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                # יצירת רקע לבן עגול כדי שהלוגו יבלוט
                bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
                logo_img.thumbnail((int(size * 0.78), int(size * 0.78)), Image.Resampling.LANCZOS)
                offset = ((size - logo_img.width) // 2, (size - logo_img.height) // 2)
                bg.paste(logo_img, offset, logo_img)
                
                # מסכה עגולה
                mask = Image.new("L", (size, size), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, size, size), fill=255)
                output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                output.paste(bg, (0, 0), mask)
                return output
        except:
            continue
    return None

def load_brand_logo(size=145):
    """טעינת הלוגו של אילן מהפרויקט"""
    for fname in ["logo.jpg", "logo.png", "logo.jpeg", "LOGO.jpg", "LOGO.png"]:
        if os.path.exists(fname):
            try:
                im = Image.open(fname).convert("RGBA")
                im = ImageOps.fit(im, (size, size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (size, size), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=24, fill=255)
                out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                out.paste(im, (0, 0), mask)
                return out
            except Exception as e:
                print(f"Logo load error: {e}")
    return None

def create_image(macro_events, bmo, amc):
    width, height = 1280, 1520
    bg_dark = (10, 16, 29)        # כחול נייבי עמוק שתואם ללוגו
    card_bg = (17, 26, 46)        # כרטיסייה כחולה כהה
    row_bg = (24, 36, 62)         # רקע שורה פנימית
    gold = (218, 176, 96)         # זהב יוקרתי מהלוגו שלך
    gold_bright = (245, 208, 125)
    white = (255, 255, 255)
    gray = (160, 174, 192)
    red_high = (239, 68, 68)
    orange_med = (245, 158, 11)
    blue_accent = (56, 189, 248)

    img = Image.new("RGBA", (width, height), bg_dark)
    draw = ImageDraw.Draw(img)

    # פונטים גדולים וחדים שתומכים בעברית ובאנגלית
    font_path_b = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font_path_r = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    
    f_header = ImageFont.truetype(font_path_b, 50)
    f_sub = ImageFont.truetype(font_path_b, 28)
    f_sec_title = ImageFont.truetype(font_path_b, 32)
    f_macro_he = ImageFont.truetype(font_path_b, 26)
    f_macro_en = ImageFont.truetype(font_path_r, 20)
    f_time = ImageFont.truetype(font_path_b, 28)
    f_ticker = ImageFont.truetype(font_path_b, 30)
    f_comp = ImageFont.truetype(font_path_r, 20)
    f_eps = ImageFont.truetype(font_path_b, 22)
    f_badge = ImageFont.truetype(font_path_b, 19)

    now_il = datetime.now(ISRAEL_TZ)
    date_display = now_il.strftime("%d/%m/%Y")

    # --- HEADER יוקרתי עם הלוגו שלך ---
    draw.rectangle([(0, 0), (width, 195)], fill=(13, 21, 38))
    draw.line([(0, 195), (width, 195)], fill=gold, width=4)

    brand_logo = load_brand_logo(145)
    if brand_logo:
        # מסגרת זהב סביב הלוגו
        draw.rounded_rectangle([(46, 21), (199, 174)], radius=26, outline=gold, width=3)
        img.paste(brand_logo, (50, 25), brand_logo)
        text_x = 230
    else:
        text_x = 50

    draw.text((text_x, 38), "ILAN.KUV | VIP MARKET BRIEF", fill=gold_bright, font=f_header)
    draw.text((text_x, 108), heb(f"יומן מאקרו כלכלי ודוחות וול סטריט  •  {date_display}"), fill=white, font=f_sub)

    # --- SECTION 1: יומן מאקרו (עברית + אנגלית) ---
    y_macro = 230
    macro_box_h = 600
    draw.rounded_rectangle([(40, y_macro), (width - 40, y_macro + macro_box_h)], radius=20, fill=card_bg, outline=gold, width=2)
    
    # כותרת סקשן מאקרו
    draw.rounded_rectangle([(40, y_macro), (width - 40, y_macro + 68)], radius=20, fill=(26, 39, 68))
    draw.text((70, y_macro + 16), "US MACRO CALENDAR", fill=gold_bright, font=f_sec_title)
    heb_macro_hdr = heb("אירועי מאקרו מרכזיים היום (שעון ישראל)")
    draw.text((width - 70 - draw.textlength(heb_macro_hdr, font=f_sec_title), y_macro + 16), heb_macro_hdr, fill=white, font=f_sec_title)

    # כותרות עמודות
    col_y = y_macro + 82
    draw.text((70, col_y), heb("שעה"), fill=gray, font=f_macro_en)
    draw.text((195, col_y), heb("חשיבות"), fill=gray, font=f_macro_en)
    draw.text((345, col_y), heb("האירוע הכלכלי (עברית + אנגלית)"), fill=gray, font=f_macro_en)
    draw.text((925, col_y), heb("צפי"), fill=gold_bright, font=f_macro_en)
    draw.text((1085, col_y), heb("קודם"), fill=gray, font=f_macro_en)

    ry = y_macro + 120
    if not macro_events:
        msg = heb("אין היום פרסומי מאקרו בעלי השפעה גבוהה בארה״ב")
        draw.text(((width - draw.textlength(msg, font=f_sec_title)) // 2, ry + 160), msg, fill=gray, font=f_sec_title)
    else:
        for ev in macro_events:
            draw.rounded_rectangle([(60, ry), (width - 60, ry + 72)], radius=12, fill=row_bg)
            
            # שעה
            draw.text((75, ry + 20), ev["time"], fill=white, font=f_time)
            
            # חשיבות
            imp_color = red_high if ev["impact"] == "High" else orange_med
            imp_text = heb("גבוהה") if ev["impact"] == "High" else heb("בינונית")
            draw.rounded_rectangle([(185, ry + 18), (310, ry + 54)], radius=8, fill=imp_color)
            tw = draw.textlength(imp_text, font=f_badge)
            draw.text((185 + (125 - tw) / 2, ry + 24), imp_text, fill=white, font=f_badge)

            # שם הדוח בעברית (גדול) + אנגלית מתחתיו
            draw.text((345, ry + 8), heb(ev["title_he"]), fill=white, font=f_macro_he)
            draw.text((345, ry + 41), ev["title_en"][:45], fill=gray, font=f_macro_en)

            # צפי וקודם
            draw.text((925, ry + 20), str(ev["forecast"]), fill=gold_bright, font=f_time)
            draw.text((1085, ry + 20), str(ev["previous"]), fill=gray, font=f_time)
            ry += 80

    # --- SECTION 2: חברות מדווחות עם לוגואים ---
    y_earn = 865
    earn_h = 575
    col_w = (width - 100) // 2

    # פונקציה פנימית לציור עמודת דוחות (BMO או AMC)
    def draw_earnings_column(x_start, title_en, title_he, items, accent_color):
        draw.rounded_rectangle([(x_start, y_earn), (x_start + col_w, y_earn + earn_h)], radius=20, fill=card_bg, outline=accent_color, width=2)
        draw.rounded_rectangle([(x_start, y_earn), (x_start + col_w, y_earn + 65)], radius=20, fill=(26, 39, 68))
        draw.text((x_start + 25, y_earn + 16), title_en, fill=accent_color, font=f_sec_title)
        h_txt = heb(title_he)
        draw.text((x_start + col_w - 25 - draw.textlength(h_txt, font=f_macro_he), y_earn + 19), h_txt, fill=white, font=f_macro_he)

        ey = y_earn + 82
        if not items:
            empty_msg = heb("אין דיווחים בולטים")
            draw.text((x_start + (col_w - draw.textlength(empty_msg, font=f_macro_he)) / 2, ey + 180), empty_msg, fill=gray, font=f_macro_he)
        else:
            for item in items:
                draw.rounded_rectangle([(x_start + 18, ey), (x_start + col_w - 18, ey + 72)], radius=14, fill=row_bg)
                
                # שליפת והדבקת לוגו המניה
                logo_im = fetch_ticker_logo(item["symbol"], size=54)
                if logo_im:
                    img.paste(logo_im, (x_start + 30, ey + 9), logo_im)
                else:
                    # עיגול זהב עם האות הראשונה אם אין לוגו
                    draw.ellipse([(x_start + 30, ey + 9), (x_start + 84, ey + 63)], fill=gold)
                    letter = item["symbol"][0]
                    lw = draw.textlength(letter, font=f_ticker)
                    draw.text((x_start + 30 + (54 - lw) / 2, ey + 17), letter, fill=bg_dark, font=f_ticker)

                # טיקר ושם חברה בגדול
                t_color = gold_bright if item["is_major"] else white
                draw.text((x_start + 100, ey + 8), f"${item['symbol']}", fill=t_color, font=f_ticker)
                draw.text((x_start + 100, ey + 42), item["name"], fill=gray, font=f_comp)

                # צפי EPS
                eps_text = f"EPS צפי: {item['eps']}"
                eps_heb = heb(eps_text)
                ew = draw.textlength(eps_heb, font=f_eps)
                draw.text((x_start + col_w - 35 - ew, ey + 23), eps_heb, fill=white, font=f_eps)
                ey += 80

    # ציור שתי העמודות
    draw_earnings_column(40, "BEFORE OPEN", "לפני הפתיחה", bmo, gold)
    draw_earnings_column(60 + col_w, "AFTER CLOSE", "אחרי הסגירה", amc, blue_accent)

    # --- FOOTER ---
    footer_txt = "ILAN.KUV  •  VIP FINANCIAL COMMUNITY  •  DAILY MARKET INTELLIGENCE"
    fw = draw.textlength(footer_txt, font=f_macro_en)
    draw.text(((width - fw) / 2, height - 48), footer_txt, fill=gold, font=f_macro_en)

    output_path = "morning_brief.png"
    img.convert("RGB").save(output_path, quality=95)
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
