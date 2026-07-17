import argparse
import sys
import time
import webbrowser
from pathlib import Path

# the shared core lives one directory up (repo root); make it importable when
# this CLI is run directly, e.g. `python3 project.py`, from any working dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

from sound_money_core import (
    BASE_PRESENTATION,
    DEFAULT_BASE,
    align_and_compute_ratio,
    amend_ratio_with_profitability,
    calculate_success_rate,
    compute_windows,
)

CACHE_DIR = Path("cache")
CACHE_MAX_AGE_IN_DAYS = 7
DEFAULT_HOLDING_PERIOD_IN_DAYS = 180
OUTPUT_CHART_FILE = Path("btc-gold-chart.html")


def fetch_price_data(asset_name: str) -> pd.DataFrame:
    """Get daily price data for BTC or gold, using a local CSV cache.

    Avoids repeated API calls by reading from cache when the cached file is
    fresher than CACHE_MAX_AGE_IN_DAYS. Network failures from yfinance
    propagate uncaught.

    Args:
        asset_name: Either "bitcoin" or "gold".

    Returns:
        DataFrame indexed by date (DatetimeIndex) with a single column
        "price" (float, USD).

    Raises:
        KeyError: If asset_name is not "bitcoin" or "gold".
    """

    asset_dict = {
        "bitcoin": {"ticker": "BTC-USD", "cache_file": "bitcoin_prices.csv"},
        "gold": {"ticker": "GC=F", "cache_file": "gold_prices.csv"},
    }

    ticker = asset_dict[asset_name]["ticker"]
    cache_file = asset_dict[asset_name]["cache_file"]

    cache_path = CACHE_DIR / cache_file

    if cache_path.exists():
        # is the file fresh enough?
        fresh = (
            (time.time() - cache_path.stat().st_mtime) / 86400
        ) <= CACHE_MAX_AGE_IN_DAYS
        if fresh:
            return pd.read_csv(cache_path, index_col="Date", parse_dates=True)

    asset_raw = yf.download(ticker, period="max")
    asset_close = asset_raw["Close"][ticker]
    asset_df = pd.DataFrame(asset_close)
    asset_df = asset_df.rename(columns={ticker: "price"})

    # save to cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    asset_df.to_csv(cache_path)
    return asset_df


def generate_chart(
    ratio_df: pd.DataFrame,
    output_path: Path,
    holding_period_days: int,
    success_rate: float,
    base: str,
) -> None:
    """Render the ratio time series as a color-coded chart and save as HTML.

    Windows are filled green (profitable) or red (not profitable). Titles and
    axis labels are composed from BASE_PRESENTATION so that every surface
    describes the same base asset.

    Args:
        ratio_df: Ratio DataFrame from amend_ratio_with_profitability.
        output_path: Relative path where the HTML file is written.
        holding_period_days: Holding period used for the analysis.
        success_rate: Fraction from calculate_success_rate.
        base: The asset you start and end in: "gold" or "bitcoin".

    Returns:
        None. The chart is written to output_path as a side effect.
    """

    ratio_df = ratio_df.copy()

    # mark a new segment each time the profitable value flips
    ratio_df["segment"] = (
        ratio_df["profitable"] != ratio_df["profitable"].shift()
    ).cumsum()

    fig = go.Figure()

    # iterate fill color by segment
    for _, segment_df in ratio_df.groupby("segment"):
        color = (
            "rgba(0, 255, 0, 0.5)"
            if segment_df["profitable"].iloc[0]
            else "rgba(255, 0, 0, 0.5)"
        )
        fig.add_trace(
            go.Scatter(
                x=segment_df.index,
                y=segment_df["ratio"],
                mode="lines",
                fill="tozeroy",
                fillcolor=color,
                line=dict(color=color),
                showlegend=False,
            )
        )

    labels = BASE_PRESENTATION[base]
    ratio_name = f"{labels['numerator']}/{labels['denominator']}"

    fig.update_layout(
        title=(
            f"{ratio_name} Ratio — Holding Period: {holding_period_days} days, "
            f"Historical Success Rate: {success_rate:.1%}"
        ),
        xaxis_title="Date",
        yaxis_title=f"{ratio_name} Ratio ({labels['unit']})",
    )

    fig.write_html(output_path)


def main() -> None:
    """Orchestrate the flow from CLI arguments to rendered chart.

    Parses arguments, resolves defaults, fetches both price series, computes
    the ratio in the chosen base asset, classifies windows, calculates the
    success rate, renders the chart, and reports the result.
    """

    parser = argparse.ArgumentParser(
        description="Analyze Bitcoin/Gold holding period profitability"
    )
    parser.add_argument(
        "--base",
        default=None,
        choices=["gold", "bitcoin"],
        help=f"Asset to measure from: gold or bitcoin (default: {DEFAULT_BASE})",
    )
    parser.add_argument(
        "holding_period",
        nargs="?",
        default=None,
        type=int,
        help="Number of days to hold the bought and held "
        "asset before converting back to base asset "
        f"(default: {DEFAULT_HOLDING_PERIOD_IN_DAYS})",
    )

    args = parser.parse_args()

    # handle no base argument with sentinel
    if args.base is None:
        print(f"No base asset specified, using default of {DEFAULT_BASE}")
        base = DEFAULT_BASE
    else:
        base = args.base

    # handle no argument with sentinel
    if args.holding_period is None:
        print(
            "No holding period specified, using default of "
            f"{DEFAULT_HOLDING_PERIOD_IN_DAYS} days"
        )
        holding_period_days = DEFAULT_HOLDING_PERIOD_IN_DAYS
    else:
        holding_period_days = args.holding_period

    try:
        btc = fetch_price_data("bitcoin")
        gold = fetch_price_data("gold")
        ratio_df = align_and_compute_ratio(btc, gold, base=base)
        windows_df = compute_windows(
            ratio_df,
            holding_period_days=holding_period_days,
        )
        success_rate = calculate_success_rate(windows_df)
        amended_ratio = amend_ratio_with_profitability(ratio_df, windows_df)
        generate_chart(
            amended_ratio,
            output_path=OUTPUT_CHART_FILE,
            holding_period_days=holding_period_days,
            success_rate=success_rate,
            base=base,
        )

        labels = BASE_PRESENTATION[base]

        print(
            f"\n\nHolding {labels['held_asset']} for {holding_period_days} days was "
            f"profitable in {base} in {success_rate:.1%} of historical windows.\n\n"
        )
        print(f"Chart saved to {OUTPUT_CHART_FILE}")

        print("Attempting to open chart in your browser...")
        webbrowser.open(OUTPUT_CHART_FILE.resolve().as_uri())

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
