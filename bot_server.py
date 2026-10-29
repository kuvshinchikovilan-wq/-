import asyncio
from datetime import datetime
import io
import os
from zoneinfo import ZoneInfo
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
# ביטול פירוש סימן $ כנוסחה מתמטית כדי למנוע ParseException כשיש שני מחירים בכותרת
plt.rcParams['text.parse_math'] = False

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


def get_extended_hours_data(ticker_symbol: str, regular_close: float):
  """שליפת נתוני פרי-מרקט ואפטר-מרקט בזמן אמת לפי שעון ניו יורק"""
  ny_tz = ZoneInfo('America/New_York')
  now_ny = datetime.now(ny_tz)
  weekday = now_ny.weekday()
  current_minutes = now_ny.hour * 60 + now_ny.minute

  ext_info = {
      'session': 'REGULAR',
      'label': 'מסחר רציף / סגירה',
      'ext_price': None,
      'ext_change_pct': 0.0,
  }

  try:
    df_intraday = yf.download(
        ticker_symbol,
        period='5d',
        interval='5m',
        prepost=True,
        progress=False,
    )
    if df_intraday is None or df_intraday.empty:
      return ext_info

    if isinstance(df_intraday.columns, pd.MultiIndex):
      df_intraday.columns = df_intraday.columns.get_level_values(0)

    df_intraday = df_intraday.dropna(subset=['Close'])
    if df_intraday.empty:
      return ext_info

    last_ts = df_intraday.index[-1]
    if last_ts.tzinfo is None:
      last_ts = last_ts.tz_localize('UTC').tz_convert(ny_tz)
    else:
      last_ts = last_ts.astimezone(ny_tz)

    latest_price = float(df_intraday['Close'].iloc[-1])
    ts_minutes = last_ts.hour * 60 + last_ts.minute

    # Pre-Market: 04:00 to 09:30 NY Time
    if 240 <= ts_minutes < 570 and weekday < 5:
      ext_info['session'] = 'PRE'
      ext_info['label'] = 'Pre-Market (טרום מסחר)'
      ext_info['ext_price'] = latest_price
      ext_info['ext_change_pct'] = (
          (latest_price - regular_close) / regular_close
      ) * 100
    # After-Hours: 16:00 to 20:00 NY Time (or overnight latest print)
    elif ts_minutes >= 960 or current_minutes >= 960 or current_minutes < 240:
      if abs(latest_price - regular_close) / regular_close > 0.0005:
        ext_info['session'] = 'POST'
        ext_info['label'] = 'After-Hours (מסחר מאוחר)'
        ext_info['ext_price'] = latest_price
        ext_info['ext_change_pct'] = (
            (latest_price - regular_close) / regular_close
        ) * 100
  except Exception:
    pass

  return ext_info


def calc_diagonal_trendlines(plot_df: pd.DataFrame):
  """חישוב קווי מגמה אלכסוניים על בסיס נקודות קיצון (Swing Highs / Lows)"""
  n = len(plot_df)
  x = np.arange(n)
  highs = plot_df['High'].values.astype(float)
  lows = plot_df['Low'].values.astype(float)

  pivots_h = []
  pivots_l = []
  start_idx = max(3, n - 75)

  for i in range(start_idx, n - 2):
    if highs[i] == np.max(highs[i - 3 : i + 3]):
      pivots_h.append((i, highs[i]))
    if lows[i] == np.min(lows[i - 3 : i + 3]):
      pivots_l.append((i, lows[i]))

  if len(pivots_h) >= 2:
    p1, p2 = pivots_h[-2], pivots_h[-1]
    if p1[0] != p2[0]:
      slope_h = (p2[1] - p1[1]) / (p2[0] - p1[0])
      intercept_h = p1[1] - slope_h * p1[0]
    else:
      slope_h, intercept_h = np.polyfit(x[-40:], highs[-40:], 1)
  else:
    slope_h, intercept_h = np.polyfit(x[-40:], highs[-40:], 1)

  if len(pivots_l) >= 2:
    p1, p2 = pivots_l[-2], pivots_l[-1]
    if p1[0] != p2[0]:
      slope_l = (p2[1] - p1[1]) / (p2[0] - p1[0])
      intercept_l = p1[1] - slope_l * p1[0]
    else:
      slope_l, intercept_l = np.polyfit(x[-40:], lows[-40:], 1)
  else:
    slope_l, intercept_l = np.polyfit(x[-40:], lows[-40:], 1)

  upper_line = slope_h * x + intercept_h
  lower_line = slope_l * x + intercept_l

  return upper_line, lower_line, slope_h, slope_l


