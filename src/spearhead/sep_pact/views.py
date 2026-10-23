"""The plots, as matplotlib figures"""
from datetime import timedelta
from functools import wraps
from types import SimpleNamespace

import pandas as pd
from matplotlib import dates as mdates
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from matplotlib.legend import Legend
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from .analysis import reference_iter, shocks_in_range


# width of the plots, and height of the title, legend and axis labels together (inches); the height of each panel is
# the panel_height parameter
PLOT_WIDTH = 10
MARGIN_HEIGHT = 2

# the font sizes of the plots (points), from the largest: the title, the axis labels, the tick labels, the panel
# titles, the legend, and the legends and texts in the panels; scaled to the width of a page (about 7 inches), the
# smallest is still 7 points
FONT_SIZES = {"figure.titlesize": 17, "figure.labelsize": 16, "xtick.labelsize": 14, "ytick.labelsize": 14,
              "axes.titlesize": 13, "legend.fontsize": 12, "font.size": 10}


def _with_font_sizes(plot):
    """Makes the figure of the plot function with FONT_SIZES"""
    @wraps(plot)
    def wrapper(*args, **kwargs):
        with plt.rc_context(FONT_SIZES):
            return plot(*args, **kwargs)
    return wrapper


# colours of the panel titles of channel groups without an onset, and with the onset at the end of the background window
NO_ONSET_COLOR = "red"
BG_END_COLOR = "darkorange"
# the shaded background window, blue-grey: unlike the brown fluence interval also for red-green colour blindness
BG_WINDOW_STYLE = {"color": "steelblue", "alpha": 0.3}
# the shaded fluence interval
FLUENCE_STYLE = {"color": "brown", "alpha": 0.2}
# the shaded analysis range, from the onset to the end time or the first shock after the onset
ANALYSIS_RANGE_STYLE = {"color": "black", "alpha": 0.1}
# as in the VDA tool
FLUX_LABEL = r"Flux (cm$^{-2}$ s$^{-1}$ sr$^{-1}$ MeV$^{-1}$)"
# the marker of the peak flux, in its panel and in its legend
PEAK_MARKER = {"marker": "o", "linestyle": "", "color": "red"}

# the zorder of the elements of the event plot, from the bottom: the shaded areas, the data (the flux of the fluence, of
# the peak flux, then of the onset on top), the horizontal lines (levels and thresholds), the vertical lines (onset and
# shocks), then the texts (3)
AREAS_ZORDER = 1
DATA_ZORDER = 2.1
HORIZONTAL_ZORDER = 2.5
VERTICAL_ZORDER = 2.7

# the style of each line of the event plot, also used in its legend; the flux at the resolution and viewing of the
# peak flux and at the resolution of the fluence are in other colours, under the flux of the onset
LINE_STYLES = {
    "data": {"color": "orange", "zorder": DATA_ZORDER + 0.2},
    # the flux in fallback_viewing of a channel group without an onset
    "data_no_onset": {"color": "orange", "alpha": 0.3, "zorder": DATA_ZORDER + 0.2},
    "data_peak": {"color": "teal", "linestyle": "--", "alpha": 0.5, "zorder": DATA_ZORDER + 0.1},
    "data_fluence": {"color": "saddlebrown", "linestyle": "-.", "linewidth": 1.5, "zorder": DATA_ZORDER},
    "bg_level": {"color": "blue", "linestyle": "--", "zorder": HORIZONTAL_ZORDER},
    "threshold": {"color": "red", "linestyle": "--", "zorder": HORIZONTAL_ZORDER},
    "peak_fraction": {"color": "purple", "linestyle": "--", "zorder": HORIZONTAL_ZORDER},
    "fluence_threshold": {"color": "purple", "linestyle": ":", "alpha": 0.7, "zorder": HORIZONTAL_ZORDER},
    "onset": {"color": "green", "linestyle": "--", "zorder": VERTICAL_ZORDER},
    # solid, in a colour of its own, unlike the dashed and dotted lines of the thresholds
    "shock": {"color": "deeppink", "linewidth": 1.5, "zorder": VERTICAL_ZORDER},
}

# the background of the labels in the corners of the panels, which keeps them readable over the data
LABEL_BOX = {"facecolor": "white", "alpha": 0.7, "edgecolor": "none", "pad": 1}
# the most ticks of the time axis, which stay apart in the width of the plot
MAX_TIME_TICKS = 7

