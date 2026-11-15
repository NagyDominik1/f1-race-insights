"""Tests of the analysis functions: fixtures for realism, synthetic data for known answers."""

import numpy as np
import pandas as pd
import pytest

from conftest import load_fixture
from f1insights import analysis, data

T0 = pd.Timestamp("2024-11-03T16:00:00Z")


def message(minute: float, text: str, lap: int, flag=None, scope=None, category="Other") -> dict:
    return {"date": (T0 + pd.Timedelta(minutes=minute)).isoformat(), "lap_number": lap,
            "category": category, "flag": flag, "scope": scope, "driver_number": None, "message": text}


@pytest.fixture
def race_control_with_incidents() -> pd.DataFrame:
    """Message sequence copied from the 2024 Sao Paulo GP: VSC, then SC turning into a red flag, then SC."""
    return data.race_control_from_raw([
        message(0, "GREEN LIGHT - PIT EXIT OPEN", 1, "GREEN", "Track", "Flag"),
        message(28, "VIRTUAL SAFETY CAR DEPLOYED", 28, category="SafetyCar"),
        message(29.5, "VIRTUAL SAFETY CAR ENDING", 28, category="SafetyCar"),
        message(30, "TRACK CLEAR", 29, "CLEAR", "Track", "Flag"),
        message(31, "YELLOW IN TRACK SECTOR 4", 29, "YELLOW", "Sector", "Flag"),
        message(31.5, "CLEAR IN TRACK SECTOR 4", 29, "CLEAR", "Sector", "Flag"),
        message(33, "SAFETY CAR DEPLOYED", 30, category="SafetyCar"),
        message(37, "RED FLAG", 32, "RED", "Track", "Flag"),
        message(61, "TRACK CLEAR", 33, "CLEAR", "Track", "Flag"),
        message(73, "SAFETY CAR DEPLOYED", 39, category="SafetyCar"),
        message(78, "SAFETY CAR IN THIS LAP", 42, category="SafetyCar"),
        message(79.5, "TRACK CLEAR", 42, "CLEAR", "Track", "Flag"),
        message(117, "CHEQUERED FLAG", 69, "CHEQUERED", "Track", "Flag"),
    ])


def synthetic_laps(times: dict[str, list[float]], lap_seconds: float = 90.0) -> pd.DataFrame:
    """Laps of one or more drivers starting together, one lap every lap_seconds."""
    frames = []
    for number, (acronym, values) in enumerate(times.items(), start=1):
        n = len(values)
        frames.append(pd.DataFrame({
            "driver_number": number, "acronym": acronym, "team_name": "Team",
            "lap_number": np.arange(1, n + 1), "LapTimeSeconds": values,
            "is_pit_out_lap": False,
            "date_start": T0 + pd.to_timedelta(np.arange(n) * lap_seconds, unit="s"),
        }))
    return pd.concat(frames, ignore_index=True).astype({"driver_number": "Int64", "lap_number": "Int64"})


NO_PITS = pd.DataFrame({"driver_number": pd.Series(dtype="Int64"), "lap_number": pd.Series(dtype="Int64")})
NO_PERIODS = pd.DataFrame(columns=analysis.PERIOD_COLUMNS)


def test_format_lap_time():
    assert analysis.format_lap_time(81.712) == "1:21.712"
    assert analysis.format_lap_time(59.9996) == "1:00.000"
    assert analysis.format_lap_time(float("nan")) == "–"


def test_neutralisations_from_messages(race_control_with_incidents):
    periods = analysis.neutralisations(race_control_with_incidents)
    assert periods["kind"].tolist() == ["VSC", "SC", "RED", "SC"]
    minutes = ((periods[["start", "end"]] - T0) / pd.Timedelta(minutes=1)).round(1)
    assert minutes["start"].tolist() == [28, 33, 37, 73]
    assert minutes["end"].tolist() == [30, 37, 61, 79.5]  # sector clears do not end a period
    assert periods["lap_start"].tolist() == [28, 30, 32, 39]


def test_no_neutralisation_in_the_demo_race():
    race_control = data.race_control_from_raw(load_fixture("race_control.json"))
    assert analysis.neutralisations(race_control).empty


def test_clean_laps_reasons_in_priority_order(race_control_with_incidents):
    times = [95.0] + [90.0] * 9 + [float("nan")] + [90.0] * 9
    times[4], times[14] = 97.0, 94.0  # lap 5 is slower than 107% of the median, lap 15 is not
    laps = synthetic_laps({"AAA": times})
    laps.loc[laps["lap_number"] == 8, "is_pit_out_lap"] = True
    pits = pd.DataFrame({"driver_number": [1], "lap_number": [7]}).astype("Int64")
    # lap 19 runs from minute 27.0 to 28.5 and overlaps the VSC that starts at minute 28
    periods = analysis.neutralisations(race_control_with_incidents)
    flagged = analysis.clean_laps(laps, pits, periods).set_index("lap_number")
    expected = {1: "lap 1", 5: "slower than 107%", 7: "pit in-lap", 8: "pit out-lap",
                11: "no lap time", 19: "safety car or red flag", 20: "safety car or red flag"}
    assert flagged.loc[flagged["reason"] != "", "reason"].to_dict() == expected
    assert flagged["is_clean"].sum() == 20 - len(expected)
    assert len(flagged) == 20  # nothing is dropped


