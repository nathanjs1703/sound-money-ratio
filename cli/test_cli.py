from project import fetch_price_data
import pytest


############################ fetch_price_data test ############################


def test_fetch_price_data_invalid_asset():

    with pytest.raises(KeyError):
        fetch_price_data("dollar")
