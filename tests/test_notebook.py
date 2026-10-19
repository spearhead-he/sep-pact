"""Notebook interface: the widgets of the parameters form, the channel group editor and the steps of the analysis"""
import os
import re
from datetime import timedelta

import pytest
from ipywidgets import widgets

import spearhead.sep_pact.data as data
import spearhead.sep_pact.notebook as notebook
from spearhead.sep_pact.notebook import SEPPACT_notebook
from tests.helpers import T0, VIEWINGS, FakeEPD, make_params, write_events, write_shocks


@pytest.fixture
def shown(monkeypatch):
    """The objects displayed by the interface"""
    objects = []
    monkeypatch.setattr(notebook, "display", lambda *args: objects.extend(args))
    return objects


def shown_text(objects) -> str:
    return " ".join(o.value for o in objects if isinstance(o, widgets.HTML))


def make_tool(tmp_path, monkeypatch, fake=None, events=None, **parameters) -> SEPPACT_notebook:
    """Returns the interface on one synthetic event (number 1, onset T0), with the fake loader, and its form"""
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    monkeypatch.setattr(data, "epd_load", fake or FakeEPD(rises))
    params = make_params(tmp_path, **parameters)
    write_events(tmp_path / "inputs", events or {1: {"Onset Time": T0}})
    write_shocks(tmp_path / "inputs", [T0 + timedelta(days=30)])
    tool = SEPPACT_notebook(params)
    tool.form = tool.parameters_form()
    return tool


def test_form_tabs_and_defaults(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch)
    assert [tool.form.get_title(i) for i in range(len(tool.form.children))] == \
        ["Events", "Data", "Energy channels", "Onsets", "Peak and fluence", "Plots and outputs"]
    assert tool.errors == {}
    assert [(g["particle"], g["label"], g["channels"], g["reference"]) for g in tool._groups][:2] == \
        [("electrons", "1 MeV", [0, 1], True), ("electrons", "5.9930 - 18.8300 MeV", [3], False)]
    # the fake channels c have a low energy of c + 1 MeV and a width of (c + 1) * 0.1 MeV
    assert tool._channel_options("electrons")[:2] == [("0: 1 - 1.1 MeV", 0), ("1: 2 - 2.2 MeV", 1)]
    assert isinstance(tool.widgets["onset_sigma"], widgets.FloatText)
    assert isinstance(tool.widgets["onset_points"], widgets.IntText)


def test_form_sets_the_parameters(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch)
    p = tool.parameters
    tool.widgets["onset_sigma"].value = 2.5
    tool.widgets["onset_points"].value = 4
    tool.widgets["bg_start_before_onset"].value = 3
    tool.widgets["bg_end_before_onset"].value = 10
    tool.widgets["min_plot_window"].value = 1.5
    tool.widgets["quality_adjustable"].value = True
    tool.widgets["fallback_viewing"].value = "north"
    tool.widgets["dir_outputs"].value = "results"
    assert (p.onset_sigma, p.onset_points, p.quality_adjustable, p.fallback_viewing, p.dir_outputs) == \
        (2.5, 4, True, "north", "results")
    assert (p.bg_start_before_onset, p.bg_end_before_onset, p.min_plot_window) == \
        (timedelta(hours=3), timedelta(minutes=10), timedelta(days=1.5))


def test_invalid_value_is_shown_and_stops_the_steps(tmp_path, monkeypatch, shown):
    tool = make_tool(tmp_path, monkeypatch)
    tool.widgets["fluence_peak_fraction"].value = 2
    assert tool.parameters.fluence_peak_fraction == 0.5
    assert tool.errors == {"fluence_peak_fraction": "fluence_peak_fraction must be in (0, 1], not 2.0."}
    tool.run_data()
    assert tool.seppact is None
    assert "fluence_peak_fraction must be in (0, 1]" in shown_text(shown) and "Correct the parameters" in shown_text(shown)
    tool.widgets["fluence_peak_fraction"].value = 0.4
    assert tool.errors == {} and tool.parameters.fluence_peak_fraction == 0.4


def test_viewings(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch)
    checkboxes = tool.widgets["viewings"]
    checkboxes["asun"].value = False
    assert tool.parameters.viewings == ["sun", "north", "south"]
    checkboxes["asun"].value = True
    assert tool.parameters.viewings == ["sun", "asun", "north", "south"]
    for checkbox in checkboxes.values():
        checkbox.value = False
    # the last accepted viewings are kept
    assert "viewings" in tool.errors and tool.parameters.viewings == ["south"]


def test_resolutions_and_spike_thresholds(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch)
    rows = tool.widgets["resample_freqs"]
    checkbox, threshold = rows[15]
    assert not checkbox.value and threshold.disabled and threshold.value == notebook.DEFAULT_SPIKE_THRESHOLD
    checkbox.value = True
    threshold.value = 2.7
    assert tool.parameters.resample_freqs == [timedelta(minutes=m) for m in (2, 5, 10, 15, 30)]
    assert tool.parameters.spike_thresholds[timedelta(minutes=15)] == 2.7
    rows[2][0].value = False
    assert timedelta(minutes=2) not in tool.parameters.spike_thresholds
    for checkbox, _ in rows.values():
        checkbox.value = False
    assert "resample_freqs" in tool.errors


