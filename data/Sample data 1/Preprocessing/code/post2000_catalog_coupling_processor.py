#!/usr/bin/env python3
"""Identify 2001-2024 inland-Japan earthquake/typhoon coupling events."""

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

import shapefile
from shapely.geometry import Point, shape as shapely_shape
from shapely.ops import unary_union
from shapely.prepared import prep


DEFAULT_EARTHQUAKE_FILE = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\01 日本国土交通省气象厅\[0] 灾害目录"
    r"\[1] 1998-2024（地震目录+knet+kiknet_元数据_合并_带EQNUM）.csv"
)
DEFAULT_TYPHOON_FILE = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\01 日本国土交通省气象厅\[0] 灾害目录"
    r"\[2] 2001-2024（台风目录+带0.1-0.25-0.5-1.0网格位置）-原文件.csv"
)
DEFAULT_DAMAGE_DIR = Path(
    r"F:\--------------0000000 期刊论文\--------------000000 4内容（地震台风耦合）"
    r"\000 日本历次台风事件及损失统计1946_2025\有损失的台风事件"
)
DEFAULT_SHAPEFILE = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\03 地图\0 Natural Earth公司文件"
    r"\（各州省）ne_10m_admin_1_states_provinces\ne_10m_admin_1_states_provinces.shp"
)
DEFAULT_OUTPUT_DIR = Path(
    r"F:\--------------0000000 期刊论文\--------------000000 4内容（地震台风耦合）"
    r"\000 日本历史耦合事件（2000年以后）"
)

START_JST = datetime(2001, 1, 1, tzinfo=timezone(timedelta(hours=9)))
END_JST = datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=9)))
SIMULTANEOUS_HOURS = 72.0
SEQUENTIAL_DAYS = 120.0
MIN_MAGNITUDE = 5.0
MIN_WIND_KT = 34.0
EARTH_RADIUS_KM = 6371.0088
NM_TO_KM = 1.852
JAPAN_BOUNDS = (20.0, 50.0, 120.0, 155.0)
JST = timezone(timedelta(hours=9))
UTC = timezone.utc
DAMAGE_COLUMNS = ("全壊", "半壊", "一部破損")
LOSS_FILE_RE = re.compile(r"^(?P<year>\d{4})年.*?(?P<code>TY\d{4}).*\.csv$", re.IGNORECASE)


@dataclass(frozen=True)
class Earthquake:
    eqnum: str
    time_jst: datetime
    time_utc: datetime
    latitude: float
    longitude: float
    depth_km: float
    magnitude: float
    prefecture: str
    station_record_count: int


@dataclass(frozen=True)
class TrackPoint:
    typhoon_number: str
    typhoon_code: str
    canonical_year: int
    name: str
    time: datetime
    latitude: float
    longitude: float
    class_code: str
    pressure_hpa: float | None
    wind_kt: float
    r50_direction: int | None
    r50_long_nm: float | None
    r50_short_nm: float | None
    r30_direction: int | None
    r30_long_nm: float | None
    r30_short_nm: float | None
    landfall_flag: str
    grid_01: str
    grid_025: str
    grid_05: str
    grid_10: str


@dataclass(frozen=True)
class Footprint:
    track: TrackPoint
    radius_nm: float
    center_latitude: float
    center_longitude: float
    method: str


def number(value: str | None) -> float | None:
    try:
        text = (value or "").strip().replace(",", "")
        return float(text) if text else None
    except ValueError:
        return None


def integer(value: str | None) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None else None


def parse_origin_time_jst(value: str) -> datetime:
    text = value.strip()
    patterns = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    )
    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=JST)
        except ValueError:
            pass
    raise ValueError(f"无法解析地震发生时间：{value!r}")


