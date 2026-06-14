# Unified Stock Hub — Build Plan & Progress Tracker
Last updated: Session 1 — COMPLETE

## Goal
Consolidate stock-news-bot, stock-monitor, stock-screener into one unified GitHub Actions repo.
Output: single responsive HTML file via GitHub Pages, accessible from any device.

## Architecture
- One workflow: unified-stock-monitor.yml (8 runs/day Mon-Fri)
- Three Python modules: module_screener.py, module_monitor.py, module_news.py
- One LLM supervisor: llm_supervisor.py (Haiku, ~280 tokens/full run)
- One HTML builder: build_report.py -> output/index.html (self-contained, no external runtime deps)
- Three-tab responsive UI: Screener | Monitor | News | LLM Log
- Taiwan timezone display throughout
- LLM audit log: output/llm_log.json (last 10 entries, hallucination check)
- Conflict detector: rule-based cross-module flag before LLM call
- Keepalive workflow to prevent GitHub disabling Actions

## Schedule (UTC, Mon-Fri)
- 13:00 -> ALL modules [full] (pre-market, 9:00 AM ET)
- 13:30 -> Screener only [screener]
- 14:30 -> Screener only [screener]
- 17:00 -> Screener only [screener]
- 19:00 -> Screener only [screener]
- 20:00 -> ALL modules [full] (close, 4:00 PM ET)
- 22:00 -> Screener + News [partial]
- 00:00 Tue-Sat -> Screener + News [partial]

## FILES STATUS — ALL COMPLETE
- [x] docs/BUILD_PLAN.md
- [x] config/config.json
- [x] config/watchlist.json
- [x] config/universe.csv
- [x] requirements.txt
- [x] scripts/module_news.py
- [x] scripts/module_monitor.py
- [x] scripts/module_screener.py
- [x] scripts/llm_supervisor.py
- [x] scripts/build_report.py
- [x] scripts/main.py
- [x] .github/workflows/unified-stock-monitor.yml
- [x] .github/workflows/keepalive.yml

## SETUP INSTRUCTIONS (for next session or user)
1. Create new GitHub repo: unified-stock-hub
2. Push all files from this archive
3. Enable GitHub Pages: Settings -> Pages -> Source: gh-pages branch
4. Add secret: Settings -> Secrets -> ANTHROPIC_API_KEY (optional, enables LLM)
5. Manually trigger workflow once: Actions -> Unified Stock Hub -> Run workflow
6. Access report at: https://[username].github.io/unified-stock-hub/

## TO CUSTOMIZE
- Add/remove watchlist tickers: config/watchlist.json -> tickers array
- Add/remove screener universe: config/universe.csv -> Symbol column
- Adjust screener thresholds: config/config.json
- Change schedule: .github/workflows/unified-stock-monitor.yml -> cron lines
