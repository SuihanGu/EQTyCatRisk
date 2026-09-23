#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recognize simultaneous events from the two Japan-only catalogues.

The earthquake catalogue is the KIK Japan catalogue and the typhoon
catalogue is the Japan-only 2001--2026 summary.  The latter stores maximum
wind in kt and the 30KT long/short radii in km.  For the coupling test we use
the arithmetic mean of the long and short radii multiplied by 1.15; no
nautical-mile conversion is applied because the catalogue is already in km.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

EARTH_KM = 6371.0088
KNOT_TO_MS = 0.514444
WINDOW_HOURS = 72.0

MAIN_COLUMNS = [
    "z_id", "coupling_type", "eq_time", "eq_lat", "eq_lon", "Mw", "depth_km",
    "tc_time", "tc_lat", "tc_lon", "wind_kt", "wind_ms", "dt_hours",
    "distance_km", "R30_km", "R30_long_km", "R30_short_km",
]
TRACK_COLUMNS = ["z_id", "coupling_type", "times", "lats", "lons", "winds", "winds_kt"]


def number(value: object) -> float | None:
    try:
        text = str(value).strip().replace(",", "")
        if not text or text.lower() in {"nan", "na", "null", "-", "--"}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_eq_time(value: object) -> datetime | None:
    text = str(value or "").strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def parse_ty_time(year: int, month: int, day: int, hour: int) -> datetime:
    # The Japan-only catalogue is in Japan Standard Time (JST).
    return datetime(year, month, day) + timedelta(hours=hour)


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return EARTH_KM * 2 * math.asin(min(1.0, math.sqrt(a)))


def read_rows(path: Path) -> list[list[str]]:
    # These files are Japanese CSVs; gb18030 also handles the legacy export
    # used in the project and errors=replace keeps the numeric columns intact.
    with path.open("r", encoding="gb18030", errors="replace", newline="") as handle:
        return list(csv.reader(handle))


def load_earthquakes(path: Path) -> list[dict]:
    result = []
    for row in read_rows(path)[1:]:
        if len(row) < 6:
            continue
        moment = parse_eq_time(row[1])
        lat, lon, depth, mag = map(number, (row[2], row[3], row[4], row[5]))
        if not moment or None in (lat, lon, mag) or mag < 5.0:
            continue
        if not (20 <= lat <= 50 and 120 <= lon <= 155):
            continue
        event_id = (row[16].strip() if len(row) > 16 and row[16].strip() else row[0].strip())
        result.append({"id": event_id, "time": moment, "lat": lat, "lon": lon,
                       "depth": depth or 0.0, "mag": mag})
    return result