def parse_typhoon_time(row: dict[str, str]) -> datetime:
    return datetime(
        int(row["年"]), int(row["月"]), int(row["日"]), int(row["時（UTC）"]), tzinfo=UTC
    )


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def load_japan_land_geometry(path: Path):
    reader = shapefile.Reader(str(path), encoding="utf-8")
    fields = [field[0] for field in reader.fields[1:]]
    geometries = []
    prefectures: list[tuple[str, object]] = []
    for shape_record in reader.iterShapeRecords():
        record = dict(zip(fields, shape_record.record))
        if str(record.get("adm0_a3") or "").upper() != "JPN":
            continue
        geometry = shapely_shape(shape_record.shape.__geo_interface__)
        if geometry.is_empty:
            continue
        geometries.append(geometry)
        name = str(record.get("name_ja") or record.get("name") or "").strip()
        prefectures.append((name, prep(geometry)))
    if not geometries:
        raise ValueError(f"底图中未找到日本行政区：{path}")
    return prep(unary_union(geometries)), prefectures


def loss_number(value: str | None) -> int:
    text = (value or "").strip().replace(",", "").replace("，", "")
    if not text or text in {"-", "－", "—", "―", "不明"}:
        return 0
    text = re.sub(r"[（(※＊*].*$", "", text).strip()
    text = re.sub(r"[^0-9.+-]", "", text)
    try:
        return int(float(text)) if text not in {"", "+", "-", "."} else 0
    except ValueError:
        return 0


def read_damage_file(path: Path) -> dict[str, object]:
    rows = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                rows = list(csv.reader(handle))
            break
        except UnicodeDecodeError:
            continue
    if rows is None:
        raise ValueError(f"无法识别台风损失CSV编码：{path}")
    header_index = next(
        (index for index, row in enumerate(rows) if row and row[0].strip() == "都道府県"), None
    )
    if header_index is None:
        raise ValueError(f"未找到都道府県表头：{path}")
    header = [cell.strip() for cell in rows[header_index]]
    missing = [column for column in DAMAGE_COLUMNS if column not in header]
    if missing:
        raise ValueError(f"{path.name} 缺少损失列：{missing}")
    indexes = {column: header.index(column) for column in DAMAGE_COLUMNS}
    total_row = next(
        (row for row in rows[header_index + 1 :] if row and row[0].strip() == "合計"), None
    )
    prefecture_rows = []
    sums = {column: 0 for column in DAMAGE_COLUMNS}
    for row in rows[header_index + 1 :]:
        if not row or not row[0].strip() or row[0].strip() == "合計":
            continue
        values = {
            column: loss_number(row[indexes[column]] if len(row) > indexes[column] else "")
            for column in DAMAGE_COLUMNS
        }
        for column in DAMAGE_COLUMNS:
            sums[column] += values[column]
        if sum(values.values()) > 0:
            prefecture_rows.append({"prefecture": row[0].strip(), **values})
    if total_row is not None:
        totals = {
            column: loss_number(total_row[indexes[column]] if len(total_row) > indexes[column] else "")
            for column in DAMAGE_COLUMNS
        }
        source = "对应台风损失CSV的合計行"
    else:
        totals = sums
        source = "对应台风损失CSV的都道府县行合计"
    return {
        "file": path.name,
        "path": str(path),
        "full_collapse": totals["全壊"],
        "half_collapse": totals["半壊"],
        "partial_damage": totals["一部破損"],
        "source": source,
        "prefecture_rows": prefecture_rows,
        "prefecture_sum_mismatch": {
            column: {"total": totals[column], "prefecture_sum": sums[column]}
            for column in DAMAGE_COLUMNS if totals[column] != sums[column]
        },
    }


def load_damage_index(path: Path) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    duplicates = []
    for file_path in sorted(path.glob("*.csv")):
        match = LOSS_FILE_RE.match(file_path.name)
        if not match:
            continue
        year = int(match.group("year"))
        if not 2001 <= year <= 2024:
            continue
        code = match.group("code").upper()
        record = read_damage_file(file_path)
        record["year"] = year
        record["code"] = code
        if code in index:
            duplicates.append([code, index[code]["file"], file_path.name])
        index[code] = record
    if duplicates:
        raise ValueError(f"台风损失文件编码重复：{duplicates}")
    return index, {
        "damage_event_count_2001_2024": len(index),
        "prefecture_reconciliation_mismatch_count": sum(
            bool(record["prefecture_sum_mismatch"]) for record in index.values()
        ),
    }


