"""Prompt 8: Pure inline SVG visualization primitives with zero external CDN dependencies."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple


def render_svg_card(number: str, label: str, subtitle: str = "", color: str = "#22c55e", width: int = 240, height: int = 120) -> str:
    """Render a standalone big-number scorecard with inline SVG."""
    return f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#1e293b;border-radius:8px;border:1px solid #334155;margin:6px;">
        <text x="20" y="30" fill="#94a3b8" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="13" font-weight="600">{label.upper()}</text>
        <text x="20" y="75" fill="{color}" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="32" font-weight="bold">{number}</text>
        <text x="20" y="102" fill="#64748b" font-family="-apple-system,BlinkMacSystemFont,sans-serif" font-size="12">{subtitle}</text>
    </svg>
    """


def render_svg_equity_curve(
    curves: Dict[str, List[float]],
    labels: Optional[List[str]] = None,
    width: int = 800,
    height: int = 340,
    colors: Optional[Dict[str, str]] = None,
) -> str:
    """Render overlaid equity curves as a pure inline SVG line chart."""
    colors = colors or {"rules": "#38bdf8", "gated": "#fbbf24", "jev": "#22c55e"}
    pad_left = 60
    pad_right = 30
    pad_top = 30
    pad_bottom = 40

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # Find min and max across all series
    all_vals = [v for s in curves.values() for v in s]
    if not all_vals:
        return "<svg></svg>"

    min_val = min(all_vals)
    max_val = max(all_vals)
    val_range = max(1.0, max_val - min_val)

    # Gridlines and y-ticks
    grid_lines = []
    for step in range(5):
        y_val = min_val + (val_range * (step / 4.0))
        y_pos = pad_top + plot_h - (plot_h * (step / 4.0))
        grid_lines.append(f'<line x1="{pad_left}" y1="{y_pos}" x2="{width - pad_right}" y2="{y_pos}" stroke="#334155" stroke-dasharray="3,3"/>')
        grid_lines.append(f'<text x="{pad_left - 8}" y="{y_pos + 4}" fill="#64748b" font-size="11" text-anchor="end">${y_val:,.0f}</text>')

    # Lines
    paths = []
    legend_items = []
    legend_x = pad_left + 10

    for arm_name, values in curves.items():
        if len(values) < 2:
            continue
        c = colors.get(arm_name, "#38bdf8")
        coords = []
        n_points = len(values)
        for i, val in enumerate(values):
            x = pad_left + (plot_w * (i / (n_points - 1)))
            y = pad_top + plot_h - (plot_h * ((val - min_val) / val_range))
            coords.append(f"{x:.1f},{y:.1f}")

        d_str = "M " + " L ".join(coords)
        paths.append(f'<path d="{d_str}" fill="none" stroke="{c}" stroke-width="2.5"/>')
        legend_items.append(f'<rect x="{legend_x}" y="12" width="14" height="14" rx="2" fill="{c}"/>')
        legend_items.append(f'<text x="{legend_x + 20}" y="24" fill="#cbd5e1" font-size="12" font-weight="600">{arm_name.upper()}</text>')
        legend_x += 120

    svg_content = f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#0f172a;border-radius:8px;border:1px solid #334155;">
        {''.join(legend_items)}
        {''.join(grid_lines)}
        {''.join(paths)}
        <line x1="{pad_left}" y1="{pad_top + plot_h}" x2="{width - pad_right}" y2="{pad_top + plot_h}" stroke="#475569" stroke-width="1.5"/>
        <line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{pad_top + plot_h}" stroke="#475569" stroke-width="1.5"/>
    </svg>
    """
    return svg_content


def render_svg_cost_waterfall(
    pnl_pre_cost: float,
    slippage: float,
    fees: float,
    pnl_net: float,
    width: int = 500,
    height: int = 240,
) -> str:
    """Render a cost waterfall chart showing friction deduction."""
    items = [
        ("Gross P&L", pnl_pre_cost, "#38bdf8"),
        ("Slippage", -slippage, "#ef4444"),
        ("Regulatory/Fees", -fees, "#f97316"),
        ("Net P&L", pnl_net, "#22c55e" if pnl_net >= 0 else "#ef4444"),
    ]

    max_mag = max(1.0, abs(pnl_pre_cost), abs(pnl_net), (slippage + fees) * 1.5)
    bar_h = 32
    pad_top = 30
    pad_left = 130
    plot_w = width - pad_left - 80

    bars = []
    for i, (name, val, color) in enumerate(items):
        y = pad_top + (i * 48)
        norm_w = (abs(val) / max_mag) * plot_w
        bars.append(f'<text x="{pad_left - 10}" y="{y + 20}" fill="#cbd5e1" font-size="12" font-weight="600" text-anchor="end">{name}</text>')
        bars.append(f'<rect x="{pad_left}" y="{y}" width="{max(2.0, norm_w):.1f}" height="{bar_h}" rx="4" fill="{color}"/>')
        sign = "+" if val > 0 else ""
        bars.append(f'<text x="{pad_left + norm_w + 8}" y="{y + 21}" fill="{color}" font-size="12" font-weight="bold">{sign}${val:,.2f}</text>')

    return f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#1e293b;border-radius:8px;border:1px solid #334155;margin:6px;">
        <text x="20" y="22" fill="#94a3b8" font-size="13" font-weight="bold">COST WATERFALL &amp; FRICTION</text>
        {''.join(bars)}
    </svg>
    """


def render_verdict_badge(verdict: str) -> str:
    """Verdict badge marked YES, MAYBE, or NO."""
    v_clean = verdict.upper().strip()
    if "YES" in v_clean or "PROFITABLE" in v_clean:
        bg, text = "#15803d", "VERDICT: YES (PROVEN EDGE)"
    elif "MAYBE" in v_clean or "BORDERLINE" in v_clean:
        bg, text = "#b45309", "VERDICT: MAYBE (BORDERLINE / REGIME-DEPENDENT)"
    else:
        bg, text = "#b91c1c", "VERDICT: NO (NO EDGE / LUCK / NOISE)"

    return f"""
    <div style="background:{bg};color:white;padding:12px 18px;border-radius:6px;font-weight:bold;font-size:16px;display:inline-block;margin-bottom:16px;">
        {text}
    </div>
    """
