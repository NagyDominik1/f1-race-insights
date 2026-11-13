"""Tests of the pure transforms with raw 2024 Hungarian GP race fixtures."""

import pandas as pd
from pandas.api import types

from f1insights import data


def test_drivers_columns_and_colours(drivers):
    assert list(drivers.columns) == [
        "driver_number", "acronym", "full_name", "team_name", "team_colour"
    ]
    assert len(drivers) == 20
    assert drivers["driver_number"].dtype == "Int64"
    assert drivers["driver_number"].is_unique
    assert types.is_string_dtype(drivers["acronym"])
    assert drivers["team_colour"].str.fullmatch("#[0-9A-F]{6}").all()
    mclaren = drivers.set_index("acronym").loc[["NOR", "PIA"]]
    assert mclaren["team_name"].tolist() == ["McLaren", "McLaren"]
    assert mclaren["team_colour"].tolist() == ["#FF8000", "#FF8000"]


def test_drivers_missing_values_get_fallbacks():
    raw = [{"driver_number": 99, "name_acronym": None, "team_colour": None}]
    drivers = data.drivers_from_raw(raw)
    assert drivers.loc[0, "acronym"] == "99"
    assert drivers.loc[0, "team_colour"] == data.FALLBACK_COLOUR
    assert pd.isna(drivers.loc[0, "team_name"])


def test_laps_columns_and_dtypes(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    assert list(laps.columns) == data.LAP_COLUMNS
    assert laps["driver_number"].dtype == "Int64"
    assert laps["lap_number"].dtype == "Int64"
    assert laps["is_pit_out_lap"].dtype == "boolean"
    for column in ["LapTimeSeconds", "Sector1Seconds", "Sector2Seconds", "Sector3Seconds"]:
        assert laps[column].dtype == "float64"
    assert types.is_string_dtype(laps["acronym"])
    assert isinstance(laps["date_start"].dtype, pd.DatetimeTZDtype)
    assert str(laps["date_start"].dt.tz) == "UTC"


def test_laps_one_row_per_driver_and_lap(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    assert len(laps) == len(raw_laps) == 140
    assert not laps.duplicated(["driver_number", "lap_number"]).any()
    per_driver = laps.groupby("acronym")["lap_number"].agg(["min", "max", "count"])
    assert per_driver.loc["NOR"].tolist() == [1, 70, 70]
    assert per_driver.loc["PIA"].tolist() == [1, 70, 70]


def test_laps_acronyms_merged_correctly(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    pairs = laps[["driver_number", "acronym"]].drop_duplicates()
    assert dict(zip(pairs["driver_number"], pairs["acronym"])) == {4: "NOR", 81: "PIA"}
    assert (laps["team_name"] == "McLaren").all()


def test_lap_times_plausible_for_hungaroring(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    times = laps["LapTimeSeconds"].dropna()
    assert len(times) >= 130
    assert times.between(75, 130).all()
    # OpenF1 lost NOR's first sector on lap 26: it must stay null, not become 0
    lap_26 = laps.loc[(laps["acronym"] == "NOR") & (laps["lap_number"] == 26)].iloc[0]
    assert pd.isna(lap_26["Sector1Seconds"]) and lap_26["LapTimeSeconds"] > 75
    sectors = laps[["Sector1Seconds", "Sector2Seconds", "Sector3Seconds"]]
    complete = sectors.notna().all(axis=1) & laps["LapTimeSeconds"].notna()
    difference = sectors[complete].sum(axis=1) - laps.loc[complete, "LapTimeSeconds"]
    assert difference.abs().max() < 0.01


def test_laps_unknown_driver_gets_number_as_acronym(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers.loc[drivers["acronym"] != "PIA"])
    unknown = laps.loc[laps["driver_number"] == 81]
    assert (unknown["acronym"] == "81").all()
    assert unknown["team_name"].isna().all()


def test_stints_columns_and_dtypes(raw_stints, drivers):
    stints = data.stints_from_raw(raw_stints, drivers)
    assert list(stints.columns) == data.STINT_COLUMNS
    for column in ["driver_number", "stint_number", "lap_start", "lap_end", "tyre_age_at_start"]:
        assert stints[column].dtype == "Int64"
    assert types.is_string_dtype(stints["compound"])
    assert set(stints["compound"]) <= {"SOFT", "MEDIUM", "HARD"}
    assert set(stints["acronym"]) == {"NOR", "PIA"}


def test_stints_cover_consecutive_laps_without_overlap(raw_stints, drivers):
    stints = data.stints_from_raw(raw_stints, drivers)
    assert (stints["lap_start"] <= stints["lap_end"]).all()
    previous_end = stints.groupby("driver_number")["lap_end"].shift()
    is_first = previous_end.isna()
    assert (stints.loc[is_first, "lap_start"] == 1).all()
    assert (stints.loc[~is_first, "lap_start"] == previous_end[~is_first] + 1).all()
    assert (stints.groupby("driver_number")["lap_end"].max() == 70).all()


def test_empty_responses_keep_the_schema(drivers):
    assert list(data.drivers_from_raw([]).columns) == list(data.DRIVER_RENAMES.values())
    laps = data.laps_from_raw([], drivers)
    assert laps.empty and list(laps.columns) == data.LAP_COLUMNS
    stints = data.stints_from_raw([], drivers)
    assert stints.empty and list(stints.columns) == data.STINT_COLUMNS


def test_meetings_exclude_testing_and_cancelled_and_sort_by_date():
    raw = [
        {"meeting_key": 3, "meeting_name": "B Grand Prix", "date_start": "2024-03-08T10:00:00+00:00",
         "date_end": "2024-03-10T16:00:00+00:00", "year": 2024, "is_cancelled": False},
        {"meeting_key": 1, "meeting_name": "Pre-Season Testing", "date_start": "2024-02-21T07:00:00+00:00",
         "date_end": "2024-02-23T16:00:00+00:00", "year": 2024, "is_cancelled": False},
        {"meeting_key": 2, "meeting_name": "A Grand Prix", "date_start": "2024-03-01T10:00:00+00:00",
         "date_end": "2024-03-03T16:00:00+00:00", "year": 2024},
        {"meeting_key": 4, "meeting_name": "C Grand Prix", "date_start": "2024-03-15T10:00:00+00:00",
         "date_end": "2024-03-17T16:00:00+00:00", "year": 2024, "is_cancelled": True},
    ]
    meetings = data.meetings_from_raw(raw)
    assert meetings["meeting_key"].tolist() == [2, 3]
    assert list(meetings.columns) == data.MEETING_COLUMNS
    assert isinstance(meetings["date_start"].dtype, pd.DatetimeTZDtype)
