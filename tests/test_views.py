"""Tests of the plots: the file names, saving, and the plot of an event compared with baseline images"""
import warnings
from datetime import timedelta
from io import BytesIO

import matplotlib.dates as mdates
import pandas as pd
import pytest
from PIL import Image
from matplotlib import pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.figure import Figure
from matplotlib.legend import Legend
from matplotlib.text import Text

from spearhead.sep_pact.views import (CORNER_PADDING, event_plot_filename, number_text, plot_background, plot_event,
                                      plot_height, quality_text)
from tests.helpers import T0, VIEWINGS, FakeEPD, bg_end_event, image_compare, synthetic_tool


def panel_title(ax) -> Text:
    """Returns the title of a panel, in its top-right corner"""
    return next(t for t in ax.texts if t.get_gid() == "panel_title")


def panel_legend(ax) -> Legend:
    """Returns the legend of the results of a panel, in its bottom-right corner"""
    return next(artist for artist in ax.artists if artist.get_gid() == "panel_legend")


def panel_legend_labels(ax) -> list[str]:
    return [text.get_text() for text in panel_legend(ax).get_texts()]


def assert_corner_texts(fig, below_the_title: bool = True) -> None:
    """The title of each panel is in its top-right corner, the legend of its results in its bottom-right corner and the
    data quality text in its bottom-left corner, inside the panel and apart from each other; the legend and text are
    below the title if below_the_title (in panels of the recommended height)"""
    fig.draw_without_rendering()
    padding = CORNER_PADDING * fig.dpi / 72
    for ax in fig.axes:
        box = ax.get_window_extent()
        title = panel_title(ax).get_window_extent()
        quality = next(t for t in ax.texts if t.get_text().startswith("quality:")).get_window_extent()
        legend = panel_legend(ax).get_window_extent()
        assert box.x0 <= title.x0 and title.x1 == pytest.approx(box.x1 - padding, abs=1)
        assert title.y1 == pytest.approx(box.y1 - padding, abs=2)
        assert quality.x0 == pytest.approx(box.x0 + padding, abs=1) and quality.y0 == pytest.approx(box.y0 + padding, abs=2)
        assert box.x0 < legend.x0 and legend.x1 < box.x1 and box.y0 < legend.y0
        assert quality.x1 < legend.x0
        assert max(quality.y1, legend.y1) < title.y0 or not below_the_title


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
    # 10 × 14.5 inches at plot_dpi, 200
    assert Image.open(filename).size == (2000, 2900)
    assert len(fig.axes) == 5
    titles = [panel_title(ax).get_text() for ax in fig.axes]
    assert titles[:2] == ["1 MeV electrons/HET", "5.9930 - 18.8300 MeV electrons/HET"]


def test_plot_event_with_the_peak_in_another_viewing(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    fake = FakeEPD(rises, peaks={("electrons", "north"): 300.0})
    tool = run(synthetic_tool(tmp_path, monkeypatch, fake=fake))
    fig = plot_event(tool, 1)
    # the flux at the onset viewing (solid) and at the peak flux viewing, north (dashed)
    assert [(line.get_color(), line.get_linestyle()) for line in fig.axes[0].get_lines()
            if line.get_color() in ("orange", "teal")] == [("orange", "-"), ("teal", "--")]


def test_plot_event_order_of_the_lines(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    fake = FakeEPD(rises, peaks={("electrons", "north"): 300.0})
    tool = run(synthetic_tool(tmp_path, monkeypatch, fake=fake, shocks=[T0 + timedelta(hours=8)]))
    ax = plot_event(tool, 1).axes[0]
    zorders = {}
    for line in ax.get_lines():
        zorders.setdefault(line.get_color(), set()).add(line.get_zorder())
    # the flux of the onset is on top of the one of the peak flux, which is on top of the one of the fluence
    data = [max(zorders[color]) for color in ("orange", "teal", "saddlebrown")]
    assert data == sorted(data, reverse=True)
    # then the horizontal lines (levels and thresholds), the vertical lines (onset and shocks), and the texts
    horizontal = set.union(*(zorders[color] for color in ("blue", "red", "purple")))
    vertical = zorders["green"] | zorders["deeppink"]
    # the shaded areas (background, event range and fluence) are behind them all
    areas = [area.get_zorder() for area in ax.collections if isinstance(area, PolyCollection)]
    assert len(areas) == 3 and max(areas) < min(zorders["saddlebrown"])
    assert max(data) < min(horizontal) and max(horizontal) < min(vertical)
    assert max(vertical) < min(text.get_zorder() for text in ax.texts)


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
    assert fig.get_suptitle() == "Event 1 (2021-01-01) | Solar Orbiter EPD"
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
    # every onset is at the end of the background
    assert all(panel_title(ax).get_color() == "darkorange" for ax in fig.axes)
    assert panel_legend_labels(fig.axes[2])[0] == "onset 11:58 (sun, 2 min, from 1 MeV electrons, at BG end)"
    return fig


@image_compare
def test_plot_event_without_proton_onsets(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    rises.update({("protons", viewing): T0 + timedelta(hours=3) for viewing in VIEWINGS})  # outside the reference window
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, rises)), 1)
    assert panel_title(fig.axes[2]).get_text() == "8 MeV protons/HET"
    assert panel_legend_labels(fig.axes[2]) == ["no onset (sun, 30 min)"]
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


