import numpy as np
import pandas as pd

from gridsense import config, io
from gridsense.models import tune_classify
from gridsense.models.classify import LowPriceClassifier
from gridsense.splits import assign_split


def test_weight_last_year_grows_as_half_life_shrinks(tiny_training_table):
    tr = tiny_training_table[assign_split(tiny_training_table["target_ts_utc"]) == "train"]
    shares = [tune_classify._weight_last_year(tr, h) for h in (None, 365.0, 90.0)]
    assert shares == sorted(shares)
    assert shares[-1] > 0.9  # with a 90-day half-life almost all weight is on the last year


def test_candidates_parse_per_step():
    assert tune_classify.parse_candidate("365") == (365.0, 365.0)
    assert tune_classify.parse_candidate("730/90") == (730.0, 90.0)
    assert tune_classify.parse_candidate("none/90") == (None, 90.0)
    assert tune_classify.candidate_name((730.0, 90.0)) == "730/90"
    assert tune_classify.candidate_name((None, None)) == "none"


def test_step_half_life_only_changes_its_step(tiny_training_table):
    split = assign_split(tiny_training_table["target_ts_utc"])
    tr, val = tiny_training_table[split == "train"], tiny_training_table[split == "val"]
    same = LowPriceClassifier(half_life_days=365.0).fit(tr, val)
    split_hl = LowPriceClassifier(
        half_life_days=365.0, step_half_lives={"p_cheap_given_near_zero": 30.0}
    ).fit(tr, val)

    assert split_hl.half_life("p_near_zero") == 365.0
    assert split_hl.half_life("p_cheap_given_near_zero") == 30.0
    a, b = same.predict(val), split_hl.predict(val)
    assert np.allclose(a["p_near_zero"], b["p_near_zero"])  # step 1 untouched
    assert not np.allclose(a["p_cheap"], b["p_cheap"])
    assert (b["p_cheap"] <= b["p_near_zero"]).all()


def test_sweep_writes_one_row_per_candidate(tiny_training_table, tmp_dirs):
    io.write(tiny_training_table, "training_table")
    tune_classify.main(["--half-lives", "180", "none/90"])

    out = pd.read_csv(config.REPORTS_DIR / "eval" / "classify_half_life_val.csv")
    # 2 candidates x raw/calibrated x 2 labels
    assert len(out) == 2 * 2 * 2
    assert set(out["half_life_days"].astype(str)) == {"180", "none/90"}
    assert out["pr_auc"].between(0, 1).all()

    by_month = pd.read_csv(config.REPORTS_DIR / "eval" / "classify_half_life_by_month_val.csv")
    assert set(by_month["month"]) <= set(range(3, 10))  # validation months only
