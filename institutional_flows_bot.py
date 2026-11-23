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
    '("Goldman Sachs" OR "Morgan Stanley" OR "Bank of America" OR "BofA" OR "JPMorgan") (overweight OR underweight OR allocation OR equities OR sector)',
    '("BlackRock" OR "Vanguard" OR "Citigroup" OR "Citi" OR "Barclays" OR "Wells Fargo" OR "UBS") (stocks OR equities OR sector OR allocation OR upgrade OR downgrade)'
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

FX_KEYWORDS = [
    "sterling", "gbp", "dollar", "usd", "euro", "eur", "yen", "jpy",
    "franc", "chf", "yuan", "cny", "peso", "forex", "currency", "currencies",
    "fx", "exchange rate"
]

EQUITY_CONTEXT_KEYWORDS = [
    "stock", "stocks", "equities", "equity", "sector", "sectors",
    "s&p 500", "s&p", "nasdaq", "dow", "wall street",
    "semiconductor", "chip", "ai ", "tech", "software", "financial",
    "bank stocks", "energy", "healthcare", "industrial", "consumer",
    "small cap", "megacap", "overweight", "underweight", "allocation",
    "portfolio", "exposure", "etf", "fund", "funds", "upgrade", "downgrade"
]

SECTORS = {
    "שבבים ו-AI (Semiconductors / AI)": ["semiconductor", "chip", "ai ", "nvidia", "nvda", "amd", "broadcom", "tsmc", "smh", "soxx"],
    "טכנולוגיה ותוכנה (Tech / Software)": ["tech", "software", "cloud", "megacap", "xlk", "igv", "qqq"],
    "פיננסים ובנקים (Financials)": ["financial", "bank stocks", "xl
