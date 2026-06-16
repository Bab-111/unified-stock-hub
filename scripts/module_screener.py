"""
module_screener.py — Unified breakout screener.
EXACT PARITY with original stock-screener/scripts/daily_report.py

6 fixes applied vs previous version:
  FIX 1: Price period = "6mo" (was "1y")
  FIX 2: Sector ETF period = "5d" interval="1d" (was "2d")
  FIX 3: Sector scoring: ONLY rank-1 = green+3pts; rank2-3 = yellow+1pt (was rank1-3=green)
  FIX 4: History lookback = 90 days (was 252)
  FIX 5: History conditions = vol>=2x AND breakout AND above_ma (was breakout only)
  FIX 6: History yellow band = hist_ret > 0 = yellow+1pt (was only green/red)

KEPT from unified (not in original, added as improvements):
  + Options enrichment: ATM call details + CSP suggestion displayed in cards
  + Candle description text in cards
  + Market cap display in cards
"""
import warnings
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
    "volume":2,"breakout":2,"ma200":2,
    "inst_own":3,"mfi":2,"sector":3,"history":2,"iv":1,
}
MAX_SCORE = sum(WEIGHTS.values())  # 17


def safe_float(val, default=None):
    try:    return float(val)
    except: return default


def classify(value, high_t, mod_t):
    """Exact copy of original classify() helper."""
    v = safe_float(value)
    if v is None: return "red"
    return "green" if v >= high_t else ("yellow" if v >= mod_t else "red")


