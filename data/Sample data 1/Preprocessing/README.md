# Coupled-event recognition

"run_japan_recognition.py" is the recognition engine used by the web
application.

## Inputs

- "data/Sample data 1/2KIK_earthquake_events_1997-2026_Japan.csv"
- "data/Sample data 1/typhoon_events_2001-2026_Japan.csv"

The Japan-only catalogues use JST. The typhoon catalogue stores maximum wind
speed in kt and 30KT long/short radii in km.

## Recognition rules

The current web release recognizes only "Simultaneous" pairs:

- absolute time difference <= 72 h;
- earthquake epicenter inside the catalogue R30 circle;
- earthquake magnitude "Mj >= 5.0";
- typhoon maximum wind speed ">= 17 kt";
- one typhoon event is matched to one earthquake, retaining the larger
  magnitude when multiple earthquakes satisfy the conditions.

The script writes:

- "Coupling moment information.csv"
- "Complete set of typhoon events satisfying coupling conditions.csv"

Run it from the repository root:

~~~powershell
python "data/Sample data 1/Preprocessing/code/run_japan_recognition.py" --earthquake-file "data/Sample data 1/2KIK_earthquake_events_1997-2026_Japan.csv" --typhoon-file "data/Sample data 1/typhoon_events_2001-2026_Japan.csv" --output-dir "data/Sample data 1"
python scripts/build-coupling-json.py
~~~
