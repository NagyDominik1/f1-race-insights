"""Pure analysis functions on the tidy DataFrames of f1insights.data.

Everything here takes DataFrames and returns DataFrames, numbers or strings:
no network, no Streamlit, no hidden state, so every function is unit tested.
"""

import numpy as np
import pandas as pd
from scipy import stats

SLOW_LAP_FACTOR = 1.07
FUEL_SECONDS_PER_LAP = 0.035
MIN_STINT_LAPS = 5
BOOTSTRAP_RESAMPLES = 5000
BOOTSTRAP_SEED = 42
PERIOD_COLUMNS = ["kind", "start", "end", "lap_start", "lap_end"]
REASONS = ["no lap time", "lap 1", "pit in-lap", "pit out-lap", "safety car or red flag", "slower than 107%"]


def format_lap_time(seconds: float) -> str:
    """Seconds as a lap time: 81.712 -> "1:21.712"."""
    if pd.isna(seconds):
        return "–"
    minutes, rest = divmod(round(float(seconds), 3), 60)
    return f"{int(minutes)}:{rest:06.3f}"


def _ns(dates: pd.Series) -> pd.Series:
    """Datetimes at nanosecond resolution, so merge_asof keys always match."""
    return dates.astype("datetime64[ns, UTC]")


# --- race order ------------------------------------------------------------

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
    same_key = {"driver_number": "int64"}  # merge_asof needs identical key dtypes on both sides
    by_lap = pd.merge_asof(ends.astype(same_key), feed.sort_values("date").astype(same_key),
                           on="date", by="driver_number")
    grid = grid_positions(positions).rename("position").reset_index()
    names = laps[["driver_number", "acronym"]].drop_duplicates()
    grid = grid.merge(names, on="driver_number").assign(lap_number=0)
    columns = ["driver_number", "acronym", "lap_number", "position"]
    by_lap = pd.concat([grid[columns], by_lap[columns]], ignore_index=True)
    by_lap = by_lap.dropna(subset=["position"]).astype({"lap_number": "Int64", "position": "Int64"})
    return by_lap.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)


