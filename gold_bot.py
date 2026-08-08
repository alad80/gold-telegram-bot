"""
GOLD AI v3.1
XAU/USD Telegram Analysis Bot
- GoldAPI spot price
- Yahoo Finance historical data
- EMA50 / EMA200
- RSI / MACD / ATR
- Support / Resistance
- Trend confidence
- LONG >= 65
- SHORT <= 35
- BEKLE between 36-64
- High-impact economic calendar
- News
- Turkish news/calendar translation
- Telegram
"""

import os
import sys
import traceback
from datetime import datetime

import requests
import pandas as pd
import yfinance as yf
import xml.etree.ElementTree as ET

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None


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

LONG_LIMIT = 65
SHORT_LIMIT = 35

REQUEST_TIMEOUT = 20

# Render Cron her çalıştığında:
# True  -> sadece "Trend: Yükseliş/Düşüş/Bekle" gönderir
# False -> tam günlük analiz gönderir
SIMPLE_TREND_ONLY = True


# ==========================================================
# LOG
# ==========================================================

def log(text):
    print(
        f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {text}",
        flush=True
    )


# ==========================================================
# TELEGRAM
# ==========================================================

def send_message(message):
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN Render Environment'ta yok.")

    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID Render Environment'ta yok.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(
        url,
        data=payload,
        timeout=REQUEST_TIMEOUT
    )

    # Telegram'ın gerçek hata mesajını göster
    if not response.ok:
        raise RuntimeError(
            f"Telegram HTTP {response.status_code}: {response.text}"
        )

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(f"Telegram API hatası: {result}")

    return result


# ==========================================================
# GOLDAPI
# ==========================================================

def get_spot_price():
    if not GOLD_API_KEY:
        raise RuntimeError("GOLD_API_KEY Render Environment'ta yok.")

    url = "https://www.goldapi.io/api/XAU/USD"

    headers = {
        "x-access-token": GOLD_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    if "price" not in data:
        raise RuntimeError(f"GoldAPI beklenmeyen cevap: {data}")

    price = float(data["price"])
    prev_close = float(data.get("prev_close_price", price))

    return price, prev_close


# ==========================================================
# YAHOO FINANCE
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
        raise RuntimeError("Yahoo Finance tarihsel verisi alınamadı.")

    # yfinance bazı sürümlerde MultiIndex döndürebilir.
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df.columns = df.columns.get_level_values(0)
        except Exception:
            df = df.xs(SYMBOL, axis=1, level=-1)

    required = ["High", "Low", "Close"]

    for column in required:
        if column not in df.columns:
            raise RuntimeError(
                f"Yahoo Finance verisinde {column} sütunu bulunamadı."
            )

    return df


# ==========================================================
# SERIES HELPER
# ==========================================================

def clean_series(value):
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]

    return pd.to_numeric(value, errors="coerce")


# ==========================================================
# EMA
# ==========================================================

def ema(series, period):
    series = clean_series(series)

    return series.ewm(
        span=period,
        adjust=False
    ).mean()


# ==========================================================
# RSI
# ==========================================================

def rsi(series, period=RSI_PERIOD):
    series = clean_series(series)

    delta = series.diff()

    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    avg_loss = avg_loss.replace(0, 1e-10)

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


# ==========================================================
# MACD
# ==========================================================

def macd(series):
    series = clean_series(series)

    ema12 = ema(series, 12)
    ema26 = ema(series, 26)

    macd_line = ema12 - ema26

    signal_line = macd_line.ewm(
        span=9,
        adjust=False
    ).mean()

    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


# ==========================================================
# ATR
# ==========================================================

def atr(df, period=ATR_PERIOD):
    high = clean_series(df["High"])
    low = clean_series(df["Low"])
    close = clean_series(df["Close"])

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return true_range.rolling(period).mean()


# ==========================================================
# SUPPORT / RESISTANCE
# ==========================================================

