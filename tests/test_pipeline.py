"""Pipeline sanity tests. Run against the committed panels, so CI does not need
the 1.8 GB of raw parquet."""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from common import ROOT, load_config, month_range
import did

CFG = load_config()
TREAT = pd.Timestamp(CFG["study"]["treatment_date"])


def test_month_range():
    assert month_range("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]


def test_crz_zones_are_38_manhattan():
    crz = pd.read_csv(ROOT / "data" / "crz_zones.csv")
    treated = crz[crz["in_crz"]]
    assert len(treated) == 38
    assert (treated["Borough"] == "Manhattan").all()
    # Empirically derived: CRZ pickup zones almost always incur the CBD fee.
    assert treated["frac_fee"].min() > 0.90
    # A few well-known CRZ zones must be present.
    for z in ["Midtown Center", "SoHo", "Financial District North", "West Village"]:
        assert z in set(treated["Zone"])


def test_dest_panel_structure():
    d = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    assert set(d["unit"]) == {"cbd_bound", "man_control"}
    assert (d["trips"] > 0).all()
    # Two groups x daily -> roughly balanced row counts.
    counts = d["unit"].value_counts()
    assert abs(counts["cbd_bound"] - counts["man_control"]) <= 2


def test_headline_is_finite_and_small():
    d = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    r = did.headline_did(d, TREAT)
    assert math.isfinite(r["coef"]) and math.isfinite(r["se"])
    # The honest finding: no large demand response (taxis pay only a small toll).
    assert abs(r["pct_change"]) < 15


def test_toll_is_positive_post_period():
    d = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    r = did.toll_descriptive(d, TREAT)
    assert 0.3 < r["avg_cbd_fee_cbd_bound"] < 3.0  # ~$0.75 statutory taxi toll


def test_event_study_baseline_and_shape():
    d = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    es = did.event_study(d, TREAT, ref=-1)
    base = es[es["event_month"] == -1]
    assert len(base) == 1 and base["coef"].iloc[0] == 0.0
    assert es["event_month"].is_monotonic_increasing
    assert es["coef"].abs().max() < 1.0  # no numerical blow-ups


def test_parallel_trends_runs():
    d = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    r = did.parallel_trends_test(d, TREAT)
    assert 0.0 <= r["pvalue"] <= 1.0
