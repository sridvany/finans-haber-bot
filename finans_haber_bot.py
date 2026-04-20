"""
FinansHaber Bot
---------------
RSS kaynaklarından finans haberlerini takip eder,
yeni haber geldiğinde Telegram'a bildirim gönderir.

Kurulum:
    pip install feedparser requests playsound

Çalıştırma:
    python finans_haber_bot.py
"""

import feedparser
import requests
import time
import json
import os
import hashlib
import threading
from datetime import datetime

# ─── AYARLAR ──────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN  = "8378715686:AAHBfdKjRmg1UqVwg6QbrMa8bNdP3VKsMVs"
TELEGRAM_CHAT_ID = "8296673364"

KONTROL_ARALIGI = 60   # saniye — kaç saniyede bir RSS kontrol edilsin

SEEN_FILE = "goruldu.json"  # daha önce gönderilen haberler buraya kaydedilir

# ─── RSS KAYNAKLARI ───────────────────────────────────────────────────────────

RSS_KAYNAKLARI = [
    # Türkçe
    {"url": "https://www.ntv.com.tr/ekonomi.rss",                        "kaynak": "NTV Ekonomi"},
    {"url": "https://www.haberturk.com/rss/ekonomi.xml",                 "kaynak": "HaberTürk Ekonomi"},
    {"url": "https://www.investing.com/rss/news.rss",                    "kaynak": "Investing.com"},
    {"url": "https://tr.investing.com/rss/news.rss",                     "kaynak": "Investing.com TR"},
    {"url": "https://www.hurriyet.com.tr/rss/ekonomi",                   "kaynak": "Hürriyet Ekonomi"},
    {"url": "https://www.sabah.com.tr/rss/ekonomi.xml",                  "kaynak": "Sabah Ekonomi"},
    # İngilizce
    {"url": "https://feeds.reuters.com/reuters/businessNews",            "kaynak": "Reuters Business"},
    {"url": "https://feeds.bbci.co.uk/news/business/rss.xml",           "kaynak": "BBC Business"},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories",      "kaynak": "MarketWatch"},
    {"url": "https://www.ft.com/rss/home/uk",                           "kaynak": "Financial Times"},
    {"url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",     "kaynak": "CNBC Markets"},
    {"url": "https://www.bloomberg.com/feeds/podcasts/etf_report.xml",  "kaynak": "Bloomberg"},
]

# ─── ANAHTAR KELİMELER ────────────────────────────────────────────────────────

TURKCE_KELIMELER = [
    "faiz", "enflasyon", "tcmb", "merkez bankası", "bütçe", "borç",
    "büyüme", "resesyon", "durgunluk", "stagflasyon",
    "dolar", "euro", "yen", "kur", "döviz",
    "altın", "petrol", "doğalgaz", "brent", "emtia",
    "borsa", "bist", "hisse", "endeks", "piyasa", "yatırım",
    "bitcoin", "kripto", "ethereum", "kripto para",
    "savaş", "çatışma", "yaptırım", "kriz", "gerilim", "seçim",
    "iflas", "halka arz", "birleşme", "kar", "zarar", "bilanço",
    "ihracat", "ithalat", "cari açık", "kobi",
    "işsizlik", "istihdam", "ücret",
    "vergi", "bütçe açığı", "hazine",
]

INGILIZCE_KELIMELER = [
    "fed", "ecb", "interest rate", "inflation", "gdp", "recession",
    "rate hike", "rate cut", "powell", "lagarde", "central bank",
    "s&p", "nasdaq", "dow jones", "stocks", "earnings", "ipo",
    "market crash", "bull market", "bear market", "rally", "selloff",
    "gold", "oil", "crude", "brent", "opec", "commodities",
    "dollar", "euro", "yen", "currency", "forex",
    "bitcoin", "ethereum", "crypto", "blockchain", "sec", "etf",
    "war", "sanctions", "tariff", "trade war", "trump", "china",
    "middle east", "brics", "geopolitical",
    "bankruptcy", "merger", "acquisition", "layoffs",
    "earnings beat", "earnings miss", "revenue", "profit", "loss",
    "unemployment", "jobs", "nonfarm", "payroll",
    "debt", "deficit", "treasury", "yield", "bond", "small and medium enterprises", 
]

TUM_KELIMELER = TURKCE_KELIMELER + INGILIZCE_KELIMELER

# ─── YARDIMCI FONKSİYONLAR ───────────────────────────────────────────────────

def gorulenleri_yukle():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def gorulenleri_kaydet(gorulenler):
    # sadece son 2000 kaydı tut, dosya şişmesin
    liste = list(gorulenler)[-2000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False)


def haber_id(entry):
    kaynak = entry.get("link", "") + entry.get("title", "")
    return hashlib.md5(kaynak.encode()).hexdigest()


def finans_haberi_mi(baslik):
    baslik_lower = baslik.lower()
    return any(kw in baslik_lower for kw in TUM_KELIMELER)


