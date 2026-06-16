"""
main.py — Unified Stock Hub orchestrator.
Reads RUN_MODE env var to decide which modules to run.
  RUN_MODE=full     -> all three modules (pre-market + close)
  RUN_MODE=screener -> screener only (market hours)
  RUN_MODE=partial  -> screener + news (after-hours)

Cache strategy: monitor + news data saved to cache/ folder in repo,
committed back after each run so it persists across GitHub Actions runs.
"""
import os
import json
import sys
from pathlib import Path

ROOT       = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
CACHE_DIR  = ROOT / "cache"   # committed to repo — survives between runs

OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

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
        return json.load(f).get("tickers", [])


def load_cache(key):
    """Load cached module data from repo cache/ folder."""
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            print(f"  [Cache] Loaded {key} from cache ({cache_file.stat().st_size // 1024}KB)")
            return data
        except Exception as e:
            print(f"  [Cache] Failed to load {key}: {e}")
    else:
        print(f"  [Cache] No cache found for {key}")
    return None


def save_cache(key, data):
    """Save module data to repo cache/ folder so next run can use it."""
    cache_file = CACHE_DIR / f"{key}.json"
    try:
        # For news: save general + metadata only (skip per_ticker to keep size small)
        if key == "news" and data:
            slim = {
                "general":          data.get("general", []),
                "per_ticker":       data.get("per_ticker", {}),
                "generated_at_utc": data.get("generated_at_utc", ""),
                "generated_at_tw":  data.get("generated_at_tw", ""),
            }
            cache_file.write_text(json.dumps(slim, indent=2, default=str))
        else:
            cache_file.write_text(json.dumps(data, indent=2, default=str))
        print(f"  [Cache] Saved {key} ({cache_file.stat().st_size // 1024}KB)")
    except Exception as e:
        print(f"  [Cache] Failed to save {key}: {e}")


def main():
    run_mode = os.environ.get("RUN_MODE", "full").lower()
    print(f"\n{'='*50}")
    print(f"Unified Stock Hub — RUN_MODE={run_mode}")
    print(f"{'='*50}")

    cfg           = load_config()
    tickers       = load_watchlist()
    universe_file = str(CONFIG_DIR / cfg.get("universe", "universe.csv"))

    # ── Run modules ───────────────────────────────────────────────────
    screener_data = None
    monitor_data  = None
    news_data     = None

    # Screener: always runs
    print("\n[1/3] Running screener...")
    screener_data = module_screener.run(universe_file, cfg)

    # Monitor: full mode only — otherwise load from cache
    if run_mode == "full":
        print("\n[2/3] Running monitor...")
        monitor_data = module_monitor.run(tickers, cfg)
        save_cache("monitor", monitor_data)
    else:
        print("\n[2/3] Monitor skipped — loading cached data...")
        monitor_data = load_cache("monitor")

    # News: full or partial — otherwise load from cache
    if run_mode in ("full", "partial"):
        print("\n[3/3] Running news...")
        all_tickers = list(set(tickers))
        if screener_data:
            for r in screener_data.get("top_picks", []):
                t = r.get("symbol", "")
                if t and t not in all_tickers:
                    all_tickers.append(t)
        news_data = module_news.run(all_tickers, cfg)
        save_cache("news", news_data)
    else:
        print("\n[3/3] News skipped — loading cached data...")
        news_data = load_cache("news")

    # ── LLM supervision ───────────────────────────────────────────────
    print("\n[LLM] Running supervisor...")
    llm_note = llm_supervisor.run(
        screener_data, monitor_data, news_data, cfg, OUTPUT_DIR
    )
    print(f"  LLM: {str(llm_note)[:80]}...")

    # ── Build HTML ────────────────────────────────────────────────────
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
