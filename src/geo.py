"""Compute taxi-zone centroids (lon/lat) from the official TLC shapefile.

Uses pyshp + pyproj only (no GDAL/geopandas) so it installs anywhere. The
shapefile is in EPSG:2263 (NY State Plane, US feet); we reproject centroids to
EPSG:4326 for mapping in Tableau.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests
import shapefile  # pyshp
from pyproj import Transformer
from shapely.geometry import shape

from common import ROOT, load_config

SHP_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip"


def build_centroids(cfg: dict) -> pd.DataFrame:
    cache = ROOT / "data" / "zone_centroids.csv"
    if cache.exists():
        return pd.read_csv(cache)

    raw = requests.get(SHP_URL, timeout=120).content
    zf = zipfile.ZipFile(io.BytesIO(raw))
    tmp = ROOT / "data" / "_shp"
    tmp.mkdir(exist_ok=True)
    for n in zf.namelist():
        (tmp / Path(n).name).write_bytes(zf.read(n))
    base = next(tmp.glob("*.shp")).with_suffix("")

    sf = shapefile.Reader(str(base))
    fields = [f[0] for f in sf.fields[1:]]
    loc_i = fields.index("LocationID")
    tr = Transformer.from_crs(2263, 4326, always_xy=True)
    rows = []
    for sr in sf.shapeRecords():
        c = shape(sr.shape.__geo_interface__).centroid
        lon, lat = tr.transform(c.x, c.y)
        rows.append({"LocationID": int(sr.record[loc_i]), "lon": lon, "lat": lat})
    df = pd.DataFrame(rows)
    df.to_csv(cache, index=False)
    return df


if __name__ == "__main__":
    df = build_centroids(load_config())
    print(f"Centroids for {len(df)} zones -> data/zone_centroids.csv")
    print(df.head().to_string(index=False))
