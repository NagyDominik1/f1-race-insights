"""Tests of the telemetry transforms: outline, replay payload, ghost lap."""

import base64

import numpy as np
import pandas as pd
import pytest

from conftest import load_fixture
from f1insights import analysis, data, telemetry

T0 = pd.Timestamp("2024-07-21T13:00:00Z")


def circle_lap(seconds: float = 80.0, radius: float = 5000.0, samples: int = 321, speed_profile=None) -> pd.DataFrame:
    """A lap around a circle as (t, x, y); speed_profile maps lap time share -> lap distance share."""
    t = np.linspace(0, seconds, samples)
    share = t / seconds if speed_profile is None else speed_profile(t / seconds)
    angle = 2 * np.pi * share
    return pd.DataFrame({"t": t, "x": radius * np.cos(angle), "y": radius * np.sin(angle)})


def test_clip_to_window_interpolates_both_ends():
    df = pd.DataFrame({"date": T0 + pd.to_timedelta([-0.2, 0.1, 0.4, 0.7, 1.0, 1.3], unit="s"),
                       "x": [-20.0, 10.0, 40.0, 70.0, 100.0, 130.0]})
    clipped = telemetry.clip_to_window(df, T0, T0 + pd.Timedelta(seconds=1.15))
    assert clipped["t"].round(3).tolist() == [0.0, 0.1, 0.4, 0.7, 1.0, 1.15]
    assert clipped["x"].round(3).tolist() == [0.0, 10.0, 40.0, 70.0, 100.0, 115.0]


def test_lap_fraction_is_monotonic_from_0_to_1():
    location = data.location_from_raw(load_fixture("location_nor_fastest_lap.json"))
    fraction = telemetry.lap_fraction(location["x"].to_numpy(), location["y"].to_numpy())
    assert fraction[0] == 0 and fraction[-1] == pytest.approx(1)
    assert (np.diff(fraction) >= 0).all()


def test_track_outline_is_evenly_spaced_by_distance():
    lap = circle_lap(speed_profile=lambda s: s**2)  # accelerating: samples bunch up at the start
    outline = telemetry.track_outline(lap, points=100)
    steps = np.hypot(np.diff(outline["x"]), np.diff(outline["y"]))
    assert len(outline) == 100
    assert steps.std() / steps.mean() < 0.02
    assert outline["fraction"].iloc[[0, -1]].tolist() == [0, 1]


def test_fit_to_box_keeps_aspect_ratio_and_rotates_tall_tracks():
    x = np.array([0.0, 4000.0, 4000.0, 0.0])
    y = np.array([0.0, 0.0, 1000.0, 1000.0])
    wide = telemetry.fit_to_box(x, y, box=20000)
    assert not wide["rotate"] and (wide["width"], wide["height"]) == (20000, 5000)
    u, v = telemetry.to_box(x, y, wide)
    assert (u.min(), u.max(), v.min(), v.max()) == (0, 20000, 0, 5000)
    assert v[0] == 5000 and v[2] == 0  # y points down on screen

    tall = telemetry.fit_to_box(y, x, box=20000)
    assert tall["rotate"] and (tall["width"], tall["height"]) == (20000, 5000)
    u, v = telemetry.to_box(y, x, tall)
    assert np.ptp(u) == 20000 and np.ptp(v) == 5000
    # a rotation keeps distances between points in proportion: no mirroring artefacts in shape
    assert np.hypot(u[1] - u[0], v[1] - v[0]) == pytest.approx(20000)


def test_encode_int16_round_trip():
    values = np.array([0, 1, -1, 20000, telemetry.MISSING], dtype="int16")
    decoded = np.frombuffer(base64.b64decode(telemetry.encode_int16(values)), dtype="<i2")
    assert decoded.tolist() == values.tolist()


def synthetic_race_location(hz: float = 2.0, seconds: int = 20) -> pd.DataFrame:
    """Two cars driving along x at constant speed; car 2 has a gap in its data."""
    dates = pd.date_range(T0, periods=int(seconds * hz) + 1, freq=pd.Timedelta(seconds=1 / hz))
    one = pd.DataFrame({"date": dates, "driver_number": 1, "x": np.arange(len(dates)) * 100.0, "y": 0.0})
    two = one.assign(driver_number=2, x=one["x"] + 50, y=1000.0).drop(index=[10, 11, 12])
    return pd.concat([one, two], ignore_index=True)


def test_replay_tracks_share_one_grid_and_keep_gaps():
    location = synthetic_race_location()
    fit = {"rotate": False, "u_min": 0.0, "v_min": -1000.0, "scale": 1.0, "width": 4000, "height": 1000}
    grid, x, y = telemetry.replay_tracks(location, fit, hz=2.0)
    assert len(grid) == 41 and list(x.columns) == [1, 2]
    assert x[1].tolist() == (np.arange(41) * 100.0).tolist()  # smoothing leaves straight-line motion unchanged
    assert x[2].isna().sum() == 3 and x[2].iloc[9] == pytest.approx(950, abs=40)
    assert (y[1] == 1000).all()  # y is flipped: the car at y = 0 is at the bottom of the box


