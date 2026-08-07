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
        f"[{datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")}] {text}"
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

# ==========================================================
# MACD
# ==========================================================

def macd(series):

    ema12 = ema(series, 12)

    ema26 = ema(series, 26)

    macd_line = ema12 - ema26

    signal = macd_line.ewm(
        span=9,
        adjust=False
    ).mean()

    histogram = macd_line - signal

    return macd_line, signal, histogram


# ==========================================================
# ATR
# ==========================================================

def atr(df, period=14):

    high = df["High"].squeeze()

    low = df["Low"].squeeze()

    close = df["Close"].squeeze()

    tr1 = high - low

    tr2 = (high - close.shift()).abs()

    tr3 = (low - close.shift()).abs()

    tr = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return tr.rolling(period).mean()


# ==========================================================
# SUPPORT / RESISTANCE
# ==========================================================

def support_resistance(df):

    high = df["High"].squeeze()

    low = df["Low"].squeeze()

    if isinstance(high, pd.DataFrame):
        high = high.iloc[:, 0]

    if isinstance(low, pd.DataFrame):
        low = low.iloc[:, 0]

    high = high.tail(LOOKBACK_SR)
    low = low.tail(LOOKBACK_SR)

    atr_value = float(atr(df).iloc[-1])

    resistance1 = float(high.to_numpy().max())
    resistance2 = resistance1 + atr_value

    support1 = float(low.to_numpy().min())
    support2 = support1 - atr_value

    return {
        "S1": support1,
        "S2": support2,
        "R1": resistance1,
        "R2": resistance2,
        "ATR": atr_value
    }


# ==========================================================
# ECONOMIC CALENDAR
# ==========================================================

def get_calendar():

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    events = []

    try:

        r = requests.get(

            url,

            timeout=REQUEST_TIMEOUT

        )

        r.raise_for_status()

        root = ET.fromstring(r.content)

        for event in root.findall("event"):

            impact = (
                event.findtext("impact") or ""
            ).lower()

            if "high" not in impact:

                continue

            title = event.findtext("title") or ""

            country = event.findtext("country") or ""

            date = event.findtext("date") or ""

            tm = event.findtext("time") or ""

            events.append({

                "title": title,

                "country": country,

                "date": date,

                "time": tm

            })

        return events[:5]

    except Exception as e:

        log(e)

        return []


# ==========================================================
# GOLD NEWS
# ==========================================================

def get_news():

    feeds = [

        "https://www.marketwatch.com/rss/topstories",

        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F"

    ]

    keywords = [

        "gold",

        "xau",

        "fed",

        "inflation",

        "interest",

        "rate",

        "dollar",

        "treasury",

        "cpi",

        "nfp"

    ]

    news = []

    for feed in feeds:

        try:

            r = requests.get(

                feed,

                timeout=REQUEST_TIMEOUT,

                headers={

                    "User-Agent":"Mozilla/5.0"

                }

            )

            root = ET.fromstring(r.content)

            for item in root.iter("item"):

                title = item.findtext("title") or ""

                if any(

                    k in title.lower()

                    for k in keywords

                ):

                    news.append(title)

        except:

            pass

    return news[:5]

# ==========================================================
# ANALYSIS ENGINE
# ==========================================================