def support_resistance(df):
    high = clean_series(df["High"]).dropna().tail(LOOKBACK_SR)
    low = clean_series(df["Low"]).dropna().tail(LOOKBACK_SR)

    atr_series = atr(df).dropna()

    if atr_series.empty:
        raise RuntimeError("ATR hesaplanamadı.")

    atr_value = float(atr_series.iloc[-1])

    resistance1 = float(high.max())
    resistance2 = resistance1 + atr_value

    support1 = float(low.min())
    support2 = support1 - atr_value

    return {
        "S1": support1,
        "S2": support2,
        "R1": resistance1,
        "R2": resistance2,
        "ATR": atr_value
    }


# ==========================================================
# TREND ANALYSIS
# ==========================================================

def analyze_market(df, spot_price, prev_close):
    close = clean_series(df["Close"])

    ema50 = ema(close, EMA_FAST)
    ema200 = ema(close, EMA_SLOW)

    rsi14 = rsi(close)

    macd_line, signal_line, hist = macd(close)

    sr = support_resistance(df)

    ema50_now = float(ema50.dropna().iloc[-1])
    ema200_now = float(ema200.dropna().iloc[-1])

    rsi_now = float(rsi14.dropna().iloc[-1])

    macd_now = float(macd_line.dropna().iloc[-1])
    signal_now = float(signal_line.dropna().iloc[-1])
    hist_now = float(hist.dropna().iloc[-1])

    atr_now = float(sr["ATR"])

    daily_change = spot_price - prev_close

    daily_pct = (
        (daily_change / prev_close) * 100
        if prev_close
        else 0
    )

    # ------------------------------------------------------
    # PUANLAMA
    # ------------------------------------------------------

    bull = 0
    bear = 0

    # EMA TREND - 30 PUAN
    if ema50_now > ema200_now:
        bull += 30
    else:
        bear += 30

    # PRICE vs EMA50 - 20 PUAN
    if spot_price > ema50_now:
        bull += 20
    else:
        bear += 20

    # RSI - 15 PUAN
    if rsi_now > 60:
        bull += 15
    elif rsi_now < 40:
        bear += 15
    else:
        bull += 7
        bear += 7

    # MACD - 20 PUAN
    if macd_now > signal_now:
        bull += 20
    else:
        bear += 20

    # MOMENTUM - 15 PUAN
    if hist_now > 0:
        bull += 15
    else:
        bear += 15

    total = bull + bear

    confidence = int((bull / total) * 100) if total else 50

    # ------------------------------------------------------
    # 65+ LONG / 35- SHORT / 36-64 BEKLE
    # ------------------------------------------------------

    if confidence >= LONG_LIMIT:
        trade = "🟢 LONG"
        trend = "Yükseliş"
        trend_emoji = "🟢"

    elif confidence <= SHORT_LIMIT:
        trade = "🔴 SHORT"
        trend = "Düşüş"
        trend_emoji = "🔴"

    else:
        trade = "🟡 BEKLE"
        trend = "Nötr"
        trend_emoji = "🟡"

    # ------------------------------------------------------
    # STARS
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # RSI COMMENT
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # MACD COMMENT
    # ------------------------------------------------------

    if hist_now > 0 and macd_now > signal_now:
        macd_text = "Yükseliş momentumu"
    elif hist_now < 0 and macd_now < signal_now:
        macd_text = "Düşüş momentumu"
    elif hist_now > 0:
        macd_text = "Momentum güçleniyor"
    else:
        macd_text = "Momentum zayıflıyor"

    # ------------------------------------------------------
    # SUPPORT / RESISTANCE COMMENT
    # ------------------------------------------------------

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
        "trade": trade,
        "trend": trend,
        "trend_emoji": trend_emoji
    }


# ==========================================================
# TRANSLATION
# ==========================================================

_translation_cache = {}


def translate_tr(text):
    if not text:
        return ""

    if GoogleTranslator is None:
        # Paket kurulmamışsa bot yine çalışsın.
        return text

    if text in _translation_cache:
        return _translation_cache[text]

    try:
        translated = GoogleTranslator(
            source="auto",
            target="tr"
        ).translate(text)

        translated = translated or text

        _translation_cache[text] = translated

        return translated

    except Exception as exc:
        log(f"Çeviri başarısız: {exc}")
        return text