def classification(laps: pd.DataFrame, positions: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """One row per driver in finishing order: grid, finish, gained, laps, classified.

    finish is the official result when OpenF1 has one (it includes post-race
    penalties), else the last position on track. Drivers without a finishing
    position (DNF, DNS, DSQ) come last, ordered by laps completed.
    """
    table = laps.groupby("driver_number").agg(acronym=("acronym", "first"), laps=("lap_number", "max"))
    table["grid"] = grid_positions(positions)
    on_track = positions.sort_values("date").groupby("driver_number")["position"].last()
    official = results.set_index("driver_number")["position"] if not results.empty else None
    table["finish"] = official if official is not None else on_track
    table["classified"] = table["finish"].notna()
    table["gained"] = table["grid"] - table["finish"]
    table = table.sort_values(["classified", "finish", "laps"], ascending=[False, True, False])
    table["order"] = np.arange(1, len(table) + 1)
    return table.reset_index().astype({"grid": "Int64", "finish": "Int64", "gained": "Int64"})


# --- clean laps ------------------------------------------------------------

def neutralisations(race_control: pd.DataFrame) -> pd.DataFrame:
    """Safety car (SC), virtual safety car (VSC) and red flag (RED) periods.

    OpenF1 has no field for this, so the periods are read from the race control
    messages: a period starts at "SAFETY CAR DEPLOYED", "VIRTUAL SAFETY CAR
    DEPLOYED" or a red flag and ends at the next "TRACK CLEAR", at the next
    period of another kind, or at the chequered flag.
    """
    message = race_control["message"].fillna("").str.upper()
    flag, scope = race_control["flag"].fillna(""), race_control["scope"].fillna("")
    kind = np.select(
        [
            message.str.contains("VIRTUAL SAFETY CAR DEPLOYED"),
            message.str.contains("SAFETY CAR DEPLOYED"),
            flag == "RED",
            ((flag == "CLEAR") & (scope == "Track")) | (flag == "CHEQUERED"),
        ],
        ["VSC", "SC", "RED", "END"], default="",
    )
    events = race_control.assign(kind=kind).loc[kind != ""].sort_values("date", kind="stable")
    events = events.loc[events["kind"] != events["kind"].shift()]
    events = events.assign(
        start=events["date"], end=events["date"].shift(-1),
        lap_start=events["lap_number"], lap_end=events["lap_number"].shift(-1),
    )
    periods = events.loc[events["kind"] != "END", PERIOD_COLUMNS]
    periods = periods.fillna({"end": race_control["date"].max(), "lap_end": race_control["lap_number"].max()})
    return periods.reset_index(drop=True)


def _overlaps_any(start: pd.Series, end: pd.Series, periods: pd.DataFrame) -> np.ndarray:
    """True for each [start, end] interval that overlaps at least one period."""
    if periods.empty:
        return np.zeros(len(start), dtype=bool)
    lap_start, lap_end = _ns(start).to_numpy()[:, None], _ns(end).to_numpy()[:, None]
    period_start, period_end = _ns(periods["start"]).to_numpy(), _ns(periods["end"]).to_numpy()
    return ((lap_start < period_end) & (lap_end > period_start)).any(axis=1)


def clean_laps(
    laps: pd.DataFrame, pit_stops: pd.DataFrame, periods: pd.DataFrame,
    reference: str = "median", factor: float = SLOW_LAP_FACTOR,
) -> pd.DataFrame:
    """All laps with three extra columns: is_pit_in, reason and is_clean.

    A lap is clean (representative of race pace) unless one of these applies,
    checked in this order; reason holds the first that matches:
    no lap time, lap 1 (standing start), pit in-lap, pit out-lap, any part of
    the lap under safety car / virtual safety car / red flag, or slower than
    `factor` (107%) of the driver's reference lap.
    The reference is the driver's median over the laps that passed the earlier
    checks ("median", for races) or the driver's fastest such lap ("min", for
    qualifying, where most laps are deliberately slow). Clean laps have an
    empty reason. Nothing is dropped, so the UI can show what was filtered.
    """
    pit_in = pit_stops[["driver_number", "lap_number"]].drop_duplicates().assign(is_pit_in=True)
    laps = laps.merge(pit_in, on=["driver_number", "lap_number"], how="left")
    laps["is_pit_in"] = laps["is_pit_in"].fillna(False).astype(bool)
    time = laps["LapTimeSeconds"]
    conditions = [
        time.isna(),
        laps["lap_number"] == 1,
        laps["is_pit_in"],
        laps["is_pit_out_lap"].fillna(False).astype(bool),
        _overlaps_any(laps["date_start"], lap_end_times(laps), periods),
    ]
    reason = np.select(conditions, REASONS[:5], default="")
    candidate = time.where(reason == "")
    limit = candidate.groupby(laps["driver_number"]).transform(reference) * factor
    reason = np.where((reason == "") & (time > limit), REASONS[5], reason)
    return laps.assign(reason=reason, is_clean=reason == "")


def pace_stats(laps: pd.DataFrame) -> pd.DataFrame:
    """Per driver over clean laps: n, median, IQR, standard deviation and fastest lap."""
    clean = laps.loc[laps["is_clean"]]
    grouped = clean.groupby("acronym")["LapTimeSeconds"]
    table = grouped.agg(n="count", median="median", std="std", fastest="min")
    table["iqr"] = grouped.quantile(0.75) - grouped.quantile(0.25)
    return table[["n", "median", "iqr", "std", "fastest"]].sort_values("median").reset_index()


def pace_flow(laps: pd.DataFrame, drivers: int = 5, window: int = 5, points: int = 72) -> list[list[float]]:
    """Smoothed clean-lap series of the quickest drivers, for the abstract page backdrop.

    One list per driver (quickest median first), each `points` long and scaled
    to 0..1 over all of them together, so the lines keep their real relation.
    A centred rolling mean over `window` laps turns lap-to-lap noise into a
    flowing line. Returns [] when there are too few clean laps.
    """
    clean = laps.loc[laps["is_clean"]].sort_values("lap_number")
    names = pace_stats(laps).query("n >= @window")["acronym"].head(drivers)
    series = [
        clean.loc[clean["acronym"] == name, "LapTimeSeconds"].rolling(window, center=True, min_periods=1).mean()
        for name in names
    ]
    if not series:
        return []
    grid = np.linspace(0, 1, points)
    lines = np.array([np.interp(grid, np.linspace(0, 1, len(s)), s) for s in series])
    low, high = lines.min(), lines.max()
    return np.round((lines - low) / max(high - low, 1e-9), 3).tolist()


# --- tyres -----------------------------------------------------------------

def with_stints(laps: pd.DataFrame, stints: pd.DataFrame) -> pd.DataFrame:
    """Laps with stint_number, compound, stint_lap (1 = first lap of the stint) and tyre_age.

    Each lap is matched to the stint with the latest lap_start that is not
    after it (merge_asof by driver); laps beyond the stint's lap_end stay unmatched.
    """
    keys = {"driver_number": "int64", "lap_number": "int64"}
    left = laps.astype(keys).sort_values("lap_number")
    right = stints.dropna(subset=["lap_start"]).astype({"driver_number": "int64", "lap_start": "int64"})
    right = right[["driver_number", "stint_number", "compound", "lap_start", "lap_end", "tyre_age_at_start"]]
    merged = pd.merge_asof(left, right.sort_values("lap_start"), left_on="lap_number",
                           right_on="lap_start", by="driver_number")
    inside = merged["lap_number"] <= merged["lap_end"].fillna(np.inf)
    merged["stint_lap"] = (merged["lap_number"] - merged["lap_start"] + 1).where(inside)
    merged["tyre_age"] = merged["tyre_age_at_start"].fillna(0) + merged["stint_lap"] - 1
    merged[["stint_number", "compound"]] = merged[["stint_number", "compound"]].where(inside)
    merged = merged.drop(columns=["lap_start", "lap_end", "tyre_age_at_start"])
    merged = merged.astype({"driver_number": "Int64", "lap_number": "Int64"})
    return merged.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)