def load_earthquakes(path: Path, shapefile_path: Path) -> tuple[list[Earthquake], dict[str, object]]:
    japan_land, prefecture_geometries = load_japan_land_geometry(shapefile_path)
    variants: dict[str, Counter] = defaultdict(Counter)
    station_counts = Counter()
    counts = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Origin Time", "Lat", "Long", "Depth (km)", "Mag", "EQNUM"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"地震目录缺少字段：{missing}")
        for row in reader:
            counts["source_rows"] += 1
            eqnum = row["EQNUM"].strip()
            if not eqnum:
                counts["blank_eqnum_rows"] += 1
                continue
            time_jst = parse_origin_time_jst(row["Origin Time"])
            lat = number(row["Lat"])
            lon = number(row["Long"])
            depth = number(row["Depth (km)"])
            magnitude = number(row["Mag"])
            if None in (lat, lon, depth, magnitude):
                counts["invalid_event_metadata_rows"] += 1
                continue
            key = (
                time_jst.isoformat(), round(float(lat), 6), round(float(lon), 6),
                round(float(depth), 4), round(float(magnitude), 4),
            )
            variants[eqnum][key] += 1
            station_counts[eqnum] += 1
    counts["unique_eqnum_all_years"] = len(variants)
    earthquakes = []
    variant_event_count = 0
    for eqnum, value_counts in variants.items():
        if len(value_counts) > 1:
            variant_event_count += 1
        best, _ = value_counts.most_common(1)[0]
        time_jst = datetime.fromisoformat(best[0])
        if not (START_JST <= time_jst < END_JST):
            continue
        counts["unique_eqnum_2001_2024"] += 1
        magnitude = float(best[4])
        if magnitude < MIN_MAGNITUDE:
            counts["below_magnitude_threshold"] += 1
            continue
        counts["magnitude_ge5_2001_2024"] += 1
        latitude, longitude = float(best[1]), float(best[2])
        min_lat, max_lat, min_lon, max_lon = JAPAN_BOUNDS
        if not (min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon):
            counts["outside_japan_bounds"] += 1
            continue
        point = Point(longitude, latitude)
        if not japan_land.covers(point):
            counts["japan_region_off_land"] += 1
            continue
        prefecture = next(
            (name for name, geometry in prefecture_geometries if geometry.covers(point)),
            "日本内陆（都道府县边界未唯一匹配）",
        )
        earthquakes.append(Earthquake(
            eqnum=eqnum,
            time_jst=time_jst,
            time_utc=time_jst.astimezone(UTC),
            latitude=latitude,
            longitude=longitude,
            depth_km=float(best[3]),
            magnitude=magnitude,
            prefecture=prefecture,
            station_record_count=station_counts[eqnum],
        ))
    earthquakes.sort(key=lambda event: event.time_utc)
    counts["metadata_variant_event_count_after_normalization"] = variant_event_count
    counts["inland_magnitude_ge5_2001_2024"] = len(earthquakes)
    return earthquakes, dict(counts)


