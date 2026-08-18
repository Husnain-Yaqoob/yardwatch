"""Chart generation for the README.

Renders each figure twice — once for a light surface, once for a dark one —
so the README reads correctly under either GitHub theme. The dark variants use
hues stepped for a dark surface rather than the light values inverted.

Palette slots and surfaces are validated for colour-vision deficiency
separation and contrast; see the comment on THEMES.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import metrics, simulate, study  # noqa: E402
from .models import VehicleState  # noqa: E402


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    text_primary: str
    text_secondary: str
    grid: str
    series_1: str
    series_2: str


# Two validated palettes. Each passes the lightness band, chroma floor, CVD
# separation (worst adjacent pair ΔE 24.7 light / 26.8 dark, target >= 8),
# normal-vision floor and 3:1 contrast against its own surface.
THEMES = (
    Theme(
        name="light",
        surface="#fcfcfb",
        text_primary="#0b0b0b",
        text_secondary="#52514e",
        grid="#e3e2df",
        series_1="#2a78d6",
        series_2="#eb6834",
    ),
    Theme(
        name="dark",
        surface="#1a1a19",
        text_primary="#ffffff",
        text_secondary="#c3c2b7",
        grid="#383734",
        series_1="#3987e5",
        series_2="#d95926",
    ),
)

CAPACITIES = [2, 3, 4, 5]
TARGET_WAIT_MINUTES = 15


def _style(theme: Theme) -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": theme.surface,
            "axes.facecolor": theme.surface,
            "savefig.facecolor": theme.surface,
            "text.color": theme.text_primary,
            "axes.labelcolor": theme.text_secondary,
            "xtick.color": theme.text_secondary,
            "ytick.color": theme.text_secondary,
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.edgecolor": theme.grid,
            "grid.color": theme.grid,
            "grid.linewidth": 0.8,
        }
    )


def _finish_axis(ax, theme: Theme) -> None:
    """Recessive grid, no chartjunk."""
    ax.set_axisbelow(True)
    ax.yaxis.grid(True)
    ax.xaxis.grid(False)
    ax.tick_params(length=0)
    ax.spines["bottom"].set_color(theme.grid)


def capacity_figure(theme: Theme, nights: int = 300):
    """Two panels: how the decision looks. One measure per axis, never two."""
    results = study.sweep(
        CAPACITIES, nights=nights, target_wait=timedelta(minutes=TARGET_WAIT_MINUTES)
    )
    bays = [str(r.capacity) for r in results]
    slo = [r.mean_slo * 100 for r in results]
    overflow = [r.mean_overflow_minutes for r in results]

    fig, (left, right) = plt.subplots(1, 2, figsize=(10, 4.1))

    bars = left.bar(bays, slo, color=theme.series_1, width=0.62, zorder=3)
    left.bar_label(
        bars, fmt="%.0f%%", padding=4, color=theme.text_primary, fontsize=10, weight="bold"
    )
    left.set_title(
        f"Admitted within {TARGET_WAIT_MINUTES} min", color=theme.text_primary,
        fontsize=11, weight="bold", loc="left", pad=12,
    )
    left.set_xlabel("Bays")
    left.set_ylim(0, 108)
    left.set_yticks([0, 25, 50, 75, 100])
    left.set_yticklabels(["0", "25", "50", "75", "100%"])
    _finish_axis(left, theme)

    bars = right.bar(bays, overflow, color=theme.series_2, width=0.62, zorder=3)
    right.bar_label(
        bars, fmt="%.0f", padding=4, color=theme.text_primary, fontsize=10, weight="bold"
    )
    right.set_title(
        "Minutes per night with vehicles queued on the road",
        color=theme.text_primary, fontsize=11, weight="bold", loc="left", pad=12,
    )
    right.set_xlabel("Bays")
    right.set_ylim(0, max(overflow) * 1.2)
    _finish_axis(right, theme)

    fig.suptitle(
        f"Capacity sweep — {nights} simulated nights, mean {results[0].mean_arrivals:.1f} arrivals/night",
        color=theme.text_secondary, fontsize=10, y=0.99, x=0.011, ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def one_night_figure(theme: Theme, seed: int = 11, capacity: int = 2):
    """One night, second by second: why the queue happens.

    Both series are counts of vehicles, so they share one axis honestly.
    """
    _, yard = simulate.run(capacity=capacity, seed=seed)
    vehicles = yard.all_vehicles()

    # Replay the night as +1/-1 changes, same technique as metrics.
    events: list[tuple[object, int, int]] = []
    for v in vehicles:
        events.append((v.arrived_at, +1, 0))
        if v.admitted_at is not None:
            events.append((v.admitted_at, -1, +1))
        if v.departed_at is not None:
            events.append((v.departed_at, 0, -1))
    events.sort(key=lambda e: e[0])

    start = min(v.arrived_at for v in vehicles)
    times, queue_series, bay_series = [0.0], [0], [0]
    queue = bays_used = 0
    for moment, dq, db in events:
        queue += dq
        bays_used += db
        times.append((moment - start).total_seconds() / 3600)
        queue_series.append(queue)
        bay_series.append(bays_used)

    fig, ax = plt.subplots(figsize=(10, 3.8))

    ax.step(times, queue_series, where="post", color=theme.series_2,
            linewidth=2, zorder=3, label="Waiting on the road")
    ax.fill_between(times, queue_series, step="post", color=theme.series_2, alpha=0.15, zorder=2)
    ax.step(times, bay_series, where="post", color=theme.series_1,
            linewidth=2, zorder=3, label="Occupying a bay")

    ax.axhline(capacity, color=theme.text_secondary, linewidth=1,
               linestyle=(0, (4, 3)), zorder=1)
    ax.text(max(times) * 0.995, capacity + 0.18, f"{capacity} bays",
            color=theme.text_secondary, fontsize=9, ha="right")

    ax.set_title("One night — vehicles arrive in convoy, so the queue spikes",
                 color=theme.text_primary, fontsize=11, weight="bold", loc="left", pad=12)
    ax.set_xlabel("Hours into shift")
    ax.set_ylabel("Vehicles")
    ax.set_xlim(0, max(times))
    ax.set_ylim(0, max(max(queue_series), capacity) + 1.2)
    _finish_axis(ax, theme)

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9)
    for text in legend.get_texts():
        text.set_color(theme.text_secondary)

    fig.tight_layout()
    return fig


def render_all(outdir: str = "docs", nights: int = 300) -> list[str]:
    """Write every figure in both themes. Returns the paths written."""
    os.makedirs(outdir, exist_ok=True)
    written = []

    for theme in THEMES:
        _style(theme)
        for name, builder in (
            ("capacity", lambda t: capacity_figure(t, nights=nights)),
            ("one-night", one_night_figure),
        ):
            fig = builder(theme)
            path = os.path.join(outdir, f"{name}-{theme.name}.png")
            fig.savefig(path, dpi=160, bbox_inches="tight")
            plt.close(fig)
            written.append(path)

    return written


if __name__ == "__main__":
    for path in render_all():
        print(f"wrote {path}")