def test_clean_laps_reference_min_for_qualifying():
    laps = synthetic_laps({"AAA": [130.0, 76.0, 120.0, 75.0, 80.0, 81.0]})
    by_median = analysis.clean_laps(laps, NO_PITS, NO_PERIODS)
    by_fastest = analysis.clean_laps(laps, NO_PITS, NO_PERIODS, reference="min")
    assert by_median.loc[by_median["is_clean"], "lap_number"].tolist() == [2, 4, 5, 6]
    assert by_fastest.loc[by_fastest["is_clean"], "lap_number"].tolist() == [2, 4, 5]


def test_clean_laps_on_real_fixture(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    pits = data.pit_stops_from_raw(load_fixture("pit_nor_pia.json"), drivers)
    flagged = analysis.clean_laps(laps, pits, NO_PERIODS)
    nor = flagged.loc[flagged["acronym"] == "NOR"].set_index("lap_number")
    assert nor.loc[[1, 17, 18, 45, 46], "reason"].tolist() == [
        "lap 1", "pit in-lap", "pit out-lap", "pit in-lap", "pit out-lap"]
    assert nor["is_clean"].sum() >= 60


def test_pace_stats_are_robust_to_one_outlier():
    laps = synthetic_laps({"AAA": [90.0, 90.0, 91.0, 92.0, 93.0], "BBB": [90.5] * 5})
    stats_table = analysis.pace_stats(laps.assign(is_clean=True)).set_index("acronym")
    assert stats_table.loc["AAA", ["n", "median", "iqr", "fastest"]].tolist() == [5, 91.0, 2.0, 90.0]
    assert stats_table.index.tolist() == ["BBB", "AAA"]  # sorted by median


def stint_fixture(slope: float, noise: float, n: int = 25, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    times = 90 + slope * np.arange(n) + rng.normal(0, noise, n)
    laps = synthetic_laps({"AAA": times.tolist()}).assign(is_clean=True)
    stints = pd.DataFrame({"driver_number": [1], "acronym": ["AAA"], "stint_number": [1], "compound": ["HARD"],
                           "lap_start": [1], "lap_end": [n], "tyre_age_at_start": [0]}).astype(
        {c: "Int64" for c in ["driver_number", "stint_number", "lap_start", "lap_end", "tyre_age_at_start"]})
    return laps, stints


def test_with_stints_assigns_compound_and_tyre_age(raw_laps, raw_stints, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    stints = data.stints_from_raw(raw_stints, drivers)
    merged = analysis.with_stints(laps, stints)
    nor = merged.loc[merged["acronym"] == "NOR"].set_index("lap_number")
    assert nor.loc[[17, 18, 45, 46], "stint_number"].tolist() == [1, 2, 2, 3]
    assert nor.loc[[17, 18], "compound"].tolist() == ["MEDIUM", "HARD"]
    assert nor.loc[[18, 19], "stint_lap"].tolist() == [1, 2]
    assert nor.loc[18, "tyre_age"] == 1  # the hard set was one lap old when fitted
    assert len(merged) == len(laps)


def test_degradation_recovers_a_known_slope():
    laps, stints = stint_fixture(slope=0.08, noise=0.05)
    fit = analysis.degradation(analysis.with_stints(laps, stints)).iloc[0]
    assert fit["n"] == 24  # the first lap of the stint is excluded
    assert fit["slope"] == pytest.approx(0.08, abs=0.01)
    assert fit["ci_low"] < 0.08 < fit["ci_high"]
    assert fit["r2"] > 0.95


def test_degradation_without_noise_is_exact_and_fuel_correction_adds_the_constant():
    laps, stints = stint_fixture(slope=0.05, noise=0.0)
    merged = analysis.with_stints(laps, stints)
    plain = analysis.degradation(merged).iloc[0]
    corrected = analysis.degradation(merged, fuel_per_lap=analysis.FUEL_SECONDS_PER_LAP).iloc[0]
    assert plain["slope"] == pytest.approx(0.05) and plain["r2"] == pytest.approx(1.0)
    assert corrected["slope"] == pytest.approx(0.05 + analysis.FUEL_SECONDS_PER_LAP)


def test_degradation_skips_short_stints():
    laps, stints = stint_fixture(slope=0.05, noise=0.0, n=5)
    assert analysis.degradation(analysis.with_stints(laps, stints)).empty


def test_lap_deltas_only_use_laps_clean_for_both():
    laps = synthetic_laps({"AAA": [90.0, 90.2, 90.4, 90.6], "BBB": [90.5, 90.5, 90.5, 90.5]})
    laps["is_clean"] = ~((laps["acronym"] == "BBB") & (laps["lap_number"] == 2))
    deltas = analysis.lap_deltas(laps, "AAA", "BBB")
    assert deltas["lap_number"].tolist() == [1, 3, 4]
    assert deltas["delta"].round(3).tolist() == [-0.5, -0.1, 0.1]  # negative: AAA faster


def test_bootstrap_ci_contains_the_true_difference_and_is_reproducible():
    rng = np.random.default_rng(1)
    deltas = rng.normal(0.25, 0.3, size=60)
    median, low, high = analysis.bootstrap_median_ci(deltas)
    assert low < 0.25 < high
    assert low < median < high
    assert high - low < 0.4
    assert analysis.bootstrap_median_ci(deltas) == (median, low, high)
    assert all(np.isnan(v) for v in analysis.bootstrap_median_ci(np.array([])))


def test_best_lap_comparison_uses_the_sectors_of_the_best_lap():
    laps = synthetic_laps({"AAA": [80.0, 75.0], "BBB": [75.3, 79.0]})
    laps[["Sector1Seconds", "Sector2Seconds", "Sector3Seconds"]] = [
        [27.0, 28.0, 25.0], [25.0, 26.0, 24.0], [25.2, 25.9, 24.2], [26.0, 28.0, 25.0]]
    table = analysis.best_lap_comparison(laps, "AAA", "BBB").set_index("part")
    assert table["gap"].round(3).tolist() == [-0.3, -0.2, 0.1, -0.2]
    assert table.loc["Lap", ["AAA", "BBB"]].tolist() == [75.0, 75.3]


def test_position_by_lap_and_classification(raw_laps, drivers):
    laps = data.laps_from_raw(raw_laps, drivers)
    positions = data.positions_from_raw(load_fixture("position_nor_pia.json"), drivers)
    by_lap = analysis.position_by_lap(laps, positions)
    nor = by_lap.loc[by_lap["acronym"] == "NOR"].set_index("lap_number")["position"]
    assert nor.loc[0] == 1 and nor.loc[1] == 3 and nor.loc[70] == 2
    assert by_lap.groupby("acronym")["lap_number"].count().tolist() == [71, 71]

    results = data.results_from_raw(load_fixture("session_result.json"), drivers)
    table = analysis.classification(laps, positions, results)
    assert table["acronym"].tolist() == ["PIA", "NOR"]
    assert table["gained"].tolist() == [1, -1]
    on_track = analysis.classification(laps, positions, results.iloc[:0])
    assert on_track["finish"].tolist() == [1, 2]


def test_race_story_templates():
    table = pd.DataFrame({
        "driver_number": [81, 4, 44], "acronym": ["PIA", "NOR", "HAM"], "grid": [2, 1, 5],
        "finish": [1, 2, 3], "gained": [1, -1, 2], "classified": [True, True, True]})
    stats_table = pd.DataFrame({"acronym": ["NOR", "PIA"], "median": [83.9, 84.15]})
    degradation_table = pd.DataFrame({
        "acronym": ["PIA", "NOR"], "compound": ["MEDIUM", "HARD"], "slope": [0.031, 0.062],
        "ci_low": [-0.01, 0.04], "n": [15, 26]})
    pits = pd.DataFrame({"driver_number": [81, 81, 4]})
    laps = synthetic_laps({"NOR": [90.0, 81.712, 85.0]})
    story = analysis.race_story(table, stats_table, degradation_table, pits, laps)
    assert story == [
        "PIA won from P2 on the grid with 2 pit stops.",
        "NOR had the best median clean-lap pace at 1:23.900, 0.250 s per lap quicker than PIA.",
        "The steepest tyre degradation was NOR's hard stint: +0.062 s per lap over 26 laps.",
        "HAM gained the most places: 2, from P5 to P3.",
        "NOR set the fastest lap, 1:21.712, on lap 2.",
    ]
    empty = analysis.race_story(table.iloc[:0], stats_table.iloc[:1], degradation_table.iloc[:0], pits, laps.iloc[:0])
    assert empty == []


def test_pace_flow_is_smooth_scaled_and_ordered():
    rng = np.random.default_rng(5)
    times = {"FAS": (90 + rng.normal(0, 0.3, 40)).tolist(), "SLO": (92 + rng.normal(0, 0.3, 40)).tolist(),
             "FEW": [91.0, 91.2]}
    laps = synthetic_laps(times).assign(is_clean=True)
    flows = analysis.pace_flow(laps, drivers=5, window=5, points=30)
    assert len(flows) == 2  # FEW has fewer clean laps than the window
    assert all(len(line) == 30 for line in flows)
    values = np.array(flows)
    assert values.min() == 0 and values.max() == 1  # scaled over both drivers together
    assert values[0].mean() < values[1].mean()  # quickest driver first, and lower on the scale
    raw_step = np.abs(np.diff(times["FAS"])).mean() / (max(times["SLO"]) - min(times["FAS"]))
    assert np.abs(np.diff(values[0])).mean() < raw_step  # the rolling mean removed lap-to-lap noise
    assert analysis.pace_flow(laps.assign(is_clean=False)) == []