# distance (points) of the panel title and the corner labels from the corners of the panel
CORNER_PADDING = 5


def _corner_text(ax, text: str, top: bool, left: bool = False, line: int = 0, **kwargs):
    """Writes the text inside the panel, in one of its corners (top-right by default), whatever the size of the panel;
    line is the number of lines of text before it from the corner"""
    offset = CORNER_PADDING + line * 1.4 * plt.rcParams["font.size"]
    return ax.annotate(text, xy=(0 if left else 1, 1 if top else 0), xycoords="axes fraction",
                       xytext=(CORNER_PADDING if left else -CORNER_PADDING, -offset if top else offset),
                       textcoords="offset points", horizontalalignment="left" if left else "right",
                       verticalalignment="top" if top else "bottom", **kwargs)


def _time_axis(ax) -> None:
    """Labels the time axis with at most MAX_TIME_TICKS ticks, in the concise date format"""
    locator = mdates.AutoDateLocator(maxticks=MAX_TIME_TICKS)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def number_text(value: float) -> str:
    """Returns the number with 3 significant digits, as a power of ten (mathtext) below 0.01 and from 1000, e.g. 72.6,
    0.518, 3.13×10$^{5}$"""
    if 0.01 <= abs(value) < 1000:
        return f"{value:.3g}"
    mantissa, exponent = f"{value:.2e}".split("e")
    return f"{mantissa}×10$^{{{int(exponent)}}}$"


def minutes_text(resolution) -> str:
    """Returns the resolution (a timedelta) in minutes, e.g. 2 min"""
    return f"{resolution.total_seconds() / 60:g} min"


def quality_text(length, n_zeroes, ratio) -> str:
    """Returns the text of the data quality check of the onset series: its zero or missing points, and its ratio of
    transitions to them (see analysis.quality_analysis())"""
    if pd.isna(length) or pd.isna(n_zeroes):
        return "quality: N/A"
    ratio_text = "N/A" if pd.isna(ratio) else f"{ratio:.2f}"
    return f"quality: {int(n_zeroes)} of {int(length)} points zero or missing, ratio {ratio_text}"


def event_title(tool, event_no: int) -> str:
    """Returns the title of the plot of an event, as in the VDA tool, e.g. Event 20 (2021-10-31) | Solar Orbiter EPD"""
    return f"Event {event_no} ({tool.events.loc[event_no, 'Start Time']:%Y-%m-%d}) | Solar Orbiter EPD"


def _panel_legend(ax, entries: list) -> None:
    """Adds the legend of the results of a panel, [(handle, label)], in its bottom-right corner, on the semi-transparent
    white background of the labels"""
    legend = Legend(ax, [handle for handle, _ in entries], [label for _, label in entries], loc="lower right",
                    fontsize=plt.rcParams["font.size"], facecolor=LABEL_BOX["facecolor"], framealpha=LABEL_BOX["alpha"],
                    edgecolor=LABEL_BOX["edgecolor"])
    legend.set_gid("panel_legend")
    ax.add_artist(legend)


def _panel_title(ax, text: str, color: str) -> None:
    """Writes the title of a panel in its top-right corner"""
    # in the size of axes titles
    _corner_text(ax, text, top=True, color=color, fontweight="bold", fontsize=plt.rcParams["axes.titlesize"],
                 gid="panel_title")


def plot_height(panel_height: float, n_panels: int) -> float:
    """Returns the height of the plot of an event (inches), with n_panels channel groups"""
    return panel_height * n_panels + MARGIN_HEIGHT


def event_plot_filename(tool, event_no: int) -> str:
    """Returns the default file name of the plot of an event, e.g. event_007.png"""
    return f"event_{event_no:03}.png"


