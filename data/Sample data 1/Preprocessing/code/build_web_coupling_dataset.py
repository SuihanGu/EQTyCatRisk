#!/usr/bin/env python3
"""Build web-ready earthquake/typhoon coupling CSVs for the 1946-2026 study scope.

The actual recognized coupling records currently span 1951-2024 because the
available source/result catalogs contain no selected pair in 1946-1950, 2000,
or 2025-2026. All output timestamps are UTC and all winds are m/s.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


CASE_ROOT = Path(
    r"F:\--------------0000000 期刊论文\--------------000000 4内容（地震台风耦合）"
    r"\案例搜索_查找日本历次耦合事件（1946_2026）"
)
DEFAULT_PRE_RESULT = CASE_ROOT / "000 日本历史耦合事件2（1946_1999内陆地震）" / "日本地震_台风耦合事件_2000年前.csv"
DEFAULT_POST_RESULT = CASE_ROOT / "000 日本历史耦合事件（2000年以后）" / "日本内陆地震_台风耦合事件_2001_2024.csv"
DEFAULT_LOSS_DIR = CASE_ROOT / "000 日本历次台风事件及损失统计1946_2025" / "有损失的台风事件"
DEFAULT_OUTPUT_DIR = CASE_ROOT / "耦合事件识别（1946_2026）"

DEFAULT_IBTRACS = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\01 日本国土交通省气象厅"
    r"\[001]随机事件集\全球台风数据集（NOAA IBTrACS）\ibtracs.ALL.list.v04r00.csv"
)
DEFAULT_USGS = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\01 日本国土交通省气象厅"
    r"\[001]随机事件集\地震随机事件集（USGS）\usgs_earthquake_1900_2026_M5.0plus.csv"
)
DEFAULT_POST_EARTHQUAKES = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\01 日本国土交通省气象厅\[0] 灾害目录"
    r"\[1] 1998-2024（地震目录+knet+kiknet_元数据_合并_带EQNUM）.csv"
)
DEFAULT_POST_TYPHOONS = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\01 日本国土交通省气象厅\[0] 灾害目录"
    r"\[2] 2001-2024（台风目录+带0.1-0.25-0.5-1.0网格位置）-原文件.csv"
)
DEFAULT_SHAPEFILE = Path(
    r"F:\001 多灾害耦合研究（地震、台风、洪水）\03 地图\0 Natural Earth公司文件"
    r"\（各州省）ne_10m_admin_1_states_provinces\ne_10m_admin_1_states_provinces.shp"
)

WORKSPACE_ROOT = Path(r"C:\Users\wzd97\Documents\Codex\2026-08-01\codex-1-f-0000000-000000-4")
README_SOURCE = WORKSPACE_ROOT / "outputs" / "README_耦合事件网页数据.md"
PROCESSOR_SOURCES = (
    WORKSPACE_ROOT / "outputs" / "build_web_coupling_dataset.py",
    WORKSPACE_ROOT / "outputs" / "earthquake_typhoon_coupling_processor.py",
    WORKSPACE_ROOT / "outputs" / "post2000_catalog_coupling_processor.py",
)

KNOT_TO_MS = 0.514444
UTC = timezone.utc
TYPE_MAP = {
    "同时型": "Simultaneous",
    "先地震后台风": "EQ-TY",
    "先台风后地震": "TY-EQ",
}
MAIN_COLUMNS = [
    "z_id", "coupling_type", "eq_time", "eq_lat", "eq_lon", "Mw",
    "tc_time", "tc_lat", "tc_lon", "wind_ms", "dt_hours",
    "distance_km", "R34_km",
]
TRACK_COLUMNS = ["z_id", "coupling_type", "times", "lats", "lons", "winds"]


def clean_number(value: str | None) -> float | None:
    try:
        text = (value or "").strip().replace(",", "")
        return float(text) if text else None
    except ValueError:
        return None


def positive(*values: str | None) -> float | None:
    for value in values:
        parsed = clean_number(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def parse_time(value: str) -> datetime:
    text = value.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_utc(value: str | datetime) -> str:
    parsed = parse_time(value) if isinstance(value, str) else value.astimezone(UTC)
    if parsed.microsecond:
        return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def pressure_to_wind_10min_kt(pressure_hpa: float | None) -> float | None:
    if pressure_hpa is None:
        return None
    deficit = 1010.0 - pressure_hpa
    if deficit <= 0:
        return None
    wind_1min = 6.7 * (deficit ** 0.644)
    return 0.88 * wind_1min


def wind_ms_from_ibtracs(row: dict[str, str]) -> float | None:
    wind_kt = positive(row.get("TOKYO_WIND"), row.get("WMO_WIND"))
    if wind_kt is None:
        pressure = positive(row.get("TOKYO_PRES"), row.get("WMO_PRES"))
        wind_kt = pressure_to_wind_10min_kt(pressure)
    return wind_kt * KNOT_TO_MS if wind_kt is not None else None


def fmt(value: float | None, decimals: int = 6) -> str | float:
    if value is None or not math.isfinite(value):
        return ""
    return round(value, decimals)


def read_csv(path: Path, encodings: tuple[str, ...] = ("utf-8-sig", "gb18030")) -> list[dict[str, str]]:
    last_error = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"无法识别CSV编码：{path}") from last_error


def safe_token(value: str) -> str:
    token = re.sub(r"[^0-9A-Za-z_-]+", "-", value.strip())
    return token.strip("-") or "UNKNOWN"


def build_z_id(earthquake_id: str, typhoon_code: str) -> str:
    return f"EQ-{safe_token(earthquake_id)}__TC-{safe_token(typhoon_code)}"


def adapt_pre(row: dict[str, str]) -> dict[str, object]:
    return {
        "period": "pre2000",
        "source_coupling_id": row["coupling_id"],
        "earthquake_id": row["earthquake_id"],
        "typhoon_code": row["typhoon_code"],
        "track_key": row["ibtracs_sid"],
        "typhoon_file": row["typhoon_file"],
        "coupling_type": TYPE_MAP[row["coupling_type"]],
        "eq_time": iso_utc(row["earthquake_time_utc"]),
        "eq_lat": float(row["earthquake_lat"]),
        "eq_lon": float(row["earthquake_lon"]),
        "Mw": float(row["mw"]),
        "tc_time": iso_utc(row["matched_track_time_utc"]),
        "tc_lat": float(row["typhoon_lat"]),
        "tc_lon": float(row["typhoon_lon"]),
        "wind_ms": float(row["wind_kt_10min"]) * KNOT_TO_MS,
        "dt_hours": float(row["time_delta_hours"]),
        "distance_km": float(row["distance_to_typhoon_center_km"]),
        "R34_km": float(row["r34_radius_km"]),
        "magnitude_note": f"USGS {row.get('mag_type', 'mw')}",
    }


def adapt_post(row: dict[str, str]) -> dict[str, object]:
    return {
        "period": "post2000",
        "source_coupling_id": row["coupling_id"],
        "earthquake_id": row["earthquake_eqnum"],
        "typhoon_code": row["typhoon_code"],
        "track_key": row["typhoon_number"],
        "typhoon_file": row["typhoon_loss_file"],
        "coupling_type": TYPE_MAP[row["coupling_type"]],
        "eq_time": iso_utc(row["earthquake_time_utc"]),
        "eq_lat": float(row["earthquake_lat"]),
        "eq_lon": float(row["earthquake_lon"]),
        "Mw": float(row["magnitude"]),
        "tc_time": iso_utc(row["matched_track_time_utc"]),
        "tc_lat": float(row["typhoon_lat"]),
        "tc_lon": float(row["typhoon_lon"]),
        "wind_ms": float(row["wind_kt_10min"]) * KNOT_TO_MS,
        "dt_hours": float(row["time_delta_hours"]),
        "distance_km": float(row["distance_to_typhoon_center_km"]),
        "R34_km": float(row["r34_radius_km"]),
        "magnitude_note": row.get("magnitude_field", "source Mag; type unavailable"),
    }


def load_events(pre_result: Path, post_result: Path) -> list[dict[str, object]]:
    events = [adapt_pre(row) for row in read_csv(pre_result)]
    events.extend(adapt_post(row) for row in read_csv(post_result))
    for event in events:
        event["z_id"] = build_z_id(str(event["earthquake_id"]), str(event["typhoon_code"]))
    events.sort(key=lambda event: parse_time(str(event["eq_time"])), reverse=True)
    z_ids = [str(event["z_id"]) for event in events]
    if len(z_ids) != len(set(z_ids)):
        duplicates = [key for key, count in Counter(z_ids).items() if count > 1]
        raise ValueError(f"z_id重复：{duplicates}")
    return events


def load_pre_tracks(ibtracs_path: Path, wanted_sids: set[str]) -> dict[str, list[dict[str, object]]]:
    tracks: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    with ibtracs_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sid = (row.get("SID") or "").strip()
            if sid not in wanted_sids:
                continue
            time_text = (row.get("ISO_TIME") or "").strip()
            if not time_text:
                continue
            lat = positive(row.get("TOKYO_LAT"))
            lon = positive(row.get("TOKYO_LON"))
            if lat is None or lon is None:
                lat = clean_number(row.get("LAT"))
                lon = clean_number(row.get("LON"))
            if lat is None or lon is None:
                continue
            timestamp = iso_utc(time_text)
            tracks[sid][timestamp] = {
                "times": timestamp,
                "lats": lat,
                "lons": lon,
                "winds": wind_ms_from_ibtracs(row),
            }
    return {
        sid: [values[key] for key in sorted(values, key=parse_time)]
        for sid, values in tracks.items()
    }


def load_post_tracks(path: Path, wanted_numbers: set[str]) -> dict[str, list[dict[str, object]]]:
    tracks: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    with path.open("r", encoding="gb18030", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            number = row["台風番号"].strip()
            if number not in wanted_numbers:
                continue
            try:
                timestamp = datetime(
                    int(row["年"]), int(row["月"]), int(row["日"]), int(row["時（UTC）"]), tzinfo=UTC
                )
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                wind_kt = float(row["最大風速"])
            except (ValueError, TypeError):
                continue
            time_text = iso_utc(timestamp)
            tracks[number][time_text] = {
                "times": time_text,
                "lats": lat,
                "lons": lon,
                "winds": wind_kt * KNOT_TO_MS,
            }
    return {
        number: [values[key] for key in sorted(values, key=parse_time)]
        for number, values in tracks.items()
    }


def write_csv(path: Path, rows: Iterable[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\r\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main_rows(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{
        "z_id": event["z_id"],
        "coupling_type": event["coupling_type"],
        "eq_time": event["eq_time"],
        "eq_lat": fmt(float(event["eq_lat"])),
        "eq_lon": fmt(float(event["eq_lon"])),
        "Mw": fmt(float(event["Mw"]), 3),
        "tc_time": event["tc_time"],
        "tc_lat": fmt(float(event["tc_lat"])),
        "tc_lon": fmt(float(event["tc_lon"])),
        "wind_ms": fmt(float(event["wind_ms"]), 6),
        "dt_hours": fmt(float(event["dt_hours"]), 6),
        "distance_km": fmt(float(event["distance_km"]), 6),
        "R34_km": fmt(float(event["R34_km"]), 6),
    } for event in events]


def track_rows(
    events: list[dict[str, object]],
    pre_tracks: dict[str, list[dict[str, object]]],
    post_tracks: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    output = []
    missing = []
    for event in events:
        source = pre_tracks if event["period"] == "pre2000" else post_tracks
        points = source.get(str(event["track_key"]), [])
        if not points:
            missing.append({"z_id": event["z_id"], "track_key": event["track_key"]})
            continue
        for point in points:
            output.append({
                "z_id": event["z_id"],
                "coupling_type": event["coupling_type"],
                "times": point["times"],
                "lats": fmt(float(point["lats"])),
                "lons": fmt(float(point["lons"])),
                "winds": fmt(point["winds"], 6),
            })
    if missing:
        raise ValueError(f"缺少完整台风轨迹：{missing}")
    return output


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_shapefile_set(source_shp: Path, destination_dir: Path) -> list[Path]:
    copied = []
    destination_dir.mkdir(parents=True, exist_ok=True)
    for path in source_shp.parent.glob(source_shp.stem + ".*"):
        destination = destination_dir / path.name
        copy_file(path, destination)
        copied.append(destination)
    return copied


def copy_loss_files(events: list[dict[str, object]], source_dir: Path, destination_dir: Path) -> list[Path]:
    copied = []
    destination_dir.mkdir(parents=True, exist_ok=True)
    for file_name in sorted({str(event["typhoon_file"]) for event in events}):
        source = source_dir / file_name
        if not source.is_file():
            raise FileNotFoundError(f"耦合台风损失源文件不存在：{source}")
        destination = destination_dir / file_name
        copy_file(source, destination)
        copied.append(destination)
    return copied


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(package_dir: Path) -> Path:
    manifest_path = package_dir / "原始数据" / "文件清单_SHA256.csv"
    rows = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        rows.append({
            "relative_path": str(path.relative_to(package_dir)).replace("\\", "/"),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    write_csv(manifest_path, rows, ["relative_path", "size_bytes", "sha256"])
    return manifest_path


def create_package(
    args: argparse.Namespace,
    events: list[dict[str, object]],
    main_output: Path,
    track_output: Path,
    audit: dict[str, object],
) -> Path:
    package_dir = args.output_dir / args.package_name
    code_dir = package_dir / "代码"
    raw_dir = package_dir / "原始数据"
    result_snapshots = raw_dir / "识别结果原始快照"
    catalog_dir = raw_dir / "原始目录源文件"
    loss_dir = raw_dir / "耦合台风损失事件CSV"
    map_dir = raw_dir / "NaturalEarth_日本行政区底图"
    for directory in (code_dir, result_snapshots, catalog_dir, loss_dir, map_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for source in PROCESSOR_SOURCES:
        if source.is_file():
            copy_file(source, code_dir / source.name)
    (code_dir / "requirements.txt").write_text(
        "# 汇总程序仅使用 Python 3.11+ 标准库。\n"
        "# 耦合识别程序另需 numpy、pyshp、shapely、matplotlib。\n",
        encoding="utf-8",
    )
    copy_file(README_SOURCE, package_dir / "README.md")
    copy_file(main_output, package_dir / main_output.name)
    copy_file(track_output, package_dir / track_output.name)

    copy_file(args.pre_result, result_snapshots / "1946_1999_日本内陆耦合识别结果.csv")
    copy_file(args.post_result, result_snapshots / "2001_2024_日本内陆耦合识别结果.csv")
    for source in (args.usgs_file, args.ibtracs_file, args.post_earthquake_file, args.post_typhoon_file):
        copy_file(source, catalog_dir / source.name)
    copy_loss_files(events, args.loss_dir, loss_dir)
    copy_shapefile_set(args.shapefile, map_dir)

    audit_path = raw_dir / "汇总处理审计.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_manifest(package_dir)
    return package_dir


def validate(
    events: list[dict[str, object]],
    main: list[dict[str, object]],
    tracks: list[dict[str, object]],
) -> dict[str, object]:
    errors = []
    if list(main[0]) != MAIN_COLUMNS:
        errors.append("main_header_order")
    if list(tracks[0]) != TRACK_COLUMNS:
        errors.append("track_header_order")
    if len(main) != len(events):
        errors.append("main_row_count")
    main_ids = [str(row["z_id"]) for row in main]
    if len(main_ids) != len(set(main_ids)):
        errors.append("duplicate_z_id")
    track_counts = Counter(str(row["z_id"]) for row in tracks)
    if set(track_counts) != set(main_ids):
        errors.append("track_z_id_coverage")
    if set(str(row["coupling_type"]) for row in main) - set(TYPE_MAP.values()):
        errors.append("invalid_coupling_type")
    if any(float(row["R34_km"]) <= 0 or float(row["distance_km"]) < 0 for row in main):
        errors.append("invalid_distance_or_R34")
    expected_order = sorted(main, key=lambda row: parse_time(str(row["eq_time"])), reverse=True)
    if [row["z_id"] for row in main] != [row["z_id"] for row in expected_order]:
        errors.append("main_not_latest_first")
    grouped = defaultdict(list)
    for row in tracks:
        grouped[str(row["z_id"])].append(parse_time(str(row["times"])))
    if any(values != sorted(values) for values in grouped.values()):
        errors.append("track_time_not_ascending")
    return {
        "main_row_count": len(main),
        "track_row_count": len(tracks),
        "unique_z_id_count": len(set(main_ids)),
        "coupling_type_counts": dict(Counter(str(row["coupling_type"]) for row in main)),
        "track_points_per_event": {
            "min": min(track_counts.values()),
            "max": max(track_counts.values()),
            "mean": round(sum(track_counts.values()) / len(track_counts), 3),
        },
        "recognized_pair_time_range_utc": [
            iso_utc(min(parse_time(str(row["eq_time"])) for row in main)),
            iso_utc(max(parse_time(str(row["eq_time"])) for row in main)),
        ],
        "nominal_study_scope": "1946-2026",
        "errors": errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pre-result", type=Path, default=DEFAULT_PRE_RESULT)
    parser.add_argument("--post-result", type=Path, default=DEFAULT_POST_RESULT)
    parser.add_argument("--ibtracs-file", type=Path, default=DEFAULT_IBTRACS)
    parser.add_argument("--usgs-file", type=Path, default=DEFAULT_USGS)
    parser.add_argument("--post-earthquake-file", type=Path, default=DEFAULT_POST_EARTHQUAKES)
    parser.add_argument("--post-typhoon-file", type=Path, default=DEFAULT_POST_TYPHOONS)
    parser.add_argument("--loss-dir", type=Path, default=DEFAULT_LOSS_DIR)
    parser.add_argument("--shapefile", type=Path, default=DEFAULT_SHAPEFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--package-name", default="网页功能准备包")
    parser.add_argument("--skip-package", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    required_files = (
        args.pre_result, args.post_result, args.ibtracs_file, args.usgs_file,
        args.post_earthquake_file, args.post_typhoon_file, args.shapefile,
    )
    for path in required_files:
        if not path.is_file():
            raise FileNotFoundError(path)
    if not args.loss_dir.is_dir():
        raise FileNotFoundError(args.loss_dir)
    if not README_SOURCE.is_file():
        raise FileNotFoundError(README_SOURCE)

    events = load_events(args.pre_result, args.post_result)
    pre_tracks = load_pre_tracks(
        args.ibtracs_file,
        {str(event["track_key"]) for event in events if event["period"] == "pre2000"},
    )
    post_tracks = load_post_tracks(
        args.post_typhoon_file,
        {str(event["track_key"]) for event in events if event["period"] == "post2000"},
    )
    main = main_rows(events)
    tracks = track_rows(events, pre_tracks, post_tracks)
    audit = validate(events, main, tracks)
    if audit["errors"]:
        raise ValueError(f"输出核验失败：{audit['errors']}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    main_output = args.output_dir / "耦合时刻信息.csv"
    track_output = args.output_dir / "满足耦合条件的完整台风事件集.csv"
    write_csv(main_output, main, MAIN_COLUMNS)
    write_csv(track_output, tracks, TRACK_COLUMNS)

    package_dir = None
    if not args.skip_package:
        package_dir = create_package(args, events, main_output, track_output, audit)

    print(json.dumps({
        **audit,
        "main_output": str(main_output),
        "track_output": str(track_output),
        "package_dir": str(package_dir) if package_dir else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