def legend_labels(fig, empty: bool = False) -> list[str]:
    """The labels of the legend, without the empty entries that complete the columns of a group unless empty"""
    labels = [text.get_text() for text in fig.axes[0].get_legend().get_texts()]
    return labels if empty else [label for label in labels if label]


def test_legend_without_shocks_in_the_plot(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, shocks=[T0 + timedelta(days=30)])), 1)
    # the fluence is at another resolution than the peak flux: its data are drawn too
    # one group per column, as many rows as the longest group: the flux of the onset and the background, the onset
    # threshold and the event, the peak flux, and the fluence
    assert legend_labels(fig, empty=True) == [
        "Flux (onset)", "Background window", "Background level", "Onset threshold (2σ)", "Analysis range", "",
        "0.5 × peak flux", "", "", "Flux (fluence)", "Fluence threshold", ""]
    assert fig.axes[0].get_legend()._ncols == 4


def test_legend_with_the_data_of_the_peak_flux(tmp_path, monkeypatch):
    rises = {(particle, viewing): T0 for particle in ("electrons", "protons") for viewing in VIEWINGS}
    tool = run(synthetic_tool(tmp_path, monkeypatch, fake=FakeEPD(rises, peaks={("electrons", "north"): 300.0})))
    assert "Flux (peak)" in legend_labels(plot_event(tool, 1))


def test_legend_of_the_background_plot(tmp_path, monkeypatch):
    fig = plot_background(synthetic_tool(tmp_path, monkeypatch), 1)
    assert [text.get_text() for text in fig.axes[0].get_legend().get_texts()] == \
        ["1 MeV", "5.9930 - 18.8300 MeV", "background window", "start and end time"]


def test_legend_with_a_shock_in_the_plot(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, shocks=[T0 + timedelta(hours=8)])), 1)
    # at the end of the column of the onset and the event, which is the longest one
    labels = legend_labels(fig, empty=True)
    assert labels[labels.index("Analysis range") + 1] == "Shock time"
    assert fig.axes[0].get_legend()._ncols == 4 and len(labels) == 12


def test_legend_without_onsets(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch, rises={})), 1)
    assert legend_labels(fig, empty=True) == ["Background window", "Analysis range"]


def test_legend_entry_drawn_in_one_panel_only(tmp_path, monkeypatch):
    # the peak flux and fluence of only one channel group, with their thresholds
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    for label in ["5.9930 - 18.8300 MeV", "8 MeV", "25 MeV", "50 MeV"]:
        particle = "electrons" if "18.8" in label else "protons"
        columns = [c for c in tool.df_results.columns if c.startswith(("Peak Flux", "Fluence"))]
        tool.df_results.loc[(1, particle, "HET", label), columns] = None
    assert {"0.5 × peak flux", "Fluence threshold"} <= set(legend_labels(plot_event(tool, 1)))


@pytest.mark.parametrize("panel_height", [1, 2.5, 6], ids=["small", "medium", "large"])
@image_compare
def test_plot_event_panel_height(tmp_path, monkeypatch, panel_height):
    groups = {"electrons": {"1 MeV": {"sensor": "HET", "channels": [0, 1], "reference_channel": True}},
              "protons": {"8 MeV": {"sensor": "HET", "channels": [1, 2, 3]}}}
    tool = run(synthetic_tool(tmp_path, monkeypatch, group_options=groups, panel_height=panel_height))
    fig = plot_event(tool, 1)
    assert tuple(fig.get_size_inches()) == (10, plot_height(panel_height, 2)) == (10, 2 * panel_height + 2)
    fig.draw_without_rendering()
    legend = fig.axes[0].get_legend().get_window_extent()
    assert fig._suptitle.get_window_extent().y0 >= legend.y1 >= legend.y0 >= fig.axes[0].get_window_extent().y1
    # below the recommended height of 2 inches, the legend of the results reaches the title
    assert_corner_texts(fig, below_the_title=panel_height >= 2)
    return fig


