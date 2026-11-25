import os
import re
import json
import time
import hashlib
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from datetime import datetime, timezone

# ==========================================
# הגדרת ה-Webhook של חדר בנקים וקרנות גדולות
# ==========================================
INST_WEBHOOK_URL = "https://discord.com/api/webhooks/1573645677118881833/H_urKxNS7XizjGDJuKyMrCHUz9n_zQgVvj5uDoL-X5DlLMBs1_-fHnVYC3RprWIkIYoD"

CACHE_FILE = "sent_inst_notes.json"

GOOGLE_QUERIES = [
    '("Goldman Sachs" OR "Morgan Stanley" OR "Bank of America" OR "BofA" OR "JPMorgan") (stocks OR equities OR "S&P 500" OR overweight OR underweight OR sector)',
    '("BlackRock" OR "Vanguard" OR "Citigroup" OR "Barclays" OR "Wells Fargo" OR "UBS") (stocks OR equities OR market OR sector OR upgrade OR downgrade)'
]

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,IWM,XLF,XLK,XLE,XLV,XLI,XLY,XLP,SMH,IGV&region=US&lang=en-US",
    "https://search.cnbc.com/rs/search/combinedXML/view.xml?partnerId=wrss01&id=10000664",
    "https://www.investing.com/rss/news_25.rss",
    "https://www.marketwatch.com/rss/topstories",
] + [
    f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
    for q in GOOGLE_QUERIES
]

INSTITUTIONS = {
    "Goldman Sachs": ["goldman sachs", "goldman"],
    "Morgan Stanley": ["morgan stanley"],
    "Bank of America (BofA)": ["bank of america", "bofa"],
    "JPMorgan": ["jpmorgan", "jp morgan", "j.p. morgan"],
    "Citigroup (Citi)": ["citigroup", "citi"],
    "BlackRock": ["blackrock"],
    "Vanguard": ["vanguard"],
    "Barclays": ["barclays"],
    "Wells Fargo": ["wells fargo"],
    "UBS": ["ubs"],
    "Deutsche Bank": ["deutsche bank"],
    "Jefferies": ["jefferies"],
    "HSBC": ["hsbc"],
    "RBC": ["rbc", "royal bank of canada"],
    "Bernstein": ["bernstein"],
    "Evercore": ["evercore"],
    "Citadel / Hedge Funds": ["citadel", "hedge fund", "fund manager", "asset manager"],
}

# חסימת מט"ח אמיתית בלבד (לא חוסם יותר Europe או billion-dollar)
FX_REGEX_PATTERNS = [
    r"\bforex\b", r"\bfx\b", r"\bsterling\b", r"\bgbp\b", r"\bjpy\b", r"\bchf\b", r"\bcny\b",
    r"\bexchange rate\b", r"\bcurrency pair\b", r"\bcurrency market\b",
    r"\beur/usd\b", r"\bgbp/usd\b", r"\busd/jpy\b", r"\busd/chf\b", r"\beurusd\b", r"\bgbpusd\b", r"\busdjpy\b",
    r"\bvs\.?\s+dollar\b", r"\bagainst the dollar\b", r"\bdollar index\b", r"\bdxy\b"
]

EQUITY_CONTEXT_KEYWORDS = [
    "stock", "stocks", "equities", "equity", "sector", "sectors",
    "s&p 500", "s&p", "nasdaq", "dow", "wall street", "market", "markets",
    "semiconductor", "chip", "ai ", "tech", "software", "financial",
    "bank stocks", "energy", "healthcare", "industrial", "consumer",
    "small cap", "megacap", "overweight", "underweight", "allocation",
    "portfolio", "exposure", "etf", "fund", "funds", "upgrade", "downgrade",
    "rally", "selloff", "outlook", "forecast", "price target", "bull", "bear", "index"
]

SECTORS = {
    "שבבים ו-AI (Semiconductors / AI)": ["semiconductor", "chip", "ai ", "nvidia", "nvda", "amd", "broadcom", "tsmc", "smh", "soxx"],
    "טכנולוגיה ותוכנה (Tech / Software)": ["tech", "software", "cloud", "megacap", "xlk", "igv", "qqq"],
    "פיננסים ובנקים (Financials)": ["financial", "bank stocks", "xlf", "credit", "lending"],
    "אנרגיה וסחורות (Energy / Commodities)": ["energy", "oil", "crude", "xle", "commodity", "commodities", "gold"],
    "בריאות ופארמה (Healthcare)": ["healthcare", "health care", "pharma", "biotech", "xlv"],
    "תעשייה וביטחון (Industrials / Defense)": ["industrial", "defense", "xli", "aerospace"],
    "צרכנות (Consumer)": ["consumer", "retail", "xly", "xlp"],
    "מניות והקצאת נכסים (Equities / Allocation)": ["equities", "equity", "stocks", "s&p 500", "spy", "allocation", "asset mix", "inflows", "outflows", "flows"],
}

def clean_html(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def is_fx_noise(text_lower: str) -> bool:
    return any(re.search(pattern, text_lower) for pattern in FX_REGEX_PATTERNS)

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("ids", []))
        except Exception:
            pass
    return set()

def save_cache(ids_set):
    try:
        trimmed = sorted(list(ids_set))[-500:]
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ids": trimmed}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Cache save error: {e}")

def make_item_id(title: str, link: str) -> str:
    raw = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def detect_institutions(text_lower: str) -> list[str]:
    matched = []
    for name, aliases in INSTITUTIONS.items():
        if any(alias in text_lower for alias in aliases):
            matched.append(name)
    return matched