def load_typhoon_tracks(
    path: Path, damage_index: dict[str, dict[str, object]]
) -> tuple[list[TrackPoint], dict[str, object]]:
    tracks = []
    counts = Counter()
    all_numbers = set()
    selected_numbers = set()
    selected_codes = set()
    with path.open("r", encoding="gb18030", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "年", "月", "日", "時（UTC）", "台風番号", "台風名", "階級",
            "latitude", "longitude", "中心気圧", "最大風速", "50KT長径方向",
            "50KT長径", "50KT短径", "30KT長径方向", "30KT長径", "30KT短径", "上陸",
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"台风目录缺少字段：{missing}")
        for row in reader:
            counts["source_rows"] += 1
            typhoon_number = row["台風番号"].strip()
            all_numbers.add(typhoon_number)
            typhoon_code = f"TY{typhoon_number.zfill(4)}"
            damage = damage_index.get(typhoon_code)
            if damage is None:
                counts["rows_without_positive_building_damage"] += 1
                continue
            lat, lon = number(row["latitude"]), number(row["longitude"])
            wind = number(row["最大風速"])
            if lat is None or lon is None or wind is None:
                counts["rows_missing_position_or_wind"] += 1
                continue
            selected_numbers.add(typhoon_number)
            selected_codes.add(typhoon_code)
            tracks.append(TrackPoint(
                typhoon_number=typhoon_number,
                typhoon_code=typhoon_code,
                canonical_year=int(damage["year"]),
                name=row["台風名"].strip().title(),
                time=parse_typhoon_time(row),
                latitude=lat,
                longitude=lon,
                class_code=row["階級"].strip(),
                pressure_hpa=number(row["中心気圧"]),
                wind_kt=wind,
                r50_direction=integer(row["50KT長径方向"]),
                r50_long_nm=number(row["50KT長径"]),
                r50_short_nm=number(row["50KT短径"]),
                r30_direction=integer(row["30KT長径方向"]),
                r30_long_nm=number(row["30KT長径"]),
                r30_short_nm=number(row["30KT短径"]),
                landfall_flag=row["上陸"].strip(),
                grid_01=row.get("grid_id-0.1", "").strip(),
                grid_025=row.get("grid_id-0.25", "").strip(),
                grid_05=row.get("grid_id-0.5", "").strip(),
                grid_10=row.get("grid_id-1.0", "").strip(),
            ))
    tracks.sort(key=lambda item: (item.time, item.typhoon_number))
    return tracks, {
        **dict(counts),
        "unique_typhoon_numbers_all": len(all_numbers),
        "damage_event_codes_available": len(damage_index),
        "selected_damage_typhoon_numbers": len(selected_numbers),
        "selected_damage_typhoon_codes": len(selected_codes),
        "damage_codes_missing_from_track_catalog": sorted(set(damage_index) - selected_codes),
    }


def bearing_degrees(direction: int | None) -> float | None:
    return {1: 45.0, 2: 90.0, 3: 135.0, 4: 180.0, 5: 225.0, 6: 270.0, 7: 315.0, 8: 0.0, 9: None}.get(direction)


def jma_circle(direction: int | None, long_nm: float | None, short_nm: float | None):
    if long_nm is None or short_nm is None or long_nm <= 0 or short_nm <= 0:
        return None
    radius_nm = (long_nm + short_nm) / 2.0
    offset_nm = max(0.0, (long_nm - short_nm) / 2.0)
    bearing = bearing_degrees(direction)
    if bearing is None or offset_nm == 0:
        return 0.0, 0.0, radius_nm
    angle = math.radians(bearing)
    return offset_nm * math.sin(angle), offset_nm * math.cos(angle), radius_nm


def r34_from_jma(track: TrackPoint):
    r30 = jma_circle(track.r30_direction, track.r30_long_nm, track.r30_short_nm)
    if r30 is None:
        return None
    r50 = jma_circle(track.r50_direction, track.r50_long_nm, track.r50_short_nm)
    if r50 is not None:
        fraction = (34.0 - 30.0) / (50.0 - 30.0)
        return (
            (1 - fraction) * r30[0] + fraction * r50[0],
            (1 - fraction) * r30[1] + fraction * r50[1],
            (1 - fraction) * r30[2] + fraction * r50[2],
            "JMA_R30_R50_linear_interpolation",
        )
    scale = 30.0 / 34.0
    return r30[0] * scale, r30[1] * scale, r30[2] * scale, "JMA_R30_rankine_scaling"


def destination_point(latitude: float, longitude: float, east_nm: float, north_nm: float):
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
    return math.degrees(lat2), (math.degrees(lon2) + 540.0) % 360.0 - 180.0


