"""Server-side gerenderde inline-SVG trendlijnen — geen JS/CDN-afhankelijkheid
nodig, werkt overal (inclusief PDF-export contexten)."""

from __future__ import annotations


def sparkline_svg(scores: list[float], width: int = 140, height: int = 40, color: str = "#4caf7d") -> str:
    if not scores:
        return f'<svg width="{width}" height="{height}"></svg>'
    if len(scores) == 1:
        scores = [scores[0], scores[0]]

    lo, hi = 0.0, 100.0
    n = len(scores)
    step = width / (n - 1)
    points = []
    for i, s in enumerate(scores):
        x = i * step
        y = height - ((s - lo) / (hi - lo)) * height
        points.append((round(x, 1), round(y, 1)))

    path = " ".join(f"{x},{y}" for x, y in points)
    last_x, last_y = points[-1]

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" class="sparkline">
  <polyline points="{path}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
  <circle cx="{last_x}" cy="{last_y}" r="3" fill="{color}" />
</svg>"""


def trend_chart_svg(
    points: list[tuple[str, float]],
    width: int = 560,
    height: int = 220,
    color: str = "#4caf7d",
) -> str:
    """`points`: list of (label, score) tuples, oudste eerst."""
    pad_left, pad_right, pad_top, pad_bottom = 36, 12, 12, 28
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    if not points:
        return f'<svg width="{width}" height="{height}"><text x="10" y="20" fill="#9aa0ac" font-size="13">Nog geen scans.</text></svg>'

    labels = [p[0] for p in points]
    scores = [p[1] for p in points]
    n = len(scores)
    step = plot_w / (n - 1) if n > 1 else 0

    def xy(i: int, s: float) -> tuple[float, float]:
        x = pad_left + (i * step if n > 1 else plot_w / 2)
        y = pad_top + plot_h - (s / 100.0) * plot_h
        return round(x, 1), round(y, 1)

    coords = [xy(i, s) for i, s in enumerate(scores)]
    path = " ".join(f"{x},{y}" for x, y in coords)

    gridlines = ""
    for frac, label in [(0, "0"), (0.5, "50"), (1.0, "100")]:
        y = pad_top + plot_h - frac * plot_h
        gridlines += (
            f'<line x1="{pad_left}" y1="{y}" x2="{width - pad_right}" y2="{y}" '
            f'stroke="#2a2f3a" stroke-width="1" />'
            f'<text x="4" y="{y + 4}" fill="#9aa0ac" font-size="10">{label}</text>'
        )

    dots = ""
    for (x, y), s, label in zip(coords, scores, labels):
        dots += f'<circle cx="{x}" cy="{y}" r="3.5" fill="{color}" />'
        dots += f'<title>{label}: {s}</title>'

    x_labels = ""
    label_stride = max(1, n // 6)
    for i, label in enumerate(labels):
        if i % label_stride != 0 and i != n - 1:
            continue
        x, _ = coords[i]
        x_labels += f'<text x="{x}" y="{height - 6}" fill="#9aa0ac" font-size="10" text-anchor="middle">{label}</text>'

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" class="trend-chart">
  {gridlines}
  <polyline points="{path}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
  {dots}
  {x_labels}
</svg>"""
