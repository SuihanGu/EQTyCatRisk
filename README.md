# EQTyCatRisk

EQTyCatRisk is an English-language web application for Japanese
earthquake–typhoon simultaneous-event detection and residential catastrophe
risk visualization.

## Main functions

### 1. Coupled Event Detection

Route: '/events'

The page reads the Japan-only earthquake and typhoon catalogues, keeps only
'Simultaneous' pairs, and displays the selected epicenter, full typhoon track,
one track-direction arrow, coupling information, and the Japanese basemap with
English labels.

The recognition engine uses:

- Japan earthquake catalogue: 'data/Sample data 1/2KIK_earthquake_events_1997-2026_Japan.csv';
- Japan typhoon catalogue: 'data/Sample data 1/typhoon_events_2001-2026_Japan.csv';
- JST timestamps;
- absolute time difference no greater than 72 h;
- the catalogue R30 spatial condition;
- earthquake magnitude 'Mj >= 5.0';
- typhoon maximum wind speed '>= 17 kt';
- one-to-one matching between a typhoon and an earthquake, retaining the
  larger earthquake when multiple earthquakes qualify.

The 'Recognize' button runs the Python recognition engine. The two download
buttons export:

- 'Coupling moment information.csv';
- 'Complete set of typhoon events satisfying coupling conditions.csv'.

### 2. Coupled Risk Assessment

Route: '/risk'

The page provides two Chiba case studies:

1. 2005 Mj6.0 Chiba Earthquake and Typhoon BANYAN (No. 7);
2. 2004 Mj5.7 Chiba Earthquake and Typhoon MA-ON (No. 22).

For the selected case, the interface displays the epicenter, typhoon track,
PGA and maximum wind-speed heatmaps, separate legends, and the three
'without_Other' loss distributions. The 'Calculate' button executes the
repository-local scientific calculation and enables CSV downloads for
earthquake, typhoon, and coupled loss.

The calculation engine is the portable extraction of the loss-calculation
section of the 'visualization-loss-value-12' workflow. It reads the packaged
grid hazard field and Japanese residential exposure, applies the packaged
vulnerability curves and multi-hazard fragility surface, and performs 2,000
spatial Gaussian-copula Monte Carlo simulations. Results are calculated at
spatial Gaussian-copula Monte Carlo simulations. To reproduce v12 exactly,
the engine consumes the hidden random stream for 'with_Other' first and then
publishes only 'without_Other'. Results are calculated at runtime; the bundled
CSV/PNG files are reference outputs only.

## Requirements

- Node.js 18 or newer;
- npm;
- Python 3.10 or newer;
- Python packages: numpy, pandas, scipy, and matplotlib.

The frontend itself uses Vue 3, TypeScript, Vite, Pinia, Leaflet, and ECharts.
The included Windows launcher uses 'D:\\Anaconda\\python.exe' when it exists;
otherwise set 'EQTY_PYTHON' or make 'python' available on PATH.

## Local deployment

Open PowerShell in the repository root:

~~~powershell
npm install
npm run dev -- --host 127.0.0.1
~~~

Open the URL printed by Vite, normally:

- 'http://127.0.0.1:5173/events'
- 'http://127.0.0.1:5173/risk'

If Python is not available as 'python', set the executable explicitly:

~~~powershell
$env:EQTY_PYTHON = "C:/Path/to/python.exe"
npm run dev -- --host 127.0.0.1
~~~

Production build and local preview:

~~~powershell
npm run build
npm run preview
~~~

'npm run dev' is the full interactive mode because the Vite development
server provides the '/api/recognize' and '/api/calculate-loss' endpoints.
The static production build contains the packaged maps, event catalogue, and
loss figures, but a static host alone cannot execute Python calculations.

## Data and preprocessing

### Event recognition

The active recognition code is:

'data/Sample data 1/Preprocessing/code/run_japan_recognition.py'

Run it from the repository root:

