"""
build_report.py — Generates unified self-contained HTML report.
Single file, no external runtime dependencies, mobile-first, dark mode.
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

TAIWAN_TZ = ZoneInfo("Asia/Taipei")


def _tl_class(tl):
    return {"strong": "tl-strong", "moderate": "tl-moderate", "weak": "tl-weak"}.get(tl, "tl-weak")


def _tl_label(tl):
    return {"strong": "Strong", "moderate": "Moderate", "weak": "Weak"}.get(tl, "Weak")


def _factor_class(val):
    return {"green": "fg", "yellow": "fy", "red": "fr"}.get(val, "fr")


def _chg_class(v):
    try:
        return "pos" if float(v) >= 0 else "neg"
    except Exception:
        return ""


def _fmt(v, unit="", fallback="—"):
    if v is None: return fallback
    try: return f"{v}{unit}"
    except: return fallback


def render_sector_bars(sector_data):
    if not sector_data:
        return "<p class='muted'>No sector data</p>"
    sorted_s = sorted(sector_data.items(), key=lambda x: x[1], reverse=True)
    max_abs = max(abs(v) for _, v in sorted_s) if sorted_s else 1
    html = '<div class="sector-bars">'
    for sector, chg in sorted_s:
        cls = "pos" if chg >= 0 else "neg"
        bar_w = max(2, abs(chg) / max_abs * 100)
        sign = "+" if chg >= 0 else ""
        html += f'''
        <div class="sector-row">
          <span class="sector-name">{sector}</span>
          <div class="bar-track">
            <div class="bar-fill {cls}" style="width:{bar_w:.1f}%"></div>
          </div>
          <span class="sector-chg {cls}">{sign}{chg:.2f}%</span>
        </div>'''
    html += "</div>"
    return html


def render_screener_card(r, max_score):
    sym     = r.get("symbol", "")
    score   = r.get("score", 0)
    tl      = r.get("tl", "weak")
    close   = r.get("close", 0)
    chg     = r.get("change_pct", 0)
    sector  = r.get("sector", "—")
    vol_r   = r.get("vol_ratio", 0)
    ma200   = r.get("ma200")
    inst    = r.get("inst_pct")
    mfi     = r.get("mfi_val")
    iv      = r.get("iv_val")
    hist_d  = r.get("hist_date", "")
    hist_r  = r.get("hist_ret", 0)
    factors = r.get("factors", {})
    score_pct = round(score / max_score * 100)
    chg_sign = "+" if chg >= 0 else ""
    above_ma = close > (ma200 or 0)

    factor_pills = ""
    factor_labels = {
        "volume":"Vol","breakout":"Breakout","ma200":"MA200",
        "inst_own":"Inst","mfi":"MFI","sector":"Sector","history":"History","iv":"IV"
    }
    for k, label in factor_labels.items():
        cls = _factor_class(factors.get(k, "red"))
        factor_pills += f'<span class="pill {cls}">{label}</span>'

    return f'''
    <div class="card screener-card {_tl_class(tl)}">
      <div class="card-header">
        <div class="card-title-row">
          <span class="ticker">{sym}</span>
          <span class="tl-badge {_tl_class(tl)}">{_tl_label(tl)}</span>
        </div>
        <div class="card-price-row">
          <span class="price">${close:.2f}</span>
          <span class="chg {_chg_class(chg)}">{chg_sign}{chg:.2f}%</span>
          <span class="sector-tag">{sector}</span>
        </div>
      </div>
      <div class="score-bar-wrap">
        <div class="score-bar-track">
          <div class="score-bar-fill {_tl_class(tl)}" style="width:{score_pct}%"></div>
        </div>
        <span class="score-label">{score}/{max_score}</span>
      </div>
      <div class="factor-pills">{factor_pills}</div>
      <div class="card-meta">
        <span>Vol: <strong>{vol_r:.1f}x</strong></span>
        <span>MA200: <strong class="{'pos' if above_ma else 'neg'}">${ma200 or '—'}</strong></span>
        <span>Inst: <strong>{inst or '—'}{'%' if inst else ''}</strong></span>
        <span>MFI: <strong>{mfi or '—'}</strong></span>
        <span>IV: <strong>{iv or '—'}{'%' if iv else ''}</strong></span>
        {f'<span>Last breakout: <strong>{hist_d}</strong> ({hist_r:+.1f}%)</span>' if hist_d else ''}
      </div>
    </div>'''


def render_monitor_card(s):
    ticker = s.get("ticker", "")
    name   = s.get("name", ticker)
    price  = s.get("price", 0)
    chg    = s.get("change_pct", 0)
    curr   = s.get("currency", "USD")
    h52    = s.get("h52")
    l52    = s.get("l52")
    pfh    = s.get("pct_from_high")
    pfl    = s.get("pct_from_low")
    sector = s.get("sector", "—")
    tech   = s.get("technicals", {})
    mas    = s.get("moving_averages", {})
    fund   = s.get("fundamentals", {})
    opts   = s.get("options")
    earn   = s.get("earnings")
    vol    = s.get("volume", {})
    sigs   = s.get("signals", [])
    macd_d = tech.get("macd") or {}
    rsi    = tech.get("rsi")
    chg_sign = "+" if chg >= 0 else ""
    curr_sym = "$" if curr == "USD" else curr + " "

    # Signals HTML
    sig_html = ""
    for sig in sigs[:6]:
        level = sig.get("level","")
        cls = {"critical":"sig-crit","warning":"sig-warn","negative":"sig-neg",
               "positive":"sig-pos","opportunity":"sig-opp","caution":"sig-caut"}.get(level,"")
        sig_html += f'<div class="signal {cls}">{sig["icon"]} {sig["text"]}</div>'

    # Earnings badge
    earn_html = ""
    if earn:
        days = earn["days"]
        ecls = "earn-urgent" if days <= 7 else "earn-soon"
        earn_html = f'<span class="earn-badge {ecls}">📅 {earn["date"]} ({days}d)</span>'

    # MA pills
    ma_pills = ""
    for p in [20, 50, 200]:
        sma = mas.get(f"sma{p}")
        vs  = mas.get(f"vs_sma{p}")
        if sma and vs is not None:
            cls = "pos" if vs >= 0 else "neg"
            sign = "+" if vs >= 0 else ""
            ma_pills += f'<span class="ma-pill {cls}">SMA{p} {sign}{vs}%</span>'

    # Fundamentals table
    fund_rows = ""
    fmap = [
        ("PE", fund.get("pe")), ("Fwd PE", fund.get("fpe")),
        ("PEG", fund.get("peg")), ("P/B", fund.get("pb")),
        ("ROE", f'{fund.get("roe")}%' if fund.get("roe") else None),
        ("Margin", f'{fund.get("profit_margin")}%' if fund.get("profit_margin") else None),
        ("Rev Growth", f'{fund.get("revenue_growth")}%' if fund.get("revenue_growth") else None),
        ("D/E", fund.get("debt_equity")), ("Beta", fund.get("beta")),
        ("Inst Own", f'{fund.get("inst_own")}%' if fund.get("inst_own") else None),
        ("Short %", f'{fund.get("short_float")}%' if fund.get("short_float") else None),
        ("Mkt Cap", fund.get("market_cap")),
    ]
    for label, val in fmap:
        if val is not None:
            fund_rows += f'<div class="fund-row"><span>{label}</span><strong>{val}</strong></div>'

    # Options
    opts_html = ""
    if opts:
        iv = opts.get("iv", "—")
        delta = opts.get("delta", "—")
        theta = opts.get("theta", "—")
        exp   = opts.get("exp", "—")
        opts_html = f'''
        <div class="opts-section">
          <div class="section-label">Options (exp {exp})</div>
          <div class="opts-row">
            <span>IV: <strong>{iv}%</strong></span>
            <span>Delta: <strong>{delta}</strong></span>
            <span>Theta: <strong>{theta}</strong></span>
          </div>'''
        csp = opts.get("csp")
        if csp:
            opts_html += f'<div class="csp-row">CSP: ${csp.get("strike")} @ ${csp.get("premium")} IV {csp.get("iv")}%</div>'
        opts_html += "</div>"

    return f'''
    <div class="card monitor-card">
      <div class="card-header">
        <div class="card-title-row">
          <span class="ticker">{ticker}</span>
          {earn_html}
        </div>
        <div class="card-name">{name}</div>
        <div class="card-price-row">
          <span class="price">{curr_sym}{price:.2f}</span>
          <span class="chg {_chg_class(chg)}">{chg_sign}{chg:.2f}%</span>
          <span class="sector-tag">{sector}</span>
        </div>
        <div class="range-row">
          52w: <span class="neg">${l52 or '—'}</span> – <span class="pos">${h52 or '—'}</span>
          {f' <span class="muted">({pfh:+.1f}% from high)</span>' if pfh else ''}
        </div>
      </div>
      <div class="signals-wrap">{sig_html}</div>
      <div class="tech-row">
        <div class="tech-item">
          <div class="tech-label">RSI (14)</div>
          <div class="tech-val {'rsi-ob' if rsi and rsi>=70 else 'rsi-os' if rsi and rsi<=30 else ''}">{rsi or '—'}</div>
        </div>
        <div class="tech-item">
          <div class="tech-label">MACD</div>
          <div class="tech-val">{macd_d.get("trend","—")}</div>
        </div>
        <div class="tech-item">
          <div class="tech-label">Volume</div>
          <div class="tech-val {'warn' if vol.get('spike') else ''}">{vol.get("ratio","—")}x</div>
        </div>
      </div>
      <div class="ma-pills">{ma_pills}</div>
      {f'<div class="fund-grid">{fund_rows}</div>' if fund_rows else ''}
      {opts_html}
    </div>'''


def render_news_section(news_data, monitor_tickers=None):
    if not news_data:
        return "<p class='muted'>No news data available</p>"

    general = news_data.get("general", [])
    per_ticker = news_data.get("per_ticker", {})
    gen_ts = news_data.get("generated_at_tw", "")

    def article_html(a):
        src = a.get("source", "")
        pub = a.get("published", "")
        link = a.get("link", "#")
        title = a.get("title", "")
        return f'''<div class="article">
          <a href="{link}" target="_blank" rel="noopener">{title}</a>
          <div class="article-meta"><span class="src-badge">{src}</span>{f' <span class="muted">{pub}</span>' if pub else ''}</div>
        </div>'''

    html = ""

    # General market
    if general:
        html += '<div class="news-section"><div class="section-label">🌍 General Market</div>'
        for a in general[:8]:
            html += article_html(a)
        html += "</div>"

    # Per-ticker
    for ticker, articles in per_ticker.items():
        if not articles:
            continue
        html += f'<div class="news-section"><div class="section-label">📰 {ticker}</div>'
        for a in articles[:6]:
            html += article_html(a)
        html += "</div>"

    return html


def render_llm_log(llm_log):
    if not llm_log:
        return "<p class='muted'>No LLM supervision history yet.</p>"
    html = ""
    for entry in reversed(llm_log[-5:]):
        ts = entry.get("ts_utc", "")
        phase = entry.get("phase", "")
        note = entry.get("note", "").replace("\n", "<br>")
        conflicts = entry.get("conflicts", [])
        suspicious = entry.get("suspicious_tickers", [])

        conflict_html = ""
        if conflicts:
            conflict_html = "<div class='conflict-list'>"
            for c in conflicts:
                conflict_html += f'<span class="conflict-badge">⚠️ {c["ticker"]}</span> '
            conflict_html += "</div>"

        hall_html = ""
        if suspicious:
            hall_html = f'<div class="hall-warn">🔍 Hallucination check flagged: {", ".join(suspicious)}</div>'

        html += f'''
        <div class="llm-entry">
          <div class="llm-meta">{ts} &nbsp;·&nbsp; {phase}</div>
          {conflict_html}
          <div class="llm-note">{note}</div>
          {hall_html}
        </div>'''
    return html


def _css():
    return """
