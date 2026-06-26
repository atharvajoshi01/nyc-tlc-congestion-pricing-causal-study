"""Fetch TLC trip parquet for the study window, with backoff.

Auto-discovers the latest available month (TLC publishes on a ~2-month lag), so
re-running keeps the study current. CloudFront rate-limits bursts, so failed
fetches retry with exponential backoff. Already-present valid files are skipped.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

from common import ROOT, load_config, month_range


def discover_end_month(base: str, service: str = "yellow") -> str:
    """Walk forward from 2024-01 until a month 404s; return the last good one."""
    y, m, last = 2024, 1, "2024-01"
    while True:
        ym = f"{y:04d}-{m:02d}"
        url = f"{base}/{service}_tripdata_{ym}.parquet"
        if requests.head(url, timeout=30).status_code != 200:
            return last
        last = ym
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch(url: str, dest: Path, min_bytes: int, tries: int = 8) -> bool:
    if dest.exists() and dest.stat().st_size > min_bytes:
        return True
    for i in range(tries):
        r = requests.get(url, timeout=300)
        if r.status_code == 200 and len(r.content) > min_bytes:
            dest.write_bytes(r.content)
            return True
        time.sleep((i + 1) * 30)  # back off past the rate limiter
    print(f"  FAILED {url}", file=sys.stderr)
    return False


def main() -> None:
    cfg = load_config()
    base = cfg["data"]["cloudfront_base"]
    raw = ROOT / cfg["data"]["raw_dir"]
    raw.mkdir(parents=True, exist_ok=True)
    start = cfg["study"]["start_month"]
    end = cfg["study"]["end_month"]
    if end == "auto":
        end = discover_end_month(base)
        print(f"Latest available month: {end}")
    for service in cfg["data"]["services"]:
        min_bytes = 100_000 if service == "yellow" else 5_000
        for ym in month_range(start, end):
            f = raw / f"{service}_tripdata_{ym}.parquet"
            if fetch(f"{base}/{service}_tripdata_{ym}.parquet", f, min_bytes):
                print(f"  ok {f.name} ({f.stat().st_size // 1024} KB)")
            time.sleep(1)  # be polite to CloudFront


if __name__ == "__main__":
    main()