~~~powershell
python "data/Sample data 1/Preprocessing/code/run_japan_recognition.py" --earthquake-file "data/Sample data 1/2KIK_earthquake_events_1997-2026_Japan.csv" --typhoon-file "data/Sample data 1/typhoon_events_2001-2026_Japan.csv" --output-dir "data/Sample data 1"
python scripts/build-coupling-json.py
~~~

The second command regenerates 'public/data/coupling-events.json', which is
the frontend event catalogue.

### Risk calculation

The active web runner is:

'data/Sample data 2/Preprocessing/run_v12_loss_calculation.py'

The compatibility launcher 'run_chiba_calculation.py' forwards to the same
engine. It calculates only the 270 non-Other vulnerability IDs and writes
three CSV distributions plus three PNG distributions into
'data/Sample data 2/risk-loss/' and, during a web request, into
'public/data/risk-loss/'. It has no dependency on the original local F: drive
paths.

Run a packaged case directly from the repository root:

~~~powershell
python "data/Sample data 2/Preprocessing/run_v12_loss_calculation.py" --case 2005
python "data/Sample data 2/Preprocessing/run_v12_loss_calculation.py" --case 2004
~~~

The case definitions are in
'data/Sample data 2/Preprocessing/cases.json'. A new event can be validated by
adding a case entry or by supplying the input paths directly:

~~~powershell
python "data/Sample data 2/Preprocessing/run_v12_loss_calculation.py" `
  --grid-file "path/to/event_grid.csv" `
  --exposure-file "path/to/region_exposure.csv" `
  --output-stem "MyEvent" `
  --wind-column "max_10min_mean_wind_speed_mps" `
  --pga-column "PGA" `
  --sequence simultaneous
~~~

The grid must contain 'Unique_ID', 'longitude', 'latitude', a wind-speed
column in m/s, and PGA in gal. The exposure table must contain
'Unique_ID', 'Vulner_ID_y', and 'value_split' in JPY. The model assets are
kept in 'data/Sample data 2/Preprocessing/model/'. The output CSV column
'loss_oku' is loss in 100 million JPY, and every run records its inputs,
seed, sample count, random-stream order, and output names in a manifest JSON.
The coupled MDR follows v12's signed 3-D interaction surface:
`clip(EQ_MDR + interaction, 0, 1)`. Therefore, a coupled loss lower than
pure earthquake loss is possible when the fitted interaction term is negative;
the engine does not replace this scientific rule with an artificial
`max(EQ, Coupled)` operation.

The risk-grid inputs used by the interface are:

- 'public/data/risk-grid-cells-2004.json';
- 'public/data/risk-grid-cells-2005.json'.

The case metadata is stored in 'public/data/risk-cases.json'.

## Repository structure

~~~text
data/
  Sample data 1/              Japan catalogues and recognition outputs
  Sample data 2/              Chiba risk outputs and calculation inputs
    Preprocessing/            Reproducible recognition/loss engines and models
public/data/                  Frontend JSON, maps, grids, and loss figures
scripts/                      Dataset-to-frontend JSON builders
src/                          Vue application source
docs/                         Architecture and workflow documentation
~~~

## GitHub deployment notes

This repository is ready to be committed to GitHub as a source repository.
Do not commit 'node_modules/' or 'dist/'; both are reproducible from the
commands above and are excluded by '.gitignore'.

For a server that supports the interactive buttons, deploy the repository on
a machine with Node.js and Python, then run:

~~~powershell
npm install
npm run dev -- --host 0.0.0.0
~~~

For GitHub Pages or another static host, run 'npm run build' and publish the
generated 'dist/' directory. Static hosting can display the packaged
catalogue, maps, heatmaps, and loss figures, but it cannot run the Python
recognition or risk endpoint. Those buttons require the Vite server (or a
separate backend deployment).

## Scope of the packaged release

The package contains the data required by the current Japan-only web release.
The old Hokkaido, Niigata, global IBTrACS, USGS, backup, and temporary build
artefacts are intentionally excluded because they are not used by the current
interface and would make the GitHub package inconsistent or unnecessarily
large.

