import argparse
import sys
import time
import webbrowser
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

CACHE_DIR = Path("cache")
CACHE_MAX_AGE_IN_DAYS = 3
DEFAULT_HOLDING_PERIOD_IN_DAYS = 180
OUTPUT_CHART_FILE = Path("btc-gold-chart.html")


def fetch_price_data(asset_name: str) -> pd.DataFrame:
    """
    Get daily price data for BTC or Gold, using a local CSV cache to avoid
    repeated API calls, fresh up to the CACHE_MAX_AGE_IN_DAYS

    :param asset_name: "bitcoin" or "gold"
    :type asset_name: str
    :raise KeyError: If asset_name is not "bitcoin" or "gold"
    :return: A pandas DataFrame indexed by date (Datetimeindex), with a single
        column "price" (float, USD)
    :rtype: pd.DataFrame
    """

    asset_dict = {
        "bitcoin": {"ticker": "BTC-USD", "cache_file": "bitcoin_prices.csv"},
        "gold": {"ticker": "GC=F", "cache_file": "gold_prices.csv"},
    }

    ticker = asset_dict[asset_name]["ticker"]
    cache_file = asset_dict[asset_name]["cache_file"]

    # construct the full path to the cache file
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
    btc_df: pd.DataFrame, gold_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Outer-join the two price series on the dateindex of each DataFrame; reindex
    to a continuous daily range. Forward-filling is done with epistemic
    conservatism. When the gold market is closed (weekends) or the data
    provider has a gap (occasional missing days), the last known price is used
    rather than interpolated or backfilled. This makes sure the downstream
    window analysis is done with a price that existed at the time. Finally, it
    computes the BTC/Gold ratio

    :param btc_df: Bitcoin DataFrame
    :type btc_df: pd.DataFrame
    :param gold_df: Gold DataFrame
    :type gold_df: pd.DataFrame
    :raise TypeError: btc_df or gold_df is not a DataFrame
    :return: A pandas DataFrame indexed by every calendar day from the first
        BTC trading day to the most recent available date with columns
        "price_btc", "price_gold", "ratio"
    :rtype: pd.DataFrame
    """

    # guard against non-DataFrame input
    if not isinstance(btc_df, pd.DataFrame) or not isinstance(gold_df, pd.DataFrame):
        raise TypeError("btc_df and gold_df must be pandas DataFrames")

    # to join data sets
    combined = btc_df.join(gold_df, how="outer", lsuffix="_btc", rsuffix="_gold")

    # to fill missing rows from data provider
    full_range = pd.date_range(
        start=combined.index.min(), end=combined.index.max(), freq="D"
    )
    combined = combined.reindex(full_range)

    combined = combined.ffill()

    # drop leading rows where bitcoin has no data yet
    combined = combined.dropna(subset=["price_btc"])

    # compute ratio
    combined["ratio"] = combined["price_btc"] / combined["price_gold"]

    return combined


def compute_windows(ratio_df: pd.DataFrame, holding_period_days: int) -> pd.DataFrame:
    """
    Generate every valid holding-period window from the ratio time series and
    classify each as profitable or not

    :param ratio_df: Ratio DataFrame from align_and_compute_ratio
    :type ratio_df: pd.DataFrame
    :param holding_period_days: Number of days between hypothetical entry into
        BTC and exit back to gold
    :type holding_period_days: int
    :raise ValueError: If holding_period_days is less than or equal to zero or
        greater than or equal to len(ratio_df) - 1
    :return: A DataFrame with one row per valid window. Columns: entry_date,
        entry_ratio, exit_date, exit_ratio, profitable (bool)
    :rtype: pd.DataFrame
    """

    # filtering holding_period_days too small or too large
    if holding_period_days <= 0:
        raise ValueError("Holding period (in days) must be greater than 0.")

    if holding_period_days >= (len(ratio_df) - 1):
        raise ValueError(
            f"Holding period (in days) must be less than {len(ratio_df) - 1}."
        )

    # accumulate results in list of dicts to build windows DataFrame
    windows = []

    for entry_date, row in ratio_df.iterrows():
        exit_date = entry_date + pd.Timedelta(days=holding_period_days)
        if exit_date in ratio_df.index:
            entry_ratio = row["ratio"]
            exit_ratio = ratio_df.loc[exit_date, "ratio"]
            profitable = exit_ratio > entry_ratio

            windows.append(
                {
                    "entry_date": entry_date,
                    "entry_ratio": entry_ratio,
                    "exit_date": exit_date,
                    "exit_ratio": exit_ratio,
                    "profitable": profitable,
                }
            )

    return pd.DataFrame(windows)


def calculate_success_rate(windows_df: pd.DataFrame) -> float:
    """
    Compute the fraction of windows in which BTC outperformed Gold

    :param windows_df: Windows DataFrame from compute_windows
    :type windows_df: pd.DataFrame
    :raise ValueError: If windows_df is empty
    :return: A float between 0.0 and 1.0 representing the fraction of windows
        that were profitable.
    :rtype: float
    """

    if windows_df.empty:
        raise ValueError("Empty DataFrame.")

    # mean of a bool column = fraction that are True
    return windows_df["profitable"].mean()


def amend_ratio_with_profitability(
    ratio_df: pd.DataFrame, windows_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Copy ratio_df and windows_df so as not to mutate; trim the current holding
    period window off the tail of ratio_df; re-index windows_df and add
    profitable column to ratio_df

    :param ratio_df: Ratio DataFrame from align_and_compute_ratio
    :type ratio_df: pd.DataFrame
    :param windows_df: Windows DataFrame from compute_windows
    :type windows_df: pd.DataFrame
    :return: A DataFrame with one row per valid window. Columns: ratio,
        profitable (bool)
    :rtype: pd.DataFrame
    """

    # create DataFrame copies to avoid mutation
    ratio_df = ratio_df.copy()
    windows_df = windows_df.copy()

    # trim window off tail of ratio_df
    last_entry_date = windows_df["entry_date"].max()
    ratio_df = ratio_df.loc[:last_entry_date]

    # index by entry_date so the subsequent column assignment aligns on date
    windows_df = windows_df.set_index("entry_date")

    # add "profitable" column of windows_df on to ratio_df
    # pandas aligns on the date index
    ratio_df["profitable"] = windows_df["profitable"]

    return ratio_df


