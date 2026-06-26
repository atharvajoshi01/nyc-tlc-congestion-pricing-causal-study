"""Figures (PNG, for the README/notebook) and Tableau Public export files.

Figures -> figures/:   event_study.png, trends.png, permutation.png
Tableau  -> data/:     tableau_export.csv (daily series), tableau_zone_map.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import ROOT, load_config
from geo import build_centroids

FIG = ROOT / "figures"
RESULTS = ROOT / "results"
TREAT = "2025-01-05"


def fig_event_study() -> None:
    es = pd.read_csv(RESULTS / "event_study.csv")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.axhline(0, color="#888", lw=1)
    ax.axvline(-0.5, color="#c0392b", ls="--", lw=1.4, label="Congestion pricing (Jan 5 2025)")
    ax.errorbar(es.event_month, es.pct,
                yerr=[es.pct - es.ci_low, es.ci_high - es.pct],
                fmt="o", ms=4, color="#2c3e50", ecolor="#95a5a6", capsize=2)
    ax.set_xlabel("Months relative to rollout")
    ax.set_ylabel("Effect on CBD-bound trips (%)")
    ax.set_title("Event study: no systematic change in taxi demand into the CRZ")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "event_study.png", dpi=130)
    plt.close(fig)


def fig_trends(dest: pd.DataFrame) -> None:
    dest["trip_date"] = pd.to_datetime(dest["trip_date"])
    m = (dest.assign(ym=dest.trip_date.dt.to_period("M").dt.to_timestamp())
             .groupby(["ym", "unit"]).trips.sum().unstack())
    base = m.loc[m.index < TREAT].mean()
    idx = m / base * 100  # index to pre-period average = 100
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(idx.index, idx["cbd_bound"], color="#2c3e50", lw=2, label="CBD-bound (treated)")
    ax.plot(idx.index, idx["man_control"], color="#16a085", lw=2,
            label="Manhattan control")
    ax.axvline(pd.Timestamp(TREAT), color="#c0392b", ls="--", lw=1.4)
    ax.set_ylabel("Monthly trips (pre-period avg = 100)")
    ax.set_title("CBD-bound and control demand move together through rollout")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "trends.png", dpi=130)
    plt.close(fig)


def fig_permutation() -> None:
    f = RESULTS / "permutation_null.csv"
    if not f.exists():
        return
    null = pd.read_csv(f)["null_coef"] * 100
    res = pd.read_json(RESULTS / "did_results.json", typ="series")
    actual = res["zone_fe_manhattan"]["pct_change"]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.hist(null, bins=30, color="#bdc3c7", edgecolor="white")
    ax.axvline(actual, color="#c0392b", lw=2,
               label=f"Actual estimate ({actual:+.1f}%)")
    ax.set_xlabel("DiD coefficient under random zone assignment (%)")
    ax.set_ylabel("Frequency")
    ax.set_title("Permutation null: the real effect is typical of random noise")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "permutation.png", dpi=130)
    plt.close(fig)


def tableau_exports(cfg: dict, dest: pd.DataFrame, zone: pd.DataFrame) -> None:
    # 1) Daily time series (long) for the trend chart + DiD panel.
    ts = dest.copy()
    ts["trip_date"] = pd.to_datetime(ts["trip_date"])
    ts["group"] = ts["unit"].map({"cbd_bound": "CBD-bound (treated)",
                                  "man_control": "Manhattan control"})
    ts["period"] = np.where(ts["trip_date"] < pd.Timestamp(TREAT), "Pre", "Post")
    ts[["trip_date", "group", "period", "trips", "avg_fare", "avg_cbd_fee"]] \
        .to_csv(ROOT / "data" / "tableau_export.csv", index=False)

    # 2) Zone map layer: pre/post daily trips + % change + centroid + CRZ flag.
    zone["trip_date"] = pd.to_datetime(zone["trip_date"])
    zone["period"] = np.where(zone["trip_date"] < pd.Timestamp(TREAT), "pre", "post")
    daily = (zone.groupby(["unit", "period"])
                 .agg(trips=("trips", "sum"),
                      days=("trip_date", "nunique"),
                      fee=("avg_cbd_fee", "mean")).reset_index())
    daily["trips_per_day"] = daily["trips"] / daily["days"]
    wide = daily.pivot(index="unit", columns="period",
                       values="trips_per_day").reset_index()
    wide["LocationID"] = wide["unit"].astype(int)
    wide["pct_change"] = (wide["post"] / wide["pre"] - 1) * 100
    crz = pd.read_csv(ROOT / cfg["crz"]["derived_file"])
    cent = build_centroids(cfg)
    mp = (crz.merge(cent, on="LocationID", how="left")
             .merge(wide[["LocationID", "pre", "post", "pct_change"]],
                    on="LocationID", how="left"))
    mp = mp[["LocationID", "Zone", "Borough", "in_crz", "lon", "lat",
             "pre", "post", "pct_change"]].rename(
        columns={"pre": "trips_per_day_pre", "post": "trips_per_day_post"})
    mp.to_csv(ROOT / "data" / "tableau_zone_map.csv", index=False)


def main() -> None:
    cfg = load_config()
    FIG.mkdir(exist_ok=True)
    dest = pd.read_csv(ROOT / "data" / "panel_dest_day.csv")
    zone = pd.read_csv(ROOT / "data" / "panel_zone_day.csv")
    fig_event_study()
    fig_trends(dest)
    fig_permutation()
    tableau_exports(cfg, dest, zone)
    print("Wrote figures/event_study.png, figures/trends.png, figures/permutation.png")
    print("Wrote data/tableau_export.csv, data/tableau_zone_map.csv")


if __name__ == "__main__":
    main()
