"""Robustness checks for the DiD estimate.

  * placebo_dates       -- fake treatment dates inside the pre-period; a credible
                           design returns ~0 effect (there was no policy yet).
  * permutation_test    -- randomly reassign which Manhattan zones are "treated"
                           (keeping the count fixed) and rebuild the null
                           distribution of the DiD coefficient -> a design-based
                           p-value that does not rely on parametric SEs.
  * alternate_controls  -- re-estimate with different control groups (adjacent
                           Manhattan vs contaminated outer-borough) to show the
                           result is not an artifact of one control choice.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import ROOT, load_config
from did import headline_did, zone_fe_did, _prep

RESULTS = ROOT / "results"
RNG = np.random.default_rng(20250105)  # fixed seed -> reproducible


def placebo_dates(dest: pd.DataFrame, treat_date: pd.Timestamp,
                  fake_dates: list[str]) -> list[dict]:
    pre = dest.copy()
    pre["trip_date"] = pd.to_datetime(pre["trip_date"])
    pre = pre[pre["trip_date"] < treat_date]
    out = []
    for fd in fake_dates:
        r = headline_did(pre, pd.Timestamp(fd))
        out.append({"placebo_date": fd, "pct_change": r["pct_change"],
                    "pvalue": r["pvalue"]})
    return out


def permutation_test(zone: pd.DataFrame, treat_date: pd.Timestamp,
                     n_draws: int = 500) -> dict:
    df = _prep(zone.dropna(subset=["borough"]), treat_date)
    df = df[df["borough"] == "Manhattan"]
    nmonths = df["cal_month"].nunique()
    g = df.groupby("unit").agg(m=("cal_month", "nunique"), t=("trips", "sum"),
                               treated=("treated", "first"))
    keep = g[(g["m"] == nmonths) & (g["t"] >= 50 * nmonths)].index
    df = df[df["unit"].isin(keep)]
    units = df[["unit", "treated"]].drop_duplicates()
    n_treated = int(units["treated"].sum())
    all_units = units["unit"].tolist()

    def did_coef(assign: dict) -> float:
        d = df.copy()
        d["tr"] = d["unit"].map(assign).astype(int)
        m = smf.wls("log_trips ~ C(unit) + C(cal_month) + C(dow) + tr:post",
                    data=d, weights=d["trips"]).fit()
        return float(m.params["tr:post"])

    actual = did_coef(dict(zip(units["unit"], units["treated"])))
    null = np.empty(n_draws)
    for i in range(n_draws):
        chosen = set(RNG.choice(all_units, size=n_treated, replace=False))
        null[i] = did_coef({u: (u in chosen) for u in all_units})
    p = float((np.abs(null) >= abs(actual)).mean())
    pd.DataFrame({"null_coef": null}).to_csv(
        RESULTS / "permutation_null.csv", index=False)
    return {"spec": "permutation_zone_assignment", "actual_coef": actual,
            "actual_pct": float(np.expm1(actual) * 100), "n_draws": n_draws,
            "null_mean_pct": float(np.expm1(null.mean()) * 100),
            "null_sd": float(null.std()), "perm_pvalue": p}


def alternate_controls(zone: pd.DataFrame, treat_date: pd.Timestamp) -> list[dict]:
    out = []
    for mo, label in [(True, "adjacent_manhattan"), (False, "all_nyc_outer")]:
        r = zone_fe_did(zone, treat_date, manhattan_only=mo)
        out.append({"control_def": label, "pct_change": r["pct_change"],
                    "pvalue": r["pvalue"], "n_zones": r["n_zones"]})
    return out


def main() -> None:
    cfg = load_config()
    td = pd.Timestamp(cfg["study"]["treatment_date"])
    dest = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    zone = pd.read_csv(ROOT / "data" / "panel_zone_day.csv")
    RESULTS.mkdir(exist_ok=True)

    out = {
        "placebo_dates": placebo_dates(dest, td,
                                       ["2024-05-01", "2024-07-01", "2024-09-01"]),
        "alternate_controls": alternate_controls(zone, td),
        "permutation_test": permutation_test(zone, td, n_draws=500),
    }
    (RESULTS / "robustness.json").write_text(json.dumps(out, indent=2))
    print("Placebo (pre-period, expect ~0):")
    for p in out["placebo_dates"]:
        print(f"  {p['placebo_date']}: {p['pct_change']:+.1f}%  p={p['pvalue']:.3f}")
    print("Alternate controls:")
    for a in out["alternate_controls"]:
        print(f"  {a['control_def']}: {a['pct_change']:+.1f}%  p={a['pvalue']:.3f}")
    pt = out["permutation_test"]
    print(f"Permutation: actual {pt['actual_pct']:+.1f}%, null mean "
          f"{pt['null_mean_pct']:+.2f}%, perm p={pt['perm_pvalue']:.3f}")


if __name__ == "__main__":
    main()
