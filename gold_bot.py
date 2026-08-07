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
        if daily_change > 0:
            bullish_signals += 1
        else:
            bearish_signals += 1

    if current_macd > current_signal:
        bullish_signals += 1
    else:
        bearish_signals += 1

    if daily_change > 0:
        bullish_signals += 1
    else:
        bearish_signals += 1

    if bullish_signals > bearish_signals:
        trend = "YUKSELIS 🟢📈"
        trend_emoji = "🟢"
    else:
        trend = "DUSUS 🔴📉"
        trend_emoji = "🔴"

    # RSI yorumu
    if current_rsi >= 70:
        rsi_comment = "⚠️ Asiri Alim"
    elif current_rsi <= 30:
        rsi_comment = "⚠️ Asiri Satim"
    elif current_rsi > 55:
        rsi_comment = "Guclu"
    elif current_rsi < 45:
        rsi_comment = "Zayif"
    else:
        rsi_comment = "Orta"

    # MACD yorumu
    if current_hist > 0 and current_macd > current_signal:
        macd_comment = "Yukselis Momentumu ✅"
    elif current_hist < 0 and current_macd < current_signal:
        macd_comment = "Dusus Momentumu ❌"
    elif current_hist > 0:
        macd_comment = "Momentum Gucleniyor"
    else:
        macd_comment = "Momentum Zayifliyor"

    total = bullish_signals + bearish_signals
    bull_pct = int((bullish_signals / total) * 100)

    return {
        "trend": trend,
        "trend_emoji": trend_emoji,
        "price": current_price,
        "ema_fast": current_ema_fast,
        "ema_slow": current_ema_slow,
        "daily_change": daily_change,
        "daily_change_pct": daily_change_pct,
        "rsi": current_rsi,
        "rsi_comment": rsi_comment,
        "macd": current_macd,
        "signal": current_signal,
        "macd_hist": current_hist,
        "macd_comment": macd_comment,
        "bull_pct": bull_pct,
    }

def get_gold_news():
    """Reuters ve MarketWatch RSS'den altin/piyasa haberlerini ceker ve ozet uretir."""
    feeds = [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://www.marketwatch.com/rss/topstories",
    ]
    keywords = ["gold", "xauusd", "fed", "federal reserve", "inflation", "dollar", "interest rate", "faiz", "enflasyon"]
    headlines = []

    for url in feeds:
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                title = item.findtext("title") or ""
                desc = item.findtext("description") or ""
                if any(kw in title.lower() or kw in desc.lower() for kw in keywords):
                    headlines.append(title.strip())
                if len(headlines) >= 4:
                    break
        except Exception:
            continue

    return headlines[:4]

def summarize_news(headlines):
    """Haber basliklarini ozetler."""
    if not headlines:
        return "Bugun altin piyasasini etkileyecek onemli bir haber bulunamadi."

    summary_parts = []
    keywords_map = {
        "fed": "Fed politikasi",
        "federal reserve": "Fed politikasi",
        "interest rate": "faiz karari",
        "inflation": "enflasyon verisi",
        "dollar": "dolar hareketi",
        "gold": "altin piyasasi",
        "recession": "resesyon endisesi",
        "gdp": "buyume verisi",
    }

    mentioned = set()
    for h in headlines:
        for kw, label in keywords_map.items():
            if kw in h.lower() and label not in mentioned:
                mentioned.add(label)

    if mentioned:
        return "Piyasada one cikan konular: " + ", ".join(mentioned) + "."
    else:
        return headlines[0] if headlines else "Onemli haber bulunamadi."

def format_message(analysis, headlines):
    news_summary = summarize_news(headlines)

    headlines_text = ""
    for h in headlines:
        headlines_text += f"• {h}\n"

    change_emoji = "🔺" if analysis['daily_change'] > 0 else "🔻"

    return (
        f"{analysis['trend_emoji']} *GOLD AI - Gunluk Analiz*\n\n"
        f"💰 *Spot Fiyat (XAU/USD):* ${analysis['price']:.2f}\n"
        f"{change_emoji} *Gunluk Degisim:* {analysis['daily_change']:+.2f} ({analysis['daily_change_pct']:+.2f}%)\n\n"
        f"📊 *Teknik Gostergeler:*\n"
        f"├ EMA{EMA_FAST}: {analysis['ema_fast']:.2f}\n"
        f"├ EMA{EMA_SLOW}: {analysis['ema_slow']:.2f}\n"
        f"├ RSI(14): {analysis['rsi']:.1f} — {analysis['rsi_comment']}\n"
        f"└ MACD: {analysis['macd_comment']}\n\n"
        f"🎯 *Trend Karari:* {analysis['trend']}\n"
        f"📈 Yukselis %{analysis['bull_pct']} / 📉 Dusus %{100 - analysis['bull_pct']}\n\n"
        f"📰 *Piyasa Ozeti:*\n{news_summary}\n\n"
        f"🔍 *Haber Baslikları:*\n{headlines_text}\n"
        f"_⚠️ Bu otomatik teknik analizdir, yatirim tavsiyesi degildir._"
    )

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Token veya Chat ID tanimli degil.")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    response = requests.post(url, data=payload, timeout=15)
    response.raise_for_status()
    return response.json()

def main():
    try:
        current_price, prev_price = get_spot_price()
        data = get_gold_data()
        analysis = calculate_indicators(data, current_price, prev_price)
        headlines = get_gold_news()
        message = format_message(analysis, headlines)
        send_telegram_message(message)
        print("Mesaj basariyla gonderildi.")
        print(message)
    except Exception as e:
        error_msg = f"⚠️ GOLD AI Bot Hatasi: {e}"
        print(error_msg, file=sys.stderr)
        try:
            send_telegram_message(error_msg)
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
