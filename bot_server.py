import asyncio
import io
import os
import discord
from discord import app_commands
from discord.ext import commands
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

matplotlib.use('Agg')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


def generate_ta_chart(ticker_symbol: str):
  ticker_symbol = ticker_symbol.upper().strip()
  df = yf.download(ticker_symbol, period='1y', interval='1d', progress=False)

  if df is None or df.empty:
    return None, None, None

  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

  df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
  if len(df) < 5:
    return None, None, None

  df['SMA50'] = df['Close'].rolling(window=50).mean()
  df['SMA100'] = df['Close'].rolling(window=100).mean()
  df['SMA200'] = df['Close'].rolling(window=200).mean()

  plot_df = df.tail(90).copy()
  plot_df['DateNum'] = mdates.date2num(plot_df.index.to_pydatetime())

  last_close = float(plot_df['Close'].iloc[-1])
  prev_close = (
      float(plot_df['Close'].iloc[-2]) if len(plot_df) > 1 else last_close
  )
  pct_change = ((last_close - prev_close) / prev_close) * 100

  recent_highs = plot_df['High'].nlargest(6).values
  recent_lows = plot_df['Low'].nsmallest(6).values

  above_prices = [h for h in recent_highs if h > last_close]
  below_prices = [l for l in recent_lows if l < last_close]

  r1 = min(above_prices) if above_prices else float(plot_df['High'].max())
  r2 = max(above_prices) if len(above_prices) > 1 else r1 * 1.02

  s1 = max(below_prices) if below_prices else float(plot_df['Low'].min())
  s2 = min(below_prices) if len(below_prices) > 1 else s1 * 0.98

  fig = plt.figure(
