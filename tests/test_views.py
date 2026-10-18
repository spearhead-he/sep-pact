"""Tests of the plots: the file names, saving, and the plot of an event compared with baseline images"""
import os
from datetime import timedelta

import pytest
from matplotlib.figure import Figure
from matplotlib.text import Text

from spearhead.sep_pact.views import event_plot_filename, plot_event
from tests.helpers import T0, VIEWINGS, FakeEPD, image_compare, synthetic_tool


def right_title(ax) -> Text:
    """Returns the title of a panel, which is on the right"""
    return next(t for t in ax.get_children() if isinstance(t, Text) and t.get_text() == ax.get_title(loc="right"))


def run(tool):
    tool.run_onsets()
    tool.run_spikes()
    tool.run_peaks()
    tool.run_fluences()
    return tool


def test_event_plot_filename():
    assert event_plot_filename(None, 7) == "event_007.png"
    assert event_plot_filename(None, 1234) == "event_1234.png"


def test_plot_event_returns_a_figure_and_saves_it(tmp_path, monkeypatch):
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    filename = str(tmp_path / "event.png")
    fig = plot_event(tool, 1, filename=filename)
    assert isinstance(fig, Figure)
    assert os.path.getsize(filename) > 0
    assert len(fig.axes) == 5
    titles = [ax.get_title(loc="right") for ax in fig.axes]
    assert titles[:2] == ["1 MeV electrons/HET (sun viewing, 2 mins resolution)",
                          "5.9930 - 18.8300 MeV electrons/HET (sun viewing, 2 mins resolution)"]


def test_plot_event_with_the_peak_in_another_viewing(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    fake = FakeEPD(rises, peaks={("electrons", "north"): 300.0})
    tool = run(synthetic_tool(tmp_path, monkeypatch, fake=fake))
    fig = plot_event(tool, 1)
    # the flux at the onset viewing (solid) and at the peak flux viewing, north (dashed)
    assert [line.get_linestyle() for line in fig.axes[0].get_lines() if line.get_color() == "orange"] == ["-", "--"]


def test_plot_event_with_one_channel_group(tmp_path, monkeypatch):
    groups = {"electrons": {"1 MeV": {"sensor": "HET", "channels": [0, 1]}}}
    tool = run(synthetic_tool(tmp_path, monkeypatch, group_options=groups))
    assert len(plot_event(tool, 1).axes) == 1


@image_compare
def test_plot_event(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    return plot_event(run(synthetic_tool(tmp_path, monkeypatch, rises, shocks=[T0 + timedelta(hours=8)])), 1)


@image_compare
def test_plot_event_copied_onsets_at_the_end_of_the_background(tmp_path, monkeypatch):
    rises = {("electrons", viewing): T0 for viewing in VIEWINGS}  # flat protons
    events = {1: {"Onset Time": T0, "BG End": T0 - timedelta(minutes=2)}}
    tool = run(synthetic_tool(tmp_path, monkeypatch, rises, events=events))
    fig = plot_event(tool, 1)
    assert all(right_title(ax).get_color() == "red" for ax in fig.axes)  # every onset is at the end of the background
    texts = [t.get_text() for t in fig.axes[2].texts]
    assert any("(from 1 MeV electrons, at BG end)" in text for text in texts)
    return fig


@image_compare
def test_plot_event_without_proton_onsets(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises.update({("protons", viewing): T0 + timedelta(hours=3) for viewing in VIEWINGS})  # outside the reference window
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, rises)), 1)
    assert fig.axes[2].get_title(loc="right") == "8 MeV protons/HET (sun viewing, 30 mins resolution)"
    assert right_title(fig.axes[2]).get_color() == "red" and right_title(fig.axes[0]).get_color() == "black"
    return fig


@image_compare
def test_plot_event_without_peak_flux_and_fluence(tmp_path, monkeypatch):
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    for quantity in ("Peak Flux", "Fluence"):
        columns = [c for c in tool.df_results.columns if c.startswith(quantity)]
        tool.df_results.loc[(1, "protons", "HET", "50 MeV"), columns] = None
    fig = plot_event(tool, 1)
    assert fig.axes[4].get_ylim()[1] == pytest.approx(1e3)  # two decades above the decade of the maximum flux, 99.8
    return fig