def degradation_laps(laps: pd.DataFrame, fuel_per_lap: float = 0.0) -> pd.DataFrame:
    """Laps used for the degradation fit: clean, in a stint, not the first lap of a stint.

    Adds "fit_seconds": the lap time, plus fuel_per_lap seconds for every lap
    already driven when the fuel correction is on. A car gets lighter and
    faster as it burns fuel, which hides tyre wear; adding the assumed gain
    back leaves the tyre effect.
    """
    use = laps.loc[laps["is_clean"] & (laps["stint_lap"] > 1)].copy()
    use["fit_seconds"] = use["LapTimeSeconds"] + fuel_per_lap * (use["lap_number"] - 1)
    return use


def _fit_stint(stint: pd.DataFrame) -> dict:
    """Least-squares line through one stint: slope with 95% CI, R² and the fitted range."""
    fit = stats.linregress(stint["tyre_age"].astype("float64"), stint["fit_seconds"])
    margin = stats.t.ppf(0.975, len(stint) - 2) * fit.stderr
    return {
        "n": len(stint), "slope": fit.slope, "ci_low": fit.slope - margin, "ci_high": fit.slope + margin,
        "r2": fit.rvalue**2, "intercept": fit.intercept,
        "age_min": float(stint["tyre_age"].min()), "age_max": float(stint["tyre_age"].max()),
    }


def degradation(laps: pd.DataFrame, fuel_per_lap: float = 0.0, min_laps: int = MIN_STINT_LAPS) -> pd.DataFrame:
    """Linear tyre degradation per driver and stint: lap time = intercept + slope × tyre age.

    slope is in seconds per lap; ci_low and ci_high are its 95% confidence
    interval (t distribution, n − 2 degrees of freedom); r2 is the share of
    lap-time variance the line explains. Stints with fewer than min_laps
    usable laps are skipped.
    """
    keys = ["driver_number", "acronym", "stint_number", "compound"]
    columns = [*keys, "n", "slope", "ci_low", "ci_high", "r2", "intercept", "age_min", "age_max"]
    use = degradation_laps(laps, fuel_per_lap)
    rows = [
        dict(zip(keys, key)) | _fit_stint(stint)
        for key, stint in use.groupby(keys)
        if len(stint) >= min_laps and stint["tyre_age"].nunique() > 2
    ]
    return pd.DataFrame(rows, columns=columns)


# --- head to head ----------------------------------------------------------