def test_plot_background_returns_a_figure_and_saves_it(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.params.plot_dpi = 100
    filename = str(tmp_path / "background.png")
    fig = plot_background(tool, 1, filename=filename)
    # 10 × 7 inches at plot_dpi
    assert Image.open(filename).size == (1000, 700)
    # one panel per particle and sensor, with all its channel groups and the window
    assert [panel_title(ax).get_text() for ax in fig.axes] == ["electrons/HET", "protons/HET"]
    assert [len(ax.lines) for ax in fig.axes] == [2 + 2, 3 + 2]
    assert fig.get_suptitle() == "Event 1 (2021-01-01) | Solar Orbiter EPD, sun viewing, 2 min\nBackground 2021-01-01 " \
        "10:00 to 2021-01-01 " \
        "11:55 (default)\nEnd 2021-01-03 12:00 (default)"


def shaded(ax, label: str) -> tuple:
    """Returns the first and last time of the area of the label in the panel"""
    area = next(artist for artist in [*ax.collections, *ax.patches] if artist.get_label() == label)
    if isinstance(area, PolyCollection):
        times = area.get_paths()[0].vertices[:, 0]
    else:
        # axvspan: a rectangle
        times = area.get_patch_transform().transform(area.get_path().vertices)[:, 0]
    return tuple(pd.Timestamp(mdates.num2date(t)).tz_localize(None) for t in (times.min(), times.max()))


def test_plot_background_with_the_window_of_a_particle(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.set_bg_window(1, T0 - timedelta(hours=1), T0 - timedelta(minutes=10), "protons", "HET")
    fig = plot_background(tool, 1)
    assert [panel_title(ax).get_text() for ax in fig.axes] == [
        "electrons/HET", "protons/HET: background 2021-01-01 11:00 to 11:50 of protons HET (set)"]
    # the layout fits the titles
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        fig.savefig(BytesIO(), bbox_inches="tight")
    assert shaded(fig.axes[0], "background window") == (pd.Timestamp(T0 - timedelta(hours=2)),
                                                        pd.Timestamp(T0 - timedelta(minutes=5)))
    assert shaded(fig.axes[1], "background window") == (pd.Timestamp(T0 - timedelta(hours=1)),
                                                        pd.Timestamp(T0 - timedelta(minutes=10)))


def test_plot_event_with_the_window_of_a_particle(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch)
    tool.set_bg_window(1, T0 - timedelta(hours=1), T0 - timedelta(minutes=10), "protons")
    fig = plot_event(run(tool), 1)
    # the electrons, then the protons
    assert [shaded(ax, "background window")[1] for ax in fig.axes] == \
        [pd.Timestamp(T0 - timedelta(minutes=5))] * 2 + [pd.Timestamp(T0 - timedelta(minutes=10))] * 3


@image_compare
def test_plot_background(tmp_path, monkeypatch):
    tool = synthetic_tool(tmp_path, monkeypatch, events={1: bg_end_event(T0 - timedelta(minutes=5))})
    tool.set_bg_window(1, T0 - timedelta(hours=1), T0 - timedelta(minutes=10))
    return plot_background(tool, 1)


def test_plot_event_titles_of_corrected_onsets(tmp_path, monkeypatch):
    tool = run(synthetic_tool(tmp_path, monkeypatch))
    tool.set_onset(1, "electrons", "HET", "1 MeV", 2, "asun")
    tool.set_onset(1, "protons", "HET", "8 MeV")
    titles = [panel_title(ax) for ax in plot_event(tool, 1).axes]
    assert titles[0].get_text() == "1 MeV electrons/HET (corrected)"
    assert titles[2].get_text() == "8 MeV protons/HET (corrected)"
    assert titles[2].get_color() == "red"
    assert not titles[1].get_text().endswith("(corrected)") and not titles[3].get_text().endswith("(corrected)")


@pytest.mark.parametrize("value, text", [
    (72.64031, "72.6"), (0.5183, "0.518"), (0.01, "0.01"), (205.0, "205"),
    (312964.0, "3.13×10$^{5}$"), (1000, "1.00×10$^{3}$"), (0.002491, "2.49×10$^{-3}$"),
])
def test_number_text(value, text):
    assert number_text(value) == text


def test_quality_text():
    assert quality_text(569, 44, 0.0703) == "quality: 44 of 569 points zero or missing, ratio 0.07"
    assert quality_text(1, 0, float("nan")) == "quality: 0 of 1 points zero or missing, ratio N/A"
    assert quality_text(float("nan"), float("nan"), float("nan")) == "quality: N/A"


def test_plot_event_labels(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch)), 1)
    # the onset, the peak flux and the fluence, in this order, in the legend of the panel
    assert panel_legend_labels(fig.axes[0]) == ["onset 11:58 (sun, 2 min)", "peak 99.8 at 13:00 (sun, 2 min)",
                                                "fluence 7.40×10$^{5}$ (sun, 30 min)"]
    assert "quality: 0 of 1441 points zero or missing, ratio 0.00" in [text.get_text() for text in fig.axes[0].texts]


def test_plot_event_font_sizes_from_the_title_to_the_labels(tmp_path, monkeypatch):
    fig = plot_event(run(synthetic_tool(tmp_path, monkeypatch)), 1)
    ax = fig.axes[0]
    sizes = [fig._suptitle.get_fontsize(), fig._supylabel.get_fontsize(), fig.axes[-1].get_xticklabels()[0].get_fontsize(),
             panel_title(ax).get_fontsize(), ax.get_legend().get_texts()[0].get_fontsize(),
             panel_legend(ax).get_texts()[0].get_fontsize()]
    assert sizes == [17, 16, 14, 13, 12, 10]
    # the sizes of the plots do not change the default ones
    assert plt.rcParams["figure.titlesize"] == "large"
