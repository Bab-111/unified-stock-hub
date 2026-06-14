"""
module_screener.py — Breakout screener for 120+ stock universe.
Ported from stock-screener/scripts/daily_report.py with structural refactor.
Returns structured dict for build_report.py to consume.
No matplotlib dependency here — charts are built inline in HTML.
"""
import warnings
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

SECTOR_MAP = {
    "AAPL":"Technology","MSFT":"Technology","NVDA":"Technology",
    "GOOGL":"Comm. Services","AMZN":"Consumer Disc","META":"Comm. Services",
    "TSLA":"Consumer Disc","JPM":"Financials","JNJ":"Healthcare",
    "UNH":"Healthcare","V":"Financials","MA":"Financials",
    "HD":"Consumer Disc","PG":"Consumer Stpl","XOM":"Energy",
    "CVX":"Energy","MRK":"Healthcare","ABBV":"Healthcare",
    "PFE":"Healthcare","LLY":"Healthcare","AVGO":"Technology",
    "ORCL":"Technology","CSCO":"Technology","ADBE":"Technology",
    "CRM":"Technology","AMD":"Technology","INTC":"Technology",
    "QCOM":"Technology","TXN":"Technology","AMAT":"Technology",
    "NFLX":"Comm. Services","DIS":"Comm. Services","CMCSA":"Comm. Services",
    "VZ":"Comm. Services","T":"Comm. Services","WMT":"Consumer Stpl",
    "COST":"Consumer Stpl","TGT":"Consumer Disc","MCD":"Consumer Disc",
    "SBUX":"Consumer Disc","NKE":"Consumer Disc","BA":"Industrials",
    "CAT":"Industrials","DE":"Industrials","HON":"Industrials",
    "GE":"Industrials","MMM":"Industrials","UPS":"Industrials",
    "RTX":"Industrials","LMT":"Industrials","GS":"Financials",
    "MS":"Financials","BAC":"Financials","WFC":"Financials",
    "C":"Financials","BLK":"Financials","AXP":"Financials",
    "SCHW":"Financials","USB":"Financials","PNC":"Financials",
    "CME":"Financials","SPG":"Real Estate","AMT":"Real Estate",
    "PLD":"Real Estate","CCI":"Real Estate","EQIX":"Real Estate",
    "DLR":"Real Estate","O":"Real Estate","PSA":"Real Estate",
    "AVB":"Real Estate","KO":"Consumer Stpl","PEP":"Consumer Stpl",
    "PM":"Consumer Stpl","MO":"Consumer Stpl","MDLZ":"Consumer Stpl",
    "STZ":"Consumer Stpl","GIS":"Consumer Stpl","EL":"Consumer Stpl",
    "CL":"Consumer Stpl","CLX":"Consumer Stpl","ECL":"Materials",
    "EMR":"Industrials","ETN":"Industrials","PH":"Industrials",
    "ROK":"Industrials","SWK":"Industrials","ITW":"Industrials",
    "ROP":"Industrials","CARR":"Industrials","OTIS":"Industrials",
    "TT":"Industrials","AME":"Industrials","XYL":"Industrials",
    "FAST":"Industrials","ROST":"Consumer Disc","TJX":"Consumer Disc",
    "LOW":"Consumer Disc","EBAY":"Consumer Disc","BKNG":"Consumer Disc",
    "EXPE":"Consumer Disc","MAR":"Consumer Disc","HLT":"Consumer Disc",
    "NEE":"Utilities","DUK":"Utilities","SO":"Utilities",
    "D":"Utilities","AEP":"Utilities","EXC":"Utilities",
    "SRE":"Utilities","PCG":"Utilities","ED":"Utilities",
    "WEC":"Utilities","AWK":"Utilities","TRGP":"Energy",
    "WMB":"Energy","OKE":"Energy","KMI":"Energy","BKR":"Energy",
    "SLB":"Energy","HAL":"Energy","DVN":"Energy","MRO":"Energy",
    "EOG":"Energy","HES":"Energy","COP":"Energy","OXY":"Energy",
    "PSX":"Energy","VLO":"Energy","MPC":"Energy",
    "SOFI":"Financials","PLTR":"Technology","NOW":"Technology",
    "SCO":"Energy","LULU":"Consumer Disc",
}

