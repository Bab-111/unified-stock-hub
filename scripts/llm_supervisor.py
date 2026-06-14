"""
llm_supervisor.py — Cross-module LLM supervision via Google Gemini Flash (FREE).
Free tier: 1,500 requests/day, no credit card required.
Get key at: https://aistudio.google.com/apikey (sign in with Google, click Get API Key)

Validates screener picks, monitor signals in one prompt.
Includes hallucination guard and audit log.
"""
import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


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
    Rule-based conflict detection before LLM call (free, no API needed).
    Returns list of conflict dicts.
    """
    conflicts = []
    if not screener_data or not monitor_data:
        return conflicts

    screener_tickers = {r["symbol"]: r for r in screener_data.get("top_picks", [])}
    monitor_tickers  = {s["ticker"]: s for s in monitor_data.get("stocks", [])}

    for sym, sr in screener_tickers.items():
        mon = monitor_tickers.get(sym)
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
            reasons.append("Screener=strong but MACD bearish crossover")
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


def build_prompt(screener_data, monitor_data, conflicts, phase):
    """Build compact prompt — kept short to stay well within free tier limits."""
    lines = [f"You are validating an automated stock report. Market phase: {phase}."]

    if screener_data:
        top_sector = screener_data.get("top_sector", "Unknown")
        max_score  = screener_data.get("max_score", 17)
        lines.append(f"Top sector today: {top_sector}")
        lines.append("Screener top picks:")
        for r in screener_data.get("top_picks", []):
            above = "above" if r.get("close", 0) > (r.get("ma200") or 0) else "below"
            lines.append(
                f"  {r['symbol']} ({r.get('sector','?')}): score={r['score']}/{max_score} "
                f"vol={r.get('vol_ratio',0):.1f}x MA200={above} "
                f"inst={r.get('inst_pct','?')}% MFI={r.get('mfi_val','?')}"
            )

    if monitor_data and monitor_data.get("stocks"):
        lines.append("Watchlist alerts:")
        for s in monitor_data["stocks"]:
            sigs = [sig["text"] for sig in s.get("signals", [])
                    if sig["level"] in ("critical", "warning", "negative")]
            if sigs:
                lines.append(f"  {s['ticker']}: {' | '.join(sigs[:2])}")

    if conflicts:
        lines.append("Rule-based conflicts detected:")
        for c in conflicts:
            lines.append(f"  {c['ticker']}: {' + '.join(c['reasons'])}")

    lines.append(
        "\nRespond in exactly 4 bullet points, 90 words max total:\n"
        "• Validate top screener picks vs sector momentum\n"
        "• Flag any contradiction between screener and monitor signals\n"
        "• Name the strongest and weakest pick with one reason each\n"
        "• Overall confidence: HIGH / MEDIUM / LOW with one sentence reason\n"
        "No disclaimers. No financial advice language. Be direct and specific."
    )
    return "\n".join(lines)


def check_hallucinations(text, known_tickers):
    """Flag uppercase ticker-like words in LLM output not in actual data."""
    import re
    skip = {"RSI","MFI","MACD","MA","IV","HIGH","LOW","MEDIUM","ETF",
            "PE","EPS","CEO","AI","US","GDP","FED","CPI","IPO","EV"}
    words = re.findall(r'\b[A-Z]{2,5}\b', text)
    return [w for w in words if w not in known_tickers and w not in skip]


def run(screener_data, monitor_data, news_data, cfg: dict, output_dir: Path) -> str:
    """
    Call Gemini Flash (free) to validate the combined report.
    Falls back gracefully if no key set.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return (
            "⚠️ LLM supervision disabled.\n"
            "To enable FREE supervision: get a key at https://aistudio.google.com/apikey "
            "(Google sign-in only, no credit card) then add GEMINI_API_KEY as a GitHub Secret."
        )

    phase    = (screener_data or {}).get("phase", "Unknown")
    conflicts = detect_conflicts(screener_data, monitor_data)
    prompt   = build_prompt(screener_data, monitor_data, conflicts, phase)
    known    = _valid_tickers(screener_data, monitor_data)
    log_max  = int(cfg.get("llm_log_max_entries", 10))

    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 300,
                    "temperature": 0.3,
                },
            },
            timeout=25,
        )

        if resp.status_code != 200:
            return f"LLM API error {resp.status_code}: {resp.text[:200]}"

        data = resp.json()
        note = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Hallucination check
        suspicious = check_hallucinations(note, known)
        if suspicious:
            note += f"\n⚠️ Hallucination check flagged: {', '.join(suspicious)}"

        conflict_summary = [{"ticker": c["ticker"], "reasons": c["reasons"]} for c in conflicts]

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
            "model": "gemini-2.0-flash (free)",
        })
        log = log[-log_max:]
        log_file.write_text(json.dumps(log, indent=2))

        return note

    except Exception as e:
        return f"LLM supervision unavailable: {e}"