:root {
  --bg: #0f1117;
  --bg2: #161b27;
  --bg3: #1e2535;
  --border: #2a3347;
  --text: #e2e8f0;
  --muted: #64748b;
  --accent: #00d4aa;
  --accent2: #0ea5e9;
  --amber: #f59e0b;
  --red: #ef4444;
  --green: #22c55e;
  --pos: #22c55e;
  --neg: #ef4444;
  --warn: #f59e0b;
  --pill-r: 4px;
}
[data-theme="light"] {
  --bg: #f8fafc; --bg2: #ffffff; --bg3: #f1f5f9;
  --border: #e2e8f0; --text: #0f172a; --muted: #64748b;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 17px; }
body {
  font-family: 'Inter', system-ui, sans-serif;
  background: var(--bg); color: var(--text);
  min-height: 100vh; padding-bottom: 80px;
}
a { color: var(--accent2); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Header ── */
#header {
  background: var(--bg2); border-bottom: 1px solid var(--border);
  padding: 12px 20px; position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.header-title { font-weight: 700; font-size: 1.2rem; color: var(--accent); letter-spacing: -.02em; }
.phase-badge {
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: 20px; padding: 3px 10px; font-size: 1.05rem;
  color: var(--muted); display: flex; align-items: center; gap: 6px;
}
.phase-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.header-time { font-size: .88rem; color: var(--muted); margin-left: auto; }
.theme-btn {
  background: var(--bg3); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); padding: 4px 8px; cursor: pointer; font-size: .88rem;
}

/* ── Tabs ── */
#tabs { display: flex; background: var(--bg2); border-bottom: 1px solid var(--border); overflow-x: auto; }
.tab-btn {
  padding: 12px 20px; font-size: 1.05rem; font-weight: 500; color: var(--muted);
  border: none; background: none; cursor: pointer; white-space: nowrap;
  border-bottom: 2px solid transparent; transition: all .2s;
}
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-btn:hover { color: var(--text); }

/* ── Content ── */
.tab-pane { display: none; padding: 20px; max-width: 1200px; margin: 0 auto; }
.tab-pane.active { display: block; }

/* ── Two-column layout ── */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 768px) { .two-col { grid-template-columns: 1fr; } }

