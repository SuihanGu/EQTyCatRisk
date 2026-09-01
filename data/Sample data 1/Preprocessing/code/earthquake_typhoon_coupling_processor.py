#!/usr/bin/env python3
"""识别 2000 年以前日本地震—台风耦合事件。

规则：
1. 地震严格使用 USGS magType 为 Mw 系列且震级 >= 5.0 的记录。
2. 台风轨迹最大 10 分钟平均风速 >= 34 kt；1977 年以后优先使用 JMA R30/R50，
   早期记录用西北太平洋气压—风速关系和后期 JMA 风圈校准模型估算 R34。
3. 地震点须位于某一台风轨迹时刻的 R34 圆内。
4. |Δt| <= 72 h 为同时型；72 h < |Δt| <= 120 day 为顺序型。

程序不修改地震目录和台风事件 CSV，只在输出目录创建结果文件。
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import shapefile
from shapely.geometry import Point, shape as shapely_shape
from shapely.ops import unary_union
from shapely.prepared import prep


DEFAULT_TYPHOON_DIR = Path(
    r"F:\--------------0000000 期刊论文\--------------000000 4内容（地震台风耦合）"
    r"\000 日本历次台风事件及损失1946_2025\有损失的台风事件"
)
DEFAULT_EARTHQUAKE_FILE = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\01 日本国土交通省气象厅"
    r"\[001]随机事件集\地震随机事件集（USGS）\usgs_earthquake_1900_2026_M5.0plus.csv"
)
DEFAULT_OUTPUT_DIR = Path(
    r"F:\--------------0000000 期刊论文\--------------000000 4内容（地震台风耦合）"
    r"\000 日本历史耦合事件2"
)
DEFAULT_SHAPEFILE = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\03 地图\0 Natural Earth公司文件"
    r"\（各州省）ne_10m_admin_1_states_provinces\ne_10m_admin_1_states_provinces.shp"
)

CUTOFF = datetime(2000, 1, 1, tzinfo=timezone.utc)
SIMULTANEOUS_HOURS = 72.0
SEQUENTIAL_DAYS = 120.0
MIN_WIND_KT = 34.0
EARTH_RADIUS_KM = 6371.0088
NM_TO_KM = 1.852
JAPAN_REGION_BOUNDS = {
    "min_lat": 20.0,
    "max_lat": 50.0,
    "min_lon": 120.0,
    "max_lon": 155.0,
}
DAMAGE_COLUMNS = ("全壊", "半壊", "一部破損")

EVENT_RE = re.compile(
    r"^(?P<year>\d{4})年.*?\((?P<name>[^()]*)\).*?(?P<code>TY\d{4})\.csv$",
    re.IGNORECASE,
)

REFERENCES = {
    "jma_r30_geometry": "https://www.data.jma.go.jp/typhoon/position_table/format_csv.html",
    "ibtracs_columns": "https://www.ncei.noaa.gov/sites/g/files/anmtlf171/files/2025-02/IBTrACS_v04r01_column_documentation.pdf",
    "jma_34kt_threshold": "https://www.data.jma.go.jp/multi/cyclone/cyclone_caplink.html?lang=en",
    "atkinson_holliday": "https://doi.org/10.1175/1520-0493(1977)105%3C0421:TCMSLP%3E2.0.CO;2",
    "wmo_wind_conversion": "https://cyclone.wmo.int/pdf/Global-Guide-to-Tropical-Cyclone-Forecasting.pdf",
}


@dataclass(frozen=True)
class Earthquake:
    time: datetime
    latitude: float
    longitude: float
    depth_km: float | None
    magnitude: float
    mag_type: str
    event_id: str
    place: str
    prefecture: str


@dataclass
class TyphoonTrackRaw:
    event_file: str
    year: int
    name: str
    code: str
    sid: str
    ibtracs_name: str
    time: datetime
    nature: str
    latitude: float
    longitude: float
    wind_kt: float | None
    wind_source: str
    pressure_hpa: float | None
    pressure_source: str
    r30_dir: int | None
    r30_long_nm: float | None
    r30_short_nm: float | None
    r50_dir: int | None
    r50_long_nm: float | None
    r50_short_nm: float | None


@dataclass
class Footprint:
    raw: TyphoonTrackRaw
    wind_kt: float
    wind_source: str
    pressure_hpa: float | None
    pressure_source: str
    r34_radius_nm: float
    r34_center_lat: float
    r34_center_lon: float
    r34_method: str
    r34_quality: str


def number(value: str | None) -> float | None:
    try:
        text = (value or "").strip()
        return float(text) if text else None
    except ValueError:
        return None


def parse_time(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def loss_number(value: str | None) -> float | None:
    text = (value or "").strip().replace(",", "").replace("，", "")
    if not text or text in {"-", "－", "—", "―", "…", "不明"}:
        return None
    text = re.sub(r"[※*＊†‡].*$", "", text).strip()
    text = re.sub(r"[^0-9.+-]", "", text)
    if not text or text in {"+", "-", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_typhoon_damage_totals(
    typhoon_dir: Path,
    event_files: Iterable[str],
) -> tuple[dict[str, dict[str, int | str]], dict[str, object]]:
    """Read the authoritative 合計 row and audit it against 47 prefecture rows."""
    results: dict[str, dict[str, int | str]] = {}
    mismatches: list[dict[str, object]] = []
    for event_file in sorted(set(event_files)):
        path = typhoon_dir / event_file
        rows = read_csv_rows(path)
        header_index = next(
            (i for i, row in enumerate(rows) if row and row[0].strip() == "都道府県"),
            None,
        )
        if header_index is None:
            raise ValueError(f"未找到都道府県表头：{path}")
        header = [cell.strip() for cell in rows[header_index]]
        missing = [column for column in DAMAGE_COLUMNS if column not in header]
        if missing:
            raise ValueError(f"{event_file} 缺少损失列：{', '.join(missing)}")
        indexes = {column: header.index(column) for column in DAMAGE_COLUMNS}
        total_rows = [row for row in rows[header_index + 1 :] if row and row[0].strip() == "合計"]
        if len(total_rows) != 1:
            raise ValueError(f"{event_file} 的‘合計’行数量应为 1，实际为 {len(total_rows)}")
        total_row = total_rows[0]
        totals: dict[str, int] = {}
        prefecture_sums: dict[str, int] = {}
        for column, column_index in indexes.items():
            total_value = loss_number(total_row[column_index] if column_index < len(total_row) else "")
            totals[column] = int(total_value or 0)
            prefecture_sum = 0.0
            for row in rows[header_index + 1 :]:
                if not row or not row[0].strip() or row[0].strip() == "合計":
                    continue
                value = loss_number(row[column_index] if column_index < len(row) else "")
                prefecture_sum += value or 0.0
            prefecture_sums[column] = int(prefecture_sum)
            if totals[column] != prefecture_sums[column]:
                mismatches.append({
                    "file": event_file,
                    "column": column,
                    "total_row": totals[column],
                    "prefecture_sum": prefecture_sums[column],
                })
        results[event_file] = {
            "typhoon_loss_full_collapse_buildings": totals["全壊"],
            "typhoon_loss_half_collapse_buildings": totals["半壊"],
            "typhoon_loss_partial_damage_buildings": totals["一部破損"],
            "typhoon_loss_source_row": "对应台风CSV的合計行",
        }
    report = {
        "event_count": len(results),
        "aggregation_rule": "read 全壊, 半壊 and 一部破損 from each event CSV 合計 row",
        "prefecture_reconciliation_mismatch_count": len(mismatches),
        "prefecture_reconciliation_mismatches": mismatches,
        "selected_event_totals": {
            "full_collapse_buildings": sum(int(item["typhoon_loss_full_collapse_buildings"]) for item in results.values()),
            "half_collapse_buildings": sum(int(item["typhoon_loss_half_collapse_buildings"]) for item in results.values()),
            "partial_damage_buildings": sum(int(item["typhoon_loss_partial_damage_buildings"]) for item in results.values()),
        },
    }
    return results, report


def first_positive(*values: str | None) -> tuple[float | None, int]:
    for index, value in enumerate(values):
        parsed = number(value)
        if parsed is not None and parsed > 0:
            return parsed, index
    return None, -1


def parse_direction(value: str | None) -> int | None:
    parsed = number(value)
    if parsed is None:
        return None
    integer = int(parsed)
    return integer if 1 <= integer <= 9 else None


def load_prior_match_metadata(typhoon_dir: Path) -> dict[str, dict[str, str]]:
    report_path = typhoon_dir / "处理报告_台风损失_IBTrACS.json"
    if not report_path.exists():
        return {}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {item["file"]: item for item in report.get("events", [])}


def load_typhoon_tracks(typhoon_dir: Path) -> tuple[list[TyphoonTrackRaw], list[str]]:
    match_metadata = load_prior_match_metadata(typhoon_dir)
    tracks: list[TyphoonTrackRaw] = []
    files_without_track: list[str] = []

    for path in sorted(typhoon_dir.glob("*.csv")):
        match = EVENT_RE.match(path.name)
        if not match:
            continue
        groups = match.groupdict()
        year = int(groups["year"])
        if year >= 2000:
            continue
        rows = read_csv_rows(path)
        header_index = next(
            (i for i, row in enumerate(rows) if row and row[0].strip() == "都道府県"),
            None,
        )
        if header_index is None:
            raise ValueError(f"未找到都道府県表头：{path}")
        header = [cell.strip() for cell in rows[header_index]]
        required = {"ISO_TIME", "NATURE", "LAT", "LON", "WMO_WIND", "WMO_PRES", "TOKYO_LAT", "TOKYO_LON", "TOKYO_WIND", "TOKYO_PRES", "TOKYO_R30_DIR", "TOKYO_R30_LONG", "TOKYO_R30_SHORT", "TOKYO_R50_DIR", "TOKYO_R50_LONG", "TOKYO_R50_SHORT"}
        missing = sorted(required - set(header))
        if missing:
            raise ValueError(f"{path.name} 缺少轨迹字段：{', '.join(missing)}")

        metadata = match_metadata.get(path.name, {})
        file_track_count = 0
        for raw_row in rows[header_index + 1 :]:
            if len(raw_row) <= header.index("ISO_TIME") or not raw_row[header.index("ISO_TIME")].strip():
                continue
            row = dict(zip(header, raw_row))
            lat, lat_choice = first_positive(row.get("TOKYO_LAT"), row.get("LAT"))
            lon, lon_choice = first_positive(row.get("TOKYO_LON"), row.get("LON"))
            if lat is None or lon is None:
                continue
            wind, wind_choice = first_positive(row.get("TOKYO_WIND"), row.get("WMO_WIND"))
            pressure, pressure_choice = first_positive(row.get("TOKYO_PRES"), row.get("WMO_PRES"))
            tracks.append(
                TyphoonTrackRaw(
                    event_file=path.name,
                    year=year,
                    name=groups["name"].strip(),
                    code=groups["code"].upper(),
                    sid=str(metadata.get("ibtracs_sid", "")),
                    ibtracs_name=str(metadata.get("ibtracs_name", "")),
                    time=parse_time(row["ISO_TIME"] + "+00:00" if "+" not in row["ISO_TIME"] and not row["ISO_TIME"].endswith("Z") else row["ISO_TIME"]),
                    nature=row.get("NATURE", "").strip(),
                    latitude=lat,
                    longitude=lon,
                    wind_kt=wind,
                    wind_source=("TOKYO_WIND" if wind_choice == 0 else "WMO_WIND") if wind is not None else "",
                    pressure_hpa=pressure,
                    pressure_source=("TOKYO_PRES" if pressure_choice == 0 else "WMO_PRES") if pressure is not None else "",
                    r30_dir=parse_direction(row.get("TOKYO_R30_DIR")),
                    r30_long_nm=number(row.get("TOKYO_R30_LONG")),
                    r30_short_nm=number(row.get("TOKYO_R30_SHORT")),
                    r50_dir=parse_direction(row.get("TOKYO_R50_DIR")),
                    r50_long_nm=number(row.get("TOKYO_R50_LONG")),
                    r50_short_nm=number(row.get("TOKYO_R50_SHORT")),
                )
            )
            file_track_count += 1
        if file_track_count == 0:
            files_without_track.append(path.name)
    return tracks, files_without_track


def load_japan_land_geometry(path: Path):
    """Return Japanese admin-1 land geometry and prefecture geometries."""
    reader = shapefile.Reader(str(path), encoding="utf-8")
    fields = [field[0] for field in reader.fields[1:]]
    prefectures: list[tuple[str, object]] = []
    geometries = []
    for shape_record in reader.iterShapeRecords():
        record = dict(zip(fields, shape_record.record))
        if str(record.get("adm0_a3") or "").upper() != "JPN":
            continue
        geometry = shapely_shape(shape_record.shape.__geo_interface__)
        if geometry.is_empty:
            continue
        prefecture = str(record.get("name_ja") or record.get("name") or "").strip()
        prefectures.append((prefecture, prep(geometry)))
        geometries.append(geometry)
    if not geometries:
        raise ValueError(f"底图中未找到日本行政区：{path}")
    return prep(unary_union(geometries)), prefectures


def load_earthquakes(path: Path, shapefile_path: Path) -> tuple[list[Earthquake], dict[str, int]]:
    japan_land, prefecture_geometries = load_japan_land_geometry(shapefile_path)
    earthquakes: list[Earthquake] = []
    counts = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"time", "latitude", "longitude", "depth", "mag", "magType", "id", "place", "type"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"USGS 文件缺少字段：{', '.join(missing)}")
        for row in reader:
            counts["rows_total"] += 1
            event_time = parse_time(row["time"])
            if event_time >= CUTOFF:
                continue
            counts["rows_pre2000"] += 1
            mag_type = row.get("magType", "").strip().lower()
            magnitude = number(row.get("mag"))
            if not mag_type.startswith("mw") or magnitude is None or magnitude < 5.0:
                continue
            if row.get("type", "").strip().lower() != "earthquake":
                continue
            latitude, longitude = number(row.get("latitude")), number(row.get("longitude"))
            if latitude is None or longitude is None:
                continue
            counts["mw_family_pre2000_global"] += 1
            if not (
                JAPAN_REGION_BOUNDS["min_lat"] <= latitude <= JAPAN_REGION_BOUNDS["max_lat"]
                and JAPAN_REGION_BOUNDS["min_lon"] <= longitude <= JAPAN_REGION_BOUNDS["max_lon"]
            ):
                continue
            point = Point(longitude, latitude)
            if not japan_land.covers(point):
                counts["mw_family_pre2000_japan_region_off_land"] += 1
                continue
            prefecture = next(
                (name for name, geometry in prefecture_geometries if geometry.covers(point)),
                "日本内陆（都道府县边界未唯一匹配）",
            )
            earthquakes.append(
                Earthquake(
                    time=event_time,
                    latitude=latitude,
                    longitude=longitude,
                    depth_km=number(row.get("depth")),
                    magnitude=magnitude,
                    mag_type=mag_type,
                    event_id=row.get("id", "").strip(),
                    place=row.get("place", "").strip(),
                    prefecture=prefecture,
                )
            )
    earthquakes.sort(key=lambda item: item.time)
    counts["mw_family_pre2000_japan_region_inland"] = len(earthquakes)
    counts["mw_family_pre2000_japan_region"] = len(earthquakes)
    counts["mw_family_pre2000"] = len(earthquakes)
    return earthquakes, dict(counts)


def bearing_degrees(direction: int | None) -> float | None:
    return {
        1: 45.0,
        2: 90.0,
        3: 135.0,
        4: 180.0,
        5: 225.0,
        6: 270.0,
        7: 315.0,
        8: 0.0,
        9: None,
    }.get(direction)


def jma_circle(direction: int | None, long_nm: float | None, short_nm: float | None) -> tuple[float, float, float] | None:
    if long_nm is None or short_nm is None or long_nm <= 0 or short_nm <= 0:
        return None
    radius_nm = (long_nm + short_nm) / 2.0
    offset_nm = max(0.0, (long_nm - short_nm) / 2.0)
    bearing = bearing_degrees(direction)
    if bearing is None or offset_nm == 0:
        return 0.0, 0.0, radius_nm
    angle = math.radians(bearing)
    east_nm = offset_nm * math.sin(angle)
    north_nm = offset_nm * math.cos(angle)
    return east_nm, north_nm, radius_nm


def r34_from_jma(raw: TyphoonTrackRaw) -> tuple[float, float, float, str] | None:
    r30 = jma_circle(raw.r30_dir, raw.r30_long_nm, raw.r30_short_nm)
    if r30 is None:
        return None
    r50 = jma_circle(raw.r50_dir, raw.r50_long_nm, raw.r50_short_nm)
    if r50 is not None:
        fraction = (34.0 - 30.0) / (50.0 - 30.0)
        east = (1.0 - fraction) * r30[0] + fraction * r50[0]
        north = (1.0 - fraction) * r30[1] + fraction * r50[1]
        radius = (1.0 - fraction) * r30[2] + fraction * r50[2]
        return east, north, radius, "JMA_R30_R50_linear_interpolation"
    scale = 30.0 / 34.0
    return r30[0] * scale, r30[1] * scale, r30[2] * scale, "JMA_R30_rankine_scaling"


def empirical_features(wind_kt: float, latitude: float, pressure_hpa: float) -> list[float]:
    wind_scaled = (wind_kt - 60.0) / 30.0
    lat_scaled = (abs(latitude) - 25.0) / 10.0
    deficit_scaled = (1010.0 - pressure_hpa) / 50.0
    return [
        1.0,
        wind_scaled,
        wind_scaled * wind_scaled,
        lat_scaled,
        lat_scaled * lat_scaled,
        deficit_scaled,
        deficit_scaled * deficit_scaled,
        wind_scaled * lat_scaled,
    ]


FEATURE_NAMES = [
    "intercept",
    "wind_scaled",
    "wind_scaled_squared",
    "latitude_scaled",
    "latitude_scaled_squared",
    "pressure_deficit_scaled",
    "pressure_deficit_scaled_squared",
    "wind_latitude_interaction",
]


def pressure_to_wind_10min(pressure_hpa: float) -> float | None:
    deficit = 1010.0 - pressure_hpa
    if deficit <= 0:
        return None
    wind_1min = 6.7 * (deficit ** 0.644)
    return 0.88 * wind_1min


def wind_to_pressure(wind_10min_kt: float) -> float:
    wind_1min = wind_10min_kt / 0.88
    deficit = (wind_1min / 6.7) ** (1.0 / 0.644)
    return 1010.0 - deficit


def fit_r34_model(tracks: list[TyphoonTrackRaw]) -> tuple[np.ndarray, dict[str, object]]:
    records: list[tuple[int, list[float], float]] = []
    seen: set[tuple[str, str]] = set()
    for raw in tracks:
        if not (1977 <= raw.year < 2000):
            continue
        observed = r34_from_jma(raw)
        if observed is None or raw.wind_kt is None or raw.wind_kt < MIN_WIND_KT:
            continue
        pressure = raw.pressure_hpa if raw.pressure_hpa is not None else wind_to_pressure(raw.wind_kt)
        dedupe_key = (raw.sid or raw.event_file, raw.time.isoformat())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        records.append((raw.year, empirical_features(raw.wind_kt, raw.latitude, pressure), observed[2]))

    if len(records) < 100:
        raise ValueError("可用于 R34 校准的 JMA R30/R50 记录不足")

    train = [record for record in records if record[0] <= 1994]
    validation = [record for record in records if record[0] >= 1995]

    def fit(rows: list[tuple[int, list[float], float]]) -> np.ndarray:
        x = np.asarray([record[1] for record in rows], dtype=float)
        y = np.log(np.asarray([record[2] for record in rows], dtype=float))
        return np.linalg.lstsq(x, y, rcond=None)[0]

    def evaluate(rows: list[tuple[int, list[float], float]], beta: np.ndarray) -> dict[str, float | int]:
        actual = np.asarray([record[2] for record in rows], dtype=float)
        predicted = np.exp(np.asarray([np.dot(record[1], beta) for record in rows]))
        error = predicted - actual
        return {
            "n": len(rows),
            "mae_nm": round(float(np.mean(np.abs(error))), 3),
            "rmse_nm": round(float(np.sqrt(np.mean(error * error))), 3),
            "bias_nm": round(float(np.mean(error)), 3),
        }

    validation_beta = fit(train)
    final_beta = fit(records)
    radii = np.asarray([record[2] for record in records], dtype=float)
    lower = float(np.percentile(radii, 2.5))
    upper = float(np.percentile(radii, 97.5))
    report = {
        "calibration_records": len(records),
        "calibration_years": [min(record[0] for record in records), max(record[0] for record in records)],
        "validation_years": [1995, 1999],
        "validation_metrics": evaluate(validation, validation_beta),
        "feature_names": FEATURE_NAMES,
        "final_coefficients": [float(value) for value in final_beta],
        "prediction_clip_nm": [lower, upper],
    }
    return final_beta, report


def destination_point(latitude: float, longitude: float, east_nm: float, north_nm: float) -> tuple[float, float]:
    distance_km = math.hypot(east_nm, north_nm) * NM_TO_KM
    if distance_km == 0:
        return latitude, longitude
    bearing = math.atan2(east_nm, north_nm)
    angular = distance_km / EARTH_RADIUS_KM
    lat1, lon1 = math.radians(latitude), math.radians(longitude)
    lat2 = math.asin(math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(bearing))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    normalized_lon = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
    return math.degrees(lat2), normalized_lon


def build_footprints(
    tracks: list[TyphoonTrackRaw], beta: np.ndarray, model_report: dict[str, object]
) -> tuple[list[Footprint], dict[str, object]]:
    footprints: list[Footprint] = []
    method_counts = Counter()
    skip_counts = Counter()
    lower, upper = (float(value) for value in model_report["prediction_clip_nm"])

    for raw in tracks:
        wind = raw.wind_kt
        wind_source = raw.wind_source
        pressure = raw.pressure_hpa
        pressure_source = raw.pressure_source
        observed = r34_from_jma(raw)

        if observed is not None and wind is not None:
            if wind < MIN_WIND_KT:
                skip_counts["observed_wind_below_34kt"] += 1
                continue
            east_nm, north_nm, radius_nm, method = observed
            center_lat, center_lon = destination_point(raw.latitude, raw.longitude, east_nm, north_nm)
            footprints.append(
                Footprint(raw, wind, wind_source, pressure, pressure_source, radius_nm, center_lat, center_lon, method, "observed_JMA_wind_radii")
            )
            method_counts[method] += 1
            continue

        if raw.nature not in {"TS", "NR"}:
            skip_counts["estimated_non_tropical_nature"] += 1
            continue
        if wind is None:
            if pressure is None:
                skip_counts["missing_wind_and_pressure"] += 1
                continue
            wind = pressure_to_wind_10min(pressure)
            wind_source = "Atkinson_Holliday_from_pressure_x0.88"
        if wind is None or wind < MIN_WIND_KT:
            skip_counts["estimated_wind_below_34kt"] += 1
            continue
        if pressure is None:
            pressure = wind_to_pressure(wind)
            pressure_source = "inverse_Atkinson_Holliday"
        predicted = math.exp(float(np.dot(empirical_features(wind, raw.latitude, pressure), beta)))
        radius_nm = min(upper, max(lower, predicted))
        footprints.append(
            Footprint(
                raw,
                wind,
                wind_source,
                pressure,
                pressure_source,
                radius_nm,
                raw.latitude,
                raw.longitude,
                "empirical_R34_from_1977_1999_JMA",
                "estimated_model",
            )
        )
        method_counts["empirical_R34_from_1977_1999_JMA"] += 1

    events_with_footprints = {footprint.raw.event_file for footprint in footprints}
    return footprints, {
        "footprint_count": len(footprints),
        "event_count_with_footprints": len(events_with_footprints),
        "method_counts": dict(method_counts),
        "skip_counts": dict(skip_counts),
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(((lon2 - lon1 + 180.0) % 360.0) - 180.0)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def coupling_type(delta_hours: float) -> str | None:
    absolute = abs(delta_hours)
    if absolute <= SIMULTANEOUS_HOURS:
        return "同时型"
    if absolute <= SEQUENTIAL_DAYS * 24.0:
        return "先地震后台风" if delta_hours < -SIMULTANEOUS_HOURS else "先台风后地震"
    return None


def coupling_priority(category: str) -> int:
    """Return the user-requested temporal priority (lower is preferred)."""
    return 0 if category == "同时型" else 1


def identify_couplings(footprints: list[Footprint], earthquakes: list[Earthquake]) -> list[dict[str, object]]:
    """Return one best track-time match for every typhoon-event/earthquake pair."""
    earthquake_times = [item.time for item in earthquakes]
    best: dict[tuple[str, str], dict[str, object]] = {}
    window = timedelta(days=SEQUENTIAL_DAYS)

    for footprint in footprints:
        lower = bisect.bisect_left(earthquake_times, footprint.raw.time - window)
        upper = bisect.bisect_right(earthquake_times, footprint.raw.time + window)
        for earthquake in earthquakes[lower:upper]:
            distance_to_r34_center = haversine_km(
                earthquake.latitude,
                earthquake.longitude,
                footprint.r34_center_lat,
                footprint.r34_center_lon,
            )
            radius_km = footprint.r34_radius_nm * NM_TO_KM
            if distance_to_r34_center > radius_km:
                continue
            delta_hours = (earthquake.time - footprint.raw.time).total_seconds() / 3600.0
            category = coupling_type(delta_hours)
            if category is None:
                continue
            key = (footprint.raw.event_file, earthquake.event_id)
            distance_to_typhoon = haversine_km(
                earthquake.latitude,
                earthquake.longitude,
                footprint.raw.latitude,
                footprint.raw.longitude,
            )
            candidate = {
                "coupling_type": category,
                "time_delta_hours": delta_hours,
                "time_delta_days": delta_hours / 24.0,
                "earthquake_time_utc": earthquake.time.isoformat().replace("+00:00", "Z"),
                "earthquake_id": earthquake.event_id,
                "mw": earthquake.magnitude,
                "mag_type": earthquake.mag_type,
                "earthquake_lat": earthquake.latitude,
                "earthquake_lon": earthquake.longitude,
                "depth_km": earthquake.depth_km,
                "place": earthquake.place,
                "earthquake_prefecture": earthquake.prefecture,
                "earthquake_inland_flag": "日本行政区陆地内",
                "typhoon_year": footprint.raw.year,
                "typhoon_name": footprint.raw.name,
                "typhoon_code": footprint.raw.code,
                "typhoon_file": footprint.raw.event_file,
                "ibtracs_sid": footprint.raw.sid,
                "ibtracs_name": footprint.raw.ibtracs_name,
                "matched_track_time_utc": footprint.raw.time.isoformat().replace("+00:00", "Z"),
                "typhoon_lat": footprint.raw.latitude,
                "typhoon_lon": footprint.raw.longitude,
                "nature": footprint.raw.nature,
                "wind_kt_10min": footprint.wind_kt,
                "wind_source": footprint.wind_source,
                "central_pressure_hpa": footprint.pressure_hpa,
                "pressure_source": footprint.pressure_source,
                "r34_radius_nm": footprint.r34_radius_nm,
                "r34_radius_km": radius_km,
                "r34_circle_center_lat": footprint.r34_center_lat,
                "r34_circle_center_lon": footprint.r34_center_lon,
                "r34_method": footprint.r34_method,
                "r34_quality": footprint.r34_quality,
                "distance_to_r34_center_km": distance_to_r34_center,
                "distance_to_typhoon_center_km": distance_to_typhoon,
                "inside_radius_ratio": distance_to_r34_center / radius_km if radius_km else None,
            }
            existing = best.get(key)
            candidate_rank = (
                coupling_priority(category),
                -float(footprint.wind_kt),
                abs(delta_hours),
                footprint.raw.time.isoformat(),
            )
            if existing is None or candidate_rank < existing["_rank"]:
                candidate["_rank"] = candidate_rank
                best[key] = candidate

    results = list(best.values())
    for item in results:
        item.pop("_rank", None)
    results.sort(key=lambda item: (item["earthquake_time_utc"], item["typhoon_code"], item["earthquake_id"]))
    return results


def deduplicate_disaster_event_couplings(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    """Select one-to-one pairs by temporal phase, then stronger Mw and wind."""
    used_earthquakes: set[str] = set()
    used_typhoons: set[str] = set()
    results: list[dict[str, object]] = []
    for priority in (0, 1):
        phase = [
            candidate for candidate in candidates
            if coupling_priority(str(candidate["coupling_type"])) == priority
        ]
        phase.sort(key=lambda candidate: (
            -float(candidate["mw"]),
            -float(candidate["wind_kt_10min"]),
            abs(float(candidate["time_delta_hours"])),
            str(candidate["earthquake_id"]),
            str(candidate["typhoon_code"]),
            str(candidate["typhoon_file"]),
        ))
        for candidate in phase:
            earthquake_id = str(candidate["earthquake_id"])
            typhoon_file = str(candidate["typhoon_file"])
            if earthquake_id in used_earthquakes or typhoon_file in used_typhoons:
                continue
            results.append(dict(candidate))
            used_earthquakes.add(earthquake_id)
            used_typhoons.add(typhoon_file)

    results.sort(key=lambda item: (
        -float(item["mw"]),
        -float(item["wind_kt_10min"]),
        str(item["earthquake_time_utc"]),
        str(item["typhoon_code"]),
        str(item["earthquake_id"]),
    ))
    for index, item in enumerate(results, start=1):
        item["coupling_id"] = f"CPL{index:06d}"
    return results


COUPLING_COLUMNS = [
    "coupling_id", "coupling_type", "time_delta_hours", "time_delta_days",
    "earthquake_time_utc", "earthquake_id", "mw", "mag_type", "earthquake_lat",
    "earthquake_lon", "depth_km", "place", "earthquake_prefecture",
    "earthquake_inland_flag", "typhoon_year", "typhoon_name",
    "typhoon_code", "typhoon_file", "ibtracs_sid", "ibtracs_name",
    "matched_track_time_utc", "typhoon_lat", "typhoon_lon", "nature",
    "wind_kt_10min", "wind_source", "central_pressure_hpa", "pressure_source",
    "typhoon_loss_full_collapse_buildings", "typhoon_loss_half_collapse_buildings",
    "typhoon_loss_partial_damage_buildings", "typhoon_loss_source_row",
    "r34_radius_nm", "r34_radius_km", "r34_circle_center_lat",
    "r34_circle_center_lon", "r34_method", "r34_quality",
    "distance_to_r34_center_km", "distance_to_typhoon_center_km", "inside_radius_ratio",
]

FOOTPRINT_COLUMNS = [
    "event_file", "year", "name", "code", "ibtracs_sid", "ibtracs_name", "track_time_utc",
    "nature", "typhoon_lat", "typhoon_lon", "wind_kt_10min", "wind_source",
    "central_pressure_hpa", "pressure_source", "r34_radius_nm", "r34_radius_km",
    "r34_circle_center_lat", "r34_circle_center_lon", "r34_method", "r34_quality",
]


def footprint_record(item: Footprint) -> dict[str, object]:
    return {
        "event_file": item.raw.event_file,
        "year": item.raw.year,
        "name": item.raw.name,
        "code": item.raw.code,
        "ibtracs_sid": item.raw.sid,
        "ibtracs_name": item.raw.ibtracs_name,
        "track_time_utc": item.raw.time.isoformat().replace("+00:00", "Z"),
        "nature": item.raw.nature,
        "typhoon_lat": item.raw.latitude,
        "typhoon_lon": item.raw.longitude,
        "wind_kt_10min": item.wind_kt,
        "wind_source": item.wind_source,
        "central_pressure_hpa": item.pressure_hpa,
        "pressure_source": item.pressure_source,
        "r34_radius_nm": item.r34_radius_nm,
        "r34_radius_km": item.r34_radius_nm * NM_TO_KM,
        "r34_circle_center_lat": item.r34_center_lat,
        "r34_circle_center_lon": item.r34_center_lon,
        "r34_method": item.r34_method,
        "r34_quality": item.r34_quality,
    }


def write_dict_csv(path: Path, rows: Iterable[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            formatted = {}
            for column in columns:
                value = row.get(column, "")
                if isinstance(value, float):
                    formatted[column] = round(value, 6)
                else:
                    formatted[column] = value
            writer.writerow(formatted)


def write_summary_csv(path: Path, report: dict[str, object]) -> None:
    rows = [
        {"metric": "typhoon_events_pre2000", "value": report["typhoon_events_pre2000"], "note": "有损失台风事件"},
        {"metric": "earthquakes_mw5_pre2000", "value": report["earthquake_counts"]["mw_family_pre2000"], "note": "USGS Mw≥5.0且震中落在日本行政区陆地内"},
        {"metric": "r34_track_footprints", "value": report["footprint_report"]["footprint_count"], "note": "风速>=34 kt"},
        {"metric": "candidate_pairs_before_dedup", "value": report["candidate_pair_count_before_global_dedup"], "note": "全局去重前的台风—地震候选配对"},
        {"metric": "duplicate_candidates_removed", "value": report["duplicate_candidates_removed"], "note": "先同时型后顺序型，再按Mw和风速由强到弱一对一筛选"},
        {"metric": "coupling_pairs_total", "value": report["coupling_count"], "note": "每个 USGS 地震和每个台风事件均最多保留一次"},
        {"metric": "selected_typhoon_full_collapse_buildings", "value": report["damage_report"]["selected_event_totals"]["full_collapse_buildings"], "note": "最终耦合台风CSV合計行"},
        {"metric": "selected_typhoon_half_collapse_buildings", "value": report["damage_report"]["selected_event_totals"]["half_collapse_buildings"], "note": "最终耦合台风CSV合計行"},
        {"metric": "selected_typhoon_partial_damage_buildings", "value": report["damage_report"]["selected_event_totals"]["partial_damage_buildings"], "note": "最终耦合台风CSV合計行"},
    ]
    for category, count in report["coupling_type_counts"].items():
        rows.append({"metric": f"coupling_type_{category}", "value": count, "note": ""})
    write_dict_csv(path, rows, ["metric", "value", "note"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--typhoon-dir", type=Path, default=DEFAULT_TYPHOON_DIR)
    parser.add_argument("--earthquake-file", type=Path, default=DEFAULT_EARTHQUAKE_FILE)
    parser.add_argument("--shapefile", type=Path, default=DEFAULT_SHAPEFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-copy", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    typhoon_dir = args.typhoon_dir.resolve()
    earthquake_file = args.earthquake_file.resolve()
    shapefile_path = args.shapefile.resolve()
    output_dir = args.output_dir.resolve()
    if not typhoon_dir.is_dir():
        raise FileNotFoundError(f"台风事件目录不存在：{typhoon_dir}")
    if not earthquake_file.is_file():
        raise FileNotFoundError(f"USGS 地震目录不存在：{earthquake_file}")
    if not shapefile_path.is_file():
        raise FileNotFoundError(f"日本行政区底图不存在：{shapefile_path}")

    tracks, files_without_track = load_typhoon_tracks(typhoon_dir)
    earthquakes, earthquake_counts = load_earthquakes(earthquake_file, shapefile_path)
    beta, model_report = fit_r34_model(tracks)
    footprints, footprint_report = build_footprints(tracks, beta, model_report)
    coupling_candidates = identify_couplings(footprints, earthquakes)
    couplings = deduplicate_disaster_event_couplings(coupling_candidates)
    damage_by_event, damage_report = load_typhoon_damage_totals(
        typhoon_dir, (str(item["typhoon_file"]) for item in couplings)
    )
    for coupling in couplings:
        coupling.update(damage_by_event[str(coupling["typhoon_file"])])

    typhoon_events = sorted({track.event_file for track in tracks})
    footprint_events = {footprint.raw.event_file for footprint in footprints}
    events_without_footprints = sorted(set(typhoon_events) - footprint_events)
    type_counts = Counter(item["coupling_type"] for item in couplings)
    method_counts = Counter(item["r34_method"] for item in couplings)
    quality_counts = Counter(item["r34_quality"] for item in couplings)
    report = {
        "method_version": "earthquake_typhoon_coupling_v4_inland_intensity_one_to_one",
        "typhoon_dir": str(typhoon_dir),
        "earthquake_file": str(earthquake_file),
        "japan_admin1_shapefile": str(shapefile_path),
        "output_dir": str(output_dir),
        "cutoff_utc": CUTOFF.isoformat().replace("+00:00", "Z"),
        "magnitude_rule": "magType starts with 'mw' and mag >= 5.0",
        "japan_region_bounds_pre_filter": JAPAN_REGION_BOUNDS,
        "inland_rule": "earthquake point must be covered by a Japanese admin-1 land polygon (adm0_a3=JPN) in the Natural Earth shapefile",
        "wind_rule": "10-minute mean maximum wind >= 34 kt",
        "spatial_rule": "earthquake epicenter inside a typhoon R34 circle at one track time",
        "time_rule": {
            "simultaneous": "abs(delta_hours) <= 72",
            "earthquake_before_typhoon": "-2880 <= delta_hours < -72",
            "typhoon_before_earthquake": "72 < delta_hours <= 2880",
            "delta_definition": "earthquake_time - matched_typhoon_track_time",
        },
        "deduplication_rule": {
            "unique_keys": ["earthquake_id", "typhoon_file"],
            "constraint": "each earthquake and each typhoon event can appear at most once",
            "phase_1": "select simultaneous candidates (abs(delta_hours) <= 72)",
            "phase_2": "select sequential candidates using only still-unmatched events",
            "within_phase_order": "descending earthquake Mw, then descending matched 10-minute typhoon wind",
            "tie_breaker": "minimum abs(delta_hours), then earthquake_id, typhoon_code and typhoon_file",
            "algorithm": "deterministic greedy one-to-one selection",
            "distance_role": "physical distance is retained for R34 eligibility and audit only; it is not a deduplication ranking criterion",
        },
        "typhoon_events_pre2000": len(typhoon_events),
        "typhoon_track_rows_pre2000": len(tracks),
        "files_without_track": files_without_track,
        "events_without_valid_r34_footprints": events_without_footprints,
        "earthquake_counts": earthquake_counts,
        "r34_model": model_report,
        "footprint_report": footprint_report,
        "candidate_pair_count_before_global_dedup": len(coupling_candidates),
        "duplicate_candidates_removed": len(coupling_candidates) - len(couplings),
        "coupling_count": len(couplings),
        "unique_coupled_earthquakes": len({item["earthquake_id"] for item in couplings}),
        "unique_coupled_typhoon_events": len({item["typhoon_file"] for item in couplings}),
        "coupling_type_counts": dict(type_counts),
        "coupling_r34_method_counts": dict(method_counts),
        "coupling_r34_quality_counts": dict(quality_counts),
        "damage_report": damage_report,
        "references": REFERENCES,
        "dry_run": args.dry_run,
    }

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_dict_csv(output_dir / "日本地震_台风耦合事件_2000年前.csv", couplings, COUPLING_COLUMNS)
        write_dict_csv(
            output_dir / "台风R34计算轨迹_2000年前.csv",
            (footprint_record(item) for item in footprints),
            FOOTPRINT_COLUMNS,
        )
        write_summary_csv(output_dir / "耦合识别汇总_2000年前.csv", report)
        (output_dir / "耦合识别方法与审计报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.report_copy:
        args.report_copy.parent.mkdir(parents=True, exist_ok=True)
        args.report_copy.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "typhoon_events_pre2000": report["typhoon_events_pre2000"],
        "earthquakes_mw5_pre2000": earthquake_counts["mw_family_pre2000"],
        "r34_footprints": footprint_report["footprint_count"],
        "coupling_count": report["coupling_count"],
        "candidate_pair_count_before_global_dedup": report["candidate_pair_count_before_global_dedup"],
        "duplicate_candidates_removed": report["duplicate_candidates_removed"],
        "unique_coupled_earthquakes": report["unique_coupled_earthquakes"],
        "unique_coupled_typhoon_events": report["unique_coupled_typhoon_events"],
        "coupling_type_counts": report["coupling_type_counts"],
        "validation_metrics": model_report["validation_metrics"],
        "output_dir": str(output_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