def analyze_market(df, spot_price, prev_close):

    close = df["Close"].squeeze()

    ema50 = ema(close, EMA_FAST)
    ema200 = ema(close, EMA_SLOW)

    rsi14 = rsi(close)

    macd_line, signal_line, hist = macd(close)

    sr = support_resistance(df)

    ema50_now = float(ema50.iloc[-1])
    ema200_now = float(ema200.iloc[-1])

    rsi_now = float(rsi14.iloc[-1])

    macd_now = float(macd_line.iloc[-1])
    signal_now = float(signal_line.iloc[-1])
    hist_now = float(hist.iloc[-1])

    atr_now = sr["ATR"]

    daily_change = spot_price - prev_close
    daily_pct = (daily_change / prev_close) * 100

    bull = 0
    bear = 0

    # EMA

    if ema50_now > ema200_now:
        bull += 30
    else:
        bear += 30

    # PRICE

    if spot_price > ema50_now:
        bull += 20
    else:
        bear += 20

    # RSI

    if rsi_now > 60:
        bull += 15

    elif rsi_now < 40:
        bear += 15

    else:

        bull += 7
        bear += 7

    # MACD

    if macd_now > signal_now:

        bull += 20

    else:

        bear += 20

    # MOMENTUM

        # MOMENTUM

    if hist_now > 0:
        bull += 15

    else:
        bear += 15

    total = bull + bear

    confidence = int((bull / total) * 100)

    if confidence >= 65:
        trade = "🟢 LONG"

    elif confidence <= 35:
        trade = "🔴 SHORT"

    else:
        trade = "🟡 BEKLE"

    if confidence >= 80:
        stars = "⭐⭐⭐⭐⭐"

    elif confidence >= 65:
        stars = "⭐⭐⭐⭐"

    elif confidence >= 50:
        stars = "⭐⭐⭐"

    elif confidence >= 35:
        stars = "⭐⭐"

    else:
        stars = "⭐"
   
    # RSI COMMENT

    if rsi_now >= 75:

        rsi_text = "Aşırı Alım"

    elif rsi_now >= 60:

        rsi_text = "Güçlü"

    elif rsi_now <= 25:

        rsi_text = "Aşırı Satım"

    elif rsi_now <= 40:

        rsi_text = "Zayıf"

    else:

        rsi_text = "Nötr"

    # MACD COMMENT

    if hist_now > 0 and macd_now > signal_now:

        macd_text = "Yükseliş momentumu"

    elif hist_now < 0 and macd_now < signal_now:

        macd_text = "Düşüş momentumu"

    elif hist_now > 0:

        macd_text = "Momentum güçleniyor"

    else:

        macd_text = "Momentum zayıflıyor"

    # SUPPORT TEST

    if spot_price <= sr["S1"]:

        sr_comment = "Destek bölgesinde"

    elif spot_price >= sr["R1"]:

        sr_comment = "Direnç bölgesinde"

    else:

        sr_comment = "İki seviye arasında"

    return {
        "price": spot_price,

        "change": daily_change,

        "change_pct": daily_pct,

        "ema50": ema50_now,

        "ema200": ema200_now,

        "rsi": rsi_now,

        "rsi_text": rsi_text,

        "macd": macd_now,

        "signal": signal_now,

        "hist": hist_now,

        "macd_text": macd_text,

        "atr": atr_now,

        "support1": sr["S1"],

        "support2": sr["S2"],

        "resistance1": sr["R1"],

        "resistance2": sr["R2"],

        "support_comment": sr_comment,

        "bull": bull,

        "bear": bear,

        "confidence": confidence,

        "stars": stars,

        "trade": trade

    }
    
# ==========================================================
# NEWS SUMMARY
# ==========================================================

def summarize_news(news):

    if len(news) == 0:

        return "Bugün altını etkileyebilecek önemli bir haber bulunamadı."

    text = " ".join(news).lower()

    reasons = []

    if "fed" in text or "federal reserve" in text:
        reasons.append("Fed politikaları")

    if "inflation" in text or "cpi" in text:
        reasons.append("Enflasyon verileri")

    if "interest" in text or "rate" in text:
        reasons.append("Faiz beklentileri")

    if "dollar" in text:
        reasons.append("Dolar hareketi")

    if "treasury" in text:
        reasons.append("Tahvil faizleri")

    if "gold" in text:
        reasons.append("Altın piyasası")

    if len(reasons) == 0:

        return news[0]

    return "Bugün piyasayı etkileyen ana başlıklar: " + ", ".join(reasons)


# ==========================================================
# AI COMMENT
# ==========================================================

def ai_comment(a):

    lines = []

    if a["trade"] == "🟢 LONG":

        lines.append(
            "EMA50 EMA200 üzerinde olduğu için ana trend yükseliş yönünde."
        )

    elif a["trade"] == "🔴 SHORT":

        lines.append(
            "EMA50 EMA200 altında olduğu için ana trend düşüş yönünde."
        )

    else:

        lines.append(
            "Piyasada net yön oluşmadığı için beklemek daha güvenli görünüyor."
        )

    if a["rsi"] > 70:

        lines.append(
            "RSI aşırı alım bölgesinde."
        )

    elif a["rsi"] < 30:

        lines.append(
            "RSI aşırı satım bölgesinde."
        )

    if a["macd"] > a["signal"]:

        lines.append(
            "MACD yükselişi destekliyor."
        )

    else:

        lines.append(
            "MACD satış baskısını gösteriyor."
        )

    if a["support_comment"] == "Destek bölgesinde":

        lines.append(
            "Fiyat güçlü destek seviyesine yakın."
        )

    elif a["support_comment"] == "Direnç bölgesinde":

        lines.append(
            "Fiyat güçlü direnç seviyesine yakın."
        )

    return "\n".join(lines)