def generate_chart(
    ratio_df: pd.DataFrame,
    output_path: Path,
    holding_period_days: int,
    success_rate: float,
) -> None:
    """
    Render the BTC/Gold ratio time series with windows color-coded green
    (profitable) or red (not profitable) and save as standalone HTML

    :param ratio_df: Ratio DataFrame from amend_ratio_with_profitability
    :type ratio_df: pd.DataFrame
    :param output_path: This is the relative path where the file
        should be saved
    :type output_path: Path
    :param holding_period_days: Number of holding period days enter
        at command line
    :type holding_period_days: int
    :param success_rate: fraction given by calculate_success_rate
    :type success_rate: float
    :return: Side effect, the file is written to disk
    :rtype: None
    """

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

    fig.update_layout(
        title=(
            f"BTC/Gold Ratio — Holding Period: {holding_period_days} days, "
            f"Historical Success Rate: {success_rate:.1%}"
        ),
        xaxis_title="Date",
        yaxis_title="BTC/Gold Ratio (oz)",
    )

    fig.write_html(output_path)


def main():
    """
    Orchestrate the flow: Parse command line arguments, call fetch_price_data
    twice, call align_and_compute_ratio, call compute_windows,
    call calculate_success_rate, call amend_ratio_with_profitability, call
    generate_chart, print success rate and path to chart
    """

    parser = argparse.ArgumentParser(
        description="Analyze Bitcoin/Gold holding period profitability"
    )
    parser.add_argument(
        "holding_period",
        nargs="?",
        default=None,
        type=int,
        help=f"Number of days to hold BTC before converting back to gold "
        f"(default: {DEFAULT_HOLDING_PERIOD_IN_DAYS})",
    )

    args = parser.parse_args()

    # handle no argument with sentinel
    if args.holding_period is None:
        print(
            f"No holding period specified, using default of "
            f"{DEFAULT_HOLDING_PERIOD_IN_DAYS} days"
        )
        holding_period_days = DEFAULT_HOLDING_PERIOD_IN_DAYS
    else:
        holding_period_days = args.holding_period

    try:
        btc = fetch_price_data("bitcoin")
        gold = fetch_price_data("gold")
        ratio_df = align_and_compute_ratio(btc, gold)
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
        )

        print(f"Historical Success Rate: {success_rate:.1%}")
        print(f"Chart saved to {OUTPUT_CHART_FILE}")

        print("Attempting to open chart in your browser...")
        webbrowser.open(OUTPUT_CHART_FILE.resolve().as_uri())

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
