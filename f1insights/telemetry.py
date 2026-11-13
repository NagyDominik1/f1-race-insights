"""Pure telemetry transforms: resampling, track outline, replay and ghost-lap data."""

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
