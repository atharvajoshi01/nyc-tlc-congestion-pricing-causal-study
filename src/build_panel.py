"""Build the daily DiD panels from local TLC parquet files.

Runs sql/02_daily_panel.sql over every (service, month) in the study window and
unions the results into two tidy panels written to data/:
  * panel_dest_day.csv  -- (date, cbd_bound/man_control) Manhattan-destination
                           grain; the headline + event-study comparison.
  * panel_zone_day.csv  -- (date, pickup zone) grain; zone fixed-effects spec.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import (ROOT, connect, load_config, month_range, parquet_path,
                    pickup_col, resolve_window)

SQL_TEMPLATE = (ROOT / "sql" / "02_daily_panel.sql").read_text()


def next_month_start(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    m += 1
    if m == 13:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}-01"


def has_column(con, parquet: Path, col: str) -> bool:
    cols = con.execute(f"DESCRIBE SELECT * FROM '{parquet}'").df()["column_name"]
    return col in set(cols)


def build(cfg: dict) -> pd.DataFrame:
    start, end = resolve_window(cfg)
    crz_csv = ROOT / cfg["crz"]["derived_file"]
    con = connect()
    frames = []
    for service in cfg["data"]["services"]:
        for ym in month_range(start, end):
            pq = parquet_path(cfg, service, ym)
            if not pq.exists() or pq.stat().st_size < 5_000:
                print(f"skip {service} {ym} (missing/empty)")
                continue
            # The CBD toll column only exists from 2025; inject 0 before that.
            fee_expr = ("cbd_congestion_fee"
                        if has_column(con, pq, "cbd_congestion_fee") else "0.0")
            sql = SQL_TEMPLATE.format(
                parquet=pq, service=service, pcol=pickup_col(service),
                month_start=f"{ym}-01", month_end=next_month_start(ym),
                crz_csv=crz_csv, cbd_fee_expr=fee_expr,
            )
            df = con.execute(sql).df()
            frames.append(df)
            print(f"ok   {service} {ym}: {len(df):>6} rows")
    panel = pd.concat(frames, ignore_index=True)
    panel["trip_date"] = pd.to_datetime(panel["trip_date"])
    return panel


def pool(panel: pd.DataFrame, grain: str) -> pd.DataFrame:
    """Pool services into one row per (date, unit, treated) with trip-weighted
    averages for the cost outcomes."""
    p = panel[panel.grain == grain].copy()
    p["fare_wsum"] = p["avg_fare"] * p["trips"]
    p["fee_wsum"] = p["avg_cbd_fee"] * p["trips"]
    agg = (p.groupby(["trip_date", "unit", "treated"], as_index=False)
             .agg(trips=("trips", "sum"),
                  fare_wsum=("fare_wsum", "sum"),
                  fee_wsum=("fee_wsum", "sum")))
    agg["avg_fare"] = agg["fare_wsum"] / agg["trips"]
    agg["avg_cbd_fee"] = agg["fee_wsum"] / agg["trips"]
    return agg.drop(columns=["fare_wsum", "fee_wsum"])


def main() -> None:
    cfg = load_config()
    panel = build(cfg)

    dest = pool(panel, "dest")
    zone = pool(panel, "zone")
    # Attach borough to zone rows (for clustering / Manhattan restriction).
    zones = pd.read_csv(ROOT / "data" / "taxi_zone_lookup.csv")[["LocationID", "Borough"]]
    zones["LocationID"] = zones["LocationID"].astype(str)
    zone = zone.merge(zones, left_on="unit", right_on="LocationID", how="left") \
               .drop(columns="LocationID").rename(columns={"Borough": "borough"})

    dest.to_csv(ROOT / "data" / "panel_dest_day.csv", index=False)
    zone.to_csv(ROOT / "data" / "panel_zone_day.csv", index=False)
    print(f"\ndest-day panel:  {len(dest):>6} rows -> data/panel_dest_day.csv "
          f"({dest.trip_date.min().date()} .. {dest.trip_date.max().date()})")
    print(f"zone-day panel:  {len(zone):>6} rows -> data/panel_zone_day.csv")


if __name__ == "__main__":
    main()