def _plot_no_onset(ax, tool, event_no: int, particle: str, sensor: str, mevlbl: str, ax_title_params: dict,
                   drawn: set) -> None:
    """Plots a channel group without an onset: the flux in fallback_viewing at the coarsest resolution, with a red title"""
    p = tool.params
    bg_start, bg_end = tool.bg_window(event_no, particle, sensor)[:2]
    calc_end = tool.events.loc[event_no, "End Time"]
    chosen = tool.df_results.loc[(event_no, particle, sensor, mevlbl)]
    ts_length, n_zeroes, ratio = chosen["Quality Length"], chosen["Quality Zeroes"], chosen["Quality Ratio"]
    ax_title_params["color"] = NO_ONSET_COLOR
    _panel_title(ax, f"{mevlbl} {particle}/{sensor}{_corrected(chosen)}", ax_title_params["color"])
    flux = tool.dfs_flux[particle][sensor][p.resample_freqs[-1]].loc[event_no, (p.fallback_viewing, mevlbl)]
    ax.plot(flux.index, flux.values, label="flux", **LINE_STYLES["data_no_onset"])
    bot_lim, top_lim = ax.get_ylim()
    ax.fill_between([bg_start, bg_end], bot_lim, top_lim, label="background window", zorder=AREAS_ZORDER,
                    **BG_WINDOW_STYLE)
    ax.fill_between([bg_end, calc_end], bot_lim, top_lim, label="analysis range", zorder=AREAS_ZORDER,
                    **ANALYSIS_RANGE_STYLE)
    drawn.update({"bg_window", "analysis_range"})
    _panel_legend(ax, [(Line2D([0], [0], **LINE_STYLES["data_no_onset"]),
                        f"no onset ({p.fallback_viewing}, {minutes_text(p.resample_freqs[-1])})")])
    _corner_text(ax, quality_text(ts_length, n_zeroes, ratio), top=False, left=True, bbox=LABEL_BOX)
    ax.set_ylim([bot_lim, top_lim])


def _corrected(chosen: pd.Series) -> str:
    """The note of the panel title of a channel group whose onset is corrected"""
    return " (corrected)" if bool(chosen.get("Onset Corrected", False)) else ""


def _channel_values(tool, event_no: int, particle: str, sensor: str, mevlbl: str) -> SimpleNamespace:
    """Returns the values of the panel of a channel group with an onset: its flux at the resolutions and viewings of
    the onset, peak flux and fluence, and the results"""
    chosen = tool.df_results.loc[(event_no, particle, sensor, mevlbl)]
    bg_start, bg_end = tool.bg_window(event_no, particle, sensor)[:2]
    v = SimpleNamespace(
        bg_start=bg_start,
        bg_end=bg_end,
        calc_end=tool.events.loc[event_no, "End Time"],
        ts_length=chosen["Quality Length"], n_zeroes=chosen["Quality Zeroes"], ratio=chosen["Quality Ratio"],
        resample_ot=chosen["Onset Resolution"], viewing_ot=chosen["Onset Viewing"],
        resample_pf=chosen["Peak Flux Resolution"], viewing_pf=chosen["Peak Flux Viewing"],
        resample_flu=chosen["Fluence Resolution"], viewing_flu=chosen["Fluence Viewing"],
        onset_time=chosen["Onset Time"],
        peak_time=chosen["Peak Flux Time"], peak_flux=chosen["Peak Flux"],
        fluence_start=chosen["Fluence Start"], fluence_end=chosen["Fluence End"],
        fluence=chosen["Fluence"], fluence_threshold=chosen["Fluence Threshold"],
    )
    # a channel with an onset can still have no peak flux or no fluence
    v.has_peak = not pd.isna(v.resample_pf)
    v.has_fluence = not pd.isna(v.resample_flu)
    v.onset_copied = bool(chosen["Onset Copied"])
    v.onset_at_bg_end = bool(chosen["Onset at BG End"])
    v.corrected = _corrected(chosen)
    fluxes = tool.dfs_flux[particle][sensor]
    v.flux = fluxes[v.resample_ot].loc[event_no, (v.viewing_ot, mevlbl)]
    v.flux2 = None
    if v.has_peak and (v.viewing_ot != v.viewing_pf or v.resample_ot != v.resample_pf):
        v.flux2 = fluxes[v.resample_pf].loc[event_no, (v.viewing_pf, mevlbl)]
    v.flux3 = None
    if v.has_fluence and v.resample_pf != v.resample_flu:
        v.flux3 = fluxes[v.resample_flu].loc[event_no, (v.viewing_flu, mevlbl)]
    series = tool.df_series.loc[(event_no, particle, sensor, mevlbl, v.resample_ot, v.viewing_ot)]
    v.bg_level = series["BG Level"]
    v.threshold = series["Threshold"]
    if len(shocks := shocks_in_range(tool.shocktimes, v.onset_time, v.calc_end)) > 0:
        v.calc_end = shocks[0]
    v.shocktimes = shocks_in_range(tool.shocktimes, v.flux.index[0], v.flux.index[-1])
    return v


