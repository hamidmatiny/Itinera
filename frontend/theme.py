"""Premium dark-mode theme, glassmorphism surfaces, and layout primitives."""

from __future__ import annotations

import html
import streamlit as st

# Raw CSS rules only — wrapped in <style> at injection time.
# Fonts load via @import so the payload stays style-only for st.html routing.
_GLOBAL_THEME_RULES = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Sora:wght@500;600;700;800&display=swap');

:root {
    --bg-deep: #0c0e14;
    --bg-elevated: rgba(20, 24, 33, 0.75);
    --glass-border: rgba(255, 255, 255, 0.08);
    --glass-border-hover: rgba(255, 255, 255, 0.2);
    --text-primary: #f4f6fb;
    --text-muted: #8e9aa8;
    --accent: #7c9cff;
    --accent-soft: rgba(124, 156, 255, 0.16);
    --success: #5eead4;
    --warning: #fbbf24;
    --radius-lg: 16px;
    --radius-pill: 999px;
    --shadow-soft: 0 8px 32px rgba(0, 0, 0, 0.35);
    --transition: all 0.3s ease;
}

html, body, [class*="css"] {
    font-family: "Inter", "Sora", -apple-system, BlinkMacSystemFont, sans-serif !important;
    transition: var(--transition);
}

.stApp {
    background:
        radial-gradient(1200px 600px at 10% -10%, rgba(124, 156, 255, 0.12), transparent 55%),
        radial-gradient(900px 500px at 90% 0%, rgba(94, 234, 212, 0.08), transparent 50%),
        var(--bg-deep) !important;
    color: var(--text-primary);
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1200px;
}

h1, h2, h3, h4, h5, h6, .hero-title {
    font-family: "Sora", "Inter", sans-serif !important;
    letter-spacing: -0.03em;
}

[data-testid="stSidebar"] {
    background: rgba(12, 14, 20, 0.88) !important;
    border-right: 1px solid var(--glass-border);
    backdrop-filter: blur(18px);
}

[data-testid="stSidebar"] * {
    transition: var(--transition);
}

.stButton > button, [data-testid="stDownloadButton"] > button {
    border-radius: 12px !important;
    border: 1px solid var(--glass-border) !important;
    background: rgba(255, 255, 255, 0.04) !important;
    color: var(--text-primary) !important;
    transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1), box-shadow 0.3s ease, border-color 0.3s ease !important;
}

.stButton > button:hover, [data-testid="stDownloadButton"] > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.28);
    border-color: var(--glass-border-hover) !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: transparent;
    border-bottom: 1px solid var(--glass-border);
}

.stTabs [data-baseweb="tab"] {
    border-radius: 10px 10px 0 0;
    padding: 10px 18px;
    transition: var(--transition);
}

.hero-wrap {
    display: grid;
    grid-template-columns: 1.4fr 0.8fr;
    gap: 28px;
    align-items: end;
    margin: 0 0 36px 0;
    padding: 0 4px;
}

@media (max-width: 768px) {
    .hero-wrap { grid-template-columns: 1fr; gap: 16px; }
}

.hero-title {
    font-size: clamp(2.2rem, 4vw, 3.4rem);
    font-weight: 800;
    line-height: 1.05;
    margin: 0 0 12px 0;
    background: linear-gradient(135deg, #ffffff 0%, #b8c5ff 55%, #5eead4 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.hero-subtitle {
    font-size: 1.05rem;
    line-height: 1.65;
    color: var(--text-muted);
    margin: 0;
    max-width: 56ch;
}

.hero-kicker {
    font-size: 0.78rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 10px;
    font-weight: 600;
}

.glass-panel {
    background: var(--bg-elevated);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-lg);
    padding: 24px;
    backdrop-filter: blur(16px);
    box-shadow: var(--shadow-soft);
    transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1), box-shadow 0.3s ease, border-color 0.3s ease;
}

.glass-panel:hover {
    transform: translateY(-2px);
    border-color: var(--glass-border-hover);
}

.status-banner {
    border-radius: 14px;
    padding: 14px 18px;
    margin: 0 0 20px 0;
    border: 1px solid var(--glass-border);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
    font-size: 0.95rem;
}

