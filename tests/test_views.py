"""Tests of the plots: the file names, saving, and the plot of an event compared with baseline images"""
import os
from datetime import timedelta

import pytest
from matplotlib.figure import Figure
from matplotlib.text import Text

from spearhead.sep_pact.views import CORNER_PADDING, event_plot_filename, plot_background, plot_event, plot_height
from tests.helpers import T0, VIEWINGS, FakeEPD, bg_end_event, image_compare, synthetic_tool


def panel_title(ax) -> Text:
    """Returns the title of a panel, in its top-right corner"""
    return next(t for t in ax.texts if t.get_gid() == "panel_title")


def assert_corner_texts(fig) -> None:
    """The title of each panel is in its top-right corner and the data quality text in its bottom-right corner, inside
    the panel"""
    fig.draw_without_rendering()
    padding = CORNER_PADDING * fig.dpi / 72
    for ax in fig.axes:
        box = ax.get_window_extent()
        title = panel_title(ax).get_window_extent()
        quality = next(t for t in ax.texts if t.get_text().startswith("ratio=")).get_window_extent()
        for text in (title, quality):
            assert box.x0 <= text.x0 and text.x1 == pytest.approx(box.x1 - padding, abs=1)
        assert title.y1 == pytest.approx(box.y1 - padding, abs=2) and quality.y0 == pytest.approx(box.y0 + padding, abs=2)
        assert quality.y1 < title.y0


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
    titles = [panel_title(ax).get_text() for ax in fig.axes]
    assert titles[:2] == ["1 MeV electrons/HET (sun viewing, 2 mins resolution)",
                          "5.9930 - 18.8300 MeV electrons/HET (sun viewing, 2 mins resolution)"]


def test_plot_event_with_the_peak_in_another_viewing(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    fake = FakeEPD(rises, peaks={("electrons", "north"): 300.0})
    tool = run(synthetic_tool(tmp_path, monkeypatch, fake=fake))
    fig = plot_event(tool, 1)
    # the flux at the onset viewing (solid) and at the peak flux viewing, north (dashed)
    assert [line.get_linestyle() for line in fig.axes[0].get_lines() if line.get_color() == "orange"] == ["-", "--"]


# channel groups added one by one, for the plots of 1 to 6 groups
GROUPS = [("electrons", "1 MeV", [0, 1]), ("protons", "8 MeV", [1, 2, 3]), ("electrons", "5.9930 - 18.8300 MeV", [3]),
          ("protons", "25 MeV", [18, 19]), ("protons", "50 MeV", [27]), ("protons", "35 MeV", [22, 23])]


@pytest.mark.parametrize("n_groups", range(1, len(GROUPS) + 1))
@image_compare
def test_plot_event_with_channel_groups(tmp_path, monkeypatch, n_groups):
    groups = {}
    for particle, label, channels in GROUPS[:n_groups]:
        groups.setdefault(particle, {})[label] = {"sensor": "HET", "channels": channels}
    groups["electrons"]["1 MeV"]["reference_channel"] = True
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, group_options=groups)), 1)
    assert len(fig.axes) == n_groups
    # the legend is above the first panel, and the title above the legend, once the layout is made
    fig.draw_without_rendering()
    legend = fig.axes[0].get_legend().get_window_extent()
    assert legend.y0 >= fig.axes[0].get_window_extent().y1
    assert fig.get_suptitle() == "Event 1"
    assert fig._suptitle.get_window_extent().y0 >= legend.y1
    assert_corner_texts(fig)
    return fig