def load_typhoons(path: Path) -> tuple[list[dict], dict[str, list[dict]]]:
    points, groups = [], {}
    for row in read_rows(path)[1:]:
        if len(row) < 17:
            continue
        year, month, day, hour = map(number, row[0:4])
        number_id, lat, lon, wind_kt = number(row[4]), number(row[7]), number(row[8]), number(row[10])
        long_km, short_km = number(row[15]), number(row[16])
        if None in (year, month, day, hour, number_id, lat, lon, wind_kt, long_km, short_km):
            continue
        if long_km <= 0 or short_km <= 0 or wind_kt < 0:
            continue
        if not (5 <= lat <= 55 and 115 <= lon <= 180):
            continue
        moment = parse_ty_time(int(year), int(month), int(day), int(hour))
        sid = f"TY{int(year) % 100:02d}{int(number_id) % 100:02d}"
        point = {"sid": sid, "time": moment, "lat": lat, "lon": lon,
                 "wind_kt": wind_kt, "wind_ms": wind_kt * KNOT_TO_MS,
                 "r30_long": long_km, "r30_short": short_km,
                 # Project's established R30 circle rule: 1.15 times the
                 # arithmetic mean of the 30KT long/short radii (km).
                 "r30": max(20.0, ((long_km + short_km) / 2.0) * 1.15)}
        points.append(point)
        groups.setdefault(sid, []).append(point)
    for track in groups.values():
        track.sort(key=lambda item: item["time"])
    return points, groups


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--earthquake-file", type=Path, required=True)
    parser.add_argument("--typhoon-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    earthquakes = load_earthquakes(args.earthquake_file)
    points, groups = load_typhoons(args.typhoon_file)
    earthquakes.sort(key=lambda item: item["time"])
    eq_times = [item["time"].timestamp() for item in earthquakes]
    best: dict[tuple[str, str], tuple[float, dict, dict]] = {}
    for point in points:
        point_ts = point["time"].timestamp()
        left = bisect.bisect_left(eq_times, point_ts - WINDOW_HOURS * 3600)
        right = bisect.bisect_right(eq_times, point_ts + WINDOW_HOURS * 3600)
        for earthquake in earthquakes[left:right]:
            delta = abs((point["time"] - earthquake["time"]).total_seconds()) / 3600.0
            distance = distance_km(earthquake["lat"], earthquake["lon"], point["lat"], point["lon"])
            if distance > point["r30"]:
                continue
            key = (earthquake["id"], point["sid"])
            score = delta * 10000 + distance
            if key not in best or score < best[key][0]:
                best[key] = (score, earthquake, point)

    main_rows, selected = [], []
    # One typhoon event may be close to several earthquakes.  Keep exactly
    # one pair per typhoon, preferring the larger magnitude; for equal
    # magnitudes prefer the smallest time difference and then distance.
    one_per_typhoon: dict[str, tuple[tuple[float, float, float], dict, dict]] = {}
    for candidate in best.values():
        _, earthquake, point = candidate
        delta = abs((point["time"] - earthquake["time"]).total_seconds()) / 3600.0
        distance = distance_km(earthquake["lat"], earthquake["lon"], point["lat"], point["lon"])
        score = (-float(earthquake["mag"]), delta, distance)
        previous = one_per_typhoon.get(point["sid"])
        if previous is None:
            one_per_typhoon[point["sid"]] = (score, earthquake, point)
        else:
            previous_score, _, _ = previous
            if score < previous_score:
                one_per_typhoon[point["sid"]] = (score, earthquake, point)

    for _, earthquake, point in sorted(one_per_typhoon.values(), key=lambda item: item[1]["time"]):
        z_id = f"EQ-{earthquake['id']}__TC-{point['sid']}"
        distance = distance_km(earthquake["lat"], earthquake["lon"], point["lat"], point["lon"])
        main_rows.append({
            "z_id": z_id, "coupling_type": "Simultaneous", "eq_time": iso(earthquake["time"]),
            "eq_lat": f"{earthquake['lat']:.5f}", "eq_lon": f"{earthquake['lon']:.5f}",
            "Mw": f"{earthquake['mag']:.2f}", "depth_km": f"{earthquake['depth']:.1f}",
            "tc_time": iso(point["time"]), "tc_lat": f"{point['lat']:.5f}", "tc_lon": f"{point['lon']:.5f}",
            "wind_kt": f"{point['wind_kt']:.1f}", "wind_ms": f"{point['wind_ms']:.2f}",
            "dt_hours": f"{abs((point['time'] - earthquake['time']).total_seconds()) / 3600:.2f}",
            "distance_km": f"{distance:.2f}", "R30_km": f"{point['r30']:.2f}",
            "R30_long_km": f"{point['r30_long']:.2f}", "R30_short_km": f"{point['r30_short']:.2f}",
        })
        selected.append((z_id, point["sid"]))

    track_rows = []
    for z_id, sid in selected:
        for point in groups[sid]:
            track_rows.append({
                "z_id": z_id, "coupling_type": "Simultaneous", "times": iso(point["time"]),
                "lats": f"{point['lat']:.5f}", "lons": f"{point['lon']:.5f}",
                "winds": f"{point['wind_ms']:.2f}", "winds_kt": f"{point['wind_kt']:.1f}",
            })
    write_csv(args.output_dir / "Coupling moment information.csv", MAIN_COLUMNS, main_rows)
    write_csv(args.output_dir / "Complete set of typhoon events satisfying coupling conditions.csv", TRACK_COLUMNS, track_rows)
    print(f"recognized={len(main_rows)} track_rows={len(track_rows)} earthquakes={len(earthquakes)} typhoon_points={len(points)}")


if __name__ == "__main__":
    main()
