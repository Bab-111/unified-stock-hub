"""
module_monitor.py — Deep per-ticker analysis for watchlist stocks.
Ported from stock-monitor/scripts/monitor.py with structural refactor.
Returns structured dict for build_report.py to consume.
"""
import yfinance as yf
import requests
import warnings
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")

TAIWAN_TZ = ZoneInfo("Asia/Taipei")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ── Helpers ────────────────────────────────────────────────────────────────

def safe(v, d=2):
    try:
        f = float(v)
        if f != f:
            return None
        return round(f, d)
    except Exception:
        return None


def fmt_large(n):
    try:
        n = float(n)
        if n >= 1e12: return f"{round(n/1e12, 2)}T"
        if n >= 1e9:  return f"{round(n/1e9, 2)}B"
        if n >= 1e6:  return f"{round(n/1e6, 2)}M"
        return str(round(n, 0))
    except Exception:
        return "—"


# ── Technical indicators ───────────────────────────────────────────────────

def get_rsi(hist, period=14):
    try:
        if len(hist) < period + 1:
            return None
        delta = hist["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        if hasattr(val, "item"):
            val = val.item()
        return safe(val, 0)
    except Exception:
        return None


def get_macd(hist):
    try:
        close = hist["Close"]
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        hist_macd = macd - signal
        hist_val = float(hist_macd.iloc[-1])
        prev_val = float(hist_macd.iloc[-2])
        if hist_val > 0 and hist_val > prev_val:
            trend = "Bullish"
        elif hist_val < 0 and hist_val < prev_val:
            trend = "Bearish"
        else:
            trend = "Neutral"
        return {
            "macd": safe(float(macd.iloc[-1]), 3),
            "signal": safe(float(signal.iloc[-1]), 3),
            "histogram": safe(hist_val, 3),
            "trend": trend,
        }
    except Exception:
        return None


def get_moving_averages(hist, price):
    result = {}
    try:
        close = hist["Close"]
        for period in [20, 50, 200]:
            if len(close) >= period:
                sma = float(close.rolling(period).mean().iloc[-1])
                result[f"sma{period}"] = safe(sma)
                result[f"vs_sma{period}"] = safe((price - sma) / sma * 100, 1)
    except Exception:
        pass
    return result


def get_volume_data(hist, cfg):
    try:
        threshold = cfg.get("volume_threshold_multiplier", 2.0)
        vol = float(hist["Volume"].iloc[-1])
        avg_vol = float(hist["Volume"].rolling(20).mean().iloc[-1])
        ratio = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0
        spike = ratio >= threshold
        return {"volume": int(vol), "avg_volume": int(avg_vol), "ratio": ratio, "spike": spike}
    except Exception:
        return {}


# ── Fundamental data ───────────────────────────────────────────────────────

def get_fundamentals(info):
    try:
        return {
            "pe":             safe(info.get("trailingPE")),
            "fpe":            safe(info.get("forwardPE")),
            "peg":            safe(info.get("pegRatio")),
            "pb":             safe(info.get("priceToBook")),
            "ps":             safe(info.get("priceToSalesTrailing12Months")),
            "ev_ebitda":      safe(info.get("enterpriseToEbitda")),
            "roe":            safe((info.get("returnOnEquity") or 0) * 100, 1),
            "roa":            safe((info.get("returnOnAssets") or 0) * 100, 1),
            "profit_margin":  safe((info.get("profitMargins") or 0) * 100, 1),
            "revenue_growth": safe((info.get("revenueGrowth") or 0) * 100, 1),
            "earnings_growth":safe((info.get("earningsGrowth") or 0) * 100, 1),
            "debt_equity":    safe(info.get("debtToEquity")),
            "current_ratio":  safe(info.get("currentRatio")),
            "fcf":            fmt_large(info.get("freeCashflow")) if info.get("freeCashflow") else "—",
            "eps":            safe(info.get("trailingEps")),
            "beta":           safe(info.get("beta")),
            "short_ratio":    safe(info.get("shortRatio")),
            "inst_own":       safe((info.get("heldPercentInstitutions") or 0) * 100, 1),
            "insider_own":    safe((info.get("heldPercentInsiders") or 0) * 100, 1),
            "short_float":    safe((info.get("shortPercentOfFloat") or 0) * 100, 1),
            "market_cap":     fmt_large(info.get("marketCap")),
        }
    except Exception:
        return {}


def get_earnings(info, now_tw):
    try:
        ed = info.get("earningsDate")
        if ed and isinstance(ed, (list, tuple)) and len(ed) > 0:
            date = datetime.fromtimestamp(ed[0], tz=TAIWAN_TZ)
            days = (date.date() - now_tw.date()).days
            return {"date": date.strftime("%Y-%m-%d"), "days": days}
    except Exception:
        pass
    return None


def get_options(ticker_obj, price):
    try:
        exps = ticker_obj.options
        if not exps:
            return None
        chain = ticker_obj.option_chain(exps[0])
        calls = chain.calls
        puts = chain.puts
        if len(calls) == 0:
            return None
        atm_call = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
        result = {
            "exp": str(exps[0]),
            "iv": safe(float(atm_call["impliedVolatility"].values[0]) * 100, 1),
            "delta": safe(float(atm_call["delta"].values[0]), 3) if "delta" in atm_call.columns else None,
            "theta": safe(float(atm_call["theta"].values[0]), 4) if "theta" in atm_call.columns else None,
            "gamma": safe(float(atm_call["gamma"].values[0]), 4) if "gamma" in atm_call.columns else None,
        }
        if len(puts) > 0:
            csp_puts = puts[puts["strike"] <= price].tail(3)
            if len(csp_puts) > 0:
                best = csp_puts.iloc[-1]
                result["csp"] = {
                    "strike": safe(best["strike"]),
                    "premium": safe(best["lastPrice"]),
                    "iv": safe(float(best["impliedVolatility"]) * 100, 1),
                    "exp": str(exps[0]),
                }
        return result
    except Exception:
        return None


# ── Signals ────────────────────────────────────────────────────────────────

def analyze_signals(stock_data):
    """Generate human-readable signal list from computed data."""
    signals = []
    fund = stock_data.get("fundamentals", {})
    mas = stock_data.get("moving_averages", {})
    rsi = stock_data.get("technicals", {}).get("rsi")
    macd_data = stock_data.get("technicals", {}).get("macd", {})
    vol = stock_data.get("volume", {})
    chg = stock_data.get("change_pct", 0)
    earnings = stock_data.get("earnings")
    price = stock_data.get("price", 0)

    vol_ratio = vol.get("ratio", 1)
    if vol_ratio >= 3.0:
        signals.append({"icon": "🔥", "text": f"EXTREME Volume: {vol_ratio}x average", "level": "critical"})
    elif vol_ratio >= 2.0:
        signals.append({"icon": "⚡", "text": f"Volume spike: {vol_ratio}x average", "level": "warning"})

    if rsi is not None:
        if rsi >= 75:
            signals.append({"icon": "🔴", "text": f"Overbought — RSI {int(rsi)}", "level": "warning"})
        elif rsi <= 25:
            signals.append({"icon": "🟢", "text": f"Oversold — RSI {int(rsi)}", "level": "opportunity"})
        elif rsi >= 65:
            signals.append({"icon": "🟠", "text": f"Near overbought — RSI {int(rsi)}", "level": "caution"})
        elif rsi <= 35:
            signals.append({"icon": "🟡", "text": f"Near oversold — RSI {int(rsi)}", "level": "caution"})

    if macd_data:
        trend = macd_data.get("trend", "")
        if trend == "Bullish":
            signals.append({"icon": "📈", "text": "MACD bullish crossover", "level": "positive"})
        elif trend == "Bearish":
            signals.append({"icon": "📉", "text": "MACD bearish crossover", "level": "negative"})

    if chg >= 7:
        signals.append({"icon": "🚀", "text": f"Strong rally: +{chg}%", "level": "positive"})
    elif chg <= -7:
        signals.append({"icon": "💥", "text": f"Heavy drop: {chg}%", "level": "negative"})

    if earnings:
        days = earnings["days"]
        if days == 0:
            signals.append({"icon": "🚨", "text": "EARNINGS TODAY", "level": "critical"})
        elif 0 < days <= 7:
            signals.append({"icon": "📅", "text": f"Earnings in {days} days ({earnings['date']})", "level": "warning"})

    sma200 = mas.get("sma200")
    if sma200 and price:
        if price > sma200:
            signals.append({"icon": "✅", "text": f"Above 200-day MA (${sma200})", "level": "positive"})
        else:
            signals.append({"icon": "⛔", "text": f"Below 200-day MA (${sma200})", "level": "negative"})

    return signals


# ── Main runner ────────────────────────────────────────────────────────────

def run(tickers: list, cfg: dict) -> dict:
    """
    Deep analysis for each watchlist ticker.
    Returns structured dict for build_report.py.
    """
    now_utc = datetime.now(timezone.utc)
    now_tw = now_utc.astimezone(TAIWAN_TZ)
    print(f"[Monitor] Analyzing {len(tickers)} watchlist tickers...")

    stocks = []
    for ticker in tickers:
        print(f"  {ticker}...", end=" ", flush=True)
        try:
            t = yf.Ticker(ticker)
            info = t.info
            hist = t.history(period="1y")

            if hist.empty:
                print("no data")
                continue

            price = float(hist["Close"].iloc[-1])
            prev_price = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
            change_pct = round((price - prev_price) / prev_price * 100, 2) if prev_price else 0

            h52 = safe(info.get("fiftyTwoWeekHigh"))
            l52 = safe(info.get("fiftyTwoWeekLow"))
            pct_from_high = round((price - h52) / h52 * 100, 1) if h52 else None
            pct_from_low  = round((price - l52) / l52 * 100, 1) if l52 else None

            rsi = get_rsi(hist)
            macd_data = get_macd(hist)
            mas = get_moving_averages(hist, price)
            vol_data = get_volume_data(hist, cfg)
            fund = get_fundamentals(info)
            earnings = get_earnings(info, now_tw)
            options = get_options(t, price)

            stock_data = {
                "ticker": ticker,
                "name": info.get("longName", ticker),
                "price": round(price, 2),
                "prev_price": round(prev_price, 2),
                "change_pct": change_pct,
                "h52": h52,
                "l52": l52,
                "pct_from_high": pct_from_high,
                "pct_from_low": pct_from_low,
                "sector": info.get("sector", "—"),
                "industry": info.get("industry", "—"),
                "technicals": {"rsi": rsi, "macd": macd_data},
                "moving_averages": mas,
                "volume": vol_data,
                "fundamentals": fund,
                "earnings": earnings,
                "options": options,
                "currency": info.get("currency", "USD"),
            }
            stock_data["signals"] = analyze_signals(stock_data)
            stocks.append(stock_data)
            print(f"${price} | RSI:{rsi} | {change_pct:+.1f}%")

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    return {
        "stocks": stocks,
        "generated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_at_tw": now_tw.strftime("%Y-%m-%d %H:%M TW"),
        "ticker_count": len(stocks),
    }