def generate_ta_package(ticker_symbol: str):
  ticker_symbol = ticker_symbol.upper().strip()
  df = yf.download(ticker_symbol, period='1y', interval='1d', progress=False)

  if df is None or df.empty:
    return None, None

  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

  df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
  if len(df) < 25:
    return None, None

  df['SMA50'] = df['Close'].rolling(window=50).mean()
  df['SMA100'] = df['Close'].rolling(window=100).mean()
  df['SMA200'] = df['Close'].rolling(window=200).mean()

  # חישוב RSI (14) בשיטת Wilder
  delta = df['Close'].diff()
  gain = delta.clip(lower=0)
  loss = -1 * delta.clip(upper=0)
  avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
  avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
  rs = avg_gain / avg_loss
  df['RSI'] = 100 - (100 / (1 + rs))

  plot_df = df.tail(95).copy()
  plot_df['DateNum'] = mdates.date2num(plot_df.index.to_pydatetime())

  last_close = float(plot_df['Close'].iloc[-1])
  prev_close = (
      float(plot_df['Close'].iloc[-2]) if len(plot_df) > 1 else last_close
  )
  pct_change = ((last_close - prev_close) / prev_close) * 100
  last_rsi = (
      float(plot_df['RSI'].iloc[-1])
      if pd.notna(plot_df['RSI'].iloc[-1])
      else 50.0
  )

  sma50_val = (
      float(plot_df['SMA50'].iloc[-1])
      if pd.notna(plot_df['SMA50'].iloc[-1])
      else None
  )
  sma100_val = (
      float(plot_df['SMA100'].iloc[-1])
      if pd.notna(plot_df['SMA100'].iloc[-1])
      else None
  )
  sma200_val = (
      float(plot_df['SMA200'].iloc[-1])
      if pd.notna(plot_df['SMA200'].iloc[-1])
      else None
  )

  # בדיקת Pre-Market / After-Hours
  ext_info = get_extended_hours_data(ticker_symbol, last_close)
  active_price = (
      ext_info['ext_price']
      if ext_info['ext_price'] is not None
      else last_close
  )

  # רמות תמיכה והתנגדות אופקיות
  recent_highs = plot_df['High'].nlargest(8).values
  recent_lows = plot_df['Low'].nsmallest(8).values

  above_prices = sorted(
      [float(h) for h in recent_highs if h > last_close * 1.003]
  )
  below_prices = sorted(
      [float(l) for l in recent_lows if l < last_close * 0.997], reverse=True
  )

  r1 = above_prices[0] if above_prices else float(plot_df['High'].max()) * 1.01
  r2 = (
      above_prices[-1]
      if len(above_prices) > 1 and above_prices[-1] > r1 * 1.01
      else r1 * 1.035
  )

  s1 = below_prices[0] if below_prices else float(plot_df['Low'].min()) * 0.99
  s2 = (
      below_prices[-1]
      if len(below_prices) > 1 and below_prices[-1] < s1 * 0.99
      else s1 * 0.965
  )

  # קווים אלכסוניים
  upper_trend, lower_trend, slope_h, slope_l = calc_diagonal_trendlines(plot_df)
  diag_res_now = float(upper_trend[-1])
  diag_sup_now = float(lower_trend[-1])

  # ================= בניית הגרף היוקרתי (3 פאנלים) =================
  fig = plt.figure(figsize=(13.5, 9.2), facecolor='#07090e')
  gs = fig.add_gridspec(3, 1, height_ratios=[3.8, 1.0, 1.2], hspace=0.07)

  ax1 = fig.add_subplot(gs[0], facecolor='#0a0d14')
  ax2 = fig.add_subplot(gs[1], facecolor='#0a0d14', sharex=ax1)
  ax3 = fig.add_subplot(gs[2], facecolor='#0a0d14', sharex=ax1)

  for ax in [ax1, ax2, ax3]:
    ax.grid(True, color='#161c28', linestyle='-', linewidth=0.6, alpha=0.85)
    for spine in ax.spines.values():
      spine.set_color('#1e2636')

  ax1.text(
      0.5,
      0.5,
      f'{ticker_symbol} • ILAN VIP',
      transform=ax1.transAxes,
      fontsize=34,
      color='#ffffff',
      alpha=0.035,
      ha='center',
      va='center',
      fontweight='bold',
      zorder=1,
  )

  width = 0.62
  for idx, row in plot_df.iterrows():
    x = row['DateNum']
    o, h, l, c = (
        float(row['Open']),
        float(row['High']),
        float(row['Low']),
        float(row['Close']),
    )
    v = float(row['Volume']) if 'Volume' in row else 0.0

    is_bull = c >= o
    color = '#00e676' if is_bull else '#ff3b5c'
    ax1.plot([x, x], [l, h], color=color, linewidth=1.15, zorder=2)

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
    ax2.bar(x, v, width=width, color=color, alpha=0.55, zorder=2)

  if plot_df['SMA50'].notna().any():
    ax1.plot(
        plot_df['DateNum'],
        plot_df['SMA50'],
        color='#00d2ff',
        linewidth=1.6,
        label='SMA 50',
        zorder=4,
    )
  if plot_df['SMA100'].notna().any():
    ax1.plot(
        plot_df['DateNum'],
        plot_df['SMA100'],
        color='#ffaa00',
        linewidth=1.6,
        label='SMA 100',
        zorder=4,
    )
  if plot_df['SMA200'].notna().any():
    ax1.plot(
        plot_df['DateNum'],
        plot_df['SMA200'],
        color='#b366ff',
        linewidth=1.8,
        label='SMA 200',
        zorder=4,
    )

  trend_len = min(55, len(plot_df))
  ax1.plot(
      plot_df['DateNum'].values[-trend_len:],
      upper_trend[-trend_len:],
      color='#ff6b81',
      linestyle='-.',
      linewidth=1.4,
      alpha=0.85,
      label='Diag Resistance',
      zorder=4,
  )
  ax1.plot(
      plot_df['DateNum'].values[-trend_len:],
      lower_trend[-trend_len:],
      color='#2ed573',
      linestyle='-.',
      linewidth=1.4,
      alpha=0.85,
      label='Diag Support',
      zorder=4,
  )

  x_max = plot_df['DateNum'].max() + 2
  ax1.set_xlim(plot_df['DateNum'].min() - 2, x_max + 15)

  y_min = min(float(plot_df['Low'].min()), s2) * 0.975
  y_max = max(float(plot_df['High'].max()), r2) * 1.025
  ax1.set_ylim(y_min, y_max)

  levels = [
      (r2, f'R2: ${r2:.2f}', '#ff3b5c', 'white'),
      (r1, f'R1: ${r1:.2f}', '#ff3b5c', 'white'),
      (last_close, f'CLOSE: ${last_close:.2f}', '#ffd32a', 'black'),
      (s1, f'S1: ${s1:.2f}', '#00e676', 'black'),
      (s2, f'S2: ${s2:.2f}', '#00e676', 'black'),
  ]

  if ext_info['ext_price'] is not None:
    ext_tag = 'PRE' if ext_info['session'] == 'PRE' else 'AH'
    levels.append(
        (
            ext_info['ext_price'],
            f"{ext_tag}: ${ext_info['ext_price']:.2f}",
            '#d980fa',
            'black',
        )
    )

  for val, text, bg_color, txt_color in levels:
    if y_min <= val <= y_max:
      ax1.axhline(
          val,
          color=bg_color,
          linestyle='--',
          linewidth=0.8,
          alpha=0.55,
          zorder=1,
      )
      ax1.text(
          x_max + 0.6,
          val,
          f' {text} ',
          color=txt_color,
          fontsize=7.8,
          fontweight='bold',
          va='center',
          ha='left',
          bbox=dict(
              boxstyle='round,pad=0.22', facecolor=bg_color, edgecolor='none'
          ),
          zorder=6,
      )

  ax2.set_ylabel('VOLUME', color='#7f8fa6', fontsize=8, fontweight='bold')

  # ================= פאנל RSI (14) =================
  rsi_series = plot_df['RSI'].values.astype(float)
  dates_num = plot_df['DateNum'].values

  ax3.plot(dates_num, rsi_series, color='#00d2ff', linewidth=1.5, zorder=4)
  ax3.fill_between(
      dates_num,
      rsi_series,
      50,
      where=(rsi_series >= 50),
      color='#00d2ff',
      alpha=0.10,
  )
  ax3.fill_between(
      dates_num,
      rsi_series,
      50,
      where=(rsi_series < 50),
      color='#ff3b5c',
      alpha=0.10,
  )
  ax3.axhspan(70, 100, color='#ff3b5c', alpha=0.06)
  ax3.axhspan(0, 30, color='#00e676', alpha=0.06)

  ax3.axhline(70, color='#ff3b5c', linestyle='--', linewidth=0.85, alpha=0.75)
  ax3.axhline(50, color='#7f8fa6', linestyle=':', linewidth=0.7, alpha=0.5)
  ax3.axhline(30, color='#00e676', linestyle='--', linewidth=0.85, alpha=0.75)

  ax3.set_ylim(10, 90)
  ax3.set_yticks([30, 50, 70])
  ax3.set_ylabel('RSI (14)', color='#00d2ff', fontsize=8.5, fontweight='bold')

  rsi_badge_color = (
      '#ff3b5c'
      if last_rsi >= 70
      else ('#00e676' if last_rsi <= 30 else '#00d2ff')
  )
  ax3.text(
      x_max + 0.6,
      last_rsi,
      f' RSI: {last_rsi:.1f} ',
      color='black',
      fontsize=7.8,
      fontweight='bold',
      va='center',
      ha='left',
      bbox=dict(
          boxstyle='round,pad=0.22', facecolor=rsi_badge_color, edgecolor='none'
      ),
      zorder=6,
  )

  # כותרות עליונות
  sign = '+' if pct_change >= 0 else ''
  header_left = f'{ticker_symbol} • INSTITUTIONAL TECHNICAL CHART (1D)'
  header_right = f'CLOSE: ${last_close:.2f} ({sign}{pct_change:.2f}%)'
  if ext_info['ext_price'] is not None:
    ext_s = '+' if ext_info['ext_change_pct'] >= 0 else ''
    header_right += f"  |  {ext_info['session']}: ${ext_info['ext_price']:.2f} ({ext_s}{ext_info['ext_change_pct']:.2f}%)"

  ax1.set_title(
      header_left,
      color='#f5f6fa',
      fontsize=10.5,
      fontweight='bold',
      loc='left',
      pad=12,
  )
  ax1.set_title(
      header_right,
      color='#ffd32a',
      fontsize=10,
      fontweight='bold',
      loc='right',
      pad=12,
  )

  legend = ax1.legend(
      loc='upper left',
      frameon=True,
      facecolor='#111622',
      edgecolor='#232c40',
      fontsize=7.8,
      ncol=5,
  )
  for text in legend.get_texts():
    text.set_color('#dcdde1')

  ax1.tick_params(colors='#8b949e', labelsize=8, labelbottom=False)
  ax2.tick_params(colors='#8b949e', labelsize=7.5, labelbottom=False)
  ax3.tick_params(colors='#8b949e', labelsize=8)

  ax3.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
  ax3.xaxis.set_major_locator(mdates.DayLocator(interval=15))

  buf = io.BytesIO()
  plt.savefig(
      buf,
      format='png',
      dpi=170,
      bbox_inches='tight',
      facecolor=fig.get_facecolor(),
  )
  plt.close(fig)
  buf.seek(0)

  # ================= בניית הניתוח המילולי והתרחישים (Embed) =================
  ma_signals = []
  if sma50_val:
    ma_signals.append(
        f'מעל SMA50 (${sma50_val:.2f})'
        if active_price >= sma50_val
        else f'מתחת ל-SMA50 (${sma50_val:.2f})'
    )
  if sma100_val:
    ma_signals.append(
        f'מעל SMA100 (${sma100_val:.2f})'
        if active_price >= sma100_val
        else f'מתחת ל-SMA100 (${sma100_val:.2f})'
    )
  if sma200_val:
    ma_signals.append(
        f'מעל SMA200 (${sma200_val:.2f})'
        if active_price >= sma200_val
        else f'מתחת ל-SMA200 (${sma200_val:.2f})'
    )

  if sma50_val and sma200_val:
    if active_price > sma50_val and active_price > sma200_val:
      trend_summary = (
          '🟢 **מגמה חיובית (Bullish):** המניה נסחרת מעל הממוצעים המרכזיים'
      )
    elif active_price < sma50_val and active_price < sma200_val:
      trend_summary = (
          '🔴 **מגמה שלילית (Bearish):** המניה נסחרת מתחת לממוצעים המרכזיים'
      )
    else:
      trend_summary = '🟡 **מגמה מעורבת / התכנסות:** המניה נסחרת בין הממוצעים הנעים'
  else:
    trend_summary = '🟡 **מבנה מחיר בבחינה**'

  if last_rsi >= 70:
    rsi_desc = f'**{last_rsi:.1f}** (קניית יתר / Overbought – מומנטום חזק אך קיימת סכנת מימוש קצר טווח)'
  elif last_rsi <= 30:
    rsi_desc = f'**{last_rsi:.1f}** (מכירת יתר / Oversold – לחץ מוכרים קיצוני, פוטנציאל לריבאונד טכני)'
  elif last_rsi >= 55:
    rsi_desc = (
        f'**{last_rsi:.1f}** (מומנטום חיובי בשליטת קונים, עם מרווח להמשך תנועה)'
    )
  elif last_rsi <= 45:
    rsi_desc = f'**{last_rsi:.1f}** (מומנטום חלש הנוטה למוכרים מתחת לקו ה-50)'
  else:
    rsi_desc = f'**{last_rsi:.1f}** (אזור ניטרלי / שיווי משקל)'

  if slope_h > 0 and slope_l > 0:
    channel_desc = 'תעלה אלכסונית עולה (שפלים ופסגות עולים)'
  elif slope_h < 0 and slope_l < 0:
    channel_desc = 'תעלה אלכסונית יורדת (לחץ היצע אלכסוני מלמעלה)'
  elif slope_h < 0 and slope_l > 0:
    channel_desc = 'התכנסות משולש סימטרי (דחיסת קפיץ לקראת תנועה חדה)'
  else:
    channel_desc = 'מבנה התרחבות תנודתי'

  if ext_info['ext_price'] is not None:
    ext_s = '+' if ext_info['ext_change_pct'] >= 0 else ''
    session_text = (
        f"🕒 **זיהוי מסחר מורחב ({ext_info['label']}):**\n"
        f"המניה נסחרת כעת ב-**${ext_info['ext_price']:.2f}** ({ext_s}{ext_info['ext_change_pct']:.2f}% ביחס לסגירה ב-${last_close:.2f}). "
    )
    if ext_info['ext_price'] > r1:
      session_text += f'⚠️ שים לב: המניה פורצת במסחר המורחב מעל רמת ההתנגדות R1 (${r1:.2f}) – במידה ותחזיק מעליה בפתיחה, צפוי מומנטום חיובי חזק.'
    elif ext_info['ext_price'] < s1:
      session_text += f'⚠️ שים לב: המניה נסחרת במסחר המורחב מתחת לתמיכה S1 (${s1:.2f}) – סכנת שבירה בפתיחת המסחר.'
    else:
      session_text += 'המחיר נע בתוך טווח התמיכה וההתנגדות הקרוב.'
  else:
    session_text = f'🕒 **מצב מסחר:** נתוני סגירה / מסחר רציף אחרון (**${last_close:.2f}**, {sign}{pct_change:.2f}%).'

  embed_color = 0x00E676 if pct_change >= 0 else 0xFF3B5C
  embed = discord.Embed(
      title=f'📊 ניתוח טכני מקיף ותוכנית עבודה: ${ticker_symbol}',
      description=session_text,
      color=embed_color,
  )

  embed.add_field(
      name='📐 מבנה מגמה, ממוצעים וקווים אלכסוניים',
      value=(
          f'• {trend_summary}\n'
          f'• **מיקום ביחס לממוצעים:** {", ".join(ma_signals)}\n'
          f'• **מבנה אלכסוני:** {channel_desc} (התנגדות אלכסונית ב-**${diag_res_now:.2f}**, תמיכה אלכסונית ב-**${diag_sup_now:.2f}**)'
      ),
      inline=False,
  )

  embed.add_field(
      name='⚡ מדד עוצמה יחסית – RSI (14)',
      value=f'• **קריאה נוכחית:** {rsi_desc}',
      inline=False,
  )

  embed.add_field(
      name='🟢 תרחיש חיובי (Bullish Scenario)',
      value=(
          f'התבססות מעל **${s1:.2f}** ופריצה במומנטום של רמת ההתנגדות האופקית ב-**${r1:.2f}** '
          f'(והקו האלכסוני באזור **${diag_res_now:.2f}**) יפתחו פוטנציאל מהלך לעבר היעד הבא ב-**${r2:.2f}**.'
      ),
      inline=False,
  )

  embed.add_field(
      name='🔴 תרחיש שלילי (Bearish Scenario)',
      value=(
          f'חולשה מתחת ל-**${r1:.2f}** ושבירה בסגירה יומית של רמת התמיכה ב-**${s1:.2f}** '
          f'(או שבירת התמיכה האלכסונית ב-**${diag_sup_now:.2f}**) עלולות להוביל להעמקת מימושים לעבר רצועת התמיכה ב-**${s2:.2f}**.'
      ),
      inline=False,
  )

  embed.set_image(url=f'attachment://{ticker_symbol}_vip_ta.png')
  embed.set_footer(text='Ilan VIP Quant System • נשמר עבורך באופן קבוע בפרטי')

  return buf, embed


