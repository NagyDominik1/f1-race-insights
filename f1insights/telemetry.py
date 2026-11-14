"""Pure telemetry transforms: resampling, track outline, replay and ghost-lap data."""

import base64

import numpy as np
import pandas as pd


def seconds_since(dates: pd.Series | pd.DatetimeIndex, origin: pd.Timestamp) -> np.ndarray:
    """Seconds elapsed since origin as a float array (NaN for missing dates)."""
    return np.asarray((dates - origin) / pd.Timedelta(seconds=1), dtype="float64")


def time_grid(laps: pd.DataFrame, hz: float) -> pd.DatetimeIndex:
    """Evenly spaced UTC timestamps covering all timed laps (5 s before, 10 s after)."""
    if laps["date_start"].isna().all():
        return pd.DatetimeIndex([], tz="UTC")
    ends = laps["date_start"] + pd.to_timedelta(laps["LapTimeSeconds"].fillna(0), unit="s")
    start = laps["date_start"].min() - pd.Timedelta(seconds=5)
    end = ends.max() + pd.Timedelta(seconds=10)
    return pd.date_range(start.floor("s"), end.ceil("s"), freq=pd.Timedelta(seconds=1 / hz))


def resample_location(location: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Linearly interpolate (date, x, y) onto grid; no rows outside the car's own data.

    Downsampling ~3.7 Hz GPS to a shared grid lets every driver use one time
    axis; the renderer interpolates between grid points again.
    """
    if location.empty or len(grid) == 0:
        empty = np.array([], dtype="float32")
        return pd.DataFrame({"date": grid[:0], "x": empty, "y": empty})
    t = seconds_since(location["date"], grid[0])
    g = seconds_since(grid, grid[0])
    inside = (g >= t[0]) & (g <= t[-1])
    return pd.DataFrame({
        "date": grid[inside],
        "x": np.interp(g[inside], t, location["x"]).round().astype("float32"),
        "y": np.interp(g[inside], t, location["y"]).round().astype("float32"),
    })


BOX = 20000  # width of the normalised coordinate box; fits int16 with headroom


def clip_to_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Rows between start and end with a "t" column (seconds since start).

    Every numeric column is linearly interpolated at exactly start and end, so
    a lap begins at t = 0 and finishes at t = lap time whatever the sampling.
    Needs at least one sample on each side of the window (fetch with padding).
    """
    t = seconds_since(df["date"], start)
    duration = (end - start) / pd.Timedelta(seconds=1)
    inside = (t > 0) & (t < duration)
    new_t = np.concatenate([[0.0], t[inside], [duration]])
    columns = [c for c in df.columns if c != "date"]
    clipped = {c: np.interp(new_t, t, df[c].to_numpy(dtype="float64")) for c in columns}
    return pd.DataFrame({"t": new_t, **clipped})


def lap_fraction(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Share of the lap distance covered at each sample: 0 at the first, 1 at the last."""
    steps = np.hypot(np.diff(x, prepend=x[0]), np.diff(y, prepend=y[0]))
    distance = np.cumsum(steps)
    return distance / distance[-1]


def track_outline(lap_location: pd.DataFrame, points: int = 400) -> pd.DataFrame:
    """Track centre line from one lap: `points` rows (fraction, x, y) evenly spaced by distance."""
    x = lap_location["x"].to_numpy(dtype="float64")
    y = lap_location["y"].to_numpy(dtype="float64")
    own = lap_fraction(x, y)
    fraction = np.linspace(0, 1, points)
    return pd.DataFrame({
        "fraction": fraction, "x": np.interp(fraction, own, x), "y": np.interp(fraction, own, y),
    })


def _oriented(x: np.ndarray, y: np.ndarray, rotate: bool) -> tuple[np.ndarray, np.ndarray]:
    """Screen orientation: optional quarter turn, then y pointing down."""
    x, y = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
    return (y, x) if rotate else (x, -y)


def fit_to_box(x: np.ndarray, y: np.ndarray, box: int = BOX) -> dict:
    """Transform that fits a track into a box `box` wide, keeping the aspect ratio.

    A track that is taller than wide is turned by 90 degrees so it uses a
    landscape canvas better. Returns the parameters used by to_box.
    """
    rotate = bool(np.ptp(y) > np.ptp(x))
    u, v = _oriented(x, y, rotate)
    scale = box / np.ptp(u)
    return {
        "rotate": rotate, "u_min": float(u.min()), "v_min": float(v.min()), "scale": float(scale),
        "width": box, "height": int(round(np.ptp(v) * scale)),
    }


def to_box(x: np.ndarray, y: np.ndarray, fit: dict) -> tuple[np.ndarray, np.ndarray]:
    """Apply a fit_to_box transform; NaN stays NaN."""
    u, v = _oriented(x, y, fit["rotate"])
    return (u - fit["u_min"]) * fit["scale"], (v - fit["v_min"]) * fit["scale"]


# --- race replay -----------------------------------------------------------

MISSING = -32768  # int16 sentinel for "no position at this sample"


def encode_int16(values: np.ndarray) -> str:
    """Base64 of little-endian int16 values: a compact payload a browser reads as Int16Array."""
    return base64.b64encode(np.asarray(values).astype("<i2").tobytes()).decode("ascii")


def replay_tracks(race_location: pd.DataFrame, fit: dict, hz: float, smooth: int = 3) -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame]:
    """Box coordinates of every driver on one gap-free time grid: (grid, x, y), columns = driver_number.

    OpenF1 location timestamps jitter by about 0.1 s, which makes cars pulse
    along the track; a centred rolling mean over `smooth` samples evens that
    out (at 2 Hz it moves a car less than ~2 m sideways in a corner).
    """
    step = pd.Timedelta(seconds=1 / hz)
    grid = pd.date_range(race_location["date"].min(), race_location["date"].max(), freq=step)
    wide = race_location.pivot(index="date", columns="driver_number", values=["x", "y"]).reindex(grid)
    # samples without a full window (start, end, next to a gap) keep their raw value
    wide = wide.rolling(smooth, center=True).mean().fillna(wide)
    x, y = to_box(wide["x"].to_numpy(), wide["y"].to_numpy(), fit)
    columns = wide["x"].columns
    return grid, pd.DataFrame(x, index=grid, columns=columns), pd.DataFrame(y, index=grid, columns=columns)


def _interleave(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """x0, y0, x1, y1, ... as int16 with MISSING where a sample is NaN."""
    pairs = np.column_stack([x, y])
    return np.where(np.isnan(pairs), MISSING, np.round(pairs)).astype("int16").ravel()


def _per_driver(df: pd.DataFrame, columns: list[str]) -> dict:
    """{driver_number: [[row values], ...]} for a few columns, as plain Python lists."""
    return {int(number): group[columns].to_numpy().tolist() for number, group in df.groupby("driver_number")}


def replay_payload(
    race_location: pd.DataFrame, outline_lap: pd.DataFrame, laps: pd.DataFrame,
    positions: pd.DataFrame, stints: pd.DataFrame, pit_stops: pd.DataFrame,
    periods: pd.DataFrame, drivers: pd.DataFrame, classification: pd.DataFrame, hz: float,
) -> dict:
    """Everything the replay component needs, as one compact JSON-serialisable dict.

    Times are seconds since the first sample. Car paths are base64 int16 arrays
    on a shared grid (sample i is at i / hz seconds); events are short lists.
    """
    outline = track_outline(outline_lap, points=500)
    fit = fit_to_box(outline["x"], outline["y"])
    grid, x, y = replay_tracks(race_location, fit, hz)
    origin = grid[0]

    def seconds(dates: pd.Series) -> pd.Series:
        return pd.Series(seconds_since(dates, origin), index=dates.index).round(1)

    lap_starts = laps["date_start"].fillna(laps.groupby("lap_number")["date_start"].transform("min"))
    laps = laps.assign(t=seconds(lap_starts), end=seconds(lap_starts) + laps["LapTimeSeconds"].fillna(0))
    laps = laps.dropna(subset=["t"]).sort_values(["driver_number", "lap_number"])
    lap_times = {int(number): group["t"].tolist() for number, group in laps.groupby("driver_number")}
    last_lap_end = laps.groupby("driver_number")["end"].max()

    feed = positions.assign(t=seconds(positions["date"]).clip(lower=0), position=positions["position"].astype(int))
    stint_rows = stints.dropna(subset=["lap_start", "lap_end"]).assign(
        age=lambda d: d["tyre_age_at_start"].fillna(0))[["driver_number", "lap_start", "lap_end", "compound", "age"]]
    stint_rows = stint_rows.astype({"lap_start": int, "lap_end": int, "age": int, "compound": str})
    # OpenF1 stamps a pit stop when the car leaves the pit lane; pit_duration reaches back from there
    pits = pit_stops.dropna(subset=["pit_duration"]).assign(end=lambda d: seconds(d["date"]))
    pits = pits.assign(start=(pits["end"] - pits["pit_duration"]).round(1))

    position_feed, stint_lists, pit_lists = (
        _per_driver(feed, ["t", "position"]), _per_driver(stint_rows, ["lap_start", "lap_end", "compound", "age"]),
        _per_driver(pits, ["start", "end"]),
    )
    info = drivers.set_index("driver_number")
    retired = classification.loc[~classification["classified"], "driver_number"].tolist()
    cars = [
        {
            "n": int(number), "a": info.loc[number, "acronym"], "c": info.loc[number, "team_colour"],
            "team": info["team_name"].fillna("").loc[number],
            "xy": encode_int16(_interleave(x[number].to_numpy(), y[number].to_numpy())),
            "laps": lap_times.get(int(number), []), "pos": position_feed.get(int(number), []),
            "stints": stint_lists.get(int(number), []), "pits": pit_lists.get(int(number), []),
            "out": float(last_lap_end[number]) if number in retired and number in last_lap_end.index else None,
        }
        for number in x.columns if number in info.index
    ]
    track_x, track_y = to_box(outline["x"], outline["y"], fit)
    leader_laps = laps.groupby("lap_number")["t"].min()
    neutral = periods.assign(t0=seconds(periods["start"]), t1=seconds(periods["end"])) if not periods.empty else periods
    return {
        "hz": hz, "samples": len(grid), "duration": round((len(grid) - 1) / hz, 1),
        "width": fit["width"], "height": fit["height"],
        "track": {"x": np.round(track_x).astype(int).tolist(), "y": np.round(track_y).astype(int).tolist()},
        "lapStarts": leader_laps.tolist(), "totalLaps": int(laps["lap_number"].max()),
        "finish": float(laps.loc[laps["lap_number"] == laps["lap_number"].max(), "end"].min()),
        "periods": neutral[["t0", "t1", "kind"]].to_numpy().tolist() if not periods.empty else [],
        "cars": cars,
    }
