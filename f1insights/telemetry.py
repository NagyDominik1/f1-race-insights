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
