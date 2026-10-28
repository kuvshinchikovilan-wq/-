אין בעיה אחי, הנה **הקוד המלא והמעודכן קומפלט** לקובץ `bot_server.py`.

כל מה שאתה צריך לעשות זה להיכנס ל-GitHub, לפתוח את הקובץ `bot_server.py`, למחוק את כל מה שיש שם, להדביק את הקוד הבא וללחוץ **Commit changes**:

```python
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

  fig = plt.figure(figsize=(12, 7), facecolor='#0b0e14')
  gs = fig.add_gridspec(2, 1, height_ratios=[3.2, 1], hspace=0.06)
  ax1 = fig.add_subplot(gs[0], facecolor='#0b0e14')
  ax2 = fig.add_subplot(gs[1], facecolor='#0b0e14', sharex=ax1)

  ax1.grid(True, color='#1b222d', linestyle='-', linewidth=0.6, alpha=0.8)
  ax2.grid(True, color='#1b222d', linestyle='-', linewidth=0.6, alpha=0.8)

  width = 0.6
  for idx, row in plot_df.iterrows():
    x = row['DateNum']
    o = float(row['Open'])
    h = float(row['High'])
    l = float(row['Low'])
    c = float(row['Close'])
    v = float(row['Volume']) if 'Volume' in row else 0.0

    color = '#10b981' if c >= o else '#ef4444'
    ax1.plot([x, x], [l, h], color=color, linewidth=1.1, zorder=2)

    lower = min(o, c)
    height = max(abs(c - o), (h - l) * 0.015 if h != l else 0.05)
    rect = plt.Rectangle(
        (x - width / 2, lower),
        width,
        height,
        facecolor=color,
        edgecolor=color,
        zorder=3,
    )
    ax1.add_patch(rect)
    ax2.bar(x, v, width=width, color=color, alpha=0.65, zorder=2)

  if plot_df['SMA50'].notna().any():
    ax1.plot(
        plot_df['DateNum'],
        plot_df['SMA50'],
        color='#00a8ff',
        linewidth=1.5,
        label='SMA 50',
        zorder=4,
    )
  if plot_df['SMA100'].notna().any():
    ax1.plot(
        plot_df['DateNum'],
        plot_df['SMA100'],
        color='#f59e0b',
        linewidth=1.5,
        label='SMA 100',
        zorder=4,
    )
  if plot_df['SMA200'].notna().any():
    ax1.plot(
        plot_df['DateNum'],
        plot_df['SMA200'],
        color='#8b5cf6',
        linewidth=1.5,
        label='SMA 200',
        zorder=4,
    )

  x_max = plot_df['DateNum'].max() + 2
  ax1.set_xlim(plot_df['DateNum'].min() - 2, x_max + 14)

  levels = [
      (r2, f'R2: ${r2:.2f}', '#ef4444', 'white'),
      (r1, f'R1: ${r1:.2f}', '#ef4444', 'white'),
      (last_close, f'LAST: ${last_close:.2f}', '#facc15', 'black'),
      (s1, f'S1: ${s1:.2f}', '#10b981', 'white'),
      (s2, f'S2: ${s2:.2f}', '#10b981', 'white'),
  ]

  for val, text, bg_color, txt_color in levels:
    ax1.axhline(
        val, color=bg_color, linestyle='--', linewidth=0.8, alpha=0.6, zorder=1
    )
    ax1.text(
        x_max + 0.5,
        val,
        f' {text} ',
        color=txt_color,
        fontsize=7.5,
        fontweight='bold',
        va='center',
        ha='left',
        bbox=dict(
            boxstyle='round,pad=0.2', facecolor=bg_color, edgecolor='none'
        ),
        zorder=5,
    )

  ax1.set_title(
      f'{ticker_symbol} • DAILY CHART (1D)',
      color='#facc15',
      fontsize=10,
      fontweight='bold',
      loc='right',
      pad=10,
  )
  legend = ax1.legend(
      loc='upper left',
      frameon=True,
      facecolor='#161b22',
      edgecolor='#30363d',
      fontsize=8,
      ncol=3,
  )
  for text in legend.get_texts():
    text.set_color('#c9d1d9')

  ax1.tick_params(colors='#8b949e', labelsize=8, labelbottom=False)
  ax2.tick_params(colors='#8b949e', labelsize=8)

  ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
  ax2.xaxis.set_major_locator(mdates.DayLocator(interval=18))

  for ax in [ax1, ax2]:
    for spine in ax.spines.values():
      spine.set_color('#1b222d')

  buf = io.BytesIO()
  plt.savefig(
      buf,
      format='png',
      dpi=150,
      bbox_inches='tight',
      facecolor=fig.get_facecolor(),
  )
  plt.close(fig)
  buf.seek(0)

  return buf, last_close, pct_change


@bot.event
async def on_ready():
  print(f'Logged in as {bot.user} (ID: {bot.user.id})')
  try:
    for guild in bot.guilds:
      bot.tree.copy_global_to(guild=guild)
      await bot.tree.sync(guild=guild)
    print('Slash commands synced instantly to server!')
  except Exception as e:
    print(f'Sync error: {e}')


@bot.tree.command(name='ta', description='Get private technical analysis chart')
@app_commands.describe(ticker='Stock ticker symbol (e.g. NVDA, KLAC)')
async def slash_ta(interaction: discord.Interaction, ticker: str):
  await interaction.response.defer(ephemeral=True)
  clean_ticker = ticker.upper().strip()

  try:
    buf, last_close, pct_change = await asyncio.to_thread(
        generate_ta_chart, clean_ticker
    )
    if buf is None:
      await interaction.followup.send(
          f'❌ לא נמצאו נתונים עבור **{clean_ticker}**.', ephemeral=True
      )
      return

    sign = '+' if pct_change >= 0 else ''
    msg = f'📊 **ניתוח טכני לבקשתך עבור ${clean_ticker}** | מחיר: **${last_close:.2f}** ({sign}{pct_change:.2f}%)'
    file = discord.File(fp=buf, filename=f'{clean_ticker}_ta.png')
    await interaction.followup.send(content=msg, file=file, ephemeral=True)

  except Exception as e:
    await interaction.followup.send(
        f'❌ שגיאה בהפקת הגרף: {e}', ephemeral=True
    )


@bot.command(name='ta')
async def prefix_ta(ctx: commands.Context, ticker: str = None):
  try:
    await ctx.message.delete()
  except Exception:
    pass

  if not ticker:
    return

  clean_ticker = ticker.upper().strip()
  try:
    buf, last_close, pct_change = await asyncio.to_thread(
        generate_ta_chart, clean_ticker
    )
    if buf is None:
      await ctx.send(
          f'❌ {ctx.author.mention} לא נמצאו נתונים עבור **{clean_ticker}**.',
          delete_after=15,
      )
      return

    sign = '+' if pct_change >= 0 else ''
    msg = f'📊 {ctx.author.mention} **ניתוח טכני לבקשתך עבור ${clean_ticker}** | מחיר: **${last_close:.2f}** ({sign}{pct_change:.2f}%)'
    file = discord.File(fp=buf, filename=f'{clean_ticker}_ta.png')
    await ctx.send(content=msg, file=file)

  except Exception as e:
    await ctx.send(f'❌ שגיאה בהפקת הגרף: {e}', delete_after=15)


TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if TOKEN:
  bot.run(TOKEN)
else:
  print('Error: DISCORD_BOT_TOKEN not found.')

```