/* ── Cards ── */
.card {
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px; margin-bottom: 14px;
}
.card.tl-strong  { border-left: 3px solid var(--green); }
.card.tl-moderate { border-left: 3px solid var(--amber); }
.card.tl-weak    { border-left: 3px solid var(--red); }

/* ── Card internals ── */
.card-header { margin-bottom: 10px; }
.card-title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }
.ticker { font-size: 1.4rem; font-weight: 700; letter-spacing: -.02em; }
.tl-badge {
  font-size: .92rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; text-transform: uppercase;
}
.tl-badge.tl-strong  { background: rgba(34,197,94,.15); color: var(--green); }
.tl-badge.tl-moderate { background: rgba(245,158,11,.15); color: var(--amber); }
.tl-badge.tl-weak    { background: rgba(239,68,68,.15); color: var(--red); }
.card-price-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.price { font-size: 1.2rem; font-weight: 600; }
.chg { font-weight: 600; font-size: 1.0rem; }
.pos { color: var(--green); }
.neg { color: var(--red); }
.sector-tag { font-size: .88rem; color: var(--muted); background: var(--bg3); border-radius: 4px; padding: 2px 6px; }
.card-name { font-size: .90rem; color: var(--muted); margin-bottom: 4px; }
.range-row { font-size: .90rem; color: var(--muted); margin-top: 4px; }

