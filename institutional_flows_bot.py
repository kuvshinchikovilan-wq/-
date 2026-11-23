import os
import re
import json
import time
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# ==========================================
# הגדרת ה-Webhook של חדר בנקים וקרנות גדולות
# ==========================================
INST_WEBHOOK_URL = "https://discord.com/api/webhooks/1573645677118881833/H_urKxNS7XizjGDJuKyMrCHUz9n_zQgVvj5uDoL-X5DlLMBs1_-fHnVYC3RprWIkIYoD"

CACHE_FILE = "sent_inst_notes.json"

RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,IWM,XLF,XLK,XLE,XLV,XLI,XLY,XLP,SMH,IGV&region=US&lang=en-US",
    "https://search.cnbc.com/rs/search/combinedXML/view.xml?partnerId=wrss01&id=10000664",
    "https://www.investing.com/rss/news_25.rss",
    "https://www.investing.com/rss/news_1.rss",
    "https://www.marketwatch.com/rss/topstories",
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

SECTORS = {
    "שבבים ו-AI (Semiconductors / AI)": ["semiconductor", "chip", "ai ", "nvidia", "nvda", "amd", "broadcom", "tsmc", "smh", "soxx"],
    "טכנולוגיה ותוכנה (Tech / Software)": ["tech", "software", "cloud", "megacap", "xlk", "igv", "qqq"],
    "פיננסים ובנקים (Financials)": ["bank", "financial", "xlf", "credit", "lending"],
    "אנרגיה וסחורות (Energy / Commodities)": ["energy", "oil", "crude", "xle", "commodity", "commodities", "gold"],
    "בריאות ופארמה (Healthcare)": ["healthcare", "health care", "pharma", "biotech", "xlv"],
    "תעשייה וביטחון (Industrials / Defense)": ["industrial", "defense", "xli", "aerospace"],
    "צרכנות (Consumer)": ["consumer", "retail", "xly", "xlp", "spending"],
    "מניות ואקוויטי כללי (Equities / Allocation)": ["equities", "equity", "stocks", "s&p 500", "spy", "allocation", "asset mix", "inflows", "outflows", "flows"],
    "אג\"ח ותשואות (Rates / Bonds)": ["treasury", "yields", "bonds", "fixed income", "rates"],
}

ALLOCATION_KEYWORDS = [
    "overweight", "underweight", "equal-weight", "equal weight",
    "allocation", "equities", "stocks", "sector", "exposure",
    "raise", "raises", "raised", "cut", "cuts", "lower", "lowers",
    "upgrade", "downgrade", "bullish", "bearish", "rotate", "rotation",
    "tilt", "favor", "favors", "cautious", "defensive", "cyclical",
    "target", "price target", "outperform", "underperform",
    "buy", "sell", "inflows", "outflows", "flows", "rally", "risk"
]

def clean_html(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

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
    return matched if matched else ["הקצאת נכסים כללית (General Market / Strategy)"]

def detect_stance(text_lower: str):
    bull_words = ["overweight", "raise", "raises", "raised", "upgrade", "upgraded", "bullish", "favor", "favors", "increase", "boost", "outperform", "buy", "inflows"]
    bear_words = ["underweight", "cut", "cuts", "lower", "lowers", "downgrade", "downgraded", "bearish", "cautious", "defensive", "trim", "reduce", "underperform", "sell", "outflows"]

    bull_hits = sum(1 for w in bull_words if w in text_lower)
    bear_hits = sum(1 for w in bear_words if w in text_lower)

    if bull_hits > bear_hits:
        return (
            "🟢 העלאת חשיפה / עמדה שורית (Overweight / Bullish)",
            0x00E676,
            "הגדלה / חיזוק"
        )
    elif bear_hits > bull_hits:
        return (
            "🔴 הפחתת חשיפה / עמדה זהירה-דובית (Underweight / Cautious)",
            0xFF3B5C,
            "הורדה / צמצום"
        )
    return (
        "🟡 עדכון הקצאה / שינוי עמדה (Allocation / Sector Note)",
        0xFFD700,
        "עדכון עמדה"
    )

def fetch_institutional_items():
    found = []
    total_parsed = 0
    inst_only_count = 0
    headers = {"User-Agent": "Mozilla/5.0"}

    for url in RSS_FEEDS:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                print(f"Feed returned status {resp.status_code}: {url}")
                continue
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            total_parsed += len(items)
            for item in items:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                pub_el = item.find("pubDate")

                title = clean_html(title_el.text) if title_el is not None and title_el.text else ""
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                desc = clean_html(desc_el.text) if desc_el is not None and desc_el.text else ""
                pub_date = clean_html(pub_el.text) if pub_el is not None and pub_el.text else ""

                if not title:
                    continue

                combined = f"{title} {desc}".lower()
                insts = detect_institutions(combined)
                if insts:
                    inst_only_count += 1
                alloc_hits = sum(1 for kw in ALLOCATION_KEYWORDS if kw in combined)

                if insts and alloc_hits >= 1:
                    sectors = detect_sectors(combined)
                    stance = detect_stance(combined)
                    score = len(insts) * 2 + alloc_hits
                    found.append({
                        "id": make_item_id(title, link),
                        "title": title,
                        "desc": desc,
                        "link": link,
                        "pub_date": pub_date,
                        "institutions": insts,
                        "sectors": sectors,
                        "stance": stance,
                        "score": score
                    })
        except Exception as e:
            print(f"RSS error for {url}: {e}")

    print(f"Parsed {total_parsed} RSS items | Matched institutions: {inst_only_count} | Passed allocation filter: {len(found)}")
    found.sort(key=lambda x: x["score"], reverse=True)
    return found

def send_inst_alert(item: dict):
    if not INST_WEBHOOK_URL or "YOUR_" in INST_WEBHOOK_URL:
        print("INST_WEBHOOK_URL is not set.")
        return

    stance_text, color, action_short = item["stance"]
    inst_str = ", ".join(item["institutions"])
    sector_str = ", ".join(item["sectors"][:2])

    short_desc = item["desc"]
    if len(short_desc) > 360:
        short_desc = short_desc[:357] + "..."

    description = (
        f"**מוסד / גוף מדווח:** `{inst_str}`\n"
        f"**סקטור / תחום מזוהה:** `{sector_str}`\n"
        f"**כיוון העמדה:** {stance_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**כותרת הידיעה (מקור):**\n"
        f"**{item['title']}**\n"
    )
    if short_desc:
        description += f"\n> {short_desc}\n"
    if item["link"]:
        description += f"\n🔗 [לקריאת הכתבה המלאה]({item['link']})"

    embed = {
        "title": f"🏦 עדכון מוסדי והקצאת נכסים | {action_short}",
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
    resp = requests.post(INST_WEBHOOK_URL, json=payload, timeout=20)
    if resp.status_code not in (200, 204):
        print(f"Discord webhook status {resp.status_code}: {resp.text}")
    else:
        print(f"Sent alert for: {inst_str} -> {item['title'][:60]}")

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