def build_footprints(tracks: list[TrackPoint]):
    footprints = []
    counts = Counter()
    events = set()
    for track in tracks:
        if track.wind_kt < MIN_WIND_KT:
            counts["wind_below_34kt"] += 1
            continue
        observed = r34_from_jma(track)
        if observed is None:
            counts["missing_r30_geometry"] += 1
            continue
        east, north, radius_nm, method = observed
        center_lat, center_lon = destination_point(track.latitude, track.longitude, east, north)
        footprints.append(Footprint(track, radius_nm, center_lat, center_lon, method))
        counts[method] += 1
        events.add(track.typhoon_number)
    footprints.sort(key=lambda item: item.track.time)
    return footprints, {**dict(counts), "footprint_count": len(footprints), "event_count": len(events)}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(((lon2 - lon1 + 180.0) % 360.0) - 180.0)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def coupling_type(delta_hours: float) -> str | None:
    if abs(delta_hours) <= SIMULTANEOUS_HOURS:
        return "同时型"
    if abs(delta_hours) <= SEQUENTIAL_DAYS * 24:
        return "先地震后台风" if delta_hours < -SIMULTANEOUS_HOURS else "先台风后地震"
    return None


def coupling_priority(category: str) -> int:
    return 0 if category == "同时型" else 1


def identify_candidates(footprints: list[Footprint], earthquakes: list[Earthquake]):
    earthquake_times = [item.time_utc for item in earthquakes]
    best: dict[tuple[str, str], dict[str, object]] = {}
    window = timedelta(days=SEQUENTIAL_DAYS)
    for footprint in footprints:
        lower = bisect.bisect_left(earthquake_times, footprint.track.time - window)
        upper = bisect.bisect_right(earthquake_times, footprint.track.time + window)
        for earthquake in earthquakes[lower:upper]:
            distance_r34 = haversine_km(
                earthquake.latitude, earthquake.longitude,
                footprint.center_latitude, footprint.center_longitude,
            )
            radius_km = footprint.radius_nm * NM_TO_KM
            if distance_r34 > radius_km:
                continue
            delta_hours = (earthquake.time_utc - footprint.track.time).total_seconds() / 3600
            category = coupling_type(delta_hours)
            if category is None:
                continue
            distance_center = haversine_km(
                earthquake.latitude, earthquake.longitude,
                footprint.track.latitude, footprint.track.longitude,
            )
            candidate = {
                "coupling_type": category,
                "time_delta_hours": delta_hours,
                "time_delta_days": delta_hours / 24,
                "earthquake_origin_time_jst": earthquake.time_jst.isoformat(),
                "earthquake_time_utc": iso(earthquake.time_utc),
                "earthquake_eqnum": earthquake.eqnum,
                "earthquake_station_record_count": earthquake.station_record_count,
                "magnitude": earthquake.magnitude,
                "magnitude_field": "Mag（源目录未提供震级类型）",
                "earthquake_lat": earthquake.latitude,
                "earthquake_lon": earthquake.longitude,
                "depth_km": earthquake.depth_km,
                "earthquake_prefecture": earthquake.prefecture,
                "earthquake_inland_flag": "日本行政区陆地内",
                "typhoon_year": footprint.track.canonical_year,
                "typhoon_number": footprint.track.typhoon_number,
                "typhoon_code": footprint.track.typhoon_code,
                "typhoon_name": footprint.track.name,
                "matched_track_time_utc": iso(footprint.track.time),
                "typhoon_lat": footprint.track.latitude,
                "typhoon_lon": footprint.track.longitude,
                "typhoon_class": footprint.track.class_code,
                "wind_kt_10min": footprint.track.wind_kt,
                "central_pressure_hpa": footprint.track.pressure_hpa,
                "landfall_flag": footprint.track.landfall_flag,
                "grid_id_0_1": footprint.track.grid_01,
                "grid_id_0_25": footprint.track.grid_025,
                "grid_id_0_5": footprint.track.grid_05,
                "grid_id_1_0": footprint.track.grid_10,
                "r34_radius_nm": footprint.radius_nm,
                "r34_radius_km": radius_km,
                "r34_circle_center_lat": footprint.center_latitude,
                "r34_circle_center_lon": footprint.center_longitude,
                "r34_method": footprint.method,
                "r34_quality": "observed_JMA_wind_radii",
                "distance_to_r34_center_km": distance_r34,
                "distance_to_typhoon_center_km": distance_center,
                "inside_radius_ratio": distance_r34 / radius_km,
            }
            key = (earthquake.eqnum, footprint.track.typhoon_number)
            rank = (
                coupling_priority(category),
                -footprint.track.wind_kt,
                abs(delta_hours),
                footprint.track.time.isoformat(),
            )
            if key not in best or rank < best[key]["_rank"]:
                candidate["_rank"] = rank
                best[key] = candidate
    results = list(best.values())
    for item in results:
        item.pop("_rank", None)
    return results


