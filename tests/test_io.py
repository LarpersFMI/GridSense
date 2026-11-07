import pandas as pd
import pytest

from gridsense import io


def test_check_columns_rejects_missing():
    with pytest.raises(ValueError, match="price_min"):
        io.check_columns(pd.DataFrame(columns=["ts_utc", "price_mean", "price_max"]), "prices_hourly")
