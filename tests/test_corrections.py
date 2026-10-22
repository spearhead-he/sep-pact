"""Tests of the onset corrections: set_onset(), reset_onset(), the reference channel, save_corrections() and
file_corrections"""
from datetime import timedelta

import pandas as pd
import pytest

from spearhead.sep_pact import SEPPACT
from spearhead.sep_pact.inputs import CORRECTION_COLUMNS, read_corrections
from tests.helpers import T0, VIEWINGS, FakeEPD, make_params, synthetic_tool, write_events, write_shocks

HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)
TWO_MIN = pd.Timedelta(minutes=2)
REFERENCE = (1, "electrons", "HET", "1 MeV")
PROTONS_8 = (1, "protons", "HET", "8 MeV")
PROTONS_25 = (1, "protons", "HET", "25 MeV")
# two events over the same data, with a spike in the decay
EVENTS = {1: {"Start Time": T0 - 2 * HOUR, "End Time": T0 + 48 * HOUR},
          2: {"Start Time": T0 - 3 * HOUR, "End Time": T0 + 40 * HOUR}}


def run(tool):
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    return tool


def make_tool(tmp_path, monkeypatch, asun=T0 + HOUR, protons=T0, **parameters):
    """Returns the analysis of EVENTS: the electrons rise at T0 in the sun viewing and at asun in the others, the
    protons at protons in all the viewings"""
    rises = {("electrons", viewing): T0 if viewing == "sun" else asun for viewing in VIEWINGS}
    rises.update({("protons", viewing): protons for viewing in VIEWINGS})
    spikes = {("electrons", "sun"): {T0 + 3 * HOUR: 1000.0}}
    return run(synthetic_tool(tmp_path, monkeypatch, fake=FakeEPD(rises, spikes=spikes), events=EVENTS, **parameters))


@pytest.fixture
def tool(tmp_path, monkeypatch):
    return make_tool(tmp_path, monkeypatch)


def series(tool, key, minutes, viewing):
    return tool.df_series.loc[(*key, pd.Timedelta(minutes=minutes), viewing)]


def test_set_onset_to_another_viewing(tool):
    before = tool.df_results.copy()
    assert before.loc[REFERENCE, "Onset Viewing"] == "sun" and not before["Onset Corrected"].any()
    tool.set_onset(*REFERENCE, timedelta(minutes=2), "asun")
    after = tool.df_results.loc[REFERENCE]
    assert after["Onset Time"] == series(tool, REFERENCE, 2, "asun")["Onset Time"]
    assert after["Onset Time"] > pd.Timestamp(T0 + 30 * MINUTE)
    assert (after["Onset Resolution"], after["Onset Viewing"], after["Onset Corrected"]) == (TWO_MIN, "asun", True)
    # the peak flux and fluence are those after the new onset
    assert after["Peak Flux Time"] >= after["Onset Time"] and after["Fluence Start"] >= after["Onset Time"]
    assert tool.corrections == {REFERENCE: (TWO_MIN, "asun")}
    # the other event is unchanged
    pd.testing.assert_frame_equal(tool.df_results.loc[[2]], before.loc[[2]])


def test_set_onset_with_the_resolution_in_minutes(tool):
    tool.set_onset(*REFERENCE, 5, "north")
    assert tool.df_results.loc[REFERENCE, ["Onset Resolution", "Onset Viewing"]].tolist() == [pd.Timedelta(minutes=5),
                                                                                              "north"]


def test_set_onset_of_one_event_as_running_all_the_events(tool):
    """Running the steps again for the corrected event gives the results of running them for all the events"""
    tool.set_onset(*REFERENCE, 2, "asun")
    tool.set_onset(*PROTONS_25, 10, "south")
    assert not tool.df_spikes.empty
    once = (tool.df_series.copy(), tool.df_results.copy(), tool.df_spikes.copy())
    run(tool)
    pd.testing.assert_frame_equal(tool.df_series, once[0])
    pd.testing.assert_frame_equal(tool.df_results, once[1])
    pd.testing.assert_frame_equal(tool.df_spikes, once[2])


def test_set_no_onset_of_all_the_groups_of_an_event_with_spikes(tool):
    groups = list(tool.df_results.loc[[1]].index)
    for key in groups:
        tool.set_onset(*key)
    assert 1 not in tool.df_spikes.index.get_level_values("Event No") and not tool.df_spikes.empty
    once = tool.df_spikes.copy()
    run(tool)
    pd.testing.assert_frame_equal(tool.df_spikes, once)


