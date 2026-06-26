"""Derive the Congestion Relief Zone (CRZ) empirically from the data.

Rather than hand-listing taxi zones "south of 60th St", we exploit the
`cbd_congestion_fee` column that TLC added to trip records when the toll went
live (Jan 2025). The per-trip CBD toll applies to any taxi trip that touches the
CRZ, so a *pickup* zone where virtually every trip incurs the fee must itself be
inside the zone. Pickup zones outside the CRZ only get charged when the trip's
dropoff happens to fall inside, so their fee incidence is far lower. The gap
between the two groups is stark (~0.95+ vs ~0.5 and below), giving a clean,
reproducible boundary.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import ROOT, connect, load_config, parquet_path, pickup_col


def derive_crz(cfg: dict) -> pd.DataFrame:
    ref_month = cfg["crz"]["reference_month"]
    threshold = cfg["crz"]["fee_threshold"]
    service = "yellow"  # densest CRZ coverage; cleanest signal
    pq = parquet_path(cfg, service, ref_month)
    if not pq.exists():
        raise FileNotFoundError(
            f"Reference month parquet missing: {pq}. Run `make data` first."
        )

    lookup = ROOT / "data" / "taxi_zone_lookup.csv"
    pcol = pickup_col(service)
    con = connect()
    con.execute(f"CREATE TABLE zones AS SELECT * FROM read_csv_auto('{lookup}')")
    fee_by_zone = con.execute(f"""
        WITH t AS (
            SELECT PULocationID AS loc,
                   COUNT(*) AS trips,
                   AVG(CASE WHEN cbd_congestion_fee > 0 THEN 1.0 ELSE 0.0 END) AS frac_fee
            FROM read_parquet('{pq}')
            WHERE PULocationID IS NOT NULL
              AND {pcol} >= DATE '{ref_month}-01'
            GROUP BY 1
        )
        SELECT z.LocationID, z.Borough, z.Zone,
               COALESCE(t.trips, 0) AS ref_trips,
               COALESCE(t.frac_fee, 0.0) AS frac_fee
        FROM zones z LEFT JOIN t ON z.LocationID = t.loc
        ORDER BY z.LocationID
    """).df()

    fee_by_zone["in_crz"] = (
        (fee_by_zone["Borough"] == "Manhattan")
        & (fee_by_zone["frac_fee"] >= threshold)
    )
    return fee_by_zone


def main() -> None:
    cfg = load_config()
    crz = derive_crz(cfg)
    out = ROOT / cfg["crz"]["derived_file"]
    crz.to_csv(out, index=False)
    n = int(crz["in_crz"].sum())
    print(f"Derived {n} CRZ zones (threshold={cfg['crz']['fee_threshold']}) -> {out}")
    print(crz[crz["in_crz"]][["LocationID", "Zone", "frac_fee"]].to_string(index=False))


if __name__ == "__main__":
    main()