# ==========================================================
# ECONOMIC CALENDAR TEXT
# ==========================================================

def calendar_text(events):

    if len(events) == 0:

        return "Bugün yüksek etkili veri bulunmuyor."

    txt = ""

    for e in events:

        txt += (
            f"🔴 {e['time']} "
            f"{e['country']} "
            f"{e['title']}\n"
        )

    return txt


# ==========================================================
# TELEGRAM MESSAGE
# ==========================================================

def create_message(a, news, events):

    summary = summarize_news(news)

    comment = ai_comment(a)

    calendar = calendar_text(events)

    headlines = ""

    for n in news:

        headlines += f"• {n}\n"

    emoji = "📈"

    if a["change"] < 0:

        emoji = "📉"

    msg = f"""
🏆 *GOLD AI v3.0*

━━━━━━━━━━━━━━━━━━

💰 *Spot XAU/USD*

{a["price"]:.2f}

{emoji} Günlük Değişim

{a["change"]:+.2f}

({a["change_pct"]:+.2f}%)

━━━━━━━━━━━━━━━━━━

📊 *Teknik Analiz*

EMA50 : {a["ema50"]:.2f}

EMA200 : {a["ema200"]:.2f}

RSI : {a["rsi"]:.1f}

➡️ {a["rsi_text"]}

MACD

➡️ {a["macd_text"]}

ATR

{a["atr"]:.2f}

━━━━━━━━━━━━━━━━━━

📌 *Destekler*

S1 : {a["support1"]:.2f}

S2 : {a["support2"]:.2f}

📌 *Dirençler*

R1 : {a["resistance1"]:.2f}

R2 : {a["resistance2"]:.2f}

━━━━━━━━━━━━━━━━━━

⭐ *Trend Güveni*

{a["confidence"]}/100

{a["stars"]}

🎯 *Bugünkü İşlem*

{a["trade"]}

━━━━━━━━━━━━━━━━━━

📅 *Bugünkü Kritik Veriler*

{calendar}

━━━━━━━━━━━━━━━━━━

📰 *Piyasa Özeti*

{summary}

━━━━━━━━━━━━━━━━━━

📰 *Son Haberler*

{headlines}

━━━━━━━━━━━━━━━━━━

🧠 *GOLD AI Yorumu*

{comment}

━━━━━━━━━━━━━━━━━━

⚠️ Bu analiz tamamen otomatik üretilmiştir.
Yatırım tavsiyesi değildir.
"""

    return msg
    # ==========================================================
# MAIN
# ==========================================================

def main():

    log("GOLD AI v3.0 Baslatiliyor...")

    try:

        # Spot fiyat
        spot_price, prev_close = get_spot_price()

        log(f"Spot : {spot_price}")

        # Tarihsel veri
        df = download_history()

        log("Veriler indirildi.")

        # Teknik analiz
        analysis = analyze_market(
            df,
            spot_price,
            prev_close
        )

        log("Teknik analiz tamam.")

        # Haberler
        news = get_news()

        log(f"{len(news)} haber bulundu.")

        # Ekonomik Takvim
        events = get_calendar()

        log(f"{len(events)} ekonomik olay bulundu.")

        # Telegram mesajı
        message = create_message(
            analysis,
            news,
            events
        )

        # Telegram
        send_message(message)

        log("Telegram mesaji gonderildi.")

        print(message)

    except Exception as e:

        error = (
            "⚠️ GOLD AI v3.0 Hatası\n\n"
            f"{str(e)}\n\n"
            f"{traceback.format_exc()}"
        )

        print(error)

        try:

            send_message(error)

        except Exception:

            pass

        sys.exit(1)


# ==========================================================
# ENTRY
# ==========================================================

if __name__ == "__main__":

    main()
