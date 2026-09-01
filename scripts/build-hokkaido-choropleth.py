"""
从北海道暴露 CSV 的 WKT 网格合并市町村面，输出 GeoJSON 供地图板块着色。
用法: python scripts/build-hokkaido-choropleth.py
输出: public/data/hokkaido-municipalities.geojson
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from shapely import wkt
from shapely.geometry import mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
EXPOSURE_CSV = ROOT / "data" / "第二页数据" / "北海道风险暴露数据_PGA_Zhao2016方法_含风速.csv"
OUT = ROOT / "public" / "data" / "hokkaido-municipalities.geojson"


def main() -> None:
    by_muni: dict[str, list] = defaultdict(list)

    with EXPOSURE_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("ADM2_JA") or row.get("laa") or "").strip()
            wkt_str = (row.get("WKT") or "").strip()
            if not name or not wkt_str:
                continue
            try:
                by_muni[name].append(wkt.loads(wkt_str))
            except Exception:
                continue

    features = []
    for name, geoms in sorted(by_muni.items()):
        if not geoms:
            continue
        merged = unary_union(geoms)
        # 约 200m 量级简化，减小体积并平滑边界
        merged = merged.simplify(0.002, preserve_topology=True)
        if merged.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"id": name, "name": name},
                "geometry": mapping(merged),
            }
        )

    collection = {"type": "FeatureCollection", "features": features}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"wrote {OUT} ({len(features)} municipalities, {size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
