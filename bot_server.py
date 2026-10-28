import asyncio
import io
import os
import discord
from discord import app_commands
from discord.ext import commands
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
import yfinance as yf

# הגדרת שרת גרפי ללא מסך עבור Render
matplotlib.use('Agg')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


def generate_ta_chart(ticker_symbol: str):
  ticker_symbol = ticker_symbol.upper().strip()
  df = yf.download(ticker_symbol, period='1y', interval='1d', progress=False)

  if df is None or df.empty:
    return None, None, None

  # טיפול ב-MultiIndex של גרסאות חדשות של yfinance
  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

  df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
  if len(df) < 5:
    return None, None, None

  # חישוב ממוצעים נעים
  df['SMA50'] =
