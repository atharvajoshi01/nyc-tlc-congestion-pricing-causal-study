"""Shared helpers: config loading, month enumeration, DuckDB connections."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | os.PathLike | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path) as fh:
        return yaml.safe_load(fh)


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-MM' strings from start to end."""
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out, y, m = [], sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def discover_latest_month(raw_dir: str | os.PathLike, service: str = "yellow") -> str | None:
    """Latest YYYY-MM present locally for a service (keeps the panel 'live')."""
    raw = Path(raw_dir)
    months = sorted(
        p.stem.replace(f"{service}_tripdata_", "")
        for p in raw.glob(f"{service}_tripdata_*.parquet")
        if p.stat().st_size > 100_000
    )
    return months[-1] if months else None


def resolve_window(cfg: dict) -> tuple[str, str]:
    start = cfg["study"]["start_month"]
    end = cfg["study"]["end_month"]
    if end == "auto":
        end = discover_latest_month(ROOT / cfg["data"]["raw_dir"]) or start
    return start, end


def parquet_path(cfg: dict, service: str, ym: str) -> Path:
    return ROOT / cfg["data"]["raw_dir"] / f"{service}_tripdata_{ym}.parquet"


def pickup_col(service: str) -> str:
    return {"yellow": "tpep_pickup_datetime",
            "green": "lpep_pickup_datetime",
            "fhvhv": "pickup_datetime"}[service]


def fare_col(service: str) -> str:
    return {"yellow": "fare_amount",
            "green": "fare_amount",
            "fhvhv": "base_passenger_fare"}[service]


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("PRAGMA threads=4;")
    return con