/* ── Score bar ── */
.score-bar-wrap { display: flex; align-items: center; gap: 8px; margin: 10px 0; }
.score-bar-track { flex: 1; background: var(--bg3); border-radius: 4px; height: 6px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 4px; transition: width .5s; }
.score-bar-fill.tl-strong  { background: var(--green); }
.score-bar-fill.tl-moderate { background: var(--amber); }
.score-bar-fill.tl-weak    { background: var(--red); }
.score-label { font-size: .88rem; color: var(--muted); min-width: 32px; text-align: right; }

/* ── Factor pills ── */
.factor-pills { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.pill { font-size: .88rem; font-weight: 600; padding: 2px 7px; border-radius: var(--pill-r); text-transform: uppercase; }
.pill.fg { background: rgba(34,197,94,.15); color: var(--green); }
.pill.fy { background: rgba(245,158,11,.15); color: var(--amber); }
.pill.fr { background: rgba(239,68,68,.12); color: var(--red); }

/* ── Card meta row ── */
.card-meta { display: flex; flex-wrap: wrap; gap: 8px 14px; font-size: .88rem; color: var(--muted); }
.card-meta strong { color: var(--text); }

/* ── Sector bars ── */
.sector-bars { display: flex; flex-direction: column; gap: 6px; }
.sector-row { display: flex; align-items: center; gap: 8px; }
.sector-name { font-size: .88rem; color: var(--muted); min-width: 110px; }
.bar-track { flex: 1; background: var(--bg3); border-radius: 3px; height: 8px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 3px; min-width: 2px; }
.bar-fill.pos { background: var(--green); }
.bar-fill.neg { background: var(--red); }
.sector-chg { font-size: .88rem; font-weight: 600; min-width: 52px; text-align: right; }

/* ── Signals ── */
.signals-wrap { display: flex; flex-direction: column; gap: 4px; margin: 10px 0; }
.signal { font-size: .90rem; padding: 4px 8px; border-radius: 6px; }
.sig-crit  { background: rgba(239,68,68,.18); color: #fca5a5; }
.sig-warn  { background: rgba(245,158,11,.15); color: #fcd34d; }
.sig-neg   { background: rgba(239,68,68,.1);  color: #f87171; }
.sig-pos   { background: rgba(34,197,94,.1);  color: var(--green); }
.sig-opp   { background: rgba(0,212,170,.12); color: var(--accent); }
.sig-caut  { background: rgba(245,158,11,.1); color: var(--amber); }

/* ── Technical row ── */
.tech-row { display: flex; gap: 12px; margin: 8px 0; flex-wrap: wrap; }
.tech-item { background: var(--bg3); border-radius: 8px; padding: 8px 12px; min-width: 80px; }
.tech-label { font-size: .88rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.tech-val { font-size: 1.05rem; font-weight: 600; margin-top: 2px; }
.rsi-ob { color: var(--red); }
.rsi-os { color: var(--green); }
.warn { color: var(--amber); }

/* ── MA pills ── */
.ma-pills { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0; }
.ma-pill { font-size: 1.05rem; padding: 2px 8px; border-radius: 4px; font-weight: 500; }
.ma-pill.pos { background: rgba(34,197,94,.1); color: var(--green); }
.ma-pill.neg { background: rgba(239,68,68,.1); color: var(--red); }

/* ── Fundamentals grid ── */
.fund-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 4px; margin: 10px 0; }
.fund-row { background: var(--bg3); border-radius: 6px; padding: 5px 8px; font-size: 1.05rem; display: flex; justify-content: space-between; align-items: center; }
.fund-row span { color: var(--muted); }
.fund-row strong { color: var(--text); }

/* ── Options section ── */
.opts-section { background: var(--bg3); border-radius: 8px; padding: 10px 12px; margin: 8px 0; }
.opts-row { display: flex; gap: 16px; flex-wrap: wrap; font-size: .90rem; margin-top: 4px; }
.opts-row strong { color: var(--accent2); }
.csp-row { font-size: .88rem; color: var(--muted); margin-top: 4px; }

/* ── Earnings badges ── */
.earn-badge { font-size: 1.05rem; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.earn-urgent { background: rgba(239,68,68,.2); color: #fca5a5; }
.earn-soon   { background: rgba(245,158,11,.15); color: var(--amber); }

/* ── News section ── */
.news-section { background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }
.section-label { font-size: .88rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 10px; }
.article { padding: 7px 0; border-bottom: 1px solid var(--border); }
.article:last-child { border-bottom: none; }
.article a { font-size: 1.05rem; color: var(--text); font-weight: 500; }
.article a:hover { color: var(--accent2); }
.article-meta { display: flex; align-items: center; gap: 6px; margin-top: 3px; }
.src-badge { font-size: .88rem; background: var(--bg3); color: var(--muted); padding: 1px 6px; border-radius: 3px; }

/* ── LLM panel ── */
.llm-panel { background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 14px; }
.llm-entry { border-bottom: 1px solid var(--border); padding: 10px 0; }
.llm-entry:last-child { border-bottom: none; }
.llm-meta { font-size: 1.05rem; color: var(--muted); margin-bottom: 6px; }
.llm-note { font-size: .92rem; color: var(--text); line-height: 1.6; }
.conflict-list { margin-bottom: 6px; }
.conflict-badge { font-size: 1.05rem; background: rgba(245,158,11,.15); color: var(--amber); padding: 2px 6px; border-radius: 4px; margin-right: 4px; }
.hall-warn { font-size: 1.05rem; color: var(--red); background: rgba(239,68,68,.08); border-radius: 4px; padding: 4px 8px; margin-top: 4px; }

/* ── Sentiment strip ── */
.sentiment-strip { display: flex; border-radius: 8px; overflow: hidden; height: 24px; margin: 12px 0; }
.sent-seg { display: flex; align-items: center; justify-content: center; font-size: 1.05rem; font-weight: 600; transition: width .4s; }
.sent-g { background: rgba(34,197,94,.25); color: var(--green); }
.sent-y { background: rgba(245,158,11,.25); color: var(--amber); }
.sent-r { background: rgba(239,68,68,.18); color: var(--red); }

/* ── Misc ── */
.muted { color: var(--muted); font-size: .92rem; }
.section-title { font-size: 1.1rem; font-weight: 600; margin: 20px 0 10px; }
.updated-note { font-size: 1.05rem; color: var(--muted); margin-bottom: 14px; }
.run-mode-tag { font-size: .92rem; background: var(--bg3); color: var(--muted); padding: 2px 8px; border-radius: 4px; }

/* ── Mobile bottom nav ── */
@media (max-width: 640px) {
  #tabs { display: none; }
  #bottom-nav { display: flex; }
  .tab-pane { padding: 14px; }
}
#bottom-nav {
  display: none; position: fixed; bottom: 0; left: 0; right: 0;
  background: var(--bg2); border-top: 1px solid var(--border);
  z-index: 200;
}
.bnav-btn {
  flex: 1; padding: 10px 4px; font-size: 1.05rem; color: var(--muted);
  border: none; background: none; cursor: pointer; text-align: center; font-weight: 500;
}
.bnav-btn.active { color: var(--accent); }
"""


def build(
    screener_data,
    monitor_data,
    news_data,
    llm_note,
    llm_log,
    output_path: Path,
    run_mode: str = "full",
):
    now_utc = datetime.now(timezone.utc)
    now_tw  = now_utc.astimezone(TAIWAN_TZ)
    ts_utc  = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    ts_tw   = now_tw.strftime("%Y-%m-%d %H:%M TW")

    # ── Phase & header ──
    phase = (screener_data or {}).get("phase", "Unknown")
    run_time = (screener_data or {}).get("run_time", ts_utc)
    max_score = (screener_data or {}).get("max_score", 17)

    # ── Screener tab content ──
    screener_html = ""
    if screener_data:
        sent = screener_data.get("sentiment", {})
        gp = sent.get("green", 0)
        yp = sent.get("yellow", 0)
        rp = sent.get("red", 0)
        top_sector = screener_data.get("top_sector", "—")
        screener_html += f'''
        <div class="updated-note">Run: {run_time} &nbsp;·&nbsp; {screener_data.get("all_results_count",0)} stocks scored &nbsp;·&nbsp; Top sector: <strong style="color:var(--accent)">{top_sector}</strong></div>
        <div class="sentiment-strip">
          <div class="sent-seg sent-g" style="width:{gp}%">{gp:.0f}% Strong</div>
          <div class="sent-seg sent-y" style="width:{yp}%">{yp:.0f}%</div>
          <div class="sent-seg sent-r" style="width:{rp}%">{rp:.0f}%</div>
        </div>
        <div class="two-col">
          <div>
            <div class="section-title">Top Picks</div>
            {''.join(render_screener_card(r, max_score) for r in screener_data.get("top_picks", []))}
          </div>
          <div>
            <div class="section-title">Sector Performance</div>
            <div class="card">{render_sector_bars(screener_data.get("sector_data", {}))}</div>
            <div class="section-title">LLM Supervision</div>
            <div class="llm-panel">
              <div class="llm-note">{(llm_note or "Not available").replace(chr(10), "<br>")}</div>
            </div>
          </div>
        </div>'''
    else:
        screener_html = "<p class='muted'>Screener data not available.</p>"

    # ── Monitor tab content ──
    monitor_html = ""
    if monitor_data and monitor_data.get("stocks"):
        monitor_html += f'<div class="updated-note">Updated: {monitor_data.get("generated_at_tw","—")}</div>'
        monitor_html += '<div class="two-col">'
        # Split into two columns
        stocks = monitor_data["stocks"]
        mid = (len(stocks) + 1) // 2
        monitor_html += "<div>" + "".join(render_monitor_card(s) for s in stocks[:mid]) + "</div>"
        monitor_html += "<div>" + "".join(render_monitor_card(s) for s in stocks[mid:]) + "</div>"
        monitor_html += "</div>"
    else:
        monitor_html = "<p class='muted'>Monitor data not available for this run phase. Last data shown on next full run.</p>"

    # ── News tab content ──
    all_watch_tickers = list((monitor_data or {}).get("stocks", []))
    news_html = ""
    if news_data:
        news_html += f'<div class="updated-note">Updated: {news_data.get("generated_at_tw","—")}</div>'
        news_html += render_news_section(news_data)
    else:
        news_html = "<p class='muted'>News not fetched in this run phase.</p>"

    # ── LLM History tab ──
    llm_history_html = f'''
    <div class="section-title">LLM Supervision Log (last {min(5, len(llm_log))} runs)</div>
    <div class="llm-panel">{render_llm_log(llm_log)}</div>'''

    # ── Full HTML ──
    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Hub — {ts_tw}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{_css()}</style>
</head>
<body>

<div id="header">
  <div class="header-title">📈 Stock Hub</div>
  <div class="phase-badge"><div class="phase-dot"></div>{phase}</div>
  <span class="run-mode-tag">{run_mode.upper()}</span>
  <div class="header-time" id="live-clock">{ts_tw} &nbsp;|&nbsp; {ts_utc}</div>
  <button class="theme-btn" onclick="toggleTheme()">☀ / ☾</button>
</div>

<div id="tabs">
  <button class="tab-btn active" onclick="showTab('screener',this)">📊 Screener</button>
  <button class="tab-btn" onclick="showTab('monitor',this)">👁 Monitor</button>
  <button class="tab-btn" onclick="showTab('news',this)">📰 News</button>
  <button class="tab-btn" onclick="showTab('llm',this)">🤖 LLM Log</button>
</div>

<div id="screener" class="tab-pane active">{screener_html}</div>
<div id="monitor"  class="tab-pane">{monitor_html}</div>
<div id="news"     class="tab-pane">{news_html}</div>
<div id="llm"      class="tab-pane">{llm_history_html}</div>

<nav id="bottom-nav">
  <button class="bnav-btn active" onclick="showTab('screener',this)">📊<br>Screener</button>
  <button class="bnav-btn" onclick="showTab('monitor',this)">👁<br>Monitor</button>
  <button class="bnav-btn" onclick="showTab('news',this)">📰<br>News</button>
  <button class="bnav-btn" onclick="showTab('llm',this)">🤖<br>LLM</button>
</nav>

<script>
function showTab(id, btn) {{
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn, .bnav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
  // sync both nav bars
  const idx = ['screener','monitor','news','llm'].indexOf(id);
  const allBtns = [...document.querySelectorAll('.tab-btn'), ...document.querySelectorAll('.bnav-btn')];
  allBtns.forEach(b => {{ if(b.textContent.includes(btn.textContent.trim().split('\\n')[0].trim().slice(-6,-1)||'NOPE')) b.classList.add('active'); }});
}}

function toggleTheme() {{
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', html.dataset.theme);
}}

// Restore theme
const saved = localStorage.getItem('theme');
if(saved) document.documentElement.dataset.theme = saved;

// Live clock
function updateClock() {{
  const now = new Date();
  const tw = now.toLocaleString('en-US', {{timeZone:'Asia/Taipei', hour:'2-digit', minute:'2-digit', hour12:false, month:'short', day:'numeric'}});
  const et = now.toLocaleString('en-US', {{timeZone:'America/New_York', hour:'2-digit', minute:'2-digit', hour12:false}});
  document.getElementById('live-clock').textContent = tw + ' TW  |  ' + et + ' ET';
}}
updateClock();
setInterval(updateClock, 30000);
</script>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    size_kb = output_path.stat().st_size // 1024
    print(f"  HTML written: {output_path} ({size_kb} KB)")