def test_event_list_and_shock_list_info(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch, events={1: {"Onset Time": T0}, 2: {"Onset Time": T0 + timedelta(days=3)}})
    assert tool._events_info(tool.parameters.file_events) == "2 events, with onsets from 2021-01-01 12:00 to 2021-01-04 12:00"
    assert "File not found: missing.csv" in tool._events_info("missing.csv")
    path = tmp_path / "no_onsets.csv"
    path.write_text("Event No,BG Start\n1,2021-01-01 10:00\n")
    assert "has no column" in tool._events_info(str(path))
    assert "color: red" in tool._events_info(str(tmp_path / "events.xlsx"))
    assert tool._shocks_info(tool.parameters.file_shocks) == "1 shock"
    assert "File not found: missing.dat" in tool._shocks_info("missing.dat")
    path = tmp_path / "shocks.txt"
    path.write_text("2021;6;13\n")
    assert "color: red" in tool._shocks_info(str(path))
    tool.widgets["file_events"].value = str(path)
    assert tool.parameters.file_events == str(path)


def group_by_label(tool, label):
    return next(group for group in tool._groups if group["label"] == label)


def test_channel_group_editor(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch)
    wrapper_rows = tool.widgets["group_options"]
    add_proton = tool.form.children[2].children[0].children[1].children[0].children[1]
    assert add_proton.description == "Add proton group"
    add_proton.click()
    new = tool._groups[5]
    assert (new["particle"], new["label"]) == ("protons", "protons group 4")
    assert "has no channels" in tool.errors["group_options"]
    new["widgets"]["channels"].value = (5, 4)
    assert tool.errors == {}
    assert tool.parameters.group_options["protons"]["protons group 4"] == {"sensor": "HET", "channels": [4, 5]}
    new["widgets"]["label"].value = "8 MeV"
    assert "own label" in tool.errors["group_options"]
    new["widgets"]["label"].value = "5 MeV"
    assert list(tool.parameters.group_options["protons"]) == ["8 MeV", "25 MeV", "50 MeV", "5 MeV"]
    # one reference channel at most
    new["widgets"]["reference"].value = True
    assert not group_by_label(tool, "1 MeV")["widgets"]["reference"].value
    assert tool.parameters.reference_channel == {"particle": "protons", "mev": "5 MeV", "sensor": "HET"}
    remove = wrapper_rows.children[5].children[1].children[2]
    assert remove.description == "Remove"
    remove.click()
    assert list(tool.parameters.group_options["protons"]) == ["8 MeV", "25 MeV", "50 MeV"]
    assert tool.parameters.reference_channel is None


def test_channels_without_data(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch, fake=FakeEPD(fail=1))
    section = tool._wrapper_channels.children[0]
    error, retry = section.children[1].children
    assert "No data found" in error.value and "check the event list, then read the channels again" in error.value
    # the groups are listed without the editor
    assert "1 MeV electrons: channels 0, 1, reference channel" in section.children[2].children[0].value
    assert tool.widgets["group_options"].children == ()
    retry.click()
    assert len(tool.widgets["group_options"].children) == 5


def test_channels_without_connection(tmp_path, monkeypatch):
    def no_connection(**kwargs):
        raise ConnectionError("Connection aborted.")

    tool = make_tool(tmp_path, monkeypatch, fake=no_connection)
    assert "the data server may be unavailable" in tool._read_energies()


def test_steps_need_the_previous_ones(tmp_path, monkeypatch, shown):
    tool = make_tool(tmp_path, monkeypatch)
    tool.run_analysis()
    tool.event_viewer()
    tool.save_results()
    assert shown_text(shown).count("run the data step first") == 1
    assert shown_text(shown).count("run the analysis step first") == 2


def test_run_data_without_data(tmp_path, monkeypatch, shown):
    tool = make_tool(tmp_path, monkeypatch)
    monkeypatch.setattr(data, "epd_load", FakeEPD(fail=100))
    tool.run_data()
    assert tool.seppact is None and "No data found" in shown_text(shown)


def test_steps_of_the_analysis(tmp_path, monkeypatch, shown):
    tool = make_tool(tmp_path, monkeypatch)
    tool.run_data()
    # the analysis keeps the parameters it was run with
    tool.widgets["onset_sigma"].value = 5
    assert tool.seppact.params.onset_sigma == 2
    tool.run_analysis()
    assert tool.df_results["Onset Time"].notna().all()
    assert len(tool.df_series) == 5 * 4 * 4 and tool.events.index.tolist() == [1] and tool.df_spikes.empty
    assert "5 of 5 channel groups (1 event) have an onset: 0 copied" in shown_text(shown)


