"""
module_news.py — Unified news aggregator
Merges stock-news-bot (RSS feeds) + stock-monitor's multi-source scraping.
Returns structured dict for build_report.py to consume.
"""
import feedparser
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

TAIWAN_TZ = ZoneInfo("Asia/Taipei")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def get_yahoo_rss(ticker, max_items=5):
    items = []
    seen = set()
    try:
        url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        feed = feedparser.parse(url)
        for e in feed.entries[:max_items]:
            t = e.get("title", "")[:120]
            if t and t not in seen:
                seen.add(t)
                items.append({
                    "title": t,
                    "link": e.get("link", ""),
                    "source": "Yahoo Finance",
                    "published": e.get("published", "")[:16],
                    "summary": e.get("summary", "")[:200],
                })
    except Exception:
        pass
    return items, seen


def get_google_news_ticker(ticker, seen, max_items=4):
    items = []
    try:
        q = requests.utils.quote(f"{ticker} stock")
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        )
        for e in feed.entries[:max_items]:
            t = e.get("title", "")[:120]
            if t and t not in seen:
                seen.add(t)
                items.append({
                    "title": t,
                    "link": e.get("link", ""),
                    "source": "Google News",
                    "published": e.get("published", "")[:16],
                    "summary": e.get("summary", "")[:200],
                })
    except Exception:
        pass
    return items


def get_google_news_earnings(name, seen, max_items=3):
    items = []
    try:
        short = name.split()[0] if name else ""
        if not short:
            return items
        q = requests.utils.quote(f"{short} stock earnings")
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        )
        for e in feed.entries[:max_items]:
            t = e.get("title", "")[:120]
            if t and t not in seen:
                seen.add(t)
                items.append({
                    "title": t,
                    "link": e.get("link", ""),
                    "source": "Google News",
                    "published": e.get("published", "")[:16],
                    "summary": "",
                })
    except Exception:
        pass
    return items


def get_finviz_news(ticker, seen, max_items=5):
    items = []
    try:
        r = requests.get(
            f"https://finviz.com/quote.ashx?t={ticker}",
            headers=HEADERS, timeout=8
        )
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            table = soup.find("table", {"class": "news-table"})
            if table:
                for row in table.find_all("tr")[:max_items]:
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        link = cols[1].find("a")
                        if link:
                            t = link.text.strip()[:120]
                            if t and t not in seen:
                                seen.add(t)
                                items.append({
                                    "title": t,
                                    "link": link.get("href", ""),
                                    "source": "Finviz",
                                    "published": "",
                                    "summary": "",
                                })
    except Exception:
        pass
    return items


def get_general_market_news(max_items=6):
    """Reuters + Google general market headlines."""
    items = []
    seen = set()
    try:
        feed = feedparser.parse("https://feeds.reuters.com/reuters/businessNews")
        for e in feed.entries[:max_items // 2]:
            t = e.get("title", "")[:120]
            if t and t not in seen:
                seen.add(t)
                items.append({
                    "title": t,
                    "link": e.get("link", ""),
                    "source": "Reuters",
                    "published": e.get("published", "")[:16],
                })
    except Exception:
        pass
    try:
        feed = feedparser.parse(
            "https://news.google.com/rss/search?q=stock+market+today&hl=en-US&gl=US&ceid=US:en"
        )
        for e in feed.entries[:max_items // 2]:
            t = e.get("title", "")[:120]
            if t and t not in seen:
                seen.add(t)
                items.append({
                    "title": t,
                    "link": e.get("link", ""),
                    "source": "Google News",
                    "published": e.get("published", "")[:16],
                })
    except Exception:
        pass
    return items


def run(tickers: list, cfg: dict) -> dict:
    """
    Fetch news for all tickers + general market.
    Returns:
      {
        "per_ticker": { ticker: [article, ...], ... },
        "general": [article, ...],
        "generated_at_utc": "...",
        "generated_at_tw": "...",
      }
    """
    max_per_ticker = cfg.get("news_per_ticker", 5)
    max_general = cfg.get("news_general_count", 6)

    now_utc = datetime.now(timezone.utc)
    now_tw = now_utc.astimezone(TAIWAN_TZ)

    print(f"[News] Fetching for {len(tickers)} tickers...")
    per_ticker = {}
    for ticker in tickers:
        print(f"  {ticker}...", end=" ", flush=True)
        yahoo_items, seen = get_yahoo_rss(ticker, max_per_ticker)
        google_items = get_google_news_ticker(ticker, seen, 4)
        finviz_items = get_finviz_news(ticker, seen, 3)
        all_items = yahoo_items + google_items + finviz_items
        per_ticker[ticker] = all_items[:12]
        print(f"{len(all_items)} articles")

    print("[News] Fetching general market news...")
    general = get_general_market_news(max_general)
    print(f"  {len(general)} general articles")

    return {
        "per_ticker": per_ticker,
        "general": general,
        "generated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_at_tw": now_tw.strftime("%Y-%m-%d %H:%M TW"),
    }
