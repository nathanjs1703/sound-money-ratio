"""Publish aligned price data and test fixtures for the web app.

Fetches current prices via yfinance, runs the shared core's alignment,
and writes two files into web/:

  data.json: the dense daily price series the browser loads on page open.
      Dates, price_btc, price_gold. The ratio is NOT included because it
      depends on the chosen base, so the browser computes it per-request.

  fixtures.json: Python-computed success rates at a spread of holding
      periods and both bases. The CI parity test asserts that the JS
      analytical functions reproduce these exactly before any deploy.

This script imports sound_money_core (the shared analytical core) and
fetch_price_data (the CLI's data-fetching function) without modification.
"""

import json
import sys
from pathlib import Path

# repo root and cli/ need to be importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cli"))

from sound_money_core import (
    align_and_compute_ratio,
    calculate_success_rate,
    compute_windows,
)
from project import fetch_price_data

OUTPUT_DIR = Path(__file__).resolve().parent

# spread of periods that covers short, medium, and long holds plus edge cases
FIXTURE_PERIODS = [1, 7, 30, 90, 180, 365, 730, 1095, 1825]


def main() -> None:
    btc = fetch_price_data("bitcoin")
    gold = fetch_price_data("gold")

    # alignment is base-independent: price_btc and price_gold columns are
    # identical regardless of which base is passed. only the ratio column
    # differs, and we deliberately do not ship that.
    aligned = align_and_compute_ratio(btc, gold, base="gold")

    # --- data.json ---
    data = {
        "dates": [d.strftime("%Y-%m-%d") for d in aligned.index],
        "price_btc": aligned["price_btc"].tolist(),
        "price_gold": aligned["price_gold"].tolist(),
    }

    data_path = OUTPUT_DIR / "data.json"
    with open(data_path, "w") as f:
        json.dump(data, f)
    print(f"Wrote {data_path} ({len(data['dates'])} rows)")

    # --- fixtures.json ---
    max_period = len(aligned) - 2
    fixtures = []
    for base in ("gold", "bitcoin"):
        ratio_df = align_and_compute_ratio(btc, gold, base=base)
        for period in FIXTURE_PERIODS:
            if period >= max_period:
                continue
            windows = compute_windows(ratio_df, period)
            rate = calculate_success_rate(windows)
            fixtures.append(
                {
                    "base": base,
                    "period": period,
                    "rate": round(rate, 10),
                }
            )

    fixtures_path = OUTPUT_DIR / "fixtures.json"
    with open(fixtures_path, "w") as f:
        json.dump(
            {"fixtures": fixtures, "row_count": len(data["dates"])},
            f,
            indent=2,
        )
    print(f"Wrote {fixtures_path} ({len(fixtures)} fixtures)")


if __name__ == "__main__":
    main()
