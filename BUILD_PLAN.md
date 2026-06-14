"""
llm_supervisor.py — Cross-module LLM supervision via Claude Haiku.
Validates screener picks, monitor signals, and news tone in one prompt.
Includes hallucination guard and audit log.
"""
import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path


def _valid_tickers(screener_data, monitor_data):
    """Build set of all known tickers for hallucination check."""
    known = set()
    if screener_data:
        for r in screener_data.get("top_picks", []):
            known.add(r.get("symbol", "").upper())
    if monitor_data:
        for s in monitor_data.get("stocks", []):
            known.add(s.get("ticker", "").upper())
    return known


def detect_conflicts(screener_data, monitor_data):
    """
    Rule-based conflict detection before LLM call.
    Returns list of conflict dicts: {ticker, screener_signal, monitor_signal, reason}
    """
    conflicts = []
    if not screener_data or not monitor_data:
        return conflicts

    screener_tickers = {r["symbol"]: r for r in screener_data.get("top_picks", [])}
    monitor_tickers  = {s["ticker"]: s for s in monitor_data.get("stocks", [])}

    for sym, sr in screener_tickers.items():
        # Match against monitor — GOOG vs GOOGL etc
        mon = monitor_tickers.get(sym) or monitor_tickers.get(sym.replace("L","").replace("L",""))
        if not mon:
            continue
        rsi = mon.get("technicals", {}).get("rsi")
        macd = (mon.get("technicals", {}) or {}).get("macd", {}) or {}
        macd_trend = macd.get("trend", "")

        reasons = []
        if rsi and rsi >= 75 and sr["tl"] == "strong":
            reasons.append(f"Screener=strong but RSI={int(rsi)} (overbought)")
        if rsi and rsi <= 30 and sr["tl"] == "weak":
            reasons.append(f"Screener=weak but RSI={int(rsi)} (oversold opportunity?)")
        if macd_trend == "Bearish" and sr["tl"] == "strong":
            reasons.append(f"Screener=strong but MACD bearish crossover")
        above_ma = sr.get("close", 0) > (sr.get("ma200") or 0)
        if not above_ma and sr["tl"] == "strong":
            reasons.append("Screener=strong but price below 200-day MA")

        if reasons:
            conflicts.append({
                "ticker": sym,
                "screener_rating": sr["tl"],
                "rsi": rsi,
                "macd_trend": macd_trend,
                "reasons": reasons,
            })
    return conflicts


def build_prompt(screener_data, monitor_data, news_data, conflicts, phase):
    """Build compact combined prompt for Haiku."""
    lines = [f"You are validating an automated stock report. Phase: {phase}."]

    if screener_data:
        top_sector = screener_data.get("top_sector", "Unknown")
        lines.append(f"\nTop sector today: {top_sector}")
        lines.append("Screener top picks:")
        max_score = screener_data.get("max_score", 17)
        for r in screener_data.get("top_picks", []):
            above = "above" if r.get("close", 0) > (r.get("ma200") or 0) else "below"
            lines.append(
                f"  {r['symbol']} ({r.get('sector','?')}): score={r['score']}/{max_score} "
                f"vol={r.get('vol_ratio',0):.1f}x MA200={above} "
                f"inst={r.get('inst_pct','?')}% MFI={r.get('mfi_val','?')}"
            )

    if monitor_data and monitor_data.get("stocks"):
        lines.append("\nWatchlist alerts (signals only):")
        for s in monitor_data["stocks"]:
            sigs = [sig["text"] for sig in s.get("signals", []) if sig["level"] in ("critical","warning","negative")]
            if sigs:
                lines.append(f"  {s['ticker']}: {' | '.join(sigs[:2])}")

    if conflicts:
        lines.append("\nRule-based conflicts detected:")
        for c in conflicts:
            lines.append(f"  {c['ticker']}: {' + '.join(c['reasons'])}")

    lines.append(
        "\nIn 4 bullets max (90 words total):\n"
        "1. Validate screener picks vs sector\n"
        "2. Flag contradictions between screener and monitor\n"
        "3. Note strongest and weakest pick\n"
        "4. Overall confidence: HIGH / MEDIUM / LOW\n"
        "No disclaimers. No financial advice framing. Be specific."
    )
    return "\n".join(lines)


def check_hallucinations(text, known_tickers):
    """Flag any uppercase ticker-like word in LLM output not in known set."""
    import re
    words = re.findall(r'\b[A-Z]{1,5}\b', text)
    suspicious = [w for w in words if len(w) >= 2 and w not in known_tickers
                  and w not in {"RSI","MFI","MACD","MA","IV","HIGH","LOW","MEDIUM","ETF","PE","EPS"}]
    return suspicious


def run(screener_data, monitor_data, news_data, cfg: dict, output_dir: Path) -> str:
    """
    Call Claude Haiku to validate combined report output.
    Saves note to llm_log.json. Returns note string.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "⚠️ LLM supervision disabled — add ANTHROPIC_API_KEY as GitHub Secret to enable."

    phase = (screener_data or {}).get("phase", "Unknown")
    conflicts = detect_conflicts(screener_data, monitor_data)
    prompt = build_prompt(screener_data, monitor_data, news_data, conflicts, phase)
    known_tickers = _valid_tickers(screener_data, monitor_data)

    model     = cfg.get("llm_model", "claude-haiku-4-5-20251001")
    max_tok   = int(cfg.get("llm_max_tokens", 300))
    log_max   = int(cfg.get("llm_log_max_entries", 10))

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tok,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=25,
        )
        if resp.status_code != 200:
            return f"LLM supervision API error: {resp.status_code}"

        note = resp.json()["content"][0]["text"].strip()

        # Hallucination check
        suspicious = check_hallucinations(note, known_tickers)
        if suspicious:
            note += f"\n⚠️ Hallucination check: unexpected tickers in LLM output: {', '.join(suspicious)}"

        # Conflict summary for HTML
        conflict_summary = [
            {"ticker": c["ticker"], "reasons": c["reasons"]}
            for c in conflicts
        ]

        # Append to audit log
        log_file = output_dir / "llm_log.json"
        log = []
        if log_file.exists():
            try:
                log = json.loads(log_file.read_text())
            except Exception:
                log = []
        log.append({
            "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "phase": phase,
            "note": note,
            "conflicts": conflict_summary,
            "suspicious_tickers": suspicious,
        })
        log = log[-log_max:]
        log_file.write_text(json.dumps(log, indent=2))

        return note

    except Exception as e:
        return f"LLM supervision unavailable: {e}"
