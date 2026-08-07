"""
GOLD AI TELEGRAM BOT - Gelismis Versiyon
GoldAPI.io spot fiyat, EMA, RSI, MACD ve Haber Ozeti
"""
import os
import sys
import requests
import yfinance as yf
import pandas as pd
import xml.etree.ElementTree as ET

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GOLD_API_KEY = os.environ.get("GOLD_API_KEY")
GOLD_TICKER = "GC=F"
EMA_FAST = 50
EMA_SLOW = 200

def get_spot_price():
    """GoldAPI.io'dan gercek zamanli spot fiyat ceker."""
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLD_API_KEY,
        "Content-Type": "application/json"
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return float(data["price"]), float(data["prev_close_price"])

def get_gold_data():
    """Teknik analiz icin yfinance'den tarihsel veri ceker."""
    data = yf.download(GOLD_TICKER, period="400d", interval="1d", progress=False, auto_adjust=True)
    if data.empty:
        raise RuntimeError("Tarihsel altin verisi alinamadi.")
    return data

def calculate_indicators(data, current_price, prev_price):
    close = data["Close"].squeeze()

    # EMA
    ema_fast = close.ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=EMA_SLOW, adjust=False).mean()

    # RSI (14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line

    current_ema_fast = float(ema_fast.iloc[-1])
    current_ema_slow = float(ema_slow.iloc[-1])
    current_rsi = float(rsi.iloc[-1])
    current_macd = float(macd_line.iloc[-1])
    current_signal = float(signal_line.iloc[-1])
    current_hist = float(macd_hist.iloc[-1])

    daily_change = current_price - prev_price
    daily_change_pct = (daily_change / prev_price) * 100

    # TREND KARARI - puan sistemi
    bullish_signals = 0
    bearish_signals = 0

    if current_ema_fast > current_ema_slow:
        bullish_signals += 2
    else:
        bearish_signals += 2

    if current_price > current_ema_fast:
        bullish_signals += 1
    else:
        bearish_signals += 1

    if current_rsi > 55:
        bullish_signals += 1
    elif current_rsi < 45:
        bearish_signals += 1
    else:
