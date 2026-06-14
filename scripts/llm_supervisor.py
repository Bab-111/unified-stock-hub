"""
llm_supervisor.py — Cross-module LLM supervision via Groq (FREE, no quota issues).
Free tier: 14,400 requests/day on Llama 3.1 8B — far more than we need (160/month).
Get key at: https://console.groq.com  (sign in with Google/GitHub, no credit card)
"""
import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"   # Free, fast, 131k context


def _valid_tickers(screener_data, monitor_data):
    known = set()
    if screener_data:
        for r in screener_data.get("top_picks", []):
            known.add(r.get("symbol", "").upper())
    if monitor_data:
        for s in monitor_data.get("stocks", []):
            known.add(s.get("ticker", "").upper())
    return known


def detect_conflicts(screener_data, monitor_data):
    """Rule-based conflict detection — free, no API needed."""
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
        macd_trend = ((mon.get("technicals", {}) or {}).get("macd", {}) or {}).get("trend", "")
        reasons = []
        if rsi and rsi >= 75 and sr["tl"] == "strong":
            reasons.append(f"Screener=strong but RSI={int(rsi)} (overbought)")
        if rsi and rsi <= 30 and sr["tl"] == "weak":
            reasons.append(f"Screener=weak but RSI={int(rsi)} (oversold?)")
        if macd_trend == "Bearish" and sr["tl"] == "strong":
            reasons.append("Screener=strong but MACD bearish crossover")
        if sr.get("close", 0) <= (sr.get("ma200") or 0) and sr["tl"] == "strong":
            reasons.append("Screener=strong but price below 200-day MA")
        if reasons:
            conflicts.append({"ticker": sym, "screener_rating": sr["tl"],
                               "rsi": rsi, "macd_trend": macd_trend, "reasons": reasons})
    return conflicts


def build_prompt(screener_data, monitor_data, conflicts, phase):
    lines = [f"You are validating an automated stock report. Market phase: {phase}."]
    if screener_data:
        max_score = screener_data.get("max_score", 17)
        lines.append(f"Top sector: {screener_data.get('top_sector','Unknown')}")
        lines.append("Screener top picks:")
        for r in screener_data.get("top_picks", []):
            above = "above" if r.get("close", 0) > (r.get("ma200") or 0) else "below"
            lines.append(f"  {r['symbol']} ({r.get('sector','?')}): score={r['score']}/{max_score} "
                         f"vol={r.get('vol_ratio',0):.1f}x MA200={above} "
                         f"inst={r.get('inst_pct','?')}% MFI={r.get('mfi_val','?')}")
    if monitor_data and monitor_data.get("stocks"):
        lines.append("Watchlist alerts:")
        for s in monitor_data["stocks"]:
            sigs = [sg["text"] for sg in s.get("signals", [])
                    if sg["level"] in ("critical", "warning", "negative")]
            if sigs:
                lines.append(f"  {s['ticker']}: {' | '.join(sigs[:2])}")
    if conflicts:
        lines.append("Rule-based conflicts:")
        for c in conflicts:
            lines.append(f"  {c['ticker']}: {' + '.join(c['reasons'])}")
    lines.append(
        "\nRespond in exactly 4 bullet points, 90 words max:\n"
        "• Validate top screener picks vs sector momentum\n"
        "• Flag any contradiction between screener and monitor signals\n"
        "• Name the strongest and weakest pick with one reason each\n"
        "• Overall confidence: HIGH / MEDIUM / LOW with one sentence\n"
        "No disclaimers. No financial advice. Be direct and specific."
    )
    return "\n".join(lines)


def check_hallucinations(text, known_tickers):
    import re
    skip = {"RSI","MFI","MACD","MA","IV","HIGH","LOW","MEDIUM","ETF",
            "PE","EPS","CEO","AI","US","GDP","FED","CPI","IPO","EV"}
    return [w for w in re.findall(r'\b[A-Z]{2,5}\b', text)
            if w not in known_tickers and w not in skip]


def run(screener_data, monitor_data, news_data, cfg: dict, output_dir: Path) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return (
            "⚠️ LLM supervision disabled.\n"
            "FREE setup: go to https://console.groq.com → sign in with Google/GitHub "
            "→ API Keys → Create API Key → add as GitHub Secret named GROQ_API_KEY.\n"
            "Free tier: 14,400 requests/day. No credit card needed."
        )

    phase     = (screener_data or {}).get("phase", "Unknown")
    conflicts = detect_conflicts(screener_data, monitor_data)
    prompt    = build_prompt(screener_data, monitor_data, conflicts, phase)
    known     = _valid_tickers(screener_data, monitor_data)
    log_max   = int(cfg.get("llm_log_max_entries", 10))

    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=25,
        )

        if resp.status_code != 200:
            return f"LLM API error {resp.status_code}: {resp.text[:200]}"

        note = resp.json()["choices"][0]["message"]["content"].strip()

        suspicious = check_hallucinations(note, known)
        if suspicious:
            note += f"\n⚠️ Hallucination check flagged: {', '.join(suspicious)}"

        conflict_summary = [{"ticker": c["ticker"], "reasons": c["reasons"]}
                            for c in conflicts]

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
            "model": f"groq/{GROQ_MODEL} (free)",
        })
        log = log[-log_max:]
        log_file.write_text(json.dumps(log, indent=2))
        return note

    except Exception as e:
        return f"LLM supervision unavailable: {e}"