.status-banner--success { border-color: rgba(94, 234, 212, 0.35); background: rgba(94, 234, 212, 0.08); }
.status-banner--info { border-color: rgba(124, 156, 255, 0.35); background: rgba(124, 156, 255, 0.08); }
.status-banner--warn { border-color: rgba(251, 191, 36, 0.35); background: rgba(251, 191, 36, 0.08); }

.metric-row {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin: 18px 0 28px 0;
}

.metric-pill {
    display: inline-flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 16px;
    border-radius: 14px;
    border: 1px solid var(--glass-border);
    background: rgba(255, 255, 255, 0.03);
    min-width: 120px;
    transition: var(--transition);
}

.metric-pill:hover {
    border-color: var(--glass-border-hover);
    transform: translateY(-2px);
}

.metric-pill-label {
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.metric-pill-value {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--text-primary);
}

.metric-pill-delta {
    font-size: 0.78rem;
    color: var(--warning);
}

.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: var(--radius-pill);
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    margin-right: 6px;
    margin-bottom: 6px;
}

.badge--slot { background: var(--accent-soft); color: #c7d6ff; border: 1px solid rgba(124, 156, 255, 0.25); }
.badge--live { background: rgba(251, 191, 36, 0.14); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.28); }
.badge--verified { background: rgba(94, 234, 212, 0.12); color: #99f6e4; border: 1px solid rgba(94, 234, 212, 0.25); }
.badge--warn { background: rgba(251, 191, 36, 0.12); color: #fcd34d; border: 1px solid rgba(251, 191, 36, 0.22); }

.itinerary-card {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 16px;
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(12px);
    transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1), box-shadow 0.3s ease, border-color 0.3s ease;
    will-change: transform;
}

.itinerary-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 20px rgba(0, 0, 0, 0.3);
    border-color: rgba(255, 255, 255, 0.2);
}

