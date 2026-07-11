import argparse
import sys
import time
import webbrowser
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

CACHE_DIR = Path("cache")
CACHE_MAX_AGE_IN_DAYS = 7
DEFAULT_BASE = "gold"
DEFAULT_HOLDING_PERIOD_IN_DAYS = 180
OUTPUT_CHART_FILE = Path("btc-gold-chart.html")
BASE_PRESENTATION = {
    "gold": {
        "held_asset": "bitcoin",
        "numerator": "BTC",
        "denominator": "Gold",
        "unit": "oz gold per BTC",
    },
    "bitcoin": {
        "held_asset": "gold",
        "numerator": "Gold",
        "denominator": "BTC",
        "unit": "BTC per oz gold",
    },
}


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


def align_and_compute_ratio(
    btc_df: pd.DataFrame, gold_df: pd.DataFrame, base: str = DEFAULT_BASE
) -> pd.DataFrame:
    """Align the two price series and compute the ratio in the chosen base.

    Outer-joins the two series on date, reindexes to a continuous daily range,
    and forward-fills gaps. Forward-filling is chosen for epistemic
    conservatism: when the gold market is closed (weekends) or the provider
    has a gap, the last known price is propagated rather than interpolated or
    backfilled, so the downstream window analysis only ever sees prices that
    actually existed at the time.

    The ratio is constructed directly from the two price series in whichever
    direction the chosen base implies. This is kept as the final step so a
    future supply-adjust transform can slot in ahead of it.

    Args:
        btc_df: Bitcoin prices, indexed by date.
        gold_df: Gold prices, indexed by date.
        base: The asset you start and end in: "gold" or "bitcoin". Selects the
            numerator and denominator of the ratio at construction.

    Returns:
        DataFrame indexed by every calendar day from the first BTC trading day
        to the most recent available date, with columns "price_btc",
        "price_gold", and "ratio".

    Raises:
        TypeError: If btc_df or gold_df is not a DataFrame.
        ValueError: If base is not "gold" or "bitcoin".
    """

    # guard against non-DataFrame input
    if not isinstance(btc_df, pd.DataFrame) or not isinstance(gold_df, pd.DataFrame):
        raise TypeError("btc_df and gold_df must be pandas DataFrames")

    combined = btc_df.join(gold_df, how="outer", lsuffix="_btc", rsuffix="_gold")

    # to fill missing rows from data provider
    full_range = pd.date_range(
        start=combined.index.min(), end=combined.index.max(), freq="D"
    )
    combined = combined.reindex(full_range)

    combined = combined.ffill()

    # drop leading rows where bitcoin has no data yet
    combined = combined.dropna(subset=["price_btc"])

    # compute ratio in the chosen base's direction
    if base == "gold":
        combined["ratio"] = combined["price_btc"] / combined["price_gold"]
    elif base == "bitcoin":
        combined["ratio"] = combined["price_gold"] / combined["price_btc"]
    else:
        raise ValueError(f'base must be "gold" or "bitcoin", got {base!r}')

    return combined


def compute_windows(ratio_df: pd.DataFrame, holding_period_days: int) -> pd.DataFrame:
    """Generate every valid holding-period window and classify profitability.

    Vectorized with a row-shift (.shift), which is equivalent to a calendar-day
    exit lookup only because ratio_df has a dense daily index — one row per
    calendar day, guaranteed upstream by align_and_compute_ratio's
    reindex + ffill.

    Profitability is base-agnostic: a window is profitable when the exit ratio
    exceeds the entry ratio, whichever asset is the base.

    Args:
        ratio_df: Ratio DataFrame from align_and_compute_ratio.
        holding_period_days: Days between hypothetical entry into the held
            asset and exit back to the base asset.

    Returns:
        DataFrame with one row per valid window. Columns: entry_date,
        entry_ratio, exit_date, exit_ratio, profitable (bool).

    Raises:
        ValueError: If holding_period_days is <= 0 or >= len(ratio_df) - 1.
    """

    # filtering holding_period_days too small or too large
    if holding_period_days <= 0:
        raise ValueError("Holding period (in days) must be greater than 0.")

    if holding_period_days >= (len(ratio_df) - 1):
        raise ValueError(
            f"Holding period (in days) must be less than {len(ratio_df) - 1}."
        )

    entry_ratio = ratio_df["ratio"]
    exit_ratio = ratio_df["ratio"].shift(-holding_period_days)

    windows = pd.DataFrame(
        {
            "entry_date": ratio_df.index,
            "entry_ratio": entry_ratio.values,
            "exit_date": ratio_df.index + pd.Timedelta(days=holding_period_days),
            "exit_ratio": exit_ratio.values,
            "profitable": (exit_ratio > entry_ratio).values,
        }
    )

    return windows.dropna(subset=["exit_ratio"]).reset_index(drop=True)


def calculate_success_rate(windows_df: pd.DataFrame) -> float:
    """Compute the fraction of windows where the held asset profited.

    Args:
        windows_df: Windows DataFrame from compute_windows.

    Returns:
        Fraction of windows that were profitable, between 0.0 and 1.0.

    Raises:
        ValueError: If windows_df is empty.
    """

    if windows_df.empty:
        raise ValueError("Empty DataFrame.")

    # mean of a bool column = fraction that are True
    return float(windows_df["profitable"].mean())


def amend_ratio_with_profitability(
    ratio_df: pd.DataFrame, windows_df: pd.DataFrame
) -> pd.DataFrame:
    """Attach per-window profitability back onto the ratio time series.

    Copies both inputs, trims the trailing holding-period window off ratio_df
    (those dates have no exit yet), and joins the profitable column on the
    date index.

    Args:
        ratio_df: Ratio DataFrame from align_and_compute_ratio.
        windows_df: Windows DataFrame from compute_windows.

    Returns:
        DataFrame indexed by date with columns "ratio" and "profitable" (bool).
    """

    # create DataFrame copies to avoid mutation
    ratio_df = ratio_df.copy()
    windows_df = windows_df.copy()

    last_entry_date = windows_df["entry_date"].max()
    ratio_df = ratio_df.loc[:last_entry_date]

    # index by entry_date so the subsequent column assignment aligns on date
    windows_df = windows_df.set_index("entry_date")

    ratio_df["profitable"] = windows_df["profitable"]

    return ratio_df


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