def detect_sectors(text_lower: str) -> list[str]:
    matched = []
    for sector_name, keywords in SECTORS.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(sector_name)
    return matched if matched else ["מניות והקצאת נכסים (Equities Strategy)"]

def extract_explicit_stance(text_lower: str):
    explicit_bull = [
        "overweight", "upgrade", "upgraded", "raise exposure", "raises exposure",
        "increase exposure", "outperform", "top pick", "raises target", "inflows", "bullish"
    ]
    explicit_bear = [
        "underweight", "downgrade", "downgraded", "cut exposure", "cuts exposure",
        "reduce exposure", "underperform", "lowers target", "outflows", "trim exposure", "bearish"
    ]

    bull_hits = sum(1 for phrase in explicit_bull if phrase in text_lower)
    bear_hits = sum(1 for phrase in explicit_bear if phrase in text_lower)

    if bull_hits > bear_hits:
        return (
            "🟢 ביטוי חיובי / הרחבת חשיפה מפורשת",
            0x00E676,
            "הגדלה / חיזוק"
        )
    elif bear_hits > bull_hits:
        return (
            "🔴 ביטוי זהיר / צמצום חשיפה מפורש",
            0xFF3B5C,
            "צמצום / זהירות"
        )
    return (
        "🔵 סקירה / עדכון עמדה מוסדית (ללא שינוי חשיפה מפורש)",
        0x3498DB,
        "עדכון מוסדי"
    )

def distill_takeaway(title: str, desc: str, insts: list[str], sectors: list[str]) -> str:
    inst_part = ", ".join(insts)
    sec_part = sectors[0].split(" (")[0] if sectors else "מניות"
    base = f"עדכון מאת {inst_part} בתחום {sec_part}."
    if desc and desc.lower() != title.lower():
        sentences = re.split(r"(?<=[.!?])\s+", desc)
        first_sentence = sentences[0].strip() if sentences else desc
        if len(first_sentence) > 180:
            first_sentence = first_sentence[:177] + "..."
        return f"{base} תמצית המקור: {first_sentence}"
    return f"{base} כותרת: {title}"

def fetch_institutional_items():
    found = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    total_raw = 0
    fx_blocked = 0

    for url in RSS_FEEDS:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"Feed HTTP {resp.status_code}: {url[:60]}")
                continue
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            total_raw += len(items)

            for item in items:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")

                title = clean_html(title_el.text) if title_el is not None and title_el.text else ""
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                desc = clean_html(desc_el.text) if desc_el is not None and desc_el.text else ""

                if not title:
                    continue

                combined = f"{title} {desc}".lower()

                if is_fx_noise(combined):
                    fx_blocked += 1
                    continue

                insts = detect_institutions(combined)
                has_equity_ctx = any(eq in combined for eq in EQUITY_CONTEXT_KEYWORDS)

                if insts and has_equity_ctx:
                    sectors = detect_sectors(combined)
                    stance = extract_explicit_stance(combined)
                    takeaway = distill_takeaway(title, desc, insts, sectors)
                    found.append({
                        "id": make_item_id(title, link),
                        "title": title,
                        "desc": desc,
                        "link": link,
                        "institutions": insts,
                        "sectors": sectors,
                        "stance": stance,
                        "takeaway": takeaway
                    })
        except Exception as e:
            print(f"RSS error for {url[:60]}: {e}")

    print(f"Scan summary -> Raw items: {total_raw} | FX blocked: {fx_blocked} | Matched: {len(found)}")
    return found

def send_inst_alert(item: dict):
    if not INST_WEBHOOK_URL or "YOUR_" in INST_WEBHOOK_URL:
        print("INST_WEBHOOK_URL is not set.")
        return

    stance_text, color, action_short = item["stance"]
    inst_str = ", ".join(item["institutions"])
    sector_str = ", ".join(item["sectors"][:2])

    short_desc = item["desc"]
    if len(short_desc) > 320:
        short_desc = short_desc[:317] + "..."

    description = (
        f"**מוסד / גוף מדווח:** `{inst_str}`\n"
        f"**תחום / סקטור מזוהה:** `{sector_str}`\n"
        f"**מהות העמדה בכתבה:** {stance_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**זיקוק תמציתי:**\n"
        f"{item['takeaway']}\n\n"
        f"**כותרת מקור:**\n"
        f"**{item['title']}**\n"
    )
    if short_desc and short_desc.lower() != item["title"].lower():
        description += f"\n> {short_desc}\n"
    if item["link"]:
        description += f"\n🔗 [לקריאת הכתבה המלאה]({item['link']})"

    embed = {
        "title": f"🏦 רדאר מוסדי והקצאת נכסים | {action_short}",
        "color": color,
        "description": description,
        "footer": {
            "text": f"Ilan VIP • Institutional Flows Radar • {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')} | למידע בלבד"
        }
    }

    payload = {
        "username": "Quantum Institutional Radar | Ilan VIP",
        "embeds": [embed]
    }
    requests.post(INST_WEBHOOK_URL, json=payload, timeout=20)

def run_bot():
    seen_ids = load_cache()
    items = fetch_institutional_items()
    sent_now = 0

    for item in items:
        if item["id"] in seen_ids:
            continue
        try:
            send_inst_alert(item)
            seen_ids.add(item["id"])
            sent_now += 1
            time.sleep(1.5)
            if sent_now >= 5:
                break
        except Exception as e:
            print(f"Send error: {e}")

    save_cache(seen_ids)
    print(f"Institutional scan finished. Sent {sent_now} new alerts.")

if __name__ == "__main__":
    run_bot()
