-- Derive the Congestion Relief Zone (CRZ) from the data itself (DuckDB dialect).
--
-- TLC added `cbd_congestion_fee` to trip records when the toll went live in
-- Jan 2025. The toll is charged on any taxi trip that touches the CRZ, so a
-- PICKUP zone whose trips almost always incur the fee must sit inside the zone;
-- zones outside it are only charged on the minority of trips that happen to drop
-- off inside. Empirically the two groups separate at ~0.95 vs <=0.58 incidence.
--
-- Parameters (substituted by src/zones.py): {ref_parquet}, {ref_month}, {threshold}
WITH trip_fee AS (
    SELECT PULocationID AS loc,
           COUNT(*) AS trips,
           AVG(CASE WHEN cbd_congestion_fee > 0 THEN 1.0 ELSE 0.0 END) AS frac_fee
    FROM read_parquet('{ref_parquet}')
    WHERE PULocationID IS NOT NULL
      AND tpep_pickup_datetime >= DATE '{ref_month}-01'
    GROUP BY 1
)
SELECT z.LocationID,
       z.Borough,
       z.Zone,
       COALESCE(tf.trips, 0)        AS ref_trips,
       COALESCE(tf.frac_fee, 0.0)   AS frac_fee,
       (z.Borough = 'Manhattan' AND COALESCE(tf.frac_fee, 0) >= {threshold}) AS in_crz
FROM read_csv_auto('data/taxi_zone_lookup.csv') z
LEFT JOIN trip_fee tf ON z.LocationID = tf.loc
ORDER BY z.LocationID;
