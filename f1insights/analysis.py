"""Pure analysis functions on the tidy DataFrames of f1insights.data."""

import numpy as np
import pandas as pd


def _ns(dates: pd.Series) -> pd.Series:
    """Datetimes at nanosecond resolution, so merge_asof keys always match."""
    return dates.astype("datetime64[ns, UTC]")


def lap_end_times(laps: pd.DataFrame) -> pd.Series:
    """End of each lap: start + lap time, else the start of the driver's next lap."""
    end = laps["date_start"] + pd.to_timedelta(laps["LapTimeSeconds"], unit="s")
    next_start = laps.groupby("driver_number")["date_start"].shift(-1)
    return _ns(end.fillna(next_start))


def grid_positions(positions: pd.DataFrame) -> pd.Series:
    """Starting position per driver_number: the first position the timing reported."""
    return positions.sort_values("date").groupby("driver_number")["position"].first()


def position_by_lap(laps: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    """Position of every driver at the end of each lap, plus the grid as lap 0.

    The position feed only has a row when a position changes, so each lap end
    is matched to the latest earlier row of the same driver (merge_asof).
    """
    ends = laps.assign(date=lap_end_times(laps)).dropna(subset=["date"])
    ends = ends[["date", "driver_number", "acronym", "lap_number"]].sort_values("date")
    feed = positions[["date", "driver_number", "position"]].assign(date=_ns(positions["date"]))
    by_lap = pd.merge_asof(ends, feed.sort_values("date"), on="date", by="driver_number")
    grid = grid_positions(positions).rename("position").reset_index()
    names = laps[["driver_number", "acronym"]].drop_duplicates()
    grid = grid.merge(names, on="driver_number").assign(lap_number=0)
    columns = ["driver_number", "acronym", "lap_number", "position"]
    by_lap = pd.concat([grid[columns], by_lap[columns]], ignore_index=True)
    by_lap = by_lap.dropna(subset=["position"]).astype({"lap_number": "Int64", "position": "Int64"})
    return by_lap.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
