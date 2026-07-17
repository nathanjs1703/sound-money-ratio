from sound_money_core import BASE_PRESENTATION
from sound_money_core import align_and_compute_ratio
from sound_money_core import compute_windows
from sound_money_core import calculate_success_rate
from sound_money_core import amend_ratio_with_profitability
import pytest
import pandas as pd


########################### BASE_PRESENTATION test ############################


def test_base_presentation_structure():
    for base in ("gold", "bitcoin"):
        labels = BASE_PRESENTATION[base]
        assert set(labels) == {"held_asset", "numerator", "denominator", "unit"}


######################## align_and_compute_ratio tests ########################


def test_align_and_compute_ratio_wrong_type():

    with pytest.raises(TypeError, match="btc_df and gold_df must be pandas DataFrames"):
        align_and_compute_ratio("bitcoin", "gold")


def test_align_and_compute_ratio_invalid_base():

    dates_btc = pd.date_range(start="2014-09-17", periods=3, freq="D")
    dates_gold = pd.date_range(start="2014-09-17", periods=3, freq="D")
    btc_df = pd.DataFrame({"price": [100, 200, 150]}, index=dates_btc)
    gold_df = pd.DataFrame({"price": [10, 20, 25]}, index=dates_gold)

    with pytest.raises(ValueError, match="gold"):
        align_and_compute_ratio(btc_df, gold_df, base="silver")


def test_align_and_compute_ratio_general():

    dates_btc = pd.date_range(start="2014-09-17", periods=10, freq="D")
    dates_gold = pd.date_range(start="2014-09-07", periods=15, freq="B")
    btc_df = pd.DataFrame(
        {"price": [100, 200, 150, 300, 240, 200, 375, 325, 600, 500]},
        index=dates_btc,
    )
    gold_df = pd.DataFrame(
        {"price": [10, 20, 25, 50, 25, 30, 20, 40, 50, 30, 40, 60, 65, 52, 32]},
        index=dates_gold,
    )
    btc_df = btc_df.drop(index=pd.Timestamp("2014-09-25"))

    expected_gold = [2.5, 4.0, 5.0, 10.0, 8.0, 5.0, 6.25, 5.0, 6.25, 15.625]

    assert len(align_and_compute_ratio(btc_df, gold_df)) == 10
    assert align_and_compute_ratio(btc_df, gold_df).columns.tolist() == [
        "price_btc",
        "price_gold",
        "ratio",
    ]
    assert (
        align_and_compute_ratio(btc_df, gold_df, base="gold")["ratio"].tolist()
        == expected_gold
    )
    # defaulted base must route to gold
    assert align_and_compute_ratio(btc_df, gold_df)["ratio"].tolist() == expected_gold


def test_align_and_compute_ratio_bitcoin_base():

    dates_btc = pd.date_range(start="2014-09-17", periods=10, freq="D")
    dates_gold = pd.date_range(start="2014-09-07", periods=15, freq="B")
    btc_df = pd.DataFrame(
        {"price": [100, 200, 150, 300, 240, 200, 375, 325, 600, 500]},
        index=dates_btc,
    )
    gold_df = pd.DataFrame(
        {"price": [10, 20, 25, 50, 25, 30, 20, 40, 50, 30, 40, 60, 65, 52, 32]},
        index=dates_gold,
    )
    btc_df = btc_df.drop(index=pd.Timestamp("2014-09-25"))

    result = align_and_compute_ratio(btc_df, gold_df, base="bitcoin")["ratio"].tolist()
    assert result == [0.4, 0.25, 0.2, 0.1, 0.125, 0.2, 0.16, 0.2, 0.16, 0.064]


############################ compute_windows tests ############################


def test_compute_windows_columns():

    dates = pd.date_range(start="2014-09-17", periods=5, freq="D")
    ratio_df = pd.DataFrame({"ratio": [1.0, 2.0, 1.5, 3.0, 2.5]}, index=dates)
    assert compute_windows(ratio_df, 1).columns.tolist() == [
        "entry_date",
        "entry_ratio",
        "exit_date",
        "exit_ratio",
        "profitable",
    ]


