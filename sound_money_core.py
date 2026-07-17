"""Shared analytical core for the Sound Money Ratio project.

Pure, side-effect-free analysis functions and the presentation facts they
imply. Both front doors (the CLI and the web app) are thin callers on top of
this module; neither the core nor its tests import anything caller-specific.

`base` flows through every function as a plain string ("gold" or "bitcoin"),
exactly as `holding_period_days` flows as a plain int, so any caller drives the
same neutral core without a rewrite.
"""

import pandas as pd

DEFAULT_BASE = "gold"
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
