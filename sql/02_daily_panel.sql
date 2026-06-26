-- Build the daily DiD panel for one (service, month) parquet file (DuckDB).
-- Emits two grains, tagged by `grain`:
--
--   dest  : trips whose DROPOFF is in Manhattan, split into the treated group
--           (dropoff inside the CRZ = "CBD-bound") and a spatially adjacent
--           control (dropoff in Manhattan north of 60th St). Same service, same
--           borough, neighbouring geography -> the clean headline + event-study
--           comparison of demand for trips INTO the priced zone.
--
--   zone  : every trip, aggregated by PICKUP zone, treated = pickup in CRZ.
--           Supports the zone-level fixed-effects / clustered specification.
--
-- Outcomes: trips (count), avg_fare (total_amount = what the rider pays), and
-- avg_cbd_fee (the new per-trip congestion toll; 0 before it existed).
--
-- Parameters substituted by src/build_panel.py:
--   {parquet} {service} {pcol} {month_start} {month_end} {crz_csv} {cbd_fee_expr}
WITH crz AS (
    SELECT LocationID FROM read_csv_auto('{crz_csv}') WHERE in_crz
),
man AS (  -- all Manhattan zone ids (CRZ and non-CRZ)
    SELECT LocationID FROM read_csv_auto('{crz_csv}') WHERE Borough = 'Manhattan'
),
trips AS (
    SELECT
        CAST({pcol} AS DATE)                              AS trip_date,
        PULocationID                                      AS pu,
        DOLocationID                                      AS do_,
        total_amount                                      AS fare,
        {cbd_fee_expr}                                    AS cbd_fee,
        (PULocationID IN (SELECT LocationID FROM crz))    AS pu_crz,
        (DOLocationID IN (SELECT LocationID FROM crz))    AS do_crz,
        (DOLocationID IN (SELECT LocationID FROM man))    AS do_man
    FROM read_parquet('{parquet}')
    WHERE {pcol} >= DATE '{month_start}'
      AND {pcol} <  DATE '{month_end}'
      AND PULocationID BETWEEN 1 AND 263
      AND DOLocationID BETWEEN 1 AND 263
      AND total_amount > 0 AND total_amount < 1000
),
dest_grain AS (
    SELECT 'dest'                                              AS grain,
           trip_date,
           CASE WHEN do_crz THEN 'cbd_bound' ELSE 'man_control' END AS unit,
           do_crz                                             AS treated,
           '{service}'                                        AS service,
           COUNT(*)                                           AS trips,
           AVG(fare)                                          AS avg_fare,
           AVG(cbd_fee)                                       AS avg_cbd_fee
    FROM trips
    WHERE do_man                       -- restrict to Manhattan destinations
    GROUP BY 1, 2, 3, 4
),
zone_grain AS (
    SELECT 'zone'                                             AS grain,
           trip_date,
           CAST(pu AS VARCHAR)                                AS unit,
           pu_crz                                             AS treated,
           '{service}'                                        AS service,
           COUNT(*)                                           AS trips,
           AVG(fare)                                          AS avg_fare,
           AVG(cbd_fee)                                       AS avg_cbd_fee
    FROM trips
    GROUP BY 1, 2, 3, 4, 5
)
SELECT * FROM dest_grain
UNION ALL
SELECT * FROM zone_grain;