def test_set_no_onset(tool):
    tool.set_onset(*PROTONS_8)
    row = tool.df_results.loc[PROTONS_8]
    assert pd.isna(row["Onset Time"]) and pd.isna(row["Peak Flux"]) and pd.isna(row["Fluence"])
    assert row["Onset Corrected"] and tool.corrections == {PROTONS_8: None}
    assert not tool.df_spikes.reset_index()[["Event No", "Particle", "Energy Label"]].isin([1, "protons", "8 MeV"]).all(
        axis=1).any()


def test_reset_onset(tool):
    before = (tool.df_series.copy(), tool.df_results.copy(), tool.df_spikes.copy())
    tool.set_onset(*REFERENCE, 2, "asun")
    tool.set_onset(*PROTONS_8)
    tool.reset_onset(*REFERENCE)
    tool.reset_onset(*PROTONS_8)
    assert tool.corrections == {}
    pd.testing.assert_frame_equal(tool.df_series, before[0])
    pd.testing.assert_frame_equal(tool.df_results, before[1])
    pd.testing.assert_frame_equal(tool.df_spikes, before[2])


def test_corrected_reference_channel_chooses_the_other_groups_again(tmp_path, monkeypatch):
    # the protons rise 3 h after the sun electrons, outside the reference onset window (2.5 h), with the other viewings
    tool = make_tool(tmp_path, monkeypatch, asun=T0 + 3 * HOUR, protons=T0 + 3 * HOUR)
    assert tool.df_results.loc[[PROTONS_8, PROTONS_25], "Onset Time"].isna().all()
    tool.set_onset(*PROTONS_8)
    tool.set_onset(*REFERENCE, 2, "asun")
    # the 25 MeV protons are chosen again, within the window of the new reference onset; the corrected 8 MeV are not
    assert tool.df_results.loc[PROTONS_25, "Onset Time"] == series(tool, PROTONS_25, 2, "sun")["Onset Time"]
    assert not tool.df_results.loc[PROTONS_25, "Onset Corrected"]
    assert pd.isna(tool.df_results.loc[PROTONS_8, "Onset Time"]) and tool.df_results.loc[PROTONS_8, "Onset Corrected"]


