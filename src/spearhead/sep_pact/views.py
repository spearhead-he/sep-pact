"""The plots, as matplotlib figures"""
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
from matplotlib import dates as mdates
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from .analysis import reference_iter, shocks_in_range


# width of the plots, and height of the title, legend and axis labels together (inches); the height of each panel is
# the panel_height parameter
PLOT_WIDTH = 15
MARGIN_HEIGHT = 1.5


# distance (points) of the panel title and the data quality text from the corners of the panel
CORNER_PADDING = 5


def _corner_text(ax, text: str, top: bool, **kwargs):
    """Writes the text inside the panel, in its top-right or bottom-right corner, whatever the size of the panel"""
    return ax.annotate(text, xy=(1, 1 if top else 0), xycoords="axes fraction",
                       xytext=(-CORNER_PADDING, -CORNER_PADDING if top else CORNER_PADDING), textcoords="offset points",
                       horizontalalignment="right", verticalalignment="top" if top else "bottom", **kwargs)


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
    bg_start = tool.events.loc[event_no, "BG Start"]
    bg_end = tool.events.loc[event_no, "BG End"]
    calc_end = tool.events.loc[event_no, "End Time"]
    chosen = tool.df_results.loc[(event_no, particle, sensor, mevlbl)]
    ts_length, n_zeroes, ratio = chosen["Quality Length"], chosen["Quality Zeroes"], chosen["Quality Ratio"]
    ax_title_params["color"] = "red"
    resolution = int(p.resample_freqs[-1].total_seconds()/60)
    _panel_title(ax, f"{mevlbl} {particle}/{sensor} ({p.fallback_viewing} viewing, {resolution} mins resolution)",
                 ax_title_params["color"])
    flux = tool.dfs_flux[particle][sensor][p.resample_freqs[-1]].loc[event_no, (p.fallback_viewing, mevlbl)]
    ax.plot(flux.index, flux.values, label="flux", color="orange", alpha=0.3)
    bot_lim, top_lim = ax.get_ylim()
    ax.fill_between([bg_start, bg_end], bot_lim, top_lim, color="green", alpha=0.3, label="background sample")
    ax.fill_between([bg_end, calc_end], bot_lim, top_lim, color="black", alpha=0.1, label="Event range")
    drawn.update({"data", "bg_sample", "event_range"})
    ratio_txt = f"ratio={f'{ratio:.2f}' if not pd.isna(ratio) else 'N/A'}"
    n_zeroes_txt = f"#zeroes={n_zeroes if not pd.isna(n_zeroes) else 'N/A'}"
    n_non_zeroes_txt = f"#non-zeroes={ts_length-n_zeroes if not pd.isna(ts_length) and not pd.isna(n_zeroes) else 'N/A'}"
    qties_txt = f"{ratio_txt}, {n_zeroes_txt}, {n_non_zeroes_txt}"
    _corner_text(ax, qties_txt, top=False)
    ax.set_ylim([bot_lim, top_lim])