def test_replay_tracks_smooth_timestamp_jitter():
    location = synthetic_race_location().query("driver_number == 1").copy()
    rng = np.random.default_rng(3)
    location["x"] += rng.normal(0, 12, len(location))
    fit = {"rotate": False, "u_min": 0.0, "v_min": 0.0, "scale": 1.0, "width": 4000, "height": 1}
    _, raw, _ = telemetry.replay_tracks(location, fit, hz=2.0, smooth=1)
    _, smooth, _ = telemetry.replay_tracks(location, fit, hz=2.0, smooth=3)
    assert np.diff(smooth[1]).std() < 0.7 * np.diff(raw[1]).std()


def test_replay_payload_shape(raw_laps, raw_stints, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    stints = data.stints_from_raw(raw_stints, drivers)
    positions = data.positions_from_raw(load_fixture("position_nor_pia.json"), drivers)
    pits = data.pit_stops_from_raw(load_fixture("pit_nor_pia.json"), drivers)
    results = data.results_from_raw(load_fixture("session_result.json"), drivers)
    table = analysis.classification(laps, positions, results)
    periods = analysis.neutralisations(data.race_control_from_raw(load_fixture("race_control.json")))

    lap = data.fastest_lap_window(laps, 4)
    location = data.location_from_raw(load_fixture("location_nor_fastest_lap.json"))
    outline_lap = telemetry.clip_to_window(location, lap["start"], lap["end"])
    grid = telemetry.time_grid(laps, hz=2.0)[:600]
    race_location = pd.concat([
        telemetry.resample_location(location.assign(date=location["date"] - location["date"].min() + grid[0]), grid)
        .assign(driver_number=number) for number in (4, 81)
    ])
    payload = telemetry.replay_payload(race_location, outline_lap, laps, positions, stints, pits,
                                       periods, drivers, table, hz=2.0)

    assert payload["hz"] == 2.0 and payload["totalLaps"] == 70 and payload["periods"] == []
    assert payload["width"] == telemetry.BOX and 0 < payload["height"] <= telemetry.BOX
    assert len(payload["track"]["x"]) == len(payload["track"]["y"]) == 500
    assert len(payload["lapStarts"]) == 70 and payload["lapStarts"] == sorted(payload["lapStarts"])
    assert [car["a"] for car in payload["cars"]] == ["NOR", "PIA"]
    nor = payload["cars"][0]
    path = np.frombuffer(base64.b64decode(nor["xy"]), dtype="<i2")
    assert len(path) == 2 * payload["samples"]
    assert path[path != telemetry.MISSING].min() >= -500 and path.max() <= telemetry.BOX + 500
    assert len(nor["laps"]) == 70 and nor["stints"] == [[1, 17, "MEDIUM", 0], [18, 45, "HARD", 1], [46, 70, "MEDIUM", 1]]
    assert nor["pos"][0][1] == 1 and nor["out"] is None
    assert len(nor["pits"]) == 2 and all(20 < end - start < 23 for start, end in nor["pits"])


def as_feeds(lap: pd.DataFrame, start: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Turn a synthetic (t, x, y) lap into location and car-data feeds padded like the real ones."""
    step = lap["t"].iloc[1]
    seconds = lap["t"].iloc[-1]
    t = np.arange(-4, len(lap) + 4) * step  # the circle is periodic, so padding simply continues it
    one_lap = np.unwrap(np.arctan2(lap["y"], lap["x"]))
    angle = 2 * np.pi * np.floor(t / seconds) + np.interp(t % seconds, lap["t"], one_lap)
    radius = np.hypot(lap["x"].iloc[0], lap["y"].iloc[0])
    location = pd.DataFrame({"date": start + pd.to_timedelta(t, unit="s"), "x": radius * np.cos(angle), "y": radius * np.sin(angle)})
    speed = np.gradient(angle, t) * radius / 10 * 3.6  # km/h, x and y are in 1/10 m
    car = pd.DataFrame({"date": location["date"] + pd.Timedelta(milliseconds=40), "speed": speed, "throttle": 100,
                        "brake": 0, "n_gear": 7, "rpm": 11000, "drs": 0})
    return location, car


def ghost(seconds: float, speed_profile=None) -> pd.DataFrame:
    lap = circle_lap(seconds=seconds, speed_profile=speed_profile)
    location, car = as_feeds(lap, T0)
    return telemetry.ghost_lap(location, car, T0, T0 + pd.Timedelta(seconds=seconds))


def test_ghost_lap_fraction_and_time_are_monotonic():
    lap = ghost(80.0)
    assert len(lap) == telemetry.GHOST_POINTS
    assert lap["fraction"].iloc[0] == 0 and lap["fraction"].iloc[-1] == 1
    assert (np.diff(lap["fraction"]) > 0).all() and (np.diff(lap["t"]) > 0).all()
    assert lap["t"].iloc[0] == 0 and lap["t"].iloc[-1] == pytest.approx(80.0)
    assert lap.loc[250, "t"] == pytest.approx(40.0, abs=0.05)  # constant speed: half the distance, half the time
    assert lap["speed"].round(1).eq(141.4).all()  # car data joined by time: 3 142 m in 80 s


def test_ghost_lap_on_real_fixture():
    location = data.location_from_raw(load_fixture("location_nor_fastest_lap.json"))
    car = data.car_data_from_raw(load_fixture("car_data_nor_fastest_lap.json"))
    start = location["date"].min() + pd.Timedelta(seconds=1)
    lap = telemetry.ghost_lap(location, car, start, start + pd.Timedelta(seconds=81.712))
    assert (np.diff(lap["t"]) >= 0).all() and lap["t"].iloc[-1] == pytest.approx(81.712)
    assert lap["speed"].between(60, 330).all() and lap["speed"].max() > 280


def test_lap_delta_sign_and_final_gap():
    fast, slow = ghost(80.0), ghost(81.0)
    delta = telemetry.lap_delta(fast, slow)
    assert delta[0] == 0 and delta[-1] == pytest.approx(-1.0)
    assert (delta[1:] < 0).all()  # negative: the first lap is ahead everywhere
    assert (telemetry.lap_delta(slow, fast)[1:] > 0).all()


def test_mini_sector_winner_on_synthetic_laps():
    # same lap time, but the first driver is quicker in the first half and slower in the second
    early = ghost(80.0, speed_profile=lambda s: np.where(s < 0.4, s * 1.25, 0.5 + (s - 0.4) / 0.6 * 0.5))
    steady = ghost(80.0)
    sectors = telemetry.mini_sectors(early, steady, count=10, even=0.03)
    assert sectors["faster"].tolist() == ["first"] * 5 + ["second"] * 5
    assert sectors["delta"].sum() == pytest.approx(0, abs=1e-6)
    assert sectors[["first", "second"]].sum().round(3).tolist() == [80.0, 80.0]
    assert sectors["first"].iloc[0] == pytest.approx(6.4, abs=0.1)  # 10% of the lap at 1.25 times the average speed
    same = telemetry.mini_sectors(steady, steady, count=10)
    assert (same["faster"] == "even").all()


def test_mini_sectors_rank_the_biggest_differences_first():
    early = ghost(80.0, speed_profile=lambda s: np.where(s < 0.4, s * 1.25, 0.5 + (s - 0.4) / 0.6 * 0.5))
    sectors = telemetry.mini_sectors(early, ghost(80.0), count=10)
    assert sorted(sectors["rank"]) == list(range(1, 11))  # ties still get distinct ranks
    by_rank = sectors.sort_values("rank")["delta"].abs().to_numpy()
    assert (np.diff(by_rank) <= 1e-9).all()
    top = sectors.loc[sectors["rank"] <= 5, "sector"]
    assert set(top) == set(sectors["delta"].abs().nlargest(5).index + 1)


def test_gap_metres_uses_the_speed_of_the_car_behind():
    metres = telemetry.gap_metres(np.array([-0.05, 0.05, 0.0, 1.0]), np.array([252, 252, 300, 36]))
    assert metres.round(2).tolist() == [3.5, 3.5, 0.0, 10.0]


def test_ghost_payload_shape():
    fast, slow = ghost(80.0), ghost(81.0)
    sectors = telemetry.mini_sectors(fast, slow)
    payload = telemetry.ghost_payload(fast, slow, sectors, [{"a": "AAA", "c": "#FF8000"}, {"a": "BBB", "c": "#FF8000"}])
    assert [car["a"] for car in payload["cars"]] == ["AAA", "BBB"]
    assert [car["seconds"] for car in payload["cars"]] == [80.0, 81.0]
    assert len(payload["cars"][0]["x"]) == len(payload["delta"]) == telemetry.GHOST_POINTS
    assert len(payload["sectors"]) == telemetry.MINI_SECTORS and {s[2] for s in payload["sectors"]} == {0}
    assert sorted(s[4] for s in payload["sectors"]) == list(range(1, telemetry.MINI_SECTORS + 1))
    assert len(payload["cars"][1]["v"]) == telemetry.GHOST_POINTS and payload["cars"][1]["v"][100] == 140
    assert payload["delta"][-1] == -1.0 and payload["width"] == telemetry.BOX
