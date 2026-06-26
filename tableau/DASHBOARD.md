# Building the Tableau Public dashboard

The analysis exports two tidy CSVs that drive a one-page dashboard:

| File | Grain | Use |
|------|-------|-----|
| `data/tableau_export.csv` | one row per day × group | time-series chart + KPI panel |
| `data/tableau_zone_map.csv` | one row per taxi zone (with `lon`/`lat`) | Manhattan map heat-layer |

## Steps (free Tableau Public account)

1. Sign up at https://public.tableau.com and install Tableau Public Desktop.
2. **Connect** → Text file → `tableau_export.csv`. Add a second connection to
   `tableau_zone_map.csv` (do **not** join — use them as two data sources).

### Sheet 1 — Map heat-layer (`tableau_zone_map.csv`)
- Drag `lon` → Columns, `lat` → Rows (both set to *Dimension*, *Longitude/Latitude*
  geographic role).
- Marks → Circle. `pct_change` → Color (diverging red–blue), `trips_per_day_post`
  → Size.
- Filter `Borough = Manhattan` (or keep all five boroughs).
- `in_crz` → Detail, so you can outline the 38-zone Congestion Relief Zone.

### Sheet 2 — Time series (`tableau_export.csv`)
- `trip_date` (continuous, by month) → Columns; `trips` (SUM) → Rows; `group` → Color.
- Add a reference line at **2025-01-05** labelled "Congestion pricing".
- Duplicate with `avg_cbd_fee` to show the toll appearing in 2025.

### Sheet 3 — DiD result panel
- Use a text/KPI sheet showing the headline number from `results/did_results.json`
  (DiD ≈ **+0.9%**, 95% CI −2.0% to +4.0%, not significant) and the +$0.74 toll.

### Dashboard
- Combine the three sheets on one dashboard, add a title and a one-line takeaway:
  *"Congestion pricing did not measurably reduce taxi demand into the CBD."*
- File → Save to Tableau Public, copy the public URL, and paste it at the top of
  the repo `README.md`.

> Tip: to draw the exact CRZ boundary instead of points, connect the spatial file
> `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip` and join on
> `LocationID`; colour polygons by `in_crz`.