def deduplicate(candidates: list[dict[str, object]]):
    used_earthquakes = set()
    used_typhoons = set()
    selected = []
    for priority in (0, 1):
        phase = [item for item in candidates if coupling_priority(str(item["coupling_type"])) == priority]
        phase.sort(key=lambda item: (
            -float(item["magnitude"]), -float(item["wind_kt_10min"]),
            abs(float(item["time_delta_hours"])), str(item["earthquake_eqnum"]),
            str(item["typhoon_number"]),
        ))
        for item in phase:
            eqnum = str(item["earthquake_eqnum"])
            typhoon_number = str(item["typhoon_number"])
            if eqnum in used_earthquakes or typhoon_number in used_typhoons:
                continue
            selected.append(dict(item))
            used_earthquakes.add(eqnum)
            used_typhoons.add(typhoon_number)
    selected.sort(key=lambda item: (
        -float(item["magnitude"]), -float(item["wind_kt_10min"]),
        str(item["earthquake_time_utc"]), str(item["typhoon_number"]),
    ))
    for index, item in enumerate(selected, start=1):
        item["coupling_id"] = f"CPL2K{index:05d}"
        item["one_to_one_selection_basis"] = "同时型优先；阶段内震级降序、风速降序；距离不参与去重排序"
    return selected


COUPLING_COLUMNS = [
    "coupling_id", "coupling_type", "time_delta_hours", "time_delta_days",
    "earthquake_origin_time_jst", "earthquake_time_utc", "earthquake_eqnum",
    "earthquake_station_record_count", "magnitude", "magnitude_field", "earthquake_lat",
    "earthquake_lon", "depth_km", "earthquake_prefecture", "earthquake_inland_flag",
    "typhoon_year", "typhoon_number", "typhoon_code", "typhoon_name",
    "matched_track_time_utc", "typhoon_lat", "typhoon_lon", "typhoon_class",
    "wind_kt_10min", "central_pressure_hpa", "landfall_flag", "grid_id_0_1",
    "grid_id_0_25", "grid_id_0_5", "grid_id_1_0",
    "typhoon_loss_full_collapse_buildings", "typhoon_loss_half_collapse_buildings",
    "typhoon_loss_partial_damage_buildings", "typhoon_loss_source_row", "typhoon_loss_file",
    "r34_radius_nm", "r34_radius_km", "r34_circle_center_lat", "r34_circle_center_lon",
    "r34_method", "r34_quality", "distance_to_r34_center_km",
    "distance_to_typhoon_center_km", "inside_radius_ratio", "one_to_one_selection_basis",
]

FOOTPRINT_COLUMNS = [
    "typhoon_number", "typhoon_code", "typhoon_year", "typhoon_name", "track_time_utc",
    "typhoon_lat", "typhoon_lon", "typhoon_class", "wind_kt_10min", "central_pressure_hpa",
    "landfall_flag", "grid_id_0_1", "grid_id_0_25", "grid_id_0_5", "grid_id_1_0",
    "r34_radius_nm", "r34_radius_km", "r34_circle_center_lat", "r34_circle_center_lon",
    "r34_method", "r34_quality",
]


def footprint_record(item: Footprint):
    return {
        "typhoon_number": item.track.typhoon_number,
        "typhoon_code": item.track.typhoon_code,
        "typhoon_year": item.track.canonical_year,
        "typhoon_name": item.track.name,
        "track_time_utc": iso(item.track.time),
        "typhoon_lat": item.track.latitude,
        "typhoon_lon": item.track.longitude,
        "typhoon_class": item.track.class_code,
        "wind_kt_10min": item.track.wind_kt,
        "central_pressure_hpa": item.track.pressure_hpa,
        "landfall_flag": item.track.landfall_flag,
        "grid_id_0_1": item.track.grid_01,
        "grid_id_0_25": item.track.grid_025,
        "grid_id_0_5": item.track.grid_05,
        "grid_id_1_0": item.track.grid_10,
        "r34_radius_nm": item.radius_nm,
        "r34_radius_km": item.radius_nm * NM_TO_KM,
        "r34_circle_center_lat": item.center_latitude,
        "r34_circle_center_lon": item.center_longitude,
        "r34_method": item.method,
        "r34_quality": "observed_JMA_wind_radii",
    }