@image_compare
def test_plot_event(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    return plot_event(run(synthetic_tool(tmp_path, monkeypatch, rises, shocks=[T0 + timedelta(hours=8)])), 1)


@image_compare
def test_plot_event_copied_onsets_at_the_end_of_the_background(tmp_path, monkeypatch):
    rises = {("electrons", viewing): T0 for viewing in VIEWINGS}  # flat protons
    events = {1: bg_end_event(T0 - timedelta(minutes=2))}
    tool = run(synthetic_tool(tmp_path, monkeypatch, rises, events=events))
    fig = plot_event(tool, 1)
    assert all(panel_title(ax).get_color() == "red" for ax in fig.axes)  # every onset is at the end of the background
    texts = [t.get_text() for t in fig.axes[2].texts]
    assert any("(from 1 MeV electrons, at BG end)" in text for text in texts)
    return fig


@image_compare
def test_plot_event_without_proton_onsets(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises.update({("protons", viewing): T0 + timedelta(hours=3) for viewing in VIEWINGS})  # outside the reference window
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, rises)), 1)
    assert panel_title(fig.axes[2]).get_text() == "8 MeV protons/HET (sun viewing, 30 mins resolution)"
    assert panel_title(fig.axes[2]).get_color() == "red" and panel_title(fig.axes[0]).get_color() == "black"
    # also in the panels without an onset
    assert_corner_texts(fig)
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


def legend_labels(fig) -> list[str]:
    return [text.get_text() for text in fig.axes[0].get_legend().get_texts()]


def test_legend_without_shocks_in_the_plot(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, shocks=[T0 + timedelta(days=30)])), 1)
    assert legend_labels(fig) == ["Data", "Event Range", "BG sample", "BG Level", "Peak Flux", "0.5 × Peak Flux",
                                  "2σ Threshold", "Onset Time", "Fluence"]


def test_legend_with_a_shock_in_the_plot(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, shocks=[T0 + timedelta(hours=8)])), 1)
    assert legend_labels(fig)[-1] == "Shock Time"


def test_legend_without_onsets(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, rises={})), 1)
    assert legend_labels(fig) == ["Data", "Event Range", "BG sample"]


def test_legend_entry_drawn_in_one_panel_only(tmp_path, monkeypatch):
    # the peak flux and fluence of only one channel group
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    for label in ["5.9930 - 18.8300 MeV", "8 MeV", "25 MeV", "50 MeV"]:
        particle = "electrons" if "18.8" in label else "protons"
        columns = [c for c in tool.df_results.columns if c.startswith(("Peak Flux", "Fluence"))]
        tool.df_results.loc[(1, particle, "HET", label), columns] = None
    assert {"Peak Flux", "Fluence"} <= set(legend_labels(plot_event(tool, 1)))


@pytest.mark.parametrize("panel_height", [1, 2.5, 6], ids=["small", "medium", "large"])
@image_compare
def test_plot_event_panel_height(tmp_path, monkeypatch, panel_height):
    groups = {"electrons": {"1 MeV": {"sensor": "HET", "channels": [0, 1], "reference_channel": True}},
              "protons": {"8 MeV": {"sensor": "HET", "channels": [1, 2, 3]}}}
    tool = run(synthetic_tool(tmp_path, monkeypatch, group_options=groups, panel_height=panel_height))
    fig = plot_event(tool, 1)
    assert tuple(fig.get_size_inches()) == (15, plot_height(panel_height, 2)) == (15, 2 * panel_height + 1.5)
    fig.draw_without_rendering()
    legend = fig.axes[0].get_legend().get_window_extent()
    assert fig._suptitle.get_window_extent().y0 >= legend.y1 >= legend.y0 >= fig.axes[0].get_window_extent().y1
    assert_corner_texts(fig)
    return fig


def test_plot_background_returns_a_figure_and_saves_it(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    filename = str(tmp_path / "background.png")
    fig = plot_background(tool, 1, filename=filename)
    assert os.path.getsize(filename) > 0
    # one panel per particle and sensor, with all its channel groups and the window
    assert [panel_title(ax).get_text() for ax in fig.axes] == ["electrons/HET (sun viewing, 2 mins resolution)",
                                                               "protons/HET (sun viewing, 2 mins resolution)"]
    assert [len(ax.lines) for ax in fig.axes] == [2 + 2, 3 + 2]
    assert fig.get_suptitle() == "Event 1: background 2021-01-01 10:00 to 2021-01-01 11:55 (default)"


@image_compare
def test_plot_background(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, events={1: bg_end_event(T0 - timedelta(minutes=5))})
    tool.set_bg_window(1, T0 - timedelta(hours=1), T0 - timedelta(minutes=10))
    return plot_background(tool, 1)
