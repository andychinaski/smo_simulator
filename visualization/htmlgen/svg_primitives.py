from __future__ import annotations

from typing import List, Tuple

from .formatting import esc


def svg_text(x: float, y: float, text: str, size: int = 12,
             anchor: str = "start", fill: str = "#222", css_class: str = "") -> str:
    cls = f' class="{css_class}"' if css_class else ""
    return (
        f'<text{cls} x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
        f'text-anchor="{anchor}" fill="{fill}">{esc(text)}</text>'
    )


def svg_line(x1: float, y1: float, x2: float, y2: float,
             stroke: str = "#bbb", width: float = 1.0, opacity: float = 1.0,
             nss: bool = True) -> str:
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"{ve}/>'
    )


def svg_rect(x: float, y: float, w: float, h: float,
             fill: str, stroke: str = "#333", rx: float = 4.0,
             title: str = "", nss: bool = True) -> str:
    w = max(1.0, w)
    t = f"<title>{esc(title)}</title>" if title else ""
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
        f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1"{ve}>{t}</rect>'
    )


def svg_circle(cx: float, cy: float, r: float,
               fill: str, stroke: str = "#333", title: str = "",
               css_class: str = "", nss: bool = True) -> str:
    t = f"<title>{esc(title)}</title>" if title else ""
    cls = f' class="{css_class}"' if css_class else ""
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    return (
        f'<circle{cls} cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1"{ve}>{t}</circle>'
    )


def svg_polyline(points: List[Tuple[float, float]],
                 stroke: str = "#5b7cff", width: float = 1.0,
                 opacity: float = 0.55, nss: bool = True) -> str:
    if len(points) < 2:
        return ""
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    pts = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)
    return f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"{ve}/>'


def orthogonalize(points: List[Tuple[float, float]], eps: float = 1e-9) -> List[Tuple[float, float]]:
    if not points:
        return points
    out: List[Tuple[float, float]] = [points[0]]

    for x2, y2 in points[1:]:
        x1, y1 = out[-1]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        if dx <= eps and dy <= eps:
            continue

        if dx <= eps or dy <= eps:
            out.append((x2, y2))
            continue

        out.append((x2, y1))
        out.append((x2, y2))

    compact: List[Tuple[float, float]] = []
    for p in out:
        if not compact or (abs(compact[-1][0] - p[0]) > eps or abs(compact[-1][1] - p[1]) > eps):
            compact.append(p)
    return compact