def _axis_limits(v: SimpleNamespace) -> tuple[float, float]:
    """Returns the y-axis limits: two decades above the decade of the peak flux (or of the maximum flux), and one
    below the decade of the background level (or four below the top)"""
    top_lim = 1e6
    if not pd.isna(v.peak_time):
        top_lim = float(f"1e{int(f'{v.peak_flux:e}'.split('e')[1]) + 2}")
    elif v.flux.max() > 0:
        top_lim = float(f"1e{int(f'{v.flux.max():e}'.split('e')[1]) + 2}")
    if not pd.isna(v.bg_level) and v.bg_level > 0:
        bot_lim = float(f"1e{int(f'{v.bg_level:e}'.split('e')[1]) - 1}")
    else:
        bot_lim = float(f"1e{int(f'{top_lim:e}'.split('e')[1]) - 4}")
    return bot_lim, top_lim


def _draw_data(ax, v: SimpleNamespace, bot_lim: float, top_lim: float, params, drawn: set) -> None:
    """Draws the event range, the flux, the background, the onset, the peak flux, the thresholds, the fluence and
    the shocks"""
    ax.fill_between([v.onset_time, v.calc_end], bot_lim, top_lim, label="analysis range", zorder=AREAS_ZORDER,
                    **ANALYSIS_RANGE_STYLE)
    ax.plot(v.flux.index, v.flux.values, label="flux", **LINE_STYLES["data"])
    if v.flux2 is not None:
        ax.plot(v.flux2.index, v.flux2.values, label="flux", **LINE_STYLES["data_peak"])
        drawn.add("data_peak")
    if v.flux3 is not None:
        ax.plot(v.flux3.index, v.flux3.values, label="flux", **LINE_STYLES["data_fluence"])
        drawn.add("data_fluence")
    ax.fill_between([v.bg_start, v.bg_end], bot_lim, top_lim, label="background window", zorder=AREAS_ZORDER,
                    **BG_WINDOW_STYLE)
    ax.axhline(y=v.bg_level, label="background level", **LINE_STYLES["bg_level"])
    ax.axvline(x=v.onset_time, label=f"onset time ({v.onset_time.strftime('%Y-%m-%d %H:%M')})", **LINE_STYLES["onset"])
    drawn.update({"analysis_range", "data", "bg_window", "bg_level", "onset", "threshold"})
    if not pd.isna(v.peak_time):
        drawn.update({"peak_flux", "peak_fraction"})
        ax.scatter(v.peak_time, v.peak_flux, color="red", zorder=5,
                   label=f"peak flux ({v.peak_flux:.2E}/{v.peak_time.strftime('%Y-%m-%d %H:%M')})")
        ax.axhline(y=v.peak_flux * params.fluence_peak_fraction, label=f"{params.fluence_peak_fraction:g} peak flux",
                   **LINE_STYLES["peak_fraction"])
    if not pd.isna(v.fluence_threshold):
        ax.axhline(y=v.fluence_threshold, **LINE_STYLES["fluence_threshold"])
        drawn.add("fluence_threshold")
    ax.axhline(y=v.threshold, label=f"{params.onset_sigma:g}\u03C3 threshold", **LINE_STYLES["threshold"])
    if not pd.isna(v.fluence_start) and not pd.isna(v.fluence_end):
        ax.fill_between([v.fluence_start, v.fluence_end], bot_lim, top_lim, label=f"fluence ({v.fluence:.2E})",
                        zorder=AREAS_ZORDER, **FLUENCE_STYLE)
    for shocktime in v.shocktimes:
        ax.axvline(x=shocktime, label=f"shock time ({shocktime.strftime('%Y-%m-%d %H:%M')})", **LINE_STYLES["shock"])
        drawn.add("shock")