def write_dict_csv(path: Path, rows: Iterable[dict[str, object]], columns: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                column: round(value, 6) if isinstance((value := row.get(column, "")), float) else value
                for column in columns
            })


def write_summary(path: Path, report: dict[str, object]):
    rows = [
        {"metric": "earthquake_source_rows", "value": report["earthquake_counts"]["source_rows"], "note": "台站记录"},
        {"metric": "unique_EQNUM_2001_2024", "value": report["earthquake_counts"]["unique_eqnum_2001_2024"], "note": "按EQNUM聚合"},
        {"metric": "inland_magnitude_ge5", "value": report["earthquake_counts"]["inland_magnitude_ge5_2001_2024"], "note": "日本陆地内，Mag≥5"},
        {"metric": "positive_damage_typhoon_events", "value": report["typhoon_counts"]["selected_damage_typhoon_numbers"], "note": "全壊/半壊/一部破損至少一项大于0"},
        {"metric": "r34_footprints", "value": report["footprint_report"]["footprint_count"], "note": "最大风速≥34kt且有R30"},
        {"metric": "candidate_pairs_before_dedup", "value": report["candidate_pair_count"], "note": "同一地震-台风事件已先合并轨迹时刻"},
        {"metric": "coupling_pairs_total", "value": report["coupling_count"], "note": "地震与台风双方均一对一"},
        {"metric": "duplicates_removed", "value": report["candidate_pair_count"] - report["coupling_count"], "note": "同时型优先，随后按震级/风速"},
    ]
    for category, count in report["coupling_type_counts"].items():
        rows.append({"metric": f"coupling_type_{category}", "value": count, "note": ""})
    write_dict_csv(path, rows, ["metric", "value", "note"])


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--earthquake-file", type=Path, default=DEFAULT_EARTHQUAKE_FILE)
    parser.add_argument("--typhoon-file", type=Path, default=DEFAULT_TYPHOON_FILE)
    parser.add_argument("--damage-dir", type=Path, default=DEFAULT_DAMAGE_DIR)
    parser.add_argument("--shapefile", type=Path, default=DEFAULT_SHAPEFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-copy", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    for path in (args.earthquake_file, args.typhoon_file, args.shapefile):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not args.damage_dir.is_dir():
        raise FileNotFoundError(args.damage_dir)

    damage_index, damage_report = load_damage_index(args.damage_dir)
    earthquakes, earthquake_counts = load_earthquakes(args.earthquake_file, args.shapefile)
    tracks, typhoon_counts = load_typhoon_tracks(args.typhoon_file, damage_index)
    footprints, footprint_report = build_footprints(tracks)
    candidates = identify_candidates(footprints, earthquakes)
    couplings = deduplicate(candidates)
    for item in couplings:
        damage = damage_index[str(item["typhoon_code"])]
        item.update({
            "typhoon_loss_full_collapse_buildings": damage["full_collapse"],
            "typhoon_loss_half_collapse_buildings": damage["half_collapse"],
            "typhoon_loss_partial_damage_buildings": damage["partial_damage"],
            "typhoon_loss_source_row": damage["source"],
            "typhoon_loss_file": damage["file"],
        })

    type_counts = Counter(str(item["coupling_type"]) for item in couplings)
    report = {
        "method_version": "post2000_catalog_v1_inland_intensity_one_to_one",
        "period": "2001-01-01 through 2024-12-31 (earthquake source time JST; typhoon time UTC)",
        "earthquake_file": str(args.earthquake_file),
        "typhoon_file": str(args.typhoon_file),
        "damage_dir": str(args.damage_dir),
        "shapefile": str(args.shapefile),
        "output_dir": str(args.output_dir),
        "earthquake_identity": "EQNUM",
        "typhoon_identity": "台風番号",
        "earthquake_time_rule": "Origin Time interpreted as JST and converted to UTC (the source catalog provides no timezone column)",
        "magnitude_rule": "source Mag >= 5.0; source catalog does not provide magnitude type, so results do not relabel it as Mw",
        "inland_rule": "epicenter must be covered by a Japanese admin-1 land polygon (adm0_a3=JPN)",
        "typhoon_loss_rule": "only typhoons matching a 2001-2024 loss CSV with positive full/half/partial building damage are included",
        "wind_rule": "JMA 最大風速 >= 34 kt (10-minute mean)",
        "r34_rule": "derive R34 from JMA 30KT/50KT long/short radii; radii interpreted as nautical miles",
        "spatial_rule": "earthquake epicenter inside the derived R34 circle at a track time",
        "time_rule": {
            "simultaneous": "abs(earthquake UTC - typhoon track UTC) <= 72 h",
            "earthquake_before_typhoon": "-120 day <= delta < -72 h",
            "typhoon_before_earthquake": "+72 h < delta <= +120 day",
        },
        "deduplication_rule": {
            "constraint": "each EQNUM and each 台風番号 appears at most once",
            "phase_priority": "simultaneous first, sequential second",
            "within_phase": "magnitude descending, then matched-track wind descending",
            "tie_breaker": "absolute time difference, EQNUM, 台風番号",
            "distance_role": "used only for R34 eligibility and audit, not deduplication ranking",
        },
        "earthquake_counts": earthquake_counts,
        "typhoon_counts": typhoon_counts,
        "damage_report": damage_report,
        "footprint_report": footprint_report,
        "candidate_pair_count": len(candidates),
        "coupling_count": len(couplings),
        "unique_earthquakes": len({item["earthquake_eqnum"] for item in couplings}),
        "unique_typhoons": len({item["typhoon_number"] for item in couplings}),
        "coupling_type_counts": dict(type_counts),
        "selected_damage_totals": {
            "full_collapse": sum(int(item["typhoon_loss_full_collapse_buildings"]) for item in couplings),
            "half_collapse": sum(int(item["typhoon_loss_half_collapse_buildings"]) for item in couplings),
            "partial_damage": sum(int(item["typhoon_loss_partial_damage_buildings"]) for item in couplings),
        },
        "dry_run": args.dry_run,
    }

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_dict_csv(args.output_dir / "日本内陆地震_台风耦合事件_2001_2024.csv", couplings, COUPLING_COLUMNS)
        write_dict_csv(args.output_dir / "一对一去重前候选配对_2001_2024.csv", candidates, [c for c in COUPLING_COLUMNS if c not in {"coupling_id", "one_to_one_selection_basis", "typhoon_loss_full_collapse_buildings", "typhoon_loss_half_collapse_buildings", "typhoon_loss_partial_damage_buildings", "typhoon_loss_source_row", "typhoon_loss_file"}])
        write_dict_csv(args.output_dir / "台风R34计算轨迹_2001_2024.csv", (footprint_record(item) for item in footprints), FOOTPRINT_COLUMNS)
        write_summary(args.output_dir / "耦合识别汇总_2001_2024.csv", report)
        (args.output_dir / "耦合识别方法与审计报告_2001_2024.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.report_copy:
        args.report_copy.parent.mkdir(parents=True, exist_ok=True)
        args.report_copy.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "inland_magnitude_ge5": earthquake_counts["inland_magnitude_ge5_2001_2024"],
        "positive_damage_typhoons": typhoon_counts["selected_damage_typhoon_numbers"],
        "r34_footprints": footprint_report["footprint_count"],
        "candidate_pairs": len(candidates),
        "coupling_count": len(couplings),
        "unique_earthquakes": report["unique_earthquakes"],
        "unique_typhoons": report["unique_typhoons"],
        "coupling_type_counts": report["coupling_type_counts"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