def lap_deltas(laps: pd.DataFrame, first: str, second: str) -> pd.DataFrame:
    """Laps where both drivers have a clean lap: lap_number, both times and delta.

    delta = first − second in seconds, so a negative delta means `first` was faster.
    """
    clean = laps.loc[laps["is_clean"] & laps["acronym"].isin([first, second])]
    wide = clean.pivot(index="lap_number", columns="acronym", values="LapTimeSeconds")
    wide = wide.reindex(columns=[first, second]).dropna()
    return wide.assign(delta=wide[first] - wide[second]).reset_index()


def bootstrap_median_ci(
    values: np.ndarray, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float, float]:
    """Median with a 95% bootstrap confidence interval: (median, low, high).

    The values are resampled with replacement `resamples` times; the interval
    is the 2.5th to 97.5th percentile of the resampled medians. The fixed seed
    makes the result reproducible.
    """
    values = np.asarray(values, dtype="float64")
    if len(values) == 0:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    samples = values[rng.integers(0, len(values), size=(resamples, len(values)))]
    low, high = np.percentile(np.median(samples, axis=1), [2.5, 97.5])
    return float(np.median(values)), float(low), float(high)


def best_lap_comparison(laps: pd.DataFrame, first: str, second: str) -> pd.DataFrame:
    """Best lap of two drivers side by side: rows Lap, Sector 1-3; columns first, second, gap.

    gap = first − second in seconds. The sectors are those of each driver's
    best lap, not their best individual sectors.
    """
    parts = ["LapTimeSeconds", "Sector1Seconds", "Sector2Seconds", "Sector3Seconds"]
    timed = laps.loc[laps["LapTimeSeconds"].notna() & laps["acronym"].isin([first, second])]
    best = timed.loc[timed.groupby("acronym")["LapTimeSeconds"].idxmin()].set_index("acronym")
    table = best.reindex([first, second])[parts].T
    table.index = ["Lap", "Sector 1", "Sector 2", "Sector 3"]
    return table.assign(gap=table[first] - table[second]).rename_axis("part").reset_index()


# --- overview --------------------------------------------------------------

def fastest_lap(laps: pd.DataFrame) -> pd.Series | None:
    """The fastest timed lap of the session (a row of laps), or None."""
    timed = laps.dropna(subset=["LapTimeSeconds"])
    timed = timed.loc[~timed["is_pit_out_lap"].fillna(False).astype(bool)]
    return None if timed.empty else timed.loc[timed["LapTimeSeconds"].idxmin()]


def race_story(
    table: pd.DataFrame, stats_table: pd.DataFrame, degradation_table: pd.DataFrame,
    pit_stops: pd.DataFrame, laps: pd.DataFrame,
) -> list[str]:
    """Three to five sentences about the race, built from computed numbers with fixed templates."""
    story = []
    classified = table.loc[table["classified"]]
    if not classified.empty:
        winner = classified.iloc[0]
        stops = int((pit_stops["driver_number"] == winner["driver_number"]).sum())
        grid = f" from P{winner['grid']} on the grid" if pd.notna(winner["grid"]) else ""
        story.append(f"{winner['acronym']} won{grid} with {stops} pit stop{'s' if stops != 1 else ''}.")
    if len(stats_table) >= 2:
        best, second = stats_table.iloc[0], stats_table.iloc[1]
        story.append(
            f"{best['acronym']} had the best median clean-lap pace at {format_lap_time(best['median'])}, "
            f"{second['median'] - best['median']:.3f} s per lap quicker than {second['acronym']}."
        )
    wearing = degradation_table.loc[degradation_table["ci_low"] > 0]
    if not wearing.empty:
        worst = wearing.loc[wearing["slope"].idxmax()]
        story.append(
            f"The steepest tyre degradation was {worst['acronym']}'s {str(worst['compound']).lower()} stint: "
            f"+{worst['slope']:.3f} s per lap over {int(worst['n'])} laps."
        )
    movers = classified.dropna(subset=["gained"])
    if not movers.empty and movers["gained"].max() > 0:
        mover = movers.loc[movers["gained"].idxmax()]
        story.append(
            f"{mover['acronym']} gained the most places: {int(mover['gained'])}, "
            f"from P{mover['grid']} to P{mover['finish']}."
        )
    quickest = fastest_lap(laps)
    if quickest is not None:
        story.append(
            f"{quickest['acronym']} set the fastest lap, {format_lap_time(quickest['LapTimeSeconds'])}, "
            f"on lap {quickest['lap_number']}."
        )
    return story