.itinerary-card--morning { border-left: 3px solid #93c5fd; }
.itinerary-card--lunch { border-left: 3px solid #fca5a5; }
.itinerary-card--afternoon { border-left: 3px solid #fcd34d; }
.itinerary-card--evening { border-left: 3px solid #c4b5fd; }
.itinerary-card--live { border-left: 3px solid #fbbf24; box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.12) inset; }

.card-title {
    font-size: 1.15rem;
    font-weight: 700;
    margin: 8px 0 8px 0;
    color: var(--text-primary);
}

.card-meta {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: 12px;
    line-height: 1.5;
}

.card-body {
    font-size: 0.95rem;
    line-height: 1.7;
    color: rgba(244, 246, 251, 0.88);
    margin: 0;
}

.day-section-title {
    font-size: 1.25rem;
    font-weight: 700;
    margin: 28px 0 14px 0;
    letter-spacing: -0.02em;
    color: var(--text-primary);
}

.share-snippet {
    border: 1px solid var(--glass-border);
    border-left: 3px solid var(--accent);
    border-radius: 12px;
    padding: 14px 16px;
    background: rgba(0, 0, 0, 0.28);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.82rem;
    color: #dbeafe;
    word-break: break-all;
    margin-top: 8px;
}

.section-label {
    font-size: 0.78rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 6px;
    font-weight: 600;
}

.loader-shell {
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-lg);
    padding: 28px 24px;
    background: var(--bg-elevated);
    backdrop-filter: blur(14px);
    margin: 24px 0;
}

.loader-orbit {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: 2px solid rgba(255, 255, 255, 0.08);
    border-top-color: var(--accent);
    animation: spin 0.9s linear infinite;
    margin-bottom: 18px;
}

.loader-message {
    font-size: 0.95rem;
    color: var(--text-primary);
    margin-bottom: 16px;
}

.skeleton-line {
    height: 12px;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.12) 50%, rgba(255,255,255,0.04) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.4s ease-in-out infinite;
    margin-bottom: 10px;
}

.skeleton-line--wide { width: 92%; }
.skeleton-line--mid { width: 68%; }
.skeleton-line--short { width: 42%; }

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.empty-state {
    padding: 18px;
    border-radius: 14px;
    border: 1px dashed var(--glass-border);
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.02);
}
"""


def _build_theme_style_block() -> str:
    """Return a single style-only HTML block for global theme injection."""
    return f"<style>{_GLOBAL_THEME_RULES}</style>"


def _render_html(html_content: str) -> None:
    """
    Render HTML through Streamlit's official HTML pipeline.

    Falls back to sanitized markdown when ``st.html`` is unavailable.
    """
    html_fn = getattr(st, "html", None)
    if callable(html_fn):
        html_fn(html_content)
        return
    st.markdown(html_content, unsafe_allow_html=True)


def inject_global_theme() -> None:
    """Inject premium dark theme CSS at application startup."""
    _render_html(_build_theme_style_block())


def inject_inline_style(css_rules: str) -> None:
    """Inject page-scoped CSS without rendering visible markup."""
    _render_html(f"<style>{css_rules}</style>")


# Public alias for layout fragments (cards, banners, labels).
render_html = _render_html


def render_hero_header(
    *,
    kicker: str = "Itinera Studio",
    title: str = "Itinera",
    subtitle: str,
    aside_html: str = "",
) -> None:
    """Asymmetrical hero header with bold typography."""
    aside_block = f'<div class="glass-panel">{aside_html}</div>' if aside_html else ""
    _render_html(
        f"""
        <div class="hero-wrap">
            <div>
                <div class="hero-kicker">{html.escape(kicker)}</div>
                <h1 class="hero-title">{html.escape(title)}</h1>
                <p class="hero-subtitle">{html.escape(subtitle)}</p>
            </div>
            {aside_block}
        </div>
        """
    )


def render_status_banner(message: str, *, variant: str = "info") -> None:
    """Render a styled status banner."""
    _render_html(
        f'<div class="status-banner status-banner--{html.escape(variant)}">{html.escape(message)}</div>'
    )


def render_metric_pills(items: list[tuple[str, str, str | None]]) -> None:
    """Render metric badge pills: (label, value, optional delta)."""
    pills = []
    for label, value, delta in items:
        delta_html = (
            f'<span class="metric-pill-delta">{html.escape(delta)}</span>'
            if delta
            else ""
        )
        pills.append(
            f"""
            <div class="metric-pill">
                <span class="metric-pill-label">{html.escape(label)}</span>
                <span class="metric-pill-value">{html.escape(value)}</span>
                {delta_html}
            </div>
            """
        )
    _render_html(f'<div class="metric-row">{"".join(pills)}</div>')


def render_loading_shell(message: str) -> None:
    """Animated loader with skeleton shimmer while the pipeline runs."""
    _render_html(
        f"""
        <div class="loader-shell">
            <div class="loader-orbit"></div>
            <div class="loader-message">{html.escape(message)}</div>
            <div class="skeleton-line skeleton-line--wide"></div>
            <div class="skeleton-line skeleton-line--mid"></div>
            <div class="skeleton-line skeleton-line--short"></div>
        </div>
        """
    )


def _slot_modifier(slot: str, is_live_event: bool) -> str:
    if is_live_event:
        return "live"
    return slot.lower().replace(" ", "")


def render_itinerary_card(
    *,
    time_slot: str,
    title: str,
    description: str,
    meta: str,
    badges: list[tuple[str, str]],
    is_live_event: bool = False,
    warning: str | None = None,
) -> None:
    """Glassmorphism itinerary card with hover micro-animation."""
    badge_html = "".join(
        f'<span class="badge badge--{html.escape(kind)}">{html.escape(text)}</span>'
        for kind, text in badges
    )
    warning_html = (
        f'<p class="card-meta" style="color:#fcd34d;">{html.escape(warning)}</p>'
        if warning
        else ""
    )
    modifier = _slot_modifier(time_slot, is_live_event)

    _render_html(
        f"""
        <div class="itinerary-card itinerary-card--{html.escape(modifier)}">
            <div>{badge_html}</div>
            <div class="card-title">{html.escape(title)}</div>
            <div class="card-meta">{html.escape(meta)}</div>
            {warning_html}
            <p class="card-body">{html.escape(description)}</p>
        </div>
        """
    )


def render_share_snippet(share_url: str) -> None:
    """Flat dark snippet for share URLs."""
    _render_html('<div class="section-label">Share this trip</div>')
    _render_html(f'<div class="share-snippet">{html.escape(share_url)}</div>')
    st.caption("Select the link above and copy · no account required for viewers.")