def flatten_df(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def get_regular_close_bar(df):
    """Lock to regular market close bar — skip low-volume incomplete bars."""
    df = df.copy().dropna(how="all")
    if len(df) < 2:
        return df.iloc[-1]
    last    = df.iloc[-1]
    prev    = df.iloc[-2]
    avg_vol = float(df["Volume"].mean())
    if avg_vol > 0 and float(last["Volume"]) < avg_vol * 0.20:
        return prev
    return last


def get_market_phase(utc_hour, utc_minute):
    t  = utc_hour * 60 + utc_minute
    et = t - 240
    if et < 0: et += 1440
    if   et <  570: return "Pre-Market (before 9:30 AM ET)"
    elif et <  960: return "Regular Market Hours"
    elif et < 1200: return "After-Hours (4:00-8:00 PM ET)"
    else:           return "Overnight"


def calc_ma200(data):
    """Rolling MA using min(200, available bars) — matches original."""
    cl  = flatten_df(data)["Close"].squeeze().astype(float)
    win = min(200, len(cl))
    return float(cl.rolling(win).mean().iloc[-1])


def calc_mfi(data, period=14):
    """14-period Money Flow Index — exact original formula."""
    try:
        hi  = flatten_df(data)["High"].squeeze().astype(float)
        lo  = flatten_df(data)["Low"].squeeze().astype(float)
        cl  = flatten_df(data)["Close"].squeeze().astype(float)
        vol = flatten_df(data)["Volume"].squeeze().astype(float)
        tp  = (hi + lo + cl) / 3
        rmf = tp * vol
        pos = rmf.where(tp > tp.shift(1), 0.0)
        neg = rmf.where(tp < tp.shift(1), 0.0)
        mfr = (pos.rolling(period).sum() /
               neg.rolling(period).sum().replace(0, 1e-9))
        v   = float((100 - (100 / (1 + mfr))).iloc[-1])
        return round(v, 1) if not np.isnan(v) else None
    except Exception:
        return None


def last_breakout(data, vol_threshold=2.0, brk_threshold=1.03, fwd_days=10, ret_threshold=5):
    """
    FIX 4: lookback = 90 days (was 252)
    FIX 5: requires vol>=2x AND breakout candle AND above MA (was breakout only)
    FIX 6: returns (date, ret, 'yellow') if ret > 0 but < threshold (was ignored)
    Exact logic from original last_breakout().
    """
    try:
        df      = flatten_df(data.copy())
        closes  = df["Close"].squeeze().astype(float).values
        opens   = df["Open"].squeeze().astype(float).values
        volumes = df["Volume"].squeeze().astype(float).values
        avg_vol = float(np.nanmean(volumes))
        win     = min(200, len(closes))
        # Rolling MA array — matches original exactly
        ma_vals = np.array([
            np.mean(closes[max(0, i - win):i]) if i >= 20 else np.nan
            for i in range(len(closes))
        ])
        # FIX 4: lookback 90 days only
        lookback = min(90, len(df) - fwd_days - 1)
        for i in range(len(data) - 2, max(0, len(data) - lookback), -1):
            # FIX 5: all three conditions required
            if (volumes[i] >= vol_threshold * avg_vol and
                    closes[i] > opens[i] * brk_threshold and
                    not np.isnan(ma_vals[i]) and closes[i] > ma_vals[i]):
                fwd = min(i + fwd_days, len(closes) - 1)
                ret = round((closes[fwd] - closes[i]) / closes[i] * 100, 1)
                date_str = df.index[i].strftime("%b %d, %Y")
                # FIX 6: yellow band for positive but below threshold
                if ret >= ret_threshold:
                    return date_str, ret, "green"
                elif ret > 0:
                    return date_str, ret, "yellow"
    except Exception:
        pass
    return None, None, None


def score_stock(vol_ratio, breakout, above_ma, inst_pct, mfi_val,
                sec_rank, iv_val, hist_ret, hist_color,
                vol_thresh=2.0, inst_high=60, inst_mod=40,
                mfi_thresh=50, iv_high=25, iv_mod=15):
    """
    Scoring — EXACT match to original score_stock().
    FIX 3: sector rank scoring (only rank-1=green, rank2-3=yellow)
    FIX 6: history uses hist_color (green/yellow/red)
    """
    f = {}
    s = 0

    # Volume (w:2)
    if   vol_ratio >= vol_thresh: f["volume"] = "green";  s += 2
    elif vol_ratio >= 1.3:        f["volume"] = "yellow"; s += 1
    else:                         f["volume"] = "red"

    # Breakout candle (w:2)
    if   breakout:           f["breakout"] = "green";  s += 2
    elif vol_ratio >= 1.5:   f["breakout"] = "yellow"; s += 1
    else:                    f["breakout"] = "red"

    # MA200 (w:2)
    f["ma200"] = "green" if above_ma else "red"
    s += 2 if above_ma else 0

    # Institutional ownership (w:3)
    ic = classify(inst_pct, inst_high, inst_mod)
    f["inst_own"] = ic
    s += 3 if ic == "green" else (1 if ic == "yellow" else 0)

    # MFI (w:2)
    mc = classify(mfi_val, mfi_thresh + 10, mfi_thresh)
    f["mfi"] = mc
    s += 2 if mc == "green" else (1 if mc == "yellow" else 0)

    # FIX 3: Sector (w:3) — ONLY rank-1 = full green
    if   sec_rank == 1: f["sector"] = "green";  s += 3
    elif sec_rank <= 3: f["sector"] = "yellow"; s += 1
    else:               f["sector"] = "red"

    # IV (w:1)
    ivc = classify(iv_val, iv_high, iv_mod) if iv_val is not None else "red"
    f["iv"] = ivc
    s += 1 if ivc == "green" else 0

    # FIX 6: History (w:2) — yellow band preserved
    if   hist_color == "green":  f["history"] = "green";  s += 2
    elif hist_color == "yellow": f["history"] = "yellow"; s += 1
    else:                        f["history"] = "red"

    return s, f


def traffic_light(score):
    p = score / MAX_SCORE
    return "strong" if p >= 0.70 else ("moderate" if p >= 0.45 else "weak")


def fmt_mcap(n):
    try:
        n = float(n)
        if n >= 1e12: return f"${n/1e12:.1f}T"
        if n >= 1e9:  return f"${n/1e9:.1f}B"
        if n >= 1e6:  return f"${n/1e6:.1f}M"
        return f"${n:.0f}"
    except Exception:
        return "N/A"


# ── Options enrichment (unified addition — not in original) ────────────────────

def get_options_detail(ticker_sym, price):
    result = {"iv_mean": None, "atm_call": None, "csp": None, "exp": None}
    try:
        t     = yf.Ticker(ticker_sym)
        exps  = t.options
        if not exps:
            return result
        result["exp"] = str(exps[0])
        chain = t.option_chain(exps[0])
        calls = chain.calls.dropna(subset=["impliedVolatility"])
        puts  = chain.puts.dropna(subset=["impliedVolatility"])

        # IV mean of ALL calls — matches original scoring
        if len(calls) > 0:
            result["iv_mean"] = round(float(calls["impliedVolatility"].mean()) * 100, 1)

        # ATM call detail
        if len(calls) > 0 and price:
            atm = calls.iloc[(calls["strike"] - price).abs().argsort().iloc[:1]]
            row = atm.iloc[0]
            result["atm_call"] = {
                "strike":  round(float(row["strike"]), 2),
                "premium": round(float(row["lastPrice"]), 2),
                "iv":      round(float(row["impliedVolatility"]) * 100, 1),
                "delta":   round(float(row["delta"]), 3) if "delta" in row and pd.notna(row.get("delta")) else None,
                "theta":   round(float(row["theta"]), 4) if "theta" in row and pd.notna(row.get("theta")) else None,
                "volume":  int(row["volume"]) if pd.notna(row.get("volume")) else None,
                "oi":      int(row["openInterest"]) if pd.notna(row.get("openInterest")) else None,
            }

        # Best CSP: OTM put within 5% of price with highest premium
        if len(puts) > 0 and price:
            otm = puts[puts["strike"] <= price * 0.95].copy()
            if len(otm) > 0:
                row = otm.sort_values("lastPrice", ascending=False).iloc[0]
                result["csp"] = {
                    "strike":  round(float(row["strike"]), 2),
                    "premium": round(float(row["lastPrice"]), 2),
                    "iv":      round(float(row["impliedVolatility"]) * 100, 1),
                    "pct_otm": round((price - float(row["strike"])) / price * 100, 1),
                    "exp":     str(exps[0]),
                }
    except Exception:
        pass
    return result


# ── Batch fetchers ─────────────────────────────────────────────────────────────

def batch_sector():
    """FIX 2: period=5d, interval=1d — matches original."""
    etf_list = list(SECTOR_ETFS.values())
    try:
        raw = yf.download(etf_list, period="5d", interval="1d",
                          group_by="ticker", auto_adjust=True,
                          progress=False, threads=True)
        result = {}
        for sector, etf in SECTOR_ETFS.items():
            try:
                cl = raw[etf]["Close"].squeeze() if len(etf_list) > 1 else flatten_df(raw)["Close"]
                if len(cl) >= 2:
                    result[sector] = round(
                        float((cl.iloc[-1] - cl.iloc[-2]) / cl.iloc[-2] * 100), 2)
            except Exception:
                pass
        print(f"  Got {len(result)} sectors")
        return result
    except Exception as e:
        print(f"  [Screener] sector batch error: {e}")
        return {}


def batch_price(symbols):
    """FIX 1: period=6mo, interval=1d — matches original."""
    print(f"  [2/3] Price data ({len(symbols)} tickers)...", flush=True)
    needed = ["Open", "High", "Low", "Close", "Volume"]
    try:
        raw = yf.download(symbols, period="6mo", interval="1d",
                          group_by="ticker", auto_adjust=True,
                          progress=False, threads=True)
        result = {}
        if len(symbols) == 1:
            sym = symbols[0]
            df  = flatten_df(raw)
            if len(df) >= 20 and all(c in df.columns for c in needed):
                result[sym] = df[needed].dropna(how="all")
            return result
        for sym in symbols:
            try:
                if sym not in raw.columns.get_level_values(0):
                    continue
                df = flatten_df(raw[sym])
                if len(df) < 20:
                    continue
                if not all(c in df.columns for c in needed):
                    continue
                result[sym] = df[needed].dropna(how="all")
            except Exception:
                pass
        print(f"  Got data for {len(result)} tickers")
        return result
    except Exception as e:
        print(f"  [Screener] price batch error: {e}")
        return {}


def enrich_candidate(sym, price):
    """Fetch inst%, options (iv_mean + ATM + CSP), mcap for top-10 only."""
    inst_pct = mcap = None
    opts = {"iv_mean": None, "atm_call": None, "csp": None, "exp": None}
    try:
        info = yf.Ticker(sym).info
        raw  = info.get("heldPercentInstitutions")
        if raw is not None:
            inst_pct = round(float(raw) * 100, 1)
        mcap_raw = info.get("marketCap")
        if mcap_raw:
            mcap = float(mcap_raw)
    except Exception:
        pass
    opts = get_options_detail(sym, price)
    return inst_pct, opts, mcap


# ── Main runner ────────────────────────────────────────────────────────────────

def run(universe_file: str, cfg: dict) -> dict:
    now_utc  = datetime.now(timezone.utc).replace(tzinfo=None)
    run_time = now_utc.strftime("%Y-%m-%d %H:%M")
    phase    = get_market_phase(now_utc.hour, now_utc.minute)
    print(f"[Screener] {run_time} — {phase}")

    vol_thresh  = float(cfg.get("volume_spike_threshold", 2.0))
    brk_thresh  = float(cfg.get("breakout_threshold", 1.03))
    top_n       = int(cfg.get("top_picks", 5))
    inst_high   = float(cfg.get("inst_ownership_high", 60))
    inst_mod    = float(cfg.get("inst_ownership_moderate", 40))
    mfi_thresh  = float(cfg.get("mfi_threshold", 50))
    iv_high     = float(cfg.get("iv_high_threshold", 25))
    iv_mod      = float(cfg.get("iv_moderate_threshold", 15))
    fwd_days    = int(cfg.get("forward_return_days", 10))

    symbols = pd.read_csv(universe_file)["Symbol"].dropna().tolist()
    print(f"  Universe: {len(symbols)} tickers")

    # Batch 1: Sector ETFs (FIX 2: 5d period)
    print("  [1/3] Sector rotation...", flush=True)
    sector_data    = batch_sector()
    sorted_sectors = sorted(sector_data.items(), key=lambda x: x[1], reverse=True)
    sector_rank    = {s: i + 1 for i, (s, _) in enumerate(sorted_sectors)}

    # Batch 2: All prices (FIX 1: 6mo period)
    price_data = batch_price(symbols)
    valid_syms = list(price_data.keys())

    # Score all stocks
    print(f"  [3/3] Scoring {len(valid_syms)} stocks...", flush=True)
    all_results = []
    for sym in valid_syms:
        try:
            data      = price_data[sym]
            bar       = get_regular_close_bar(data)
            close     = float(bar["Close"])
            open_     = float(bar["Open"])
            vol       = float(bar["Volume"])
            avg_v     = float(data["Volume"].squeeze().mean())
            vol_ratio = round(vol / avg_v, 2) if avg_v > 0 else 0.0
            breakout  = close > open_ * brk_thresh
            ma200     = calc_ma200(data)
            above_ma  = close > ma200
            mfi_val   = calc_mfi(data)
            sec       = SECTOR_MAP.get(sym, "Unknown")
            sec_rank  = sector_rank.get(sec, 99)
            chg_pct   = round((close - open_) / open_ * 100, 2) if open_ else 0

            # FIX 4+5+6: history with 90-day lookback + all conditions + yellow band
            hist_date, hist_ret, hist_color = last_breakout(
                data, vol_thresh, brk_thresh, fwd_days)

            score, factors = score_stock(
                vol_ratio, breakout, above_ma, None, mfi_val,
                sec_rank, None, hist_ret, hist_color,
                vol_thresh=vol_thresh, inst_high=inst_high, inst_mod=inst_mod,
                mfi_thresh=mfi_thresh, iv_high=iv_high, iv_mod=iv_mod,
            )
            all_results.append({
                "symbol": sym, "score": score, "tl": traffic_light(score),
                "factors": factors, "close": close, "open": open_,
                "change_pct": chg_pct, "vol_ratio": vol_ratio,
                "ma200": ma200, "mcap": None, "mcap_fmt": "—",
                "inst_pct": None, "mfi_val": mfi_val,
                "sector": sec, "iv_val": None,
                "hist_date": hist_date, "hist_ret": hist_ret,
                "hist_color": hist_color, "options": None,
            })
        except Exception:
            pass

    all_results.sort(key=lambda x: x["score"], reverse=True)
    top10 = all_results[:10]

    # Enrich top-10 with inst%, IV, options, mcap
    print("  Enriching top 10...", flush=True)
    for r in top10:
        sym   = r["symbol"]
        price = r["close"]
        inst_pct, opts, mcap = enrich_candidate(sym, price)
        r["inst_pct"] = inst_pct
        r["iv_val"]   = opts["iv_mean"]  # mean of ALL calls — matches original
        r["options"]  = opts
        r["mcap"]     = mcap
        r["mcap_fmt"] = fmt_mcap(mcap)

        new_score, new_factors = score_stock(
            r["vol_ratio"], r["close"] > r["open"] * brk_thresh,
            r["close"] > r["ma200"], inst_pct, r["mfi_val"],
            sector_rank.get(r["sector"], 99), opts["iv_mean"],
            r["hist_ret"], r["hist_color"],
            vol_thresh=vol_thresh, inst_high=inst_high, inst_mod=inst_mod,
            mfi_thresh=mfi_thresh, iv_high=iv_high, iv_mod=iv_mod,
        )
        r["score"]   = new_score
        r["factors"] = new_factors
        r["tl"]      = traffic_light(new_score)
        print(f"    {sym}: {new_score}/{MAX_SCORE} inst={inst_pct}% iv={opts['iv_mean']}%")

    top10.sort(key=lambda x: x["score"], reverse=True)
    top_results = top10[:top_n]

    total      = max(len(all_results), 1)
    green_pct  = sum(1 for r in all_results if r["tl"] == "strong")  / total * 100
    yellow_pct = sum(1 for r in all_results if r["tl"] == "moderate") / total * 100
    red_pct    = sum(1 for r in all_results if r["tl"] == "weak")    / total * 100

    return {
        "top_picks":         top_results,
        "all_results_count": len(all_results),
        "sector_data":       sector_data,
        "sorted_sectors":    sorted_sectors,
        "top_sector":        sorted_sectors[0][0] if sorted_sectors else "Unknown",
        "sentiment":         {"green": round(green_pct, 1),
                              "yellow": round(yellow_pct, 1),
                              "red": round(red_pct, 1)},
        "run_time":          run_time,
        "phase":             phase,
        "max_score":         MAX_SCORE,
    }