def _draw_labels(ax, v: SimpleNamespace, bot_lim: float, reference_channel: dict | None) -> None:
    """Writes the legend of the onset (with its notes), the peak flux and the fluence in the bottom-right corner, the data
    quality in the bottom-left corner, and the times of the shocks"""
    notes = [v.viewing_ot, minutes_text(v.resample_ot)]
    if v.onset_copied:
        notes.append(f"from {reference_channel['mev']} {reference_channel['particle']}")
    if v.onset_at_bg_end:
        notes.append("at BG end")
    entries = [(Line2D([0], [0], **LINE_STYLES["onset"]), f"onset {v.onset_time:%H:%M} ({', '.join(notes)})")]
    if v.has_peak:
        entries.append((Line2D([0], [0], **PEAK_MARKER), f"peak {number_text(v.peak_flux)} at {v.peak_time:%H:%M} "
                        f"({v.viewing_pf}, {minutes_text(v.resample_pf)})"))
    if v.has_fluence:
        entries.append((Patch(**FLUENCE_STYLE), f"fluence {number_text(v.fluence)} ({v.viewing_flu}, "
                        f"{minutes_text(v.resample_flu)})"))
    _panel_legend(ax, entries)
    _corner_text(ax, quality_text(v.ts_length, v.n_zeroes, v.ratio), top=False, left=True, bbox=LABEL_BOX)
    for shocktime in v.shocktimes:
        ax.text(shocktime + timedelta(minutes=15),
                bot_lim * 10,
                f"{shocktime.strftime('%H:%M')}",
                color=LINE_STYLES["shock"]["color"], bbox=LABEL_BOX)


def _plot_channel(ax, tool, event_no: int, particle: str, sensor: str, mevlbl: str, ax_title_params: dict,
                  drawn: set) -> None:
    """Plots a channel group with an onset: the flux, background, onset, peak flux, fluence and shocks"""
    v = _channel_values(tool, event_no, particle, sensor, mevlbl)
    if v.onset_at_bg_end:
        ax_title_params["color"] = BG_END_COLOR
    _panel_title(ax, f"{mevlbl} {particle}/{sensor}{v.corrected}", ax_title_params["color"])
    bot_lim, top_lim = _axis_limits(v)
    _draw_data(ax, v, bot_lim, top_lim, tool.params, drawn)
    _draw_labels(ax, v, bot_lim, tool.reference_channel)
    ax.set_ylim([bot_lim, top_lim])
    ax.set_xlim([v.flux.index[0], v.flux.index[-1]])


@_with_font_sizes
def plot_event(tool, event_no: int, filename: str | None = None) -> Figure:
    """Returns the plot of an event, with one panel per channel group, and saves it to filename if one is given

    tool is a SEPPACT whose steps have run, up to run_fluences().
    """
    p = tool.params
    num_plots = len([True for k in p.group_options.keys() for _ in p.group_options[k]])
    # the panels, and the title, legend and axis labels around them
    fig, axs = plt.subplots(figsize=(PLOT_WIDTH, plot_height(p.panel_height, num_plots)),
                            nrows=num_plots,
                            ncols=1,
                            sharex=True,
                            squeeze=False,
                            layout="constrained")
    axs = axs[:, 0]
    # the elements drawn in at least one panel, which are shown in the legend
    drawn = set()
    i_ax = 0
    for particle in reference_iter(tool.particles, tool.reference_channel):
        for sensor in reference_iter(tool.sensors[particle], tool.reference_channel):
            for mevlbl in reference_iter(p.group_options[particle].keys(), tool.reference_channel):
                ax_title_params = {"color": "black"}
                axs[i_ax].grid()
                axs[i_ax].set_yscale("log")
                if pd.isna(tool.df_results.loc[(event_no, particle, sensor, mevlbl), "Onset Resolution"]):
                    _plot_no_onset(axs[i_ax], tool, event_no, particle, sensor, mevlbl, ax_title_params, drawn)
                else:
                    _plot_channel(axs[i_ax], tool, event_no, particle, sensor, mevlbl, ax_title_params, drawn)
                i_ax += 1

    fig.suptitle(event_title(tool, event_no))
    fig.supylabel(FLUX_LABEL)
    fig.supxlabel("Time (UTC)")
    _time_axis(axs[-1])
    # one group per column: the flux of the onset and the background, the onset threshold and the event, the peak flux,
    # and the fluence; the onset, the peak flux and the fluence themselves are in the legend of each panel
    groups = [
        [("data", "Flux (onset)", Line2D([0], [0], **LINE_STYLES["data"])),
         ("bg_window", "Background window", Patch(facecolor=BG_WINDOW_STYLE["color"], alpha=BG_WINDOW_STYLE["alpha"])),
         ("bg_level", "Background level", Line2D([0], [0], **LINE_STYLES["bg_level"]))],
        [("threshold", f"Onset threshold ({p.onset_sigma:g}σ)", Line2D([0], [0], **LINE_STYLES["threshold"])),
         ("analysis_range", "Analysis range", Patch(facecolor=ANALYSIS_RANGE_STYLE["color"],
                                                    alpha=ANALYSIS_RANGE_STYLE["alpha"])),
         ("shock", "Shock time", Line2D([0], [0], **LINE_STYLES["shock"]))],
        [("data_peak", "Flux (peak)", Line2D([0], [0], **LINE_STYLES["data_peak"])),
         ("peak_fraction", f"{p.fluence_peak_fraction:g} × peak flux", Line2D([0], [0], **LINE_STYLES["peak_fraction"]))],
        [("data_fluence", "Flux (fluence)", Line2D([0], [0], **LINE_STYLES["data_fluence"])),
         ("fluence_threshold", "Fluence threshold", Line2D([0], [0], **LINE_STYLES["fluence_threshold"]))],
    ]
    columns = [entries for group in groups if (entries := [(label, handle) for key, label, handle in group if key in drawn])]
    # the legend is filled column by column, as many rows as the longest group: empty entries complete the others
    rows = max(len(entries) for entries in columns)
    legend = [entry for entries in columns for entry in entries + [("", Line2D([], [], alpha=0))] * (rows - len(entries))]
    # above the first panel, below the title
    axs[0].legend([handle for _, handle in legend], [label for label, _ in legend], loc="lower center",
                  bbox_to_anchor=(0.5, 1.02), ncol=len(columns))
    if filename is not None:
        fig.savefig(filename, dpi=p.plot_dpi)
    return fig


