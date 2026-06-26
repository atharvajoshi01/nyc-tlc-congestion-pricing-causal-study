-- BigQuery cross-check against the public dataset (Standard SQL).
--
-- NOTE ON DATA SOURCE: `bigquery-public-data.new_york_taxi_trips` only covers
-- yellow/green through 2023 -- it does NOT contain the post-treatment period
-- (congestion pricing began 2025-01-05). The live study therefore runs on the
-- TLC parquet releases (see sql/02_daily_panel.sql). This file is a portable
-- BigQuery reproduction of the SAME panel logic for the 2022-2023 baseline,
-- useful for sanity-checking pre-period levels/trends with a second engine.
--
-- CRZ zone ids come from data/crz_zones.csv (derived in sql/01). Paste the 38
-- ids below or load the CSV into a table `your_project.tlc.crz_zones`.
DECLARE crz_zones ARRAY<INT64> DEFAULT [
  4,12,13,45,48,50,68,79,87,88,90,100,107,113,114,125,137,144,148,158,
  161,162,163,164,170,186,209,211,224,229,230,231,232,233,234,246,249,261
];

WITH t AS (
  SELECT
    DATE(pickup_datetime)                                  AS trip_date,
    pickup_location_id                                     AS pu,
    dropoff_location_id                                    AS do_,
    fare_amount                                            AS fare
  FROM `bigquery-public-data.new_york_taxi_trips.tlc_yellow_trips_2022`
  WHERE fare_amount > 0 AND fare_amount < 500
    AND pickup_location_id BETWEEN 1 AND 263
    AND dropoff_location_id BETWEEN 1 AND 263
)
SELECT
  trip_date,
  CASE WHEN pu IN UNNEST(crz_zones) OR do_ IN UNNEST(crz_zones)
       THEN 'treated' ELSE 'control' END  AS grp,
  COUNT(*)    AS trips,
  AVG(fare)   AS avg_fare
FROM t
GROUP BY trip_date, grp
ORDER BY trip_date, grp;
