"""Difference-in-differences estimation for the congestion-pricing study.

Design
------
Treated  = taxi trips whose dropoff is inside the Congestion Relief Zone
           ("CBD-bound" trips into the priced area).
Control  = trips whose dropoff is in Manhattan but north of 60th St (just outside
           the zone). Same service mix, same borough, adjacent geography -- a far
           cleaner counterfactual than outer-borough trips, whose taxi volumes
           follow very different secular trends.

Specifications
--------------
1. Headline DiD (log trips):  log(trips) ~ treated*post + C(dow) + C(month), HC1.
   The treated:post coefficient reads as an approximate % change in CBD-bound
   demand relative to the control.
2. Cost DiD (rider $ / trip): same form on total_amount; recovers the toll.
3. Event study: log(trips) ~ C(group) + C(cal_month) + C(dow)
                            + treated*1[event_month=k], baseline k=-1.
4. Parallel-trends test: pre-period treated*linear-trend interaction.
5. Zone fixed-effects DiD (robustness): zone-level, clustered by borough.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import ROOT, load_config

RESULTS = ROOT / "results"


def _prep(df: pd.DataFrame, treat_date: pd.Timestamp) -> pd.DataFrame:
    df = df.copy()
    df["trip_date"] = pd.to_datetime(df["trip_date"])
    df["log_trips"] = np.log(df["trips"])
    df["post"] = (df["trip_date"] >= treat_date).astype(int)
    df["treated"] = df["treated"].astype(int)
    df["dow"] = df["trip_date"].dt.dayofweek
    df["month"] = df["trip_date"].dt.month
    df["cal_month"] = df["trip_date"].dt.to_period("M").astype(str)
    return df


def _did_dict(m, term: str, spec: str, pct: bool = True) -> dict:
    b, se = float(m.params[term]), float(m.bse[term])
    out = {"spec": spec, "coef": b, "se": se, "pvalue": float(m.pvalues[term]),
           "n_obs": int(m.nobs)}
    if pct:
        out.update(pct_change=float(np.expm1(b) * 100),
                   ci_low_pct=float(np.expm1(b - 1.96 * se) * 100),
                   ci_high_pct=float(np.expm1(b + 1.96 * se) * 100))
    else:
        out.update(usd=b, ci_low=b - 1.96 * se, ci_high=b + 1.96 * se)
    return out


def headline_did(dest: pd.DataFrame, treat_date: pd.Timestamp) -> dict:
    df = _prep(dest, treat_date)
    m = smf.ols("log_trips ~ treated * post + C(dow) + C(month)", data=df).fit(
        cov_type="HC1")
    return _did_dict(m, "treated:post", "headline_cbd_bound_vs_manhattan")


def cost_did(dest: pd.DataFrame, treat_date: pd.Timestamp) -> dict:
    df = _prep(dest, treat_date)
    m = smf.ols("avg_fare ~ treated * post + C(dow) + C(month)", data=df).fit(
        cov_type="HC1")
    return _did_dict(m, "treated:post", "cost_per_trip_usd", pct=False)


def toll_descriptive(dest: pd.DataFrame, treat_date: pd.Timestamp) -> dict:
    df = _prep(dest, treat_date)
    post_cbd = df[(df.treated == 1) & (df.post == 1)]
    return {"spec": "avg_cbd_toll_post_period_usd",
            "avg_cbd_fee_cbd_bound": float(post_cbd["avg_cbd_fee"].mean())}


def event_study(dest: pd.DataFrame, treat_date: pd.Timestamp, ref: int = -1) -> pd.DataFrame:
    df = _prep(dest, treat_date)
    per = pd.PeriodIndex(df["cal_month"], freq="M")
    base = pd.Period(treat_date, freq="M")
    ev = (per.year - base.year) * 12 + (per.month - base.month)
    df["ev"] = ev.values
    # Build treated x event-time dummies explicitly, omitting the baseline `ref`
    # (patsy does not drop a reference level inside a numeric:categorical term,
    # which would leave it collinear with the group fixed effect).
    levels = [k for k in sorted(df["ev"].unique()) if k != ref]
    dcols = []
    for k in levels:
        col = f"d{k + 100:03d}"  # offset keeps names valid (no minus sign)
        df[col] = ((df["ev"] == k) & (df["treated"] == 1)).astype(int)
        dcols.append(col)
    rhs = " + ".join(dcols)
    m = smf.ols(f"log_trips ~ C(unit) + C(cal_month) + C(dow) + {rhs}",
                data=df).fit(cov_type="HC1")
    rows = [{"event_month": ref, "coef": 0.0, "se": 0.0}]
    for col, k in zip(dcols, levels):
        rows.append({"event_month": k, "coef": float(m.params[col]),
                     "se": float(m.bse[col])})
    out = pd.DataFrame(rows).sort_values("event_month").reset_index(drop=True)
    out["pct"] = np.expm1(out["coef"]) * 100
    out["ci_low"] = np.expm1(out["coef"] - 1.96 * out["se"]) * 100
    out["ci_high"] = np.expm1(out["coef"] + 1.96 * out["se"]) * 100
    return out


def parallel_trends_test(dest: pd.DataFrame, treat_date: pd.Timestamp) -> dict:
    df = _prep(dest, treat_date)
    pre = df[df["post"] == 0].copy()
    pre["t"] = (pre["trip_date"] - pre["trip_date"].min()).dt.days
    m = smf.ols("log_trips ~ treated * t + C(dow) + C(month)", data=pre).fit(
        cov_type="HC1")
    p = float(m.pvalues["treated:t"])
    return {"spec": "parallel_trends_preperiod",
            "interaction_coef_per_day": float(m.params["treated:t"]),
            "se": float(m.bse["treated:t"]), "pvalue": p,
            "passes_at_5pct": bool(p > 0.05)}


def zone_fe_did(zone: pd.DataFrame, treat_date: pd.Timestamp,
                manhattan_only: bool = True) -> dict:
    """Zone-level two-way FE DiD (zone + calendar-month + dow), clustered by
    borough. Manhattan-only by default (CRZ vs non-CRZ Manhattan pickup zones);
    set manhattan_only=False for the contaminated all-NYC version used to show
    sensitivity to control choice."""
    df = _prep(zone.dropna(subset=["borough"]), treat_date)
    if manhattan_only:
        df = df[df["borough"] == "Manhattan"]
    # Keep zones present every month with adequate volume (else FE design is singular).
    nmonths = df["cal_month"].nunique()
    g = df.groupby("unit").agg(m=("cal_month", "nunique"), t=("trips", "sum"))
    keep = g[(g["m"] == nmonths) & (g["t"] >= 50 * nmonths)].index
    df = df[df["unit"].isin(keep)]
    cluster = "unit" if manhattan_only else "borough"
    # Weight by trips so the estimate reflects the volume-representative effect,
    # consistent with the (count-based) headline rather than tiny-zone noise.
    m = smf.wls("log_trips ~ C(unit) + C(cal_month) + C(dow) + treated:post",
                data=df, weights=df["trips"]).fit(
        cov_type="cluster", cov_kwds={"groups": df[cluster]})
    d = _did_dict(m, "treated:post",
                  f"zone_twfe_{'manhattan' if manhattan_only else 'allnyc'}_"
                  f"cluster_{cluster}")
    d["n_zones"] = int(df["unit"].nunique())
    d["n_clusters"] = int(df[cluster].nunique())
    return d


def main() -> None:
    cfg = load_config()
    td = pd.Timestamp(cfg["study"]["treatment_date"])
    dest = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    zone = pd.read_csv(ROOT / "data" / "panel_zone_day.csv")
    RESULTS.mkdir(exist_ok=True)

    results = {
        "treatment_date": cfg["study"]["treatment_date"],
        "window": [str(pd.to_datetime(dest.trip_date).min().date()),
                   str(pd.to_datetime(dest.trip_date).max().date())],
        "headline": headline_did(dest, td),
        "cost": cost_did(dest, td),
        "toll": toll_descriptive(dest, td),
        "parallel_trends": parallel_trends_test(dest, td),
        "zone_fe_manhattan": zone_fe_did(zone, td, manhattan_only=True),
        "zone_fe_allnyc": zone_fe_did(zone, td, manhattan_only=False),
    }
    es = event_study(dest, td, cfg["model"]["event_reference"])
    es.to_csv(RESULTS / "event_study.csv", index=False)
    (RESULTS / "did_results.json").write_text(json.dumps(results, indent=2))

    h = results["headline"]
    print(f"HEADLINE (CBD-bound demand): {h['pct_change']:+.1f}%  "
          f"[95% CI {h['ci_low_pct']:+.1f}%, {h['ci_high_pct']:+.1f}%]  p={h['pvalue']:.3f}")
    print(f"COST per trip: ${results['cost']['usd']:+.2f}  "
          f"[{results['cost']['ci_low']:+.2f}, {results['cost']['ci_high']:+.2f}]  "
          f"p={results['cost']['pvalue']:.2e}")
    print(f"Avg CBD toll charged (post): ${results['toll']['avg_cbd_fee_cbd_bound']:.2f}")
    pt = results["parallel_trends"]
    print(f"Parallel trends pre-period p={pt['pvalue']:.3f} -> "
          f"{'PASS' if pt['passes_at_5pct'] else 'FLAG'}")
    print(f"Zone FE (Manhattan, cluster zone):  {results['zone_fe_manhattan']['pct_change']:+.1f}%"
          f"  p={results['zone_fe_manhattan']['pvalue']:.3f}")
    print(f"Zone FE (all-NYC, cluster borough): {results['zone_fe_allnyc']['pct_change']:+.1f}%"
          f"  p={results['zone_fe_allnyc']['pvalue']:.3f}  (contaminated control)")
    print(f"Event-study rows: {len(es)} -> results/event_study.csv")


if __name__ == "__main__":
    main()
