"""
GOLD AI TELEGRAM BOT - Gelismis Versiyon
EMA, RSI, MACD ve Haber Analizi
"""
import os
import sys
import requests
import yfinance as yf
import pandas as pd
import xml.etree.ElementTree as ET

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GOLD_TICKER = "XAUUSD=X"
EMA_FAST = 50
EMA_SLOW = 200

def get_gold_data():
    data = yf.download(GOLD_TICKER, period="400d", interval="1d", progress=False, auto_adjust=True)
    if data.empty:
        data = yf.download("GC=F", period="400d", interval="1d", progress=False, auto_adjust=True)
    if data.empty:
        raise RuntimeError("Altin verisi alinamadi.")
    return data

def calculate_indicators(data):
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

    current_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    daily_change = current_price - prev_price
    daily_change_pct = (daily_change / prev_price) * 100

    current_ema_fast = float(ema_fast.iloc[-1])
    current_ema_slow = float(ema_slow.iloc[-1])
    current_rsi = float(rsi.iloc[-1])
    current_macd = float(macd_line.iloc[-1])
    current_signal = float(signal_line.iloc[-1])
    current_hist = float(macd_hist.iloc[-1])

    # TREND KARARI - kararsiz yok
    bullish_signals = 0
    bearish_signals = 0

    # EMA sinyali
    if current_ema_fast > current_ema_slow:
        bullish_signals += 2
    else:
        bearish_signals += 2

    # Fiyat EMA50'ye gore
    if current_price > current_ema_fast:
        bullish_signals += 1
    else:
        bearish_signals += 1

    # RSI sinyali
    if current_rsi > 55:
        bullish_signals += 1
    elif current_rsi < 45:
        bearish_signals += 1

    # MACD sinyali
    if current_macd > current_signal:
        bullish_signals += 1
    else:
        bearish_signals += 1

    if bullish_signals > bearish_signals:
        trend = "YUKSELIS (Bullish)"
        emoji = "🟢📈"
    else:
        trend = "DUSUS (Bearish)"
        emoji = "🔴📉"

    # RSI yorumu
    if current_rsi >= 70:
        rsi_comment = "⚠️ Asiri Alim Bolgesi"
    elif current_rsi <= 30:
        rsi_comment = "⚠️ Asiri Satim Bolgesi"
    elif current_rsi > 55:
        rsi_comment = "Guclu"
    elif current_rsi < 45:
        rsi_comment = "Zayif"
    else:
        rsi_comment = "Nötr"

    # MACD yorumu
    if current_hist > 0 and current_macd > current_signal:
        macd_comment = "Yukselis Momentumu"
    elif current_hist < 0 and current_macd < current_signal:
        macd_comment = "Dusus Momentumu"
    elif current_hist > 0:
        macd_comment = "Momentum Gucleniyor"
    else:
