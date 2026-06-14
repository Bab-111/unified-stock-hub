"""
main.py — Unified Stock Hub orchestrator.
Reads RUN_MODE env var to decide which modules to run.
  RUN_MODE=full     -> all three modules (pre-market + close)
  RUN_MODE=screener -> screener only (market hours)
  RUN_MODE=partial  -> screener + news (after-hours)
"""
import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_DIR  = ROOT / "config"
OUTPUT_DIR  = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Add scripts dir to path
sys.path.insert(0, str(ROOT / "scripts"))

import module_screener
import module_monitor
import module_news
import llm_supervisor
import build_report


def load_config():
    with open(CONFIG_DIR / "config.json") as f:
        return json.load(f)


def load_watchlist():
    with open(CONFIG_DIR / "watchlist.json") as f:
        data = json.load(f)
    return data.get("tickers", [])


def load_existing_data():
    """Load previously generated module data to preserve non-run modules."""
    data_file = OUTPUT_DIR / "last_run_data.json"
    if data_file.exists():
        try:
            return json.loads(data_file.read_text())
        except Exception:
            pass
    return {}


def save_run_data(data):
    """Persist module outputs so partial runs can merge with last full run."""
    data_file = OUTPUT_DIR / "last_run_data.json"
    # Remove news per_ticker to keep file size small
    slim = {k: v for k, v in data.items() if k != "news"}
    if "news" in data:
        slim["news"] = {
            "general": data["news"].get("general", []),
            "generated_at_utc": data["news"].get("generated_at_utc", ""),
            "generated_at_tw": data["news"].get("generated_at_tw", ""),
        }
    data_file.write_text(json.dumps(slim, indent=2, default=str))


def main():
    run_mode = os.environ.get("RUN_MODE", "full").lower()
    print(f"\n{'='*50}")
    print(f"Unified Stock Hub — RUN_MODE={run_mode}")
    print(f"{'='*50}")

    cfg = load_config()
    tickers = load_watchlist()
    universe_file = str(CONFIG_DIR / cfg.get("universe", "universe.csv"))

    # Load previous run data for modules we're skipping this run
    existing = load_existing_data()
    run_data = dict(existing)  # start with existing, overwrite what we run

    # ── Run modules based on mode ─────────────────────────────────────
    screener_data = None
    monitor_data  = None
    news_data     = None

    # Screener: always runs
    print("\n[1/3] Running screener...")
    screener_data = module_screener.run(universe_file, cfg)
    run_data["screener"] = screener_data

    # Monitor: full mode only
    if run_mode == "full":
        print("\n[2/3] Running monitor...")
        monitor_data = module_monitor.run(tickers, cfg)
        run_data["monitor"] = monitor_data
    else:
        print("\n[2/3] Monitor skipped (using cached data)")
        monitor_data = existing.get("monitor")

    # News: full or partial mode
    if run_mode in ("full", "partial"):
        print("\n[3/3] Running news...")
        all_tickers = list(set(tickers))
        # Also add screener top picks to news fetch
        if screener_data:
            for r in screener_data.get("top_picks", []):
                t = r.get("symbol", "")
                if t and t not in all_tickers:
                    all_tickers.append(t)
        news_data = module_news.run(all_tickers, cfg)
        run_data["news"] = news_data
    else:
        print("\n[3/3] News skipped (using cached data)")
        news_data = existing.get("news")

    # ── LLM supervision ───────────────────────────────────────────────
    print("\n[LLM] Running supervisor...")
    # Only call LLM when screener has fresh data (always) and at least one other module ran
    llm_note = llm_supervisor.run(
        screener_data, monitor_data, news_data, cfg, OUTPUT_DIR
    )
    print(f"  LLM: {str(llm_note)[:80]}...")
    run_data["llm_note"] = llm_note

    # ── Persist run data ──────────────────────────────────────────────
    save_run_data(run_data)

    # ── Build HTML report ─────────────────────────────────────────────
    print("\n[Build] Generating HTML report...")
    llm_log = []
    llm_log_file = OUTPUT_DIR / "llm_log.json"
    if llm_log_file.exists():
        try:
            llm_log = json.loads(llm_log_file.read_text())
        except Exception:
            pass

    build_report.build(
        screener_data=screener_data,
        monitor_data=monitor_data,
        news_data=news_data,
        llm_note=llm_note,
        llm_log=llm_log,
        output_path=OUTPUT_DIR / "index.html",
        run_mode=run_mode,
    )

    print(f"\n✓ Done. Report: {OUTPUT_DIR / 'index.html'}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
