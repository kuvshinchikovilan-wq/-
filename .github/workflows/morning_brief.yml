name: Daily Morning Brief

on:
  schedule:
    - cron: '0 11 * * 1-5'
  workflow_dispatch:

jobs:
  send_brief:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install libraries
        run: pip install requests pytz Pillow

      - name: Run script and send to Discord
        env:
          DISCORD_WEBHOOK_MORNING: ${{ secrets.DISCORD_WEBHOOK_MORNING }}
        run: python morning_brief.py