def test_compute_windows_profitability():

    dates = pd.date_range(start="2014-09-17", periods=5, freq="D")
    ratio_df = pd.DataFrame({"ratio": [1.0, 2.0, 1.5, 3.0, 2.5]}, index=dates)
    assert compute_windows(ratio_df, 1)["profitable"].tolist() == [
        True,
        False,
        True,
        False,
    ]


def test_compute_windows_invalid_period():

    dates = pd.date_range(start="2014-09-17", periods=5, freq="D")
    ratio_df = pd.DataFrame({"ratio": [1.0, 2.0, 1.5, 3.0, 2.5]}, index=dates)
    with pytest.raises(ValueError):
        compute_windows(ratio_df, 0)
    with pytest.raises(ValueError):
        compute_windows(ratio_df, len(ratio_df) - 1)
    with pytest.raises(ValueError):
        compute_windows(ratio_df, len(ratio_df))


def test_compute_windows_lengths():

    dates = pd.date_range(start="2014-09-17", periods=5, freq="D")
    ratio_df = pd.DataFrame({"ratio": [1.0, 2.0, 1.5, 3.0, 2.5]}, index=dates)
    assert len(compute_windows(ratio_df, 1)) == 4
    assert len(compute_windows(ratio_df, 2)) == 3
    assert len(compute_windows(ratio_df, 3)) == 2
    assert len(compute_windows(ratio_df, len(ratio_df) - 2)) == 2


@pytest.mark.parametrize(
    "holding_period, expected",
    [
        (1, [True, False, False, False, True, False]),
        (2, [True, False, False, True, True]),
        (3, [True, False, True, True]),
        (4, [True, True, False]),
        (5, [True, False]),
    ],
)
def test_compute_windows_characterization(holding_period, expected):
    dates = pd.date_range(start="2014-09-17", periods=7, freq="D")
    ratio_df = pd.DataFrame(
        {"ratio": [1.0, 2.0, 2.0, 1.5, 1.5, 3.0, 2.0]},
        index=dates,
    )

    result = compute_windows(ratio_df, holding_period)

    assert result["profitable"].tolist() == expected


######################## calculate_success_rate tests #########################


def test_calculate_success_rate_small_dataframe():

    assert (
        calculate_success_rate(pd.DataFrame({"profitable": [True, True, True, True]}))
        == 1.00
    )
    assert (
        calculate_success_rate(pd.DataFrame({"profitable": [True, False, True, True]}))
        == 0.75
    )
    assert (
        calculate_success_rate(pd.DataFrame({"profitable": [False, True, False, True]}))
        == 0.50
    )
    assert (
        calculate_success_rate(pd.DataFrame({"profitable": [True, True, False, False]}))
        == 0.50
    )
    assert (
        calculate_success_rate(
            pd.DataFrame({"profitable": [False, False, True, False]})
        )
        == 0.25
    )
    assert (
        calculate_success_rate(
            pd.DataFrame({"profitable": [False, False, False, False]})
        )
        == 0.00
    )


def test_calculate_success_rate_empty():

    empty_df = pd.DataFrame({"profitable": []})

    with pytest.raises(ValueError):
        calculate_success_rate(empty_df)


#################### amend_ratio_with_profitability tests #####################


def test_amend_ratio_with_profitability():

    dates_ratio = pd.date_range(start="2014-09-17", periods=5, freq="D")
    ratio_df = pd.DataFrame({"ratio": [1.0, 2.0, 1.5, 3.0, 2.5]}, index=dates_ratio)
    dates_windows = pd.date_range(start="2014-09-17", periods=3, freq="D")
    # exit_date and exit_ratio are placeholders; this function doesn't use them
    windows_df = pd.DataFrame(
        {
            "entry_date": dates_windows,
            "entry_ratio": [1.0, 2.0, 1.5],
            "exit_date": [0, 0, 0],
            "exit_ratio": [0, 0, 0],
            "profitable": [True, False, True],
        }
    )
    result = amend_ratio_with_profitability(ratio_df, windows_df)

    assert result.columns.tolist() == ["ratio", "profitable"]
    assert result.index.tolist() == dates_ratio[:3].tolist()
    assert result["profitable"].tolist() == [True, False, True]


###############################################################################