def telegram_gonder(baslik, link, kaynak, zaman):
    emoji = "🔴"  # varsayılan
    baslik_lower = baslik.lower()

    if any(k in baslik_lower for k in ["dolar", "dollar", "euro", "kur", "forex", "currency"]):
        emoji = "💵"
    elif any(k in baslik_lower for k in ["altın", "gold"]):
        emoji = "🥇"
    elif any(k in baslik_lower for k in ["petrol", "oil", "brent", "opec"]):
        emoji = "🛢️"
    elif any(k in baslik_lower for k in ["faiz", "interest rate", "fed", "ecb", "tcmb", "merkez"]):
        emoji = "🏦"
    elif any(k in baslik_lower for k in ["borsa", "bist", "nasdaq", "s&p", "stocks", "endeks"]):
        emoji = "📈"
    elif any(k in baslik_lower for k in ["bitcoin", "kripto", "crypto", "ethereum"]):
        emoji = "₿"
    elif any(k in baslik_lower for k in ["savaş", "war", "kriz", "crisis", "gerilim"]):
        emoji = "⚠️"
    elif any(k in baslik_lower for k in ["enflasyon", "inflation"]):
        emoji = "📊"

    mesaj = (
        f"{emoji} *FinansHaber Flash*\n\n"
        f"📰 {baslik}\n\n"
        f"🕐 {zaman}\n"
        f"📡 {kaynak}\n\n"
        f"🔗 [Habere Git]({link})"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"  [HATA] Telegram gönderilemedi: {e}")
        return False


def ses_cal():
    """Sistem bip sesi çalar (ek kütüphane gerektirmez)."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except ImportError:
        # macOS / Linux fallback
        try:
            os.system("printf '\\a'")
        except Exception:
            pass


def rss_kontrol(kaynak_bilgi, gorulenler, yeni_haberler):
    url     = kaynak_bilgi["url"]
    kaynak  = kaynak_bilgi["kaynak"]
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            eid    = haber_id(entry)
            baslik = entry.get("title", "").strip()
            link   = entry.get("link", "")

            if not baslik or eid in gorulenler:
                continue

            if finans_haberi_mi(baslik):
                zaman = datetime.now().strftime("%d.%m.%Y %H:%M")
                yeni_haberler.append({
                    "id": eid,
                    "baslik": baslik,
                    "link": link,
                    "kaynak": kaynak,
                    "zaman": zaman,
                })
    except Exception as e:
        print(f"  [UYARI] {kaynak} okunamadı: {e}")


# ─── ANA DÖNGÜ ────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  💹 FinansHaber Bot Başlatılıyor...")
    print("=" * 55)
    print(f"  📡 {len(RSS_KAYNAKLARI)} kaynak izleniyor")
    print(f"  🔑 {len(TUM_KELIMELER)} anahtar kelime aktif")
    print(f"  ⏱️  Her {KONTROL_ARALIGI} saniyede kontrol")
    print(f"  📱 Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print("=" * 55)

    # Başlangıç bildirimi gönder
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": (
                "✅ *FinansHaber Bot Aktif!*\n\n"
                f"📡 {len(RSS_KAYNAKLARI)} kaynak izleniyor\n"
                f"🔑 {len(TUM_KELIMELER)} anahtar kelime\n"
                f"⏱️ Her {KONTROL_ARALIGI} saniyede kontrol\n\n"
                "_Yeni finans haberi geldiğinde buraya iletilecek._"
            ),
            "parse_mode": "Markdown",
        },
        timeout=10,
    )
    print("  ✅ Telegram bağlantısı tamam, bot çalışıyor!\n")

    gorulenler = gorulenleri_yukle()
    # ilk çalışmada mevcut haberleri "görüldü" say — sadece yenilerini gönder
    ilk_calisma = len(gorulenler) == 0

    if ilk_calisma:
        print("  ⏳ İlk tarama — mevcut haberler atlanıyor, sadece yeniler gelecek...\n")
        for kaynak_bilgi in RSS_KAYNAKLARI:
            try:
                feed = feedparser.parse(kaynak_bilgi["url"])
                for entry in feed.entries:
                    gorulenler.add(haber_id(entry))
            except Exception:
                pass
        gorulenleri_kaydet(gorulenler)
        print(f"  ✅ Başlangıç taraması tamamlandı. Artık izleniyor...\n")

    dongu_sayisi = 0
    while True:
        dongu_sayisi += 1
        simdi = datetime.now().strftime("%H:%M:%S")
        print(f"[{simdi}] Tarama #{dongu_sayisi} başlıyor...", end=" ", flush=True)

        yeni_haberler = []
        threads = []

        for kaynak_bilgi in RSS_KAYNAKLARI:
            t = threading.Thread(
                target=rss_kontrol,
                args=(kaynak_bilgi, gorulenler, yeni_haberler),
                daemon=True,
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=15)

        if yeni_haberler:
            print(f"{len(yeni_haberler)} yeni haber!")
            for haber in yeni_haberler:
                gonderildi = telegram_gonder(
                    haber["baslik"], haber["link"],
                    haber["kaynak"], haber["zaman"]
                )
                if gonderildi:
                    gorulenler.add(haber["id"])
                    ses_cal()
                    print(f"  📤 [{haber['kaynak']}] {haber['baslik'][:70]}...")
                    time.sleep(1)  # Telegram rate limit
            gorulenleri_kaydet(gorulenler)
        else:
            print("yeni haber yok.")

        time.sleep(KONTROL_ARALIGI)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Bot durduruldu. Güle güle! 👋")
