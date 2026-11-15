# OpenF1 data notes

Findings of the data spike (2024 Hungarian GP, race session 9566 and qualifying 9562,
measured November 2026 against `https://api.openf1.org/v1`). They explain the
decisions in `f1insights/data.py`, `f1insights/telemetry.py` and `scripts/build_demo_data.py`.

## Access rules

| Finding | Consequence |
| --- | --- |
| Rate limit is 3 requests/second (HTTP 429 with `Retry-After: 1`). A burst of 40 requests got 34 rejections. | The client spaces requests 0.4 s apart and honours `Retry-After`. |
| `location?session_key=…` for a whole session returns HTTP 422 "too much data". | Telemetry is always fetched per driver. |
| Range filters work as `date>=…&date<=…`; the `+` of the UTC offset must be URL-encoded. | The client builds the query string itself (`{"date>": start, "date<": end}`). |
| A query without results is HTTP 404 `{"detail": "No results found."}`. | Treated as an empty list, never cached. |

## Endpoints

| Endpoint | Rows (race) | Raw size | Fetch time | Notes |
| --- | --- | --- | --- | --- |
| `location` (one driver, whole session) | 35 724 | 4.5 MB | 1.5-8 s | ~3.8 Hz (median gap 0.24 s, max 1.4 s). `x`, `y` in 1/10 m. 2 584 rows of `(0, 0, 0)` before the car goes live. |
| `location` (one lap window) | ~320 | 0.04 MB | 0.1 s | Lap length from summed steps: 4 300 m (track: 4 381 m). |
| `car_data` (one driver, whole session) | 34 680 | 5.7 MB | 2 s | ~3.7 Hz: speed, throttle, brake (0/100 only), gear, rpm, drs code. Timestamps differ from `location`. |
| `position` | 552 | 0.06 MB | <0.1 s | One row per position change. First row per driver = grid slot. |
| `race_control` | 75 | 0.02 MB | <0.1 s | Flags, safety car, DRS. `lap_number` is the leader's lap. |
| `pit` | 40 | 0.01 MB | <0.1 s | `lap_number` is the in-lap; `pit_duration` is pit-lane time. `stop_duration` is null in 2024. |
| `session_result` | 20 | <0.01 MB | <0.1 s | Official classification; `position` null for DNF. |
| `intervals` | 25 607 | 3.6 MB | 0.8 s | Gaps every ~4 s. Not used: gaps in the replay come from position only. |
| `starting_grid` | – | – | – | 404 for the race session; the grid is taken from `position`. |

All twenty drivers of a race at full rate would be ~90 MB of JSON and ~700 000 rows,
too much for Streamlit Community Cloud (about 1 GB of RAM) and for a browser payload.

## Decisions

- **Race replay: 2 Hz on a shared time grid.** Each driver is fetched separately,
  linearly interpolated onto one grid (`telemetry.resample_location`) and the raw rows
  are dropped immediately. 20 drivers × ~11 900 samples = 239 220 rows, 1.4 MB as
  parquet. At 2 Hz a car moves at most ~45 m between samples; the browser interpolates
  between them, so motion stays smooth while corners are cut by well under a car width
  at replay zoom levels.
- **Ghost lap: full rate, fastest lap only.** One lap is ~320 location rows and ~315
  car-data rows per driver, so nothing is thrown away where detail matters. Windows are
  padded by 1 s on both sides so the lap start and end can be interpolated exactly.
- **Location and car data are joined with `merge_asof`** (nearest earlier sample)
  because the two feeds are not sampled at the same instants.
- **Bulky telemetry is not written to the JSON disk cache.** The downsampled replay
  table of a finished race is cached once as parquet in `cache/derived/`.
- **First load of a non-demo race replay takes about half a minute** (20 sequential requests
  of 3-5 MB each); afterwards it is served from the parquet cache.
- **Demo weekend size:** 1.85 MB in `data/demo/` (target was < 20 MB).

## Data quality quirks

- `team_colour` comes without `#`, in mixed case, and can be missing → normalised to
  `#RRGGBB` with a grey fallback.
- The meeting list is not sorted by date and includes cancelled weekends and testing.
- Lap 1 of a pit-lane starter and the lap of a retirement have no lap time.
- A lap can have a valid lap time but a missing sector (NOR lap 26, sector 1).
- Outside races the "lap time" of a pit-out lap includes the time spent in the garage
  (up to 1 251 s in the demo qualifying).
- Lap `date_start` and the end of the previous lap differ by ~30 ms, and the nearest
  location sample can be 0.1-0.3 s away. Ghost-lap deltas are therefore accurate to
  roughly ±0.1 s inside the lap, while the final gap equals the official lap-time gap.
- **Location timestamps jitter by about 0.1 s.** Speed computed from consecutive position
  samples scatters by ±26% around the speed reported in `car_data` (same lap, same car),
  although the positions themselves lie on the track. The replay therefore applies a
  centred 3-sample rolling mean to the 2 Hz paths (cars would otherwise pulse along the
  track). The ghost lap does not use position timestamps for timing at all: elapsed time
  is rebuilt as distance / measured speed and scaled to the official lap time, and
  mini-sector gaps below 0.03 s are treated as even.
- The `date` of a pit stop is the moment the car leaves the pit lane; `pit_duration`
  reaches back from there (checked against the car's speed around NOR's first stop).
- Safety car periods are not a field: they are parsed from `race_control` messages
  ("SAFETY CAR DEPLOYED", "VIRTUAL SAFETY CAR DEPLOYED", flag `RED`) and end at the next
  "TRACK CLEAR". The 2024 Hungarian GP had none, so the parser is tested with messages
  copied from the 2025 British GP and the 2024 São Paulo GP.
- `position` reflects the order on track at the flag; `session_result` includes
  post-race penalties. The app prefers `session_result` and falls back to `position`.
