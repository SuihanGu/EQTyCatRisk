"""
将 data/第一页的数据 下两份 CSV 合并为前端可用的 JSON。
用法: python scripts/build-coupling-json.py
输出: public/data/coupling-events.json
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "第一页的数据"
MOMENT_CSV = DATA_DIR / "第一页_耦合时刻信息（新）.csv"
TRACK_CSV = DATA_DIR / "满足耦合条件的完整台风事件集.csv"
OUT = ROOT / "public" / "data" / "coupling-events.json"


def to_float(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def format_coupling_type(raw: str | None) -> str | None:
    """统一展示名：禁止 EQ-TY / TY-EQ 缩写。"""
    if not raw:
        return None
    key = raw.strip().lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    mapping = {
        "eq ty": "Earthquake followed by Typhoon",
        "ty eq": "Typhoon followed by Earthquake",
        "earthquake followed by typhoon": "Earthquake followed by Typhoon",
        "typhoon followed by earthquake": "Typhoon followed by Earthquake",
        "simultaneous": "Simultaneous",
    }
    if key in mapping:
        return mapping[key]
    # 兜底：首字母大写，避免再出现全大写缩写
    return raw.strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if not MOMENT_CSV.exists():
        raise FileNotFoundError(MOMENT_CSV)

    moments = read_csv(MOMENT_CSV)
    track_rows = read_csv(TRACK_CSV)

    tracks: dict[str, list[dict]] = defaultdict(list)
    winds_by_zid: dict[str, list[float]] = defaultdict(list)

    for row in track_rows:
        zid = (row.get("z_id") or "").strip()
        if not zid:
            continue
        lat, lon = to_float(row.get("lats")), to_float(row.get("lons"))
        if lat is None or lon is None:
            continue
        wind = to_float(row.get("winds"))
        pt: dict = {"lat": round(lat, 4), "lng": round(lon, 4)}
        if wind is not None:
            pt["windMs"] = round(wind, 2)
            winds_by_zid[zid].append(round(wind, 2))
        times = (row.get("times") or "").strip()
        if times:
            pt["time"] = times
        tracks[zid].append(pt)

    events = []
    for idx, row in enumerate(moments):
        zid = (row.get("z_id") or "").strip()
        mw, wind_ms = to_float(row.get("Mw")), to_float(row.get("wind_ms"))
        eq_lat, eq_lon = to_float(row.get("eq_lat")), to_float(row.get("eq_lon"))
        tc_lat, tc_lon = to_float(row.get("tc_lat")), to_float(row.get("tc_lon"))
        if not zid or None in (mw, wind_ms, eq_lat, eq_lon):
            continue

        path = list(tracks.get(zid, []))
        if not path and tc_lat is not None and tc_lon is not None:
            path = [{"lat": round(tc_lat, 4), "lng": round(tc_lon, 4), "windMs": round(wind_ms, 2)}]

        eq_time = (row.get("eq_time") or "").strip()
        year = int(eq_time[:4]) if len(eq_time) >= 4 and eq_time[:4].isdigit() else None
        depth_km = to_float(row.get("depth_km"))

        events.append(
            {
                "id": zid,
                "basin": "WP",
                "couplingType": format_coupling_type(row.get("coupling_type")),
                "magnitude": round(mw, 3),
                "depthKm": round(depth_km, 2) if depth_km is not None else None,
                "windMs": round(wind_ms, 2),
                "windSpeed": round(wind_ms * 3.6, 1),
                "pressureHpa": None,
                "dtHours": to_float(row.get("dt_hours")),
                "distanceKm": to_float(row.get("distance_km")),
                "r34Km": to_float(row.get("R34_km")),
                "eqTime": eq_time,
                "tcTime": (row.get("tc_time") or "").strip(),
                "year": year,
                "epicenter": {"lat": round(eq_lat, 4), "lng": round(eq_lon, 4)},
                "typhoonAtCoupling": None
                if tc_lat is None or tc_lon is None
                else {
                    "lat": round(tc_lat, 4),
                    "lng": round(tc_lon, 4),
                    "windMs": round(wind_ms, 2),
                },
                "typhoonPath": path,
                "typhoonWinds": winds_by_zid.get(zid, []),
                "index": idx,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 3, "count": len(events), "source": "csv", "events": events}
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({len(events)} events, tracks for {len(tracks)} z_id)")


if __name__ == "__main__":
    main()
