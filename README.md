# EQTyCatRisk

**EQ–Typhoon Catastrophe Risk** — a web platform for earthquake–typhoon compound hazard analysis.

The UI is in English. Two main modules:

| Route | Page | Purpose |
|-------|------|---------|
| `/events` | Coupled Event Detection | Browse historical EQ–TC coupling pairs (1946–2024), map epicenters & full typhoon tracks |
| `/risk` | Risk Assessment | 2018 Iburi East × Typhoon Jebi case: grid-level coupled loss (JPY) on Hokkaido |

---

## Features

### Coupled Event Detection
- 129 historical coupling events from local CSV
- Map: all epicenters + typhoon tracks; selected pair highlighted in red
- Track arrows point from earlier to later time
- Coupling types (no `EQ-TY` / `TY-EQ` abbreviations):
  - Earthquake followed by Typhoon
  - Typhoon followed by Earthquake
  - Simultaneous
- Side panel: coupling parameters + typhoon wind along track
- Fields include magnitude, wind, R34, focal depth (`depth_km`), distance, Δt

### Risk Assessment
- Historical case: **2018 Iburi East Earthquake × Typhoon Jebi (TY1821)**
- Grid map colored by `Coupled_Loss_with_Other_JPY` (not municipality choropleth)
- Fast Canvas rendering + compact grid JSON (async load)
- Hover a grid for loss (JPY), population, PGA, wind
- Loss probability charts (coupled / earthquake / typhoon)

---

## Tech stack

- **Vue 3** + TypeScript + Vite
- **Pinia** (state), **Vue Router**
- **Leaflet** (map), **ECharts** (charts)
- Data prep: **Python 3** (+ `openpyxl` for risk Excel inputs)

---

## Quick start

### Requirements
- Node.js 18+
- npm
- Python 3.10+ (only when rebuilding `public/data`)

### Install & run

```bash
npm install
npm run dev
```

Open the URL shown by Vite (typically `http://localhost:5173/`).

### Production build

```bash
npm run build
npm run preview
```

---

## Data pipeline

Raw tables live under `data/`. Build scripts write frontend JSON into `public/data/`.

### Rebuild coupling catalog (page 1)

```bash
python scripts/build-coupling-json.py
```

| Input (see script paths) | Output |
|--------------------------|--------|
| Coupling moment CSV (incl. `depth_km`, `coupling_type`) | `public/data/coupling-events.json` |
| Full typhoon track long table | (merged into the same JSON) |

### Rebuild risk case (page 2)

```bash
python scripts/build-risk-iburi-jebi.py
```

| Input | Output |
|-------|--------|
| Earthquake xlsx, Jebi track xlsx, Hokkaido exposure CSV (`Coupled_Loss_with_Other_JPY`) | `public/data/risk-iburi-jebi.json` (meta + regions) |
| | `public/data/risk-grid-cells.json` (compact loss grids) |

Optional (legacy municipality boundaries):

```bash
python scripts/build-hokkaido-choropleth.py
```

> **Note:** If you renamed folders under `data/` (e.g. to `Sample data 1` / `Sample data 2`), update the `DATA_DIR` / file names at the top of each script to match, then re-run.

### Served artifacts (`public/data/`)

| File | Role |
|------|------|
| `coupling-events.json` | Event catalog for `/events` |
| `risk-iburi-jebi.json` | Risk case metadata & chart context |
| `risk-grid-cells.json` | Grid losses for the Hokkaido map |
| `risk-loss/*.png` | Loss distribution figures |
| `hokkaido-municipalities.geojson` | Optional boundary layer (not used for current grid map) |

---

## Project structure

```
├── data/                      # Source CSV / XLSX / figures
├── public/data/               # Built JSON & static assets for the app
├── scripts/                   # Python builders
│   ├── build-coupling-json.py
│   ├── build-risk-iburi-jebi.py
│   └── build-hokkaido-choropleth.py
├── src/
│   ├── components/            # Map, charts, headers, layout
│   ├── views/                 # EventGeneration, RiskCalculation
│   ├── stores/                # Pinia event / risk store
│   ├── services/              # Fetch coupling & risk JSON
│   ├── utils/                 # Map layers, formatters, generators
│   └── router/
├── index.html
├── package.json
└── vite.config.ts
```

---

## Map notes

- Basemap: GSI Japan → Esri → OSM fallback (no API key)
- Attribution is shown in the panel footer (Leaflet corner attribution hidden)
- Default view focuses on the Japanese archipelago so distant typhoon legs do not over-zoom out
- Risk grids: single Canvas overlay; low-zoom thinning for performance

---

## License / data

Research prototype. Source hazard and exposure tables are project-provided; redistribute only under your data agreements.