@_with_font_sizes
def plot_background(tool, event_no: int, filename: str | None = None) -> Figure:
    """Returns the plot of the background windows of an event, and saves it to filename if one is given: one panel per
    particle and sensor with the flux of all its channel groups, at the finest resolution in the first viewing, and
    its window shaded; the title of a panel with its own window gives the window

    tool is a SEPPACT after run_data().
    """
    p = tool.params
    resample_freq, viewing = p.resample_freqs[0], p.viewings[0]
    panels = [(particle, sensor) for particle in reference_iter(tool.particles, tool.reference_channel)
              for sensor in reference_iter(tool.sensors[particle], tool.reference_channel)]
    fig, axs = plt.subplots(figsize=(PLOT_WIDTH, plot_height(p.panel_height, len(panels))), nrows=len(panels), ncols=1,
                            sharex=True, squeeze=False, layout="constrained")
    axs = axs[:, 0]
    event = tool.events.loc[event_no]
    for ax, (particle, sensor) in zip(axs, panels):
        flux = tool.dfs_flux[particle][sensor][resample_freq].loc[event_no]
        for mevlbl in reference_iter(p.group_options[particle].keys(), tool.reference_channel):
            ax.plot(flux.index, flux[(viewing, mevlbl)].values, label=mevlbl)
        ax.set_yscale("log")
        ax.grid()
        window = tool.bg_window(event_no, particle, sensor)
        ax.axvspan(window.start, window.end, label="background window", zorder=AREAS_ZORDER, **BG_WINDOW_STYLE)
        # one legend entry for both lines
        ax.axvline(event["Start Time"], color="black", linestyle=":", label="start and end time")
        ax.axvline(event["End Time"], color="black", linestyle=":", label="_nolegend_")
        ax.set_xlim(flux.index[0], flux.index[-1])
        end_format = "%H:%M" if window.start.date() == window.end.date() else "%Y-%m-%d %H:%M"
        own = (f": background {window.start:%Y-%m-%d %H:%M} to {window.end:{end_format}} of "
               f"{' '.join(filter(None, window[3:]))} ({window.source})") if window.particle else ""
        _panel_title(ax, f"{particle}/{sensor}{own}", "black")
        # right of the panel, away from the window at the start of the event
        ax.legend(loc="upper left", bbox_to_anchor=(1.005, 1))
    fig.suptitle(f"{event_title(tool, event_no)}, {viewing} viewing, {minutes_text(resample_freq)}\n"
                 f"Background {event['BG Start']:%Y-%m-%d %H:%M} to "
                 f"{event['BG End']:%Y-%m-%d %H:%M} ({event['BG Window Source']})\nEnd {event['End Time']:%Y-%m-%d %H:%M} "
                 f"({event['End Time Source']})")
    fig.supylabel(FLUX_LABEL)
    fig.supxlabel("Time (UTC)")
    _time_axis(axs[-1])
    if filename is not None:
        fig.savefig(filename, dpi=p.plot_dpi)
    return fig