# ==========================================================
# ECONOMIC CALENDAR
# ==========================================================

def get_calendar():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

    events = []

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        response.raise_for_status()

        root = ET.fromstring(response.content)

        for event in root.findall("event"):
            impact = (
                event.findtext("impact") or ""
            ).lower()

            if "high" not in impact:
                continue

            title = event.findtext("title") or ""
            country = event.findtext("country") or ""
            date = event.findtext("date") or ""
            time = event.findtext("time") or ""

            events.append({
                "title": title,
                "country": country,
                "date": date,
                "time": time
            })

        return events[:8]

    except Exception as exc:
        log(f"Ekonomik takvim alınamadı: {exc}")
        return []


def calendar_text(events):
    if not events:
        return "Bugün yüksek etkili veri bulunamadı."

    lines = []

    for event in events:
        title_tr = translate_tr(event["title"])

        lines.append(
            f"🔴 {event['time']} "
            f"{event['country']} "
            f"{title_tr}"
        )

    return "\n".join(lines)


# ==========================================================
# NEWS
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
        "federal reserve",
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
            response = requests.get(
                feed,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            response.raise_for_status()

            root = ET.fromstring(response.content)

            for item in root.iter("item"):
                title = (
                    item.findtext("title") or ""
                ).strip()

                if not title:
                    continue

                title_lower = title.lower()

                if any(
                    keyword in title_lower
                    for keyword in keywords
                ):
                    news.append(title)

                if len(news) >= 5:
                    break

        except Exception as exc:
            log(f"Haber kaynağı okunamadı: {exc}")

    # Tekrarları kaldır
    unique_news = []

    for title in news:
        if title not in unique_news:
            unique_news.append(title)

    return unique_news[:5]


def summarize_news(news):
    if not news:
        return (
            "Bugün altını etkileyebilecek "
            "önemli bir haber bulunamadı."
        )

    text = " ".join(news).lower()

    reasons = []

    if "fed" in text or "federal reserve" in text:
        reasons.append("Fed politikaları")

    if "inflation" in text or "cpi" in text:
        reasons.append("enflasyon verileri")

    if "interest" in text or "rate" in text:
        reasons.append("faiz beklentileri")

    if "dollar" in text:
        reasons.append("dolar hareketi")

    if "treasury" in text:
        reasons.append("ABD tahvil faizleri")

    if "gold" in text:
        reasons.append("altın piyasası")

    if reasons:
        return (
            "Bugün piyasayı etkileyen ana başlıklar: "
            + ", ".join(reasons)
            + "."
        )

    return translate_tr(news[0])


# ==========================================================
# AI COMMENT
# ==========================================================

def ai_comment(a):
    lines = []

    if a["trade"] == "🟢 LONG":
        lines.append(
            "Teknik göstergeler ağırlıklı olarak yükseliş yönünü destekliyor."
        )

    elif a["trade"] == "🔴 SHORT":
        lines.append(
            "Teknik göstergeler ağırlıklı olarak düşüş yönünü destekliyor."
        )

    else:
        lines.append(
            "Göstergeler arasında net bir yön üstünlüğü bulunmuyor."
        )

    if a["rsi"] > 70:
        lines.append("RSI aşırı alım bölgesinde.")
    elif a["rsi"] < 30:
        lines.append("RSI aşırı satım bölgesinde.")

    if a["macd"] > a["signal"]:
        lines.append("MACD yükseliş momentumunu destekliyor.")
    else:
        lines.append("MACD düşüş momentumunu destekliyor.")

    if a["support_comment"] == "Destek bölgesinde":
        lines.append("Fiyat önemli destek bölgesine yakın.")
    elif a["support_comment"] == "Direnç bölgesinde":
        lines.append("Fiyat önemli direnç bölgesine yakın.")

    return "\n".join(lines)


# ==========================================================
# FULL TELEGRAM MESSAGE
# ==========================================================

def create_full_message(analysis, news, events):
    summary = summarize_news(news)
    comment = ai_comment(analysis)
    calendar = calendar_text(events)

    headlines = []

    for title in news:
        headlines.append(
            f"• {translate_tr(title)}"
        )

    headlines_text = (
        "\n".join(headlines)
        if headlines
        else "Haber bulunamadı."
    )

    change_emoji = (
        "🔺"
        if analysis["change"] > 0
        else "🔻"
    )

    return f"""🏆 GOLD AI v3.1

━━━━━━━━━━━━━━━━━━

💰 Spot XAU/USD

${analysis["price"]:.2f}

{change_emoji} Günlük Değişim:
{analysis["change"]:+.2f}
({analysis["change_pct"]:+.2f}%)

━━━━━━━━━━━━━━━━━━

📊 Teknik Analiz

EMA50  : {analysis["ema50"]:.2f}
EMA200 : {analysis["ema200"]:.2f}

RSI(14): {analysis["rsi"]:.1f}
➡️ {analysis["rsi_text"]}

MACD:
➡️ {analysis["macd_text"]}

ATR:
{analysis["atr"]:.2f}

━━━━━━━━━━━━━━━━━━

🟢 Destekler

S1 : {analysis["support1"]:.2f}
S2 : {analysis["support2"]:.2f}

🔴 Dirençler

R1 : {analysis["resistance1"]:.2f}
R2 : {analysis["resistance2"]:.2f}

━━━━━━━━━━━━━━━━━━

⭐ Trend Güven Puanı

{analysis["confidence"]}/100
{analysis["stars"]}

🎯 Günün Olası İşlem Yönü

{analysis["trade"]}

━━━━━━━━━━━━━━━━━━

📅 Bugünkü Kritik Veriler

{calendar}

━━━━━━━━━━━━━━━━━━

📰 Piyasa Özeti

{summary}

━━━━━━━━━━━━━━━━━━

📰 Son Haberler

{headlines_text}

━━━━━━━━━━━━━━━━━━

🧠 GOLD AI Yorumu

{comment}

━━━━━━━━━━━━━━━━━━

⚠️ Bu otomatik teknik analizdir.
Yatırım tavsiyesi değildir.
"""


# ==========================================================
# SIMPLE TREND MESSAGE
# ==========================================================

def create_simple_trend_message(analysis):
    return f"Trend: {analysis['trend']}"


# ==========================================================
# MAIN
# ==========================================================

def main():
    log("GOLD AI v3.1 başlatılıyor...")

    try:
        # 1 - Spot fiyat
        spot_price, prev_close = get_spot_price()

        log(f"Spot fiyat: {spot_price}")

        # 2 - Tarihsel veri
        df = download_history()

        log("Tarihsel veriler alındı.")

        # 3 - Teknik analiz
        analysis = analyze_market(
            df,
            spot_price,
            prev_close
        )

        log(
            f"Trend: {analysis['trend']} | "
            f"Güven: {analysis['confidence']}/100"
        )

        # --------------------------------------------------
        # CRON HER ÇALIŞTIĞINDA SADECE TREND GÖNDER
        # --------------------------------------------------

        if SIMPLE_TREND_ONLY:
            message = create_simple_trend_message(
                analysis
            )

        # --------------------------------------------------
        # TAM ANALİZ
        # --------------------------------------------------

        else:
            news = get_news()

            log(f"{len(news)} haber bulundu.")

            events = get_calendar()

            log(f"{len(events)} yüksek etkili veri bulundu.")

            message = create_full_message(
                analysis,
                news,
                events
            )

        # 4 - Telegram
        result = send_message(message)

        log("Telegram mesajı başarıyla gönderildi.")
        log(str(result))

        print(message)

    except Exception as exc:
        error_message = (
            "⚠️ GOLD AI HATASI\n\n"
            f"{exc}"
        )

        print(error_message, file=sys.stderr)

        try:
            send_message(error_message)
        except Exception as telegram_error:
            print(
                f"Telegram hata mesajı gönderilemedi: "
                f"{telegram_error}",
                file=sys.stderr
            )

        sys.exit(1)


# ==========================================================
# START
# ==========================================================

if __name__ == "__main__":
    main()
