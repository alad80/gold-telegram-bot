"""
GOLD AI TELEGRAM BOT
--------------------
Her calistirildiginda XAUUSD (altin) icin basit EMA trend analizi yapar
ve sonucu Telegram'a mesaj olarak gonderir.

Bu bir teknik analiz aracidir, finansal tavsiye degildir.
Piyasa yonu garanti edilemez; sonuclar sadece EMA trendine dayanir.
"""

import os
import sys
import requests
import yfinance as yf
import pandas as pd

# ---------------------------------------------------------
# AYARLAR (ortam degiskenlerinden okunur - guvenlik icin)
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

GOLD_TICKER = "GC=F"     # Yahoo Finance - Gold Futures (XAUUSD'ye cok yakin hareket eder)
EMA_FAST = 50
EMA_SLOW = 200


def get_gold_data():
    """Son verileri Yahoo Finance'den ceker (gunluk mum)."""
    data = yf.download(GOLD_TICKER, period="400d", interval="1d", progress=False)
    if data.empty:
        raise RuntimeError("Altin verisi alinamadi (bos veri dondu).")
    return data


def calculate_trend(data: pd.DataFrame):
    """EMA50 / EMA200 kesisimine gore basit trend yonu hesaplar."""
    close = data["Close"]
    ema_fast = close.ewm(span=EMA_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=EMA_SLOW, adjust=False).mean()
    current_price = float(close.iloc[-1].squeeze())
    current_ema_fast = float(ema_fast.iloc[-1].squeeze())
    current_ema_slow = float(ema_slow.iloc[-1].squeeze())
    prev_price = float(close.iloc[-2].squeeze())
    daily_change = current_price - prev_price
    daily_change_pct = (daily_change / prev_price) * 100
    if current_ema_fast > current_ema_slow and current_price > current_ema_fast:
        trend = "YUKSELIS (Bullish)"
        emoji = "🟢📈"
    elif current_ema_fast < current_ema_slow and current_price < current_ema_fast:
        trend = "DUSUS (Bearish)"
        emoji = "🔴📉"
    else:
        trend = "YATAY / KARARSIZ (Neutral)"
        emoji = "🟡➡️"
    return {
        "trend": trend,
        "emoji": emoji,
        "price": current_price,
        "ema_fast": current_ema_fast,
        "ema_slow": current_ema_slow,
        "daily_change": daily_change,
        "daily_change_pct": daily_change_pct,
    }

def format_message(analysis: dict) -> str:
    return (
        f"{analysis['emoji']} *GOLD AI - Gunluk Analiz*\n\n"
        f"*Guncel Fiyat:* ${analysis['price']:.2f}\n"
        f"*Gunluk Degisim:* {analysis['daily_change']:+.2f} ({analysis['daily_change_pct']:+.2f}%)\n\n"
        f"*EMA{EMA_FAST}:* {analysis['ema_fast']:.2f}\n"
        f"*EMA{EMA_SLOW}:* {analysis['ema_slow']:.2f}\n\n"
        f"*Trend Yonu:* {analysis['trend']}\n\n"
        f"_Not: Bu otomatik bir teknik analizdir, yatirim tavsiyesi degildir. "
        f"Piyasa yonu garanti edilemez._"
    )


def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ortam degiskeni tanimli degil."
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    response = requests.post(url, data=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def main():
    try:
        data = get_gold_data()
        analysis = calculate_trend(data)
        message = format_message(analysis)
        send_telegram_message(message)
        print("Mesaj basariyla gonderildi.")
        print(message)
    except Exception as e:
        error_msg = f"⚠️ GOLD AI Bot Hatasi: {e}"
        print(error_msg, file=sys.stderr)
        # Hata olsa bile Telegram'a haber vermeyi dene
        try:
            send_telegram_message(error_msg)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