## License

MIT License. See 'LICENSE'.

---

## Details of Exposure Matching and Vulnerability Surface Modeling

### 1. Exposure

#### E — Exposure

The `Exposure/` directory provides residential exposure data for the five prefectures used in the paper: Chiba.

The exposure data are located at: `EQTyCatRisk-main\\data\\Exposure`

For every prefecture, the `Chiba Grid ID` file contains the identifier and coordinates of each 1 km × 1 km grid cell. The corresponding `Chiba Grid Value` file contains the aggregated residential value for each grid identifier and structural class (`vulner_ID`). Exposure values are expressed in **Japanese yen (JPY)**.

#### Residential structure classification

The redundant `vulnerability_ID` field is intentionally omitted from this reference table.

| vulner_ID | structural_type | construction_year | storey | occupancy |
|---:|---|---|---|---|
| 1 | Wood | 1925_1990 | 2_3 | resident |
| 4 | Wood | 1925_1990 | 1 | resident |
| 7 | Wood | 1925_1990 | 4_7 | resident |
| 10 | Wood | 1925_1990 | 8_14 | resident |
| 13 | Wood | 1925_1990 | 15_ | resident |
| 16 | Wood | 1991_1999 | 2_3 | resident |
| 19 | Wood | 1991_1999 | 1 | resident |
| 22 | Wood | 1991_1999 | 4_7 | resident |
| 25 | Wood | 1991_1999 | 8_14 | resident |
| 28 | Wood | 1991_1999 | 15_ | resident |
| 31 | Wood | 2000_2010 | 2_3 | resident |
| 34 | Wood | 2000_2010 | 1 | resident |
| 37 | Wood | 2000_2010 | 4_7 | resident |
| 40 | Wood | 2000_2010 | 8_14 | resident |
| 43 | R_C | 2000_2010 | 15_ | resident |
| 46 | R_C | 2011_ | 2_3 | resident |
| 49 | R_C | 2011_ | 1 | resident |
| 52 | R_C | 2011_ | 4_7 | resident |
| 55 | R_C | 2011_ | 8_14 | resident |
| 58 | R_C | 2011_ | 15_ | resident |
| 61 | R_C | 1925_1990 | 2_3 | resident |
| 64 | R_C | 1925_1990 | 1 | resident |
| 67 | R_C | 1925_1990 | 4_7 | resident |
| 70 | R_C | 1925_1990 | 8_14 | resident |
| 73 | R_C | 1925_1990 | 15_ | resident |
| 76 | R_C | 1991_1999 | 2_3 | resident |
| 79 | R_C | 1991_1999 | 1 | resident |
| 82 | R_C | 1991_1999 | 4_7 | resident |
| 85 | R_C | 1991_1999 | 8_14 | resident |
| 88 | R_C | 1991_1999 | 15_ | resident |
| 91 | R_C | 2000_2010 | 2_3 | resident |
| 94 | R_C | 2000_2010 | 1 | resident |
| 97 | R_C | 2000_2010 | 4_7 | resident |
| 100 | R_C | 2000_2010 | 8_14 | resident |
| 103 | Steel | 2000_2010 | 15_ | resident |
| 106 | Steel | 2011_ | 2_3 | resident |
| 109 | Steel | 2011_ | 1 | resident |
| 112 | Steel | 2011_ | 4_7 | resident |
| 115 | Steel | 2011_ | 8_14 | resident |
| 118 | Steel | 2011_ | 15_ | resident |
| 121 | Steel | 1925_1990 | 2_3 | resident |
| 124 | Steel | 1925_1990 | 1 | resident |
| 127 | Steel | 1925_1990 | 4_7 | resident |
| 130 | Steel | 1925_1990 | 8_14 | resident |
| 133 | Steel | 1925_1990 | 15_ | resident |
| 136 | Steel | 1991_1999 | 2_3 | resident |
| 139 | Steel | 1991_1999 | 1 | resident |
| 142 | Steel | 1991_1999 | 4_7 | resident |
| 145 | Steel | 1991_1999 | 8_14 | resident |
| 148 | Steel | 1991_1999 | 15_ | resident |
| 151 | Steel | 2000_2010 | 2_3 | resident |
| 154 | Steel | 2000_2010 | 1 | resident |
| 157 | Steel | 2000_2010 | 4_7 | resident |
| 160 | Steel | 2000_2010 | 8_14 | resident |
| 163 | Masonry | 2000_2010 | 15_ | resident |
| 166 | Masonry | 2011_ | 2_3 | resident |
| 169 | Masonry | 2011_ | 1 | resident |
| 172 | Masonry | 2011_ | 4_7 | resident |
| 175 | Masonry | 2011_ | 8_14 | resident |
| 178 | Masonry | 2011_ | 15_ | resident |
| 181 | Masonry | 1925_1990 | 2_3 | resident |
| 184 | Masonry | 1925_1990 | 1 | resident |
| 187 | Masonry | 1925_1990 | 4_7 | resident |
| 190 | Masonry | 1925_1990 | 8_14 | resident |
| 193 | Masonry | 1925_1990 | 15_ | resident |
| 196 | Masonry | 1991_1999 | 2_3 | resident |
| 199 | Masonry | 1991_1999 | 1 | resident |
| 202 | Masonry | 1991_1999 | 4_7 | resident |
| 205 | Masonry | 1991_1999 | 8_14 | resident |
| 208 | Masonry | 1991_1999 | 15_ | resident |
| 211 | Masonry | 2000_2010 | 2_3 | resident |
| 214 | Masonry | 2000_2010 | 1 | resident |
| 217 | Masonry | 2000_2010 | 4_7 | resident |
| 220 | Masonry | 2000_2010 | 8_14 | resident |
| 283 | Wood | 2000_2010 | 15_ | resident |
| 286 | Wood | 2011_ | 2_3 | resident |
| 289 | Wood | 2011_ | 1 | resident |
| 292 | Wood | 2011_ | 4_7 | resident |
| 295 | Wood | 2011_ | 8_14 | resident |
| 298 | Wood | 2011_ | 15_ | resident |

