"""Tests of the race-event and telemetry transforms (2024 Hungarian GP race fixtures)."""

import numpy as np
import pandas as pd

from conftest import load_fixture
from f1insights import data, telemetry


def test_positions_first_row_is_grid_and_last_is_finish(drivers):
    positions = data.positions_from_raw(load_fixture("position_nor_pia.json"), drivers)
    assert list(positions.columns) == data.POSITION_COLUMNS
    assert positions["position"].dtype == "Int64"
    assert positions["date"].is_monotonic_increasing
    by_driver = positions.groupby("acronym")["position"].agg(["first", "last"])
    assert by_driver.loc["NOR"].tolist() == [1, 2]
    assert by_driver.loc["PIA"].tolist() == [2, 1]


def test_race_control_columns_and_order():
    messages = data.race_control_from_raw(load_fixture("race_control.json"))
    assert list(messages.columns) == data.RACE_CONTROL_COLUMNS
    assert messages["lap_number"].dtype == "Int64"
    assert isinstance(messages["date"].dtype, pd.DatetimeTZDtype)
    assert messages["date"].is_monotonic_increasing
    assert (messages["flag"] == "CHEQUERED").sum() == 1


def test_pit_stops_report_the_in_lap(drivers):
    stops = data.pit_stops_from_raw(load_fixture("pit_nor_pia.json"), drivers)
    assert list(stops.columns) == data.PIT_COLUMNS
    assert stops.loc[stops["acronym"] == "NOR", "lap_number"].tolist() == [17, 45]
    assert stops["pit_duration"].between(15, 40).all()


def test_results_sorted_with_unclassified_last(drivers):
    results = data.results_from_raw(load_fixture("session_result.json"), drivers)
    assert list(results.columns) == data.RESULT_COLUMNS
    assert results["acronym"].head(3).tolist() == ["PIA", "NOR", "HAM"]
    last = results.iloc[-1]
    assert last["acronym"] == "GAS" and pd.isna(last["position"]) and last["dnf"]
    assert results["dnf"].dtype == "boolean"


def test_location_is_clean_and_covers_one_lap():
    raw = load_fixture("location_nor_fastest_lap.json")
    padded = [{"date": "2024-07-21T12:00:00+00:00", "x": 0, "y": 0}, *raw, raw[-1]]
    location = data.location_from_raw(padded)
    assert list(location.columns) == data.LOCATION_COLUMNS
    assert len(location) == len(raw)
    assert location["date"].is_monotonic_increasing and location["date"].is_unique
    metres = np.hypot(location["x"].diff(), location["y"].diff()).sum() / 10
    assert 4200 < metres < 4700  # the Hungaroring is 4381 m long, plus 2 s of padding


def test_car_data_ranges():
    car = data.car_data_from_raw(load_fixture("car_data_nor_fastest_lap.json"))
    assert list(car.columns) == data.CAR_DATA_COLUMNS
    assert car["speed"].between(50, 340).all()
    assert car["throttle"].between(0, 105).all()
    assert car["n_gear"].between(1, 8).all()


def test_fastest_lap_window(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    lap = data.fastest_lap_window(laps, 4)
    assert lap["lap_number"] == 50 and lap["seconds"] == 81.712
    assert (lap["end"] - lap["start"]).total_seconds() == 81.712
    without_start = laps.assign(date_start=laps["date_start"].where(laps["lap_number"] != 50))
    assert data.fastest_lap_window(without_start, 4)["lap_number"] != 50
    assert data.fastest_lap_window(laps, 99) is None


def test_time_grid_covers_all_laps_at_the_requested_rate(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    grid = telemetry.time_grid(laps, hz=2.0)
    assert (grid[1] - grid[0]).total_seconds() == 0.5
    assert grid[0] < laps["date_start"].min()
    assert grid[-1] > laps["date_start"].max() + pd.Timedelta(seconds=80)
    assert len(telemetry.time_grid(laps.assign(date_start=pd.NaT), hz=2.0)) == 0


def test_resample_location_interpolates_inside_the_data_only():
    start = pd.Timestamp("2024-07-21T13:00:00Z")
    location = pd.DataFrame({
        "date": start + pd.to_timedelta([1.0, 2.0, 4.0], unit="s"),
        "x": [0, 100, 300], "y": [0, -50, -150],
    })
    grid = pd.date_range(start, periods=12, freq="500ms")
    resampled = telemetry.resample_location(location, grid)
    assert resampled["date"].iloc[0] == start + pd.Timedelta(seconds=1)
    assert resampled["date"].iloc[-1] == start + pd.Timedelta(seconds=4)
    assert resampled["x"].tolist() == [0, 50, 100, 150, 200, 250, 300]
    assert resampled["y"].tolist() == [0, -25, -50, -75, -100, -125, -150]
    assert telemetry.resample_location(location.iloc[:0], grid).empty