def shown_event(tool) -> int:
    """Returns the event of the results shown in the viewer, after checking that its plot is shown"""
    assert bytes(tool.widgets["plot"].value).startswith(b"\x89PNG")
    # the first cell of each row is the event number
    events = re.findall(r"<tr>\s*<td>(\d+)</td>", tool.widgets["table"].value)
    assert len(events) == 5 and len(set(events)) == 1
    return int(events[0])


def test_event_viewer(tmp_path, monkeypatch, shown):
    events = {1: {"Onset Time": T0}, 2: {"Onset Time": T0, "BG End": T0 - timedelta(minutes=2)}}
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    tool = make_tool(tmp_path, monkeypatch, fake=FakeEPD(rises), events=events)
    tool.run_data()
    tool.run_analysis()
    tool.event_viewer()
    # the first event is shown without a click: its plot and its results
    assert tool.widgets["event"].value == 1 and shown_event(tool) == 1
    tool.widgets["next"].click()
    assert tool.widgets["event"].value == 2 and shown_event(tool) == 2
    tool.widgets["next"].click()
    assert tool.widgets["event"].value == 2
    tool.widgets["previous"].click()
    assert tool.widgets["event"].value == 1
    # the background window of event 2 ends at the rise: its onsets are at the end of the window
    assert tool._flagged_events() == [2]
    tool.widgets["flagged_only"].value = True
    assert [value for _, value in tool.widgets["event"].options] == [2] and tool.widgets["event"].value == 2


@pytest.mark.parametrize("save_plots", [True, False])
def test_save_results(tmp_path, monkeypatch, shown, save_plots):
    tool = make_tool(tmp_path, monkeypatch)
    tool.widgets["save_plots"].value = save_plots
    tool.run_data()
    tool.run_analysis()
    tool.save_results()
    assert os.listdir(tool.parameters.dir_outputs) == ["results.csv"]
    assert os.path.isdir(tool.parameters.dir_plots) == save_plots
    assert "Saved the results to" in shown_text(shown)


def test_event_viewer_without_flagged_events(tmp_path, monkeypatch, shown):
    tool = make_tool(tmp_path, monkeypatch)
    tool.run_data()
    tool.run_analysis()
    tool.event_viewer()
    assert tool._flagged_events() == []
    tool.widgets["flagged_only"].value = True
    assert tool.widgets["event"].options == () and tool.widgets["event"].value is None
    assert bytes(tool.widgets["plot"].value) == b"" and tool.widgets["table"].value == ""


def all_widgets(widget):
    yield widget
    for child in getattr(widget, "children", ()):
        yield from all_widgets(child)


def test_fields_are_wide_enough(tmp_path, monkeypatch, shown):
    # the descriptions are in their own column, so that they do not take the width of the fields
    tool = make_tool(tmp_path, monkeypatch)
    fields = [w for w in tool.widgets.values() if isinstance(w, widgets.Widget)]
    for w in fields:
        if isinstance(w, (widgets.FloatText, widgets.IntText, widgets.Dropdown)):
            assert (w.description, w.layout.width) == ("", notebook.NUMBER_WIDTH)
        elif isinstance(w, widgets.Text):
            assert (w.description, w.layout.width) == ("", notebook.TEXT_WIDTH)
    tool.run_data()
    tool.run_analysis()
    tool.event_viewer()
    # the checkboxes show their whole description
    checkboxes = [w for w in all_widgets(tool.form) if isinstance(w, widgets.Checkbox) and len(w.description) > 10]
    checkboxes.append(tool.widgets["flagged_only"])
    assert len(checkboxes) >= 8 and all(w.layout.width == "max-content" for w in checkboxes)


def test_panel_height(tmp_path, monkeypatch):
    tool = make_tool(tmp_path, monkeypatch)
    note = tool._wgt_height_note
    # 5 channel groups of 2.5 inches, and 1.5 inches for the title, legend and axis labels
    assert "Recommended: 2 to 4 inches. With 5 channel groups, the plots are 15 inches wide and 14 inches high" in note.value
    assert "darkorange" not in note.value
    tool.widgets["panel_height"].value = 1.5
    assert tool.parameters.panel_height == 1.5
    assert "9 inches high" in note.value and "Below the recommended height, the labels in a panel overlap" in note.value
    tool.widgets["panel_height"].value = 5
    assert "Above the recommended height" in note.value and tool.errors == {}
    tool.widgets["panel_height"].value = 0.5
    assert tool.parameters.panel_height == 5
    assert tool.errors == {"panel_height": "panel_height must be a number of inches from 1 to 10, not 0.5."}
    # the note follows the number of channel groups
    tool.widgets["panel_height"].value = 3
    remove = tool.widgets["group_options"].children[4].children[1].children[2]
    remove.click()
    assert "With 4 channel groups, the plots are 15 inches wide and 13.5 inches high" in note.value
