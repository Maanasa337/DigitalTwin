"""Server-side charts for reports (FR-RP-02), in the Section 9 light palette.

A report is a printed artefact, so the charts use the light theme and are embedded as base64 PNG
data URIs — one self-contained HTML file survives being emailed, archived or handed to WeasyPrint
without a second request for an image.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

log = logging.getLogger(__name__)

# Architecture §9.2, light column. Assigned in fixed order, never cycled.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
GRIDLINE = "#e1e0d9"
INK = "#0b0b0b"
MUTED = "#898781"
SURFACE = "#ffffff"

FIGSIZE = (7.2, 2.6)
DPI = 110


def _png(figure: Any) -> str:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=DPI, bbox_inches="tight", facecolor=SURFACE)
    buffer.seek(0)
    return "data:image/png;base64," + base64.b64encode(buffer.read()).decode()


def _axes() -> tuple[Any, Any]:
    import matplotlib

    matplotlib.use("Agg")  # no display on a worker; must be set before pyplot is imported
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(figsize=FIGSIZE, facecolor=SURFACE)
    axes.set_facecolor(SURFACE)
    axes.grid(True, color=GRIDLINE, linewidth=0.8)
    axes.set_axisbelow(True)
    for spine in ("top", "right"):
        axes.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        axes.spines[spine].set_color(GRIDLINE)
    axes.tick_params(colors=MUTED, labelsize=8)
    return figure, axes


def line_chart(points: list[dict[str, Any]], *, x: str, y: str, label: str, ylabel: str = "") -> str | None:
    """A time series, or None when there is nothing to draw — a report shows no empty axes."""
    usable = [(row[x], row[y]) for row in points if row.get(y) is not None]
    if len(usable) < 2:
        return None
    try:
        import matplotlib.pyplot as plt
        from matplotlib.dates import DateFormatter

        figure, axes = _axes()
        xs = [_to_datetime(a) for a, _ in usable]
        axes.plot(xs, [b for _, b in usable], color=SERIES[0], linewidth=1.8, label=label)
        axes.set_ylabel(ylabel or label, color=MUTED, fontsize=9)
        axes.xaxis.set_major_formatter(DateFormatter("%d %b\n%H:%M"))
        image = _png(figure)
        plt.close(figure)
        return image
    except Exception:
        # A missing chart must never fail a report that is otherwise complete.
        log.warning("chart rendering failed", exc_info=True)
        return None


def bar_chart(rows: list[dict[str, Any]], *, label_key: str, value_key: str, ylabel: str = "") -> str | None:
    usable = [(str(r[label_key]), float(r[value_key])) for r in rows if r.get(value_key) is not None]
    if not usable:
        return None
    try:
        import matplotlib.pyplot as plt

        figure, axes = _axes()
        axes.bar(
            [a for a, _ in usable],
            [b for _, b in usable],
            color=[SERIES[i % len(SERIES)] for i in range(len(usable))],
        )
        axes.set_ylabel(ylabel, color=MUTED, fontsize=9)
        axes.tick_params(axis="x", labelrotation=20)
        image = _png(figure)
        plt.close(figure)
        return image
    except Exception:
        log.warning("chart rendering failed", exc_info=True)
        return None


def _to_datetime(value: Any) -> Any:
    from datetime import datetime

    return datetime.fromisoformat(value) if isinstance(value, str) else value


def for_report(report_type: str, data: dict[str, Any]) -> dict[str, str]:
    """The charts each report type carries, keyed by the name its template references."""
    charts: dict[str, str | None] = {}
    if report_type == "machine_health":
        charts["health"] = line_chart(data.get("health_series", []), x="t", y="health", label="Health", ylabel="%")
        charts["rul"] = line_chart(
            data.get("rul_series", []), x="t", y="rul", label="RUL", ylabel=data.get("rul_unit", "cycles")
        )
    elif report_type == "energy":
        charts["intensity"] = line_chart(
            data.get("intensity_trend", []), x="t", y="energy_per_unit", label="kWh per unit", ylabel="kWh/unit"
        )
        charts["consumers"] = bar_chart(
            data.get("top_consumers", []), label_key="asset", value_key="energy_kwh", ylabel="kWh"
        )
    elif report_type == "weekly_maintenance":
        charts["by_status"] = bar_chart(
            [{"status": k, "count": v} for k, v in (data.get("by_status") or {}).items()],
            label_key="status",
            value_key="count",
            ylabel="Work orders",
        )
    return {key: value for key, value in charts.items() if value}