def _channel_values(tool, event_no: int, particle: str, sensor: str, mevlbl: str) -> SimpleNamespace:
    """Returns the values of the panel of a channel group with an onset: its flux at the resolutions and viewings of
    the onset, peak flux and fluence, and the results"""
    chosen = tool.df_results.loc[(event_no, particle, sensor, mevlbl)]
    v = SimpleNamespace(
        bg_start=tool.events.loc[event_no, "BG Start"],
        bg_end=tool.events.loc[event_no, "BG End"],
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
    ax.fill_between([v.onset_time, v.calc_end], bot_lim, top_lim, color="black", alpha=0.1, label="Event range")
    ax.plot(v.flux.index, v.flux.values, label="flux", color="orange")
    if v.flux2 is not None:
        ax.plot(v.flux2.index, v.flux2.values, label="flux", color="orange", linestyle="--", alpha=0.5)
    if v.flux3 is not None:
        ax.plot(v.flux3.index, v.flux3.values, label="flux", color="brown", linestyle=":", alpha=0.5)
    ax.fill_between([v.bg_start, v.bg_end], bot_lim, top_lim, color="green", alpha=0.3, label="background sample")
    ax.axhline(y=v.bg_level, color="blue", linestyle="--", label="background level")
    ax.axvline(x=v.onset_time, color="green", linestyle="--", label=f"onset time ({v.onset_time.strftime('%Y-%m-%d %H:%M')})")
    drawn.update({"event_range", "data", "bg_sample", "bg_level", "onset", "threshold"})
    if not pd.isna(v.peak_time):
        drawn.update({"peak_flux", "peak_fraction"})
        ax.scatter(v.peak_time, v.peak_flux, color="red", zorder=5,
                   label=f"peak flux ({v.peak_flux:.2E}/{v.peak_time.strftime('%Y-%m-%d %H:%M')})")
        ax.axhline(y=v.peak_flux * params.fluence_peak_fraction, color="purple", linestyle="--",
                   label=f"{params.fluence_peak_fraction:g} peak flux")
    if not pd.isna(v.fluence_threshold):
        ax.axhline(y=v.fluence_threshold, color="purple", linestyle="--", alpha=0.5)
    ax.axhline(y=v.threshold, color="red", linestyle="--", label=f"{params.onset_sigma:g}\u03C3 threshold")
    if not pd.isna(v.fluence_start) and not pd.isna(v.fluence_end):
        ax.fill_between([v.fluence_start, v.fluence_end], bot_lim, top_lim, color="brown", alpha=0.2,
                        label=f"fluence ({v.fluence:.2E})")
        drawn.add("fluence")
    for shocktime in v.shocktimes:
        ax.axvline(x=shocktime, color="purple", linestyle=":", label=f"shock time ({shocktime.strftime('%Y-%m-%d %H:%M')})")
        drawn.add("shock")


def _draw_labels(ax, v: SimpleNamespace, bot_lim: float, top_lim: float, reference_channel: dict | None) -> None:
    """Writes the labels of the peak flux, the onset (with its notes), the fluence, the data quality and the shocks"""
    if v.has_peak:
        ax.text(v.peak_time + timedelta(minutes=15),
                v.peak_flux,
                f"{v.peak_flux:.2E}/{v.peak_time.strftime('%H:%M')}/{v.viewing_pf}/"
                f"{int(v.resample_pf.total_seconds()/60)} mins",
                color="red")
    onset_notes = []
    if v.onset_copied:
        onset_notes.append(f"from {reference_channel['mev']} {reference_channel['particle']}")
    if v.onset_at_bg_end:
        onset_notes.append("at BG end")
    ax.text(v.onset_time + timedelta(minutes=15),
            bot_lim * 10,
            f"{v.onset_time.strftime('%Y-%m-%d %H:%M')}" + (f" ({', '.join(onset_notes)})" if onset_notes else ""),
            color="green")
    if v.has_fluence:
        ax.text(v.fluence_start + abs(v.fluence_end - v.fluence_start)/2,
                top_lim / 5,
                f"{v.fluence:.2E}/{v.viewing_flu}/{int(v.resample_flu.total_seconds()/60)} mins",
                color="brown",
                horizontalalignment="center")
    _corner_text(ax, f"ratio={v.ratio:.2f}, #zeroes={v.n_zeroes}, #non-zeroes={v.ts_length-v.n_zeroes}", top=False)
    for shocktime in v.shocktimes:
        ax.text(shocktime + timedelta(minutes=15),
                bot_lim * 10,
                f"{shocktime.strftime('%H:%M')}",
                color="purple")


def _plot_channel(ax, tool, event_no: int, particle: str, sensor: str, mevlbl: str, ax_title_params: dict,
                  drawn: set) -> None:
    """Plots a channel group with an onset: the flux, background, onset, peak flux, fluence and shocks"""
    v = _channel_values(tool, event_no, particle, sensor, mevlbl)
    if v.onset_at_bg_end:
        ax_title_params["color"] = "red"
    _panel_title(ax, f"{mevlbl} {particle}/{sensor} ({v.viewing_ot} viewing, {int(v.resample_ot.total_seconds()/60)} "
                 "mins resolution)", ax_title_params["color"])
    bot_lim, top_lim = _axis_limits(v)
    _draw_data(ax, v, bot_lim, top_lim, tool.params, drawn)
    _draw_labels(ax, v, bot_lim, top_lim, tool.reference_channel)
    ax.set_ylim([bot_lim, top_lim])
    ax.set_xlim([v.flux.index[0], v.flux.index[-1]])


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
    time_formatter = mdates.ConciseDateFormatter(mdates.AutoDateLocator())
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

    fig.suptitle(f"Event {event_no}")
    fig.supylabel(r"Flux (particle/(cm$^2$ s sr MeV))")
    fig.supxlabel("Time (UTC)")
    axs[-1].xaxis.set_major_formatter(time_formatter)
    legend = [
        ("data", "Data", Line2D([0], [0], color="orange")),
        ("event_range", "Event Range", Patch(facecolor="black", alpha=0.1)),
        ("bg_sample", "BG sample", Patch(facecolor="green", alpha=0.3)),
        ("bg_level", "BG Level", Line2D([0], [0], color="blue", linestyle="--")),
        ("peak_flux", "Peak Flux", Line2D([0], [0], marker="o", color="white", markerfacecolor="red")),
        ("peak_fraction", f"{p.fluence_peak_fraction:g} × Peak Flux", Line2D([0], [0], color="purple", linestyle="--")),
        ("threshold", f"{p.onset_sigma:g}σ Threshold", Line2D([0], [0], color="red", linestyle="--")),
        ("onset", "Onset Time", Line2D([0], [0], color="green", linestyle="--")),
        ("fluence", "Fluence", Patch(facecolor="brown", alpha=0.2)),
        ("shock", "Shock Time", Line2D([0], [0], color="purple", linestyle=":")),
    ]
    legend = [(label, handle) for key, label, handle in legend if key in drawn]
    # above the first panel, below the title
    axs[0].legend([handle for _, handle in legend], [label for label, _ in legend], loc="lower center",
                  bbox_to_anchor=(0.5, 1.02), ncol=len(legend))
    if filename is not None:
        fig.savefig(filename)
    return fig


def plot_background(tool, event_no: int, filename: str | None = None) -> Figure:
    """Returns the plot of the background window of an event, and saves it to filename if one is given: one panel per
    particle and sensor with the flux of all its channel groups, at the finest resolution in the first viewing, and
    the window shaded

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
        ax.axvspan(event["BG Start"], event["BG End"], color="green", alpha=0.3, label="background window")
        for column in ("Start Time", "End Time"):
            ax.axvline(event[column], color="black", linestyle=":")
        ax.set_xlim(flux.index[0], flux.index[-1])
        _panel_title(ax, f"{particle}/{sensor} ({viewing} viewing, {resample_freq.total_seconds() / 60:g} mins "
                     "resolution)", "black")
        # right of the panel, away from the window at the start of the event
        ax.legend(loc="upper left", bbox_to_anchor=(1.005, 1), fontsize="small")
    fig.suptitle(f"Event {event_no}: background {event['BG Start']:%Y-%m-%d %H:%M} to {event['BG End']:%Y-%m-%d %H:%M} "
                 f"({event['BG Window']})")
    fig.supylabel(r"Flux (particle/(cm$^2$ s sr MeV))")
    fig.supxlabel("Time (UTC); dotted lines: start and end time of the event")
    axs[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))
    if filename is not None:
        fig.savefig(filename)
    return fig
