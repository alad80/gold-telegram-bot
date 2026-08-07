"""
==========================================================
GOLD AI v3.0
Professional XAUUSD Telegram Analysis Bot
Author : Gold AI
==========================================================
"""

import os
import sys
import math
import requests
import traceback
import pandas as pd
import numpy as np
import yfinance as yf
import xml.etree.ElementTree as ET

from datetime import datetime
from datetime import timedelta

# ==========================================================
# CONFIG
# ==========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOLD_API_KEY = os.getenv("GOLD_API_KEY")

SYMBOL = "GC=F"

EMA_FAST = 50
EMA_SLOW = 200

RSI_PERIOD = 14

ATR_PERIOD = 14

LOOKBACK_SR = 30

LONG_LIMIT = 75
SHORT_LIMIT = 25

REQUEST_TIMEOUT = 20

VERSION = "3.0"

# ==========================================================
# COLORS
# ==========================================================

GREEN = "🟢"
RED = "🔴"
YELLOW = "🟡"
BLUE = "🔵"

UP = "📈"
DOWN = "📉"

CHECK = "✅"
WARNING = "⚠️"

# ==========================================================
# LOGGER
# ==========================================================

def log(text):

    print(
        f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    )


# ==========================================================
# TELEGRAM
# ==========================================================

def send_message(message):

    if not TELEGRAM_TOKEN:
        raise RuntimeError("Telegram token bulunamadi.")

    if not CHAT_ID:
        raise RuntimeError("Telegram ChatID bulunamadi.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    r = requests.post(
        url,
        data=payload,
        timeout=REQUEST_TIMEOUT
    )

    r.raise_for_status()

    return r.json()


# ==========================================================
# GOLD API
# ==========================================================

def get_spot_price():

    url = "https://www.goldapi.io/api/XAU/USD"

    headers = {
        "x-access-token": GOLD_API_KEY,
        "Content-Type": "application/json"
    }

    r = requests.get(
        url,
        headers=headers,
        timeout=REQUEST_TIMEOUT
    )

    r.raise_for_status()

    js = r.json()

    return (
        float(js["price"]),
        float(js["prev_close_price"])
    )


# ==========================================================
# YFINANCE
# ==========================================================

def download_history():

    df = yf.download(

        SYMBOL,

        period="450d",

        interval="1d",

        auto_adjust=True,

        progress=False

    )

    if df.empty:

        raise RuntimeError("Veri indirilemedi.")

    return df


# ==========================================================
# EMA
# ==========================================================

def ema(series, period):

    return series.ewm(
        span=period,
        adjust=False
    ).mean()


# ==========================================================
# RSI
# ==========================================================

def rsi(series, period=14):

    delta = series.diff()

    gain = delta.where(
        delta > 0,
        0
    )

    loss = -delta.where(
        delta < 0,
        0
    )

    avg_gain = gain.ewm(
        alpha=1/period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))
