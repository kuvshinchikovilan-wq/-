import os
import base64
import requests
from datetime import datetime
import pytz
import yfinance as yf
from playwright.sync_api import sync_playwright

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_MIDDAY") or os.environ.get("DISCORD_WEBHOOK_MORNING")
ISRAEL_TZ = pytz.timezone('Asia/Jerusalem')

# 1. מדדים מרכזיים
INDICES = [
    {"symbol": "^GSPC", "name": "S&P 500", "tag": "SPX"},
    {"symbol": "^IXIC", "name": "NASDAQ", "tag": "NDX"},
    {"symbol": "^DJI", "name": "DOW JONES", "tag": "DJI"},
    {"symbol": "^RUT", "name": "RUSSELL 2000", "tag": "RUT"},
]

# 2. כל סקטורי השוק + שבבים (Sector Rotation)
SECTORS = [
    {"symbol": "SMH", "name": "Semiconductors"},
    {"symbol": "XLK", "name": "Technology"},
    {"symbol": "XLF", "name": "Financials"},
    {"symbol": "XLE", "name": "Energy"},
    {"symbol": "XLV", "name": "Healthcare"},
    {"symbol": "XLY", "name": "Cons. Discretionary"},
    {"symbol": "XLC", "name": "Communication"},
    {"symbol": "XLI", "name": "Industrials"},
    {"symbol": "XLP", "name": "Cons. Staples"},
    {"symbol": "XLU", "name": "Utilities"},
    {"symbol": "XLRE", "name": "Real Estate"},
    {"symbol": "XLB", "name": "Materials"},
]

# 3. נכסי מאקרו, אג"ח, סחורות וקריפטו מורחב (12 נכסים)
MACRO_ASSETS = [
    {"symbol": "^VIX", "name": "VIX (FEAR)", "type": "num"},
    {"symbol": "DX-Y.NYB", "name": "DOLLAR (DXY)", "type": "num"},
    {"symbol": "^TNX", "name": "US 10Y YIELD", "type": "yield"},
    {"symbol": "^TYX", "name": "US 30Y YIELD", "type": "yield"},
    {"symbol": "TLT", "name": "20Y+ TREASURY (TLT)", "type": "price"},
    {"symbol": "GC=F", "name": "GOLD", "type": "price"},
    {"symbol": "SI=F", "name": "SILVER", "type": "price"},
    {"symbol": "CL=F", "name": "CRUDE OIL", "type": "price"},
    {"symbol": "HG=F", "name": "COPPER", "type": "price"},
    {"symbol": "NG=F", "name": "NATURAL GAS", "type": "price"},
    {"symbol": "BTC-USD", "name": "BITCOIN", "type": "crypto"},
    {"symbol": "ETH-USD", "name": "ETHERE