### 2. Vulnerability

The vulnerability surfaces are developed using OpenSees. The publicly available Dynamic Analysis of 2-Story Moment Frame example [1] is adopted as the reference model. This example represents a two-story, single-bay steel moment-resisting frame. By modifying the material definitions in OpenSees, separate models are constructed for wood, steel, reinforced concrete (RC), and masonry structures.

The seismic input is the ground-motion record obtained at K-NET station MYG004 during the 2011 Great East Japan Earthquake. Wind inputs are based on the wind spectrum recommended by the Architectural Institute of Japan (AIJ).

The ground-motion record is amplitude-scaled to peak ground acceleration levels of 0, 0.5, 1.0, 1.5, and 2.0 g. Wind inputs are specified at mean wind speeds of 0, 15, 30, 45, and 60 m/s.

The vulnerability surfaces are constructed from the structural responses under different combinations of earthquake and wind loading. The resulting surfaces are illustrated in [`data/Vulnerability/data.png`](data/Vulnerability/data.png).

## Reference

[1] OpenSeesWiki, Dynamic Analysis of 2-Story Moment Frame.
<https://opensees.berkeley.edu/wiki/index.php?title=Dynamic_Analysis_of_2-Story_Moment_Frame>

For the numerical representation of exposure and vulnerability, refer to [`data/Sample data 2/Preprocessing/run_v12_loss_calculation.py`](data/Sample%20data%202/Preprocessing/run_v12_loss_calculation.py). This script documents the exposure-value mapping, vulnerability parameters, and numerical outputs used in the loss-calculation workflow.

The script can be used as a reference when reproducing or extending the quantified exposure and vulnerability results for alternative coupled events.