def test_set_onset_after_the_onsets_only(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.run_onsets()
    tool.set_onset(*REFERENCE, 2, "asun")
    assert tool.df_results.loc[REFERENCE, "Onset Viewing"] == "asun"
    assert tool.df_spikes is None and "Peak Flux" not in tool.df_series


@pytest.mark.parametrize("key, arguments, message", [
    ((1, "protons", "HET", "1 MeV"), (2, "sun"), "event 1 has no channel group 1 MeV protons/HET"),
    ((7, *REFERENCE[1:]), (2, "sun"), "event 7 has no channel group 1 MeV electrons/HET"),
    (REFERENCE, (3, "sun"), "there is no series at the 3 min resolution in the sun viewing"),
    (REFERENCE, (2, "omni"), "there is no series at the 2 min resolution in the omni viewing"),
])
def test_set_onset_of_no_series(tool, key, arguments, message):
    with pytest.raises(ValueError, match=f"cannot be set: {message}"):
        tool.set_onset(*key, *arguments)
    assert tool.corrections == {}


def test_set_onset_of_a_series_without_onset(tmp_path, monkeypatch):
    rises = {("electrons", viewing): T0 for viewing in VIEWINGS}  # flat protons, whose onsets are copied
    tool = run(synthetic_tool(tmp_path, monkeypatch, rises, reference_onset_window=timedelta(hours=1)))
    tool.set_onset(*PROTONS_8, 2, "sun")  # a copied onset is a detected onset of the reference channel
    tool.params.group_options["electrons"]["1 MeV"].pop("reference_channel")
    tool.reference_channel = None
    tool.run_onsets()
    with pytest.raises(ValueError, match="the series at the 2 min resolution in the sun viewing has no onset"):
        tool.set_onset(*PROTONS_25, 2, "sun")


def test_set_onset_needs_the_resolution_and_the_viewing(tool):
    with pytest.raises(ValueError, match="Give both the resolution and the viewing"):
        tool.set_onset(*REFERENCE, 2)


def test_set_onset_before_the_onsets(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="run the onsets first"):
        synthetic_tool(tmp_path, monkeypatch).set_onset(*REFERENCE, 2, "sun")


def test_corrections_stay_when_the_onsets_run_again(tool):
    tool.set_onset(*REFERENCE, 2, "asun")
    tool.set_bg_window(1, T0 - 2 * HOUR, T0 - HOUR)
    run(tool)
    assert tool.df_results.loc[REFERENCE, ["Onset Viewing", "Onset Corrected"]].tolist() == ["asun", True]


def test_save_corrections(tool, tmp_path):
    tool.set_onset(*REFERENCE, 2, "asun")
    tool.set_onset(*PROTONS_8)
    path = str(tmp_path / "corrections.csv")
    tool.save_corrections(path)
    saved = pd.read_csv(path)
    assert saved.columns.tolist() == CORRECTION_COLUMNS
    onset = tool.df_results.loc[REFERENCE, "Onset Time"]
    assert saved.iloc[0].tolist() == [1, "electrons", "HET", "1 MeV", 2, "asun", f"{onset:%Y-%m-%d %H:%M:%S}"]
    assert saved.iloc[1, :4].tolist() == [1, "protons", "HET", "8 MeV"] and saved.iloc[1, 4:].isna().all()
    assert read_corrections(path) == ({REFERENCE: (TWO_MIN, "asun"), PROTONS_8: None}, {REFERENCE: onset})
    # the resolution in whole minutes, also with a row without an onset
    assert open(path).read().splitlines()[1].split(",")[4] == "2"


def test_file_corrections(tool, tmp_path, monkeypatch, capsys):
    tool.set_onset(*REFERENCE, 2, "asun")
    tool.set_onset(*PROTONS_8)
    tool.save_corrections(str(tmp_path / "corrections.csv"))
    (tmp_path / "again").mkdir()
    again = make_tool(tmp_path / "again", monkeypatch, file_corrections=str(tmp_path / "corrections.csv"))
    pd.testing.assert_frame_equal(again.df_results, tool.df_results)
    assert "onset correction" not in capsys.readouterr().out


def write_corrections(path, rows: list) -> str:
    pd.DataFrame(rows, columns=CORRECTION_COLUMNS).to_csv(path, index=False)
    return str(path)


def test_file_corrections_that_cannot_be_applied(tmp_path, monkeypatch, capsys):
    (tmp_path / "again").mkdir()
    path = write_corrections(tmp_path / "corrections.csv", [
        [1, "electrons", "HET", "1 MeV", 2, "asun", "2021-01-01 12:00:00"],    # a different onset
        [1, "protons", "HET", "50 MeV", 3, "sun", None],                      # no such resolution
        [9, "protons", "HET", "8 MeV", None, None, None],                     # no such event
    ])
    tool = make_tool(tmp_path / "again", monkeypatch, file_corrections=path)
    out = capsys.readouterr().out
    onset = tool.df_results.loc[REFERENCE, "Onset Time"]
    assert f"The onset correction of event 1, 1 MeV electrons/HET: the onset of its series is now {onset}, not " \
           "2021-01-01 12:00:00." in out
    assert "The onset correction of event 1, 50 MeV protons/HET is left out: there is no series at the 3 min " \
           "resolution in the sun viewing." in out
    assert "The onset correction of event 9, 8 MeV protons/HET is left out: event 9 has no channel group" in out
    assert tool.corrections == {REFERENCE: (TWO_MIN, "asun")}
    assert tool.df_results["Onset Corrected"].sum() == 1
    # the messages are given once
    tool.run_onsets()
    assert capsys.readouterr().out == ""


def test_read_corrections_without_a_column(tmp_path):
    path = tmp_path / "corrections.csv"
    pd.DataFrame([[1, "electrons", "HET", "1 MeV", 2]], columns=CORRECTION_COLUMNS[:5]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="have no column Onset Viewing, Onset Time"):
        read_corrections(str(path))


def test_read_corrections_with_a_resolution_without_viewing(tmp_path):
    path = write_corrections(tmp_path / "corrections.csv", [[1, "electrons", "HET", "1 MeV", 2, None, None]])
    with pytest.raises(ValueError, match="Row 2 of the onset corrections .* has an onset resolution or viewing without"):
        read_corrections(path)


def test_no_file_corrections(tmp_path):
    params = make_params(tmp_path)
    write_events(tmp_path / "inputs", {1: {"Reference Time": T0}})
    write_shocks(tmp_path / "inputs", [T0])
    tool = SEPPACT(params)
    tool.run_inputs()
    assert tool.params.file_corrections == "" and tool.corrections == {}
