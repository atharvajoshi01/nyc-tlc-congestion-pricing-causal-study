-- Internal-validity check (DuckDB): does our static, zone-based treatment label
-- agree with the actual CBD toll TLC charged in the post-period? Treated trips
-- (pickup or dropoff in the CRZ) should almost all carry cbd_congestion_fee > 0;
-- control trips should almost never. Run on any post-2025-01 month parquet.
--
-- Parameters: {parquet} {pcol} {crz_csv}
WITH crz AS (
    SELECT LocationID FROM read_csv_auto('{crz_csv}') WHERE in_crz
)
SELECT
    CASE WHEN PULocationID IN (SELECT LocationID FROM crz)
           OR DOLocationID IN (SELECT LocationID FROM crz)
         THEN 'treated' ELSE 'control' END                          AS label,
    COUNT(*)                                                        AS trips,
    AVG(CASE WHEN cbd_congestion_fee > 0 THEN 1.0 ELSE 0.0 END)     AS frac_charged_cbd_fee,
    AVG(cbd_congestion_fee)                                         AS avg_cbd_fee
FROM read_parquet('{parquet}')
WHERE PULocationID BETWEEN 1 AND 263
  AND DOLocationID BETWEEN 1 AND 263
GROUP BY 1
ORDER BY 1;