SECTOR_ETFS = {
    "Technology":"XLK","Healthcare":"XLV","Financials":"XLF",
    "Industrials":"XLI","Energy":"XLE","Consumer Disc":"XLY",
    "Consumer Stpl":"XLP","Materials":"XLB","Real Estate":"XLRE",
    "Utilities":"XLU","Comm. Services":"XLC",
}

WEIGHTS = {
    "volume":2, "breakout":2, "ma200":2,
    "inst_own":3, "mfi":2, "sector":3, "history":2, "iv":1,
}
MAX_SCORE = sum(WEIGHTS.values())  # 17


def safe_float(val, default=None):
    try:    return float(val)
    except: return default


def flatten_df(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def get_regular_close_bar(df):
    df = df.copy().dropna(how="all")
    if len(df) < 2:
        return df.iloc[-1]
    last = df.iloc[-1]
    prev = df.iloc[-2]
    avg_vol = float(df["Volume"].mean())
    if avg_vol > 0 and float(last["Volume"]) < avg_vol * 0.20:
        return prev
    return last


def get_market_phase(utc_hour, utc_minute):
    t = utc_hour * 60 + utc_minute
    et = t - 240
    if et < 0: et += 1440
    if   et <  570: return "Pre-Market"
    elif et <  960: return "Regular Hours"
    elif et < 1200: return "After-Hours"
    else:           return "Overnight"


def calc_mfi(df, period=14):
    try:
        df = flatten_df(df.copy())
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        mf = tp * df["Volume"]
        pos = mf.where(tp > tp.shift(1), 0).rolling(period).sum()
        neg = mf.where(tp < tp.shift(1), 0).rolling(period).sum()
        mfi = 100 - (100 / (1 + pos / neg.replace(0, np.nan)))
        val = mfi.iloc[-1]
        return round(float(val), 1) if not np.isnan(val) else None
    except Exception:
        return None


def calc_ma200(df):
    try:
        df = flatten_df(df)
        close = df["Close"].squeeze()
        if len(close) >= 200:
            return round(float(close.rolling(200).mean().iloc[-1]), 2)
    except Exception:
        pass
    return None


def last_breakout(df, threshold=1.03, lookback=252, fwd_days=10, ret_threshold=5):
    try:
        df = flatten_df(df.copy())
        close = df["Close"].squeeze()
        op = df["Open"].squeeze()
        for i in range(min(lookback, len(df) - fwd_days - 1), 0, -1):
            if float(close.iloc[i]) > float(op.iloc[i]) * threshold:
                fwd_end = min(i + fwd_days, len(close) - 1)
                ret = (float(close.iloc[fwd_end]) - float(close.iloc[i])) / float(close.iloc[i]) * 100
                if ret >= ret_threshold:
                    date = df.index[i].strftime("%Y-%m-%d")
                    return date, round(ret, 1)
    except Exception:
        pass
    return None, 0.0


def score_stock(vol_ratio, breakout, above_ma, inst_pct, mfi_val, sec_rank, iv_val, hist_ret,
                vol_thresh=2.0, inst_high=60, inst_mod=40, mfi_thresh=50, iv_high=25, iv_mod=15,
                hist_thresh=5):
    f = {}
    s = 0

    if vol_ratio >= vol_thresh:   f["volume"]="green";  s+=2
    elif vol_ratio >= 1.3:        f["volume"]="yellow"; s+=1
    else:                         f["volume"]="red"

    if breakout:                  f["breakout"]="green"; s+=2
    elif vol_ratio >= 1.5:        f["breakout"]="yellow"; s+=1
    else:                         f["breakout"]="red"

    f["ma200"] = "green" if above_ma else "red"
    s += 2 if above_ma else 0

    def classify(val, hi, mo):
        v = safe_float(val)
        if v is None: return "red"
        return "green" if v >= hi else ("yellow" if v >= mo else "red")

    ic = classify(inst_pct, inst_high, inst_mod)
    f["inst_own"] = ic
    s += (3 if ic=="green" else (1 if ic=="yellow" else 0))

    mc = classify(mfi_val, mfi_thresh + 10, mfi_thresh)
    f["mfi"] = mc
    s += (2 if mc=="green" else (1 if mc=="yellow" else 0))

    sec_score = 3 if sec_rank <= 3 else (2 if sec_rank <= 5 else (1 if sec_rank <= 7 else 0))
    f["sector"] = "green" if sec_score >= 2 else ("yellow" if sec_score == 1 else "red")
    s += sec_score

    hc = "green" if (hist_ret or 0) >= hist_thresh else "red"
    f["history"] = hc
    s += 2 if hc=="green" else 0

    ivc = classify(iv_val, iv_high, iv_mod) if iv_val is not None else "red"
    f["iv"] = ivc
    s += (1 if ivc in ("green","yellow") else 0)

    return s, f


def traffic_light(score):
    p = score / MAX_SCORE
    return "strong" if p >= 0.70 else ("moderate" if p >= 0.45 else "weak")


# ── Batch fetchers ─────────────────────────────────────────────────────────

def batch_sector():
    """Download all sector ETFs in one call, return % 1-day change."""
    etf_list = list(SECTOR_ETFS.values())
    try:
        raw = yf.download(etf_list, period="2d", auto_adjust=True, progress=False)
        close = flatten_df(raw["Close"] if "Close" in raw.columns.get_level_values(0) else raw)
        sector_perf = {}
        for sector, etf in SECTOR_ETFS.items():
            if etf in close.columns and len(close[etf].dropna()) >= 2:
                vals = close[etf].dropna()
                chg = (float(vals.iloc[-1]) - float(vals.iloc[-2])) / float(vals.iloc[-2]) * 100
                sector_perf[sector] = round(chg, 2)
        return sector_perf
    except Exception as e:
        print(f"  [Screener] sector batch error: {e}")
        return {}


def batch_price(symbols):
    """Download all symbols in one call. Returns {ticker: DataFrame}."""
    try:
        raw = yf.download(
            symbols, period="1y", auto_adjust=True,
            group_by="ticker", progress=False, threads=True
        )
        result = {}
        for sym in symbols:
            try:
                if sym in raw.columns.get_level_values(0):
                    df = raw[sym].dropna(how="all")
                else:
                    df = raw.dropna(how="all")
                if len(df) >= 20:
                    result[sym] = flatten_df(df)
            except Exception:
                pass
        return result
    except Exception as e:
        print(f"  [Screener] price batch error: {e}")
        return {}


def enrich_candidate(sym):
    """10 enrichment calls only for top-10 candidates."""
    inst_pct = iv_val = mcap = None
    try:
        t = yf.Ticker(sym)
        info = t.info
        inst_raw = info.get("heldPercentInstitutions")
        if inst_raw: inst_pct = round(float(inst_raw) * 100, 1)
        mcap_raw = info.get("marketCap")
        if mcap_raw: mcap = float(mcap_raw)
        exps = t.options
        if exps:
            chain = t.option_chain(exps[0])
            calls = chain.calls
            if len(calls) > 0:
                price = float(info.get("regularMarketPrice") or info.get("currentPrice") or 0)
                if price > 0:
                    atm = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
                    iv_val = round(float(atm["impliedVolatility"].values[0]) * 100, 1)
    except Exception:
        pass
    return inst_pct, iv_val, mcap


# ── Main runner ────────────────────────────────────────────────────────────

def run(universe_file: str, cfg: dict) -> dict:
    """
    Run breakout screener on universe.
    Returns structured dict for build_report.py.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    run_time = now_utc.strftime("%Y-%m-%d %H:%M")
    phase = get_market_phase(now_utc.hour, now_utc.minute)
    print(f"[Screener] {run_time} — {phase}")

    vol_thresh  = float(cfg.get("volume_spike_threshold", 2.0))
    brk_thresh  = float(cfg.get("breakout_threshold", 1.03))
    top_n       = int(cfg.get("top_picks", 5))
    inst_high   = float(cfg.get("inst_ownership_high", 60))
    inst_mod    = float(cfg.get("inst_ownership_moderate", 40))
    mfi_thresh  = float(cfg.get("mfi_threshold", 50))
    iv_high     = float(cfg.get("iv_high_threshold", 25))
    iv_mod      = float(cfg.get("iv_moderate_threshold", 15))
    hist_thresh = float(cfg.get("history_return_threshold", 5))
    fwd_days    = int(cfg.get("forward_return_days", 10))

    symbols = pd.read_csv(universe_file)["Symbol"].dropna().tolist()
    print(f"  Universe: {len(symbols)} tickers")

    # Batch 1: Sector ETFs
    print("  [1/3] Sector ETFs...", flush=True)
    sector_data = batch_sector()
    sorted_sectors = sorted(sector_data.items(), key=lambda x: x[1], reverse=True)
    sector_rank = {s: i+1 for i, (s, _) in enumerate(sorted_sectors)}

    # Batch 2: All prices
    print("  [2/3] Price data...", flush=True)
    price_data = batch_price(symbols)
    valid_syms = list(price_data.keys())
    print(f"  Downloaded {len(valid_syms)} symbols")

    # Score all stocks
    print(f"  [3/3] Scoring {len(valid_syms)} stocks...", flush=True)
    all_results = []
    for sym in valid_syms:
        try:
            data = price_data[sym]
            bar = get_regular_close_bar(data)
            close = float(bar["Close"])
            open_ = float(bar["Open"])
            vol   = float(bar["Volume"])
            avg_v = float(data["Volume"].squeeze().mean())
            vol_ratio = round(vol / avg_v, 2) if avg_v > 0 else 0.0
            breakout  = close > open_ * brk_thresh
            ma200     = calc_ma200(data)
            above_ma  = close > ma200 if ma200 else False
            mfi_val   = calc_mfi(data)
            sec       = SECTOR_MAP.get(sym, "Unknown")
            sec_rank  = sector_rank.get(sec, 99)
            hist_date, hist_ret = last_breakout(data, brk_thresh, fwd_days=fwd_days, ret_threshold=hist_thresh)
            chg_pct = round((close - open_) / open_ * 100, 2) if open_ else 0

            score, factors = score_stock(
                vol_ratio, breakout, above_ma,
                None, mfi_val, sec_rank, None, hist_ret,
                vol_thresh=vol_thresh, inst_high=inst_high, inst_mod=inst_mod,
                mfi_thresh=mfi_thresh, iv_high=iv_high, iv_mod=iv_mod,
                hist_thresh=hist_thresh,
            )
            all_results.append({
                "symbol": sym, "score": score, "tl": traffic_light(score),
                "factors": factors, "close": close, "open": open_,
                "change_pct": chg_pct,
                "vol_ratio": vol_ratio, "ma200": ma200,
                "mcap": None, "inst_pct": None,
                "mfi_val": mfi_val, "sector": sec,
                "iv_val": None, "hist_date": hist_date, "hist_ret": hist_ret,
            })
        except Exception:
            pass

    all_results.sort(key=lambda x: x["score"], reverse=True)
    top10 = all_results[:10]

    # Enrich top-10
    print("  Enriching top 10...", flush=True)
    for r in top10:
        sym = r["symbol"]
        inst_pct, iv_val, mcap = enrich_candidate(sym)
        r["inst_pct"] = inst_pct
        r["iv_val"]   = iv_val
        r["mcap"]     = mcap
        new_score, new_factors = score_stock(
            r["vol_ratio"], r["close"] > r["open"] * brk_thresh,
            r["close"] > (r["ma200"] or 0), inst_pct, r["mfi_val"],
            sector_rank.get(r["sector"], 99), iv_val, r["hist_ret"],
            vol_thresh=vol_thresh, inst_high=inst_high, inst_mod=inst_mod,
            mfi_thresh=mfi_thresh, iv_high=iv_high, iv_mod=iv_mod,
            hist_thresh=hist_thresh,
        )
        r["score"]   = new_score
        r["factors"] = new_factors
        r["tl"]      = traffic_light(new_score)
        print(f"    {sym}: {new_score}/{MAX_SCORE} inst={inst_pct}% iv={iv_val}%")

    top10.sort(key=lambda x: x["score"], reverse=True)
    top_results = top10[:top_n]

    # Sentiment summary
    total = max(len(all_results), 1)
    green_pct  = sum(1 for r in all_results if r["tl"]=="strong")  / total * 100
    yellow_pct = sum(1 for r in all_results if r["tl"]=="moderate") / total * 100
    red_pct    = sum(1 for r in all_results if r["tl"]=="weak")    / total * 100

    top_sector = sorted_sectors[0][0] if sorted_sectors else "Unknown"

    return {
        "top_picks": top_results,
        "all_results_count": len(all_results),
        "sector_data": sector_data,
        "sorted_sectors": sorted_sectors,
        "top_sector": top_sector,
        "sentiment": {"green": round(green_pct,1), "yellow": round(yellow_pct,1), "red": round(red_pct,1)},
        "run_time": run_time,
        "phase": phase,
        "max_score": MAX_SCORE,
    }