@bot.event
async def on_ready():
  print(f'Logged in as {bot.user} (ID: {bot.user.id})')
  try:
    for guild in bot.guilds:
      bot.tree.clear_commands(guild=guild)
      bot.tree.copy_global_to(guild=guild)
      await bot.tree.sync(guild=guild)
    print('VIP Slash commands synced cleanly across all servers!')
  except Exception as e:
    print(f'Sync error: {e}')


@bot.tree.command(
    name='ta',
    description=(
        'קבלת גרף פרימיום + ניתוח טכני כתוב, תרחישים וזיהוי פרימרקט (נשמר'
        ' בפרטי)'
    ),
)
@app_commands.describe(ticker='סימול המניה באנגלית (למשל NVDA, AAPL, TSLA)')
async def slash_ta(interaction: discord.Interaction, ticker: str):
  await interaction.response.defer(ephemeral=True)
  clean_ticker = ticker.upper().strip()

  try:
    buf, embed = await asyncio.to_thread(generate_ta_package, clean_ticker)
    if buf is None or embed is None:
      await interaction.followup.send(
          f'❌ לא נמצאו מספיק נתונים עבור הטיקר **{clean_ticker}**.',
          ephemeral=True,
      )
      return

    file = discord.File(fp=buf, filename=f'{clean_ticker}_vip_ta.png')

    try:
      await interaction.user.send(embed=embed, file=file)
      await interaction.followup.send(
          f'✅ **הניתוח הטכני המלא והגרף עבור ${clean_ticker} נשלחו אליך להודעות הפרטיות (DM)!**\n'
          f'*(כך התמונה והתרחישים יישארו שמורים אצלך לתמיד גם אחרי שתצא מהחדר)*',
          ephemeral=True,
      )
    except discord.Forbidden:
      buf.seek(0)
      fallback_file = discord.File(
          fp=buf, filename=f'{clean_ticker}_vip_ta.png'
      )
      await interaction.followup.send(
          content='⚠️ *ההודעות הפרטיות שלך סגורות בשרת, לכן הניתוח מוצג כאן (פתח אפשרות לקבלת DM מהשרת כדי שהגרפים יישמרו לך בפרטי לתמיד):*',
          embed=embed,
          file=fallback_file,
          ephemeral=True,
      )

  except Exception as e:
    await interaction.followup.send(
        f'❌ שגיאה בהפקת הניתוח: {e}', ephemeral=True
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
    buf, embed = await asyncio.to_thread(generate_ta_package, clean_ticker)
    if buf is None or embed is None:
      await ctx.send(
          f'❌ {ctx.author.mention} לא נמצאו נתונים עבור **{clean_ticker}**.',
          delete_after=12,
      )
      return

    file = discord.File(fp=buf, filename=f'{clean_ticker}_vip_ta.png')
    try:
      await ctx.author.send(embed=embed, file=file)
      await ctx.send(
          f'📬 {ctx.author.mention} הניתוח המלא עבור **${clean_ticker}** נשלח אליך לפרטי (DM) ונשמר שם קבוע!',
          delete_after=8,
      )
    except discord.Forbidden:
      buf.seek(0)
      fallback_file = discord.File(
          fp=buf, filename=f'{clean_ticker}_vip_ta.png'
      )
      await ctx.send(
          content=ctx.author.mention, embed=embed, file=fallback_file
      )

  except Exception as e:
    await ctx.send(f'❌ שגיאה בהפקת הגרף: {e}', delete_after=12)


TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if TOKEN:
  bot.run(TOKEN)
else:
  print('Error: DISCORD_BOT_TOKEN not found.')
