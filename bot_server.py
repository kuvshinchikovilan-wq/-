import os
import discord
from discord import app_commands
from discord.ext import commands

# הגדרת ההרשאות שהבוט צריך
intents = discord.Intents.default()
intents.message_content = True

# יצירת מופע הבוט עם קידומת ריקה או סלאש
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
  print(f"Logged in as {bot.user} (ID: {bot.user.id})")
  try:
    # סנכרון פקודות הסלאש מול השרתים של דיסקורד
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} slash command(s).")
  except Exception as e:
    print(f"Failed to sync commands: {e}")


# הגדרת פקודת סלאש: /ta [ticker]
@bot.tree.command(name="ta", description="הפקת ניתוח טכני וגרף למניה")
@app_commands.describe(ticker="הקלד את סימול המניה, לדוגמה: NVDA, AAPL")
async def slash_ta(interaction: discord.interaction, ticker: str):
  # הודעה מיידית שמודיעה למשתמש שהבוט מעבד את הנתונים
  # ephemeral=True אומר שרק המשתמש שהריץ את הפקודה רואה את התשובה!
  await interaction.response.defer(ephemeral=True)

  clean_ticker = ticker.upper().strip()

  try:
    # כאן תכניס את הלוגיקה שלך לייצור הגרף (matplotlib וכו')
    # לצורך הדוגמה אנחנו נשלח כאן את התוצאה חזרה למשתמש באופן פרטי:

    # אם יש לך קובץ תמונה מוכן, אתה שולח אותו כך:
    # file = discord.File("path_to_image.png")
    # await interaction.followup.send(content=πίנתון טכני עבור ${clean_ticker}:, file=file, ephemeral=True)

    await interaction.followup.send(
        f"הנה הניתוח הטכני המבוקש עבור: **{clean_ticker}**", ephemeral=True
    )

  except Exception as e:
    await interaction.followup.send(
        f"שגיאה בהפקת הניתוח עבור {clean_ticker}: {e}", ephemeral=True
    )


# הפעלת הבוט באמצעות הטוקן משתני הסביבה
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if TOKEN:
  bot.run(TOKEN)
else:
  print("Error: DISCORD_BOT_TOKEN environment variable not found.")
