import re
import io
import hashlib
import io as _io
from html import escape
import pandas as pd
import streamlit as st

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from parsers.pdf_parser import parse_bom_pdf
from validators.matcher import auto_detect_columns, get_product_type
from validators.filler import validate_and_fill, NEW_COLUMNS, QUICK_COLUMNS, QUICK_COLUMN_REMAP


st.set_page_config(
    page_title="Columbia BOM Automation",
    page_icon="\U0001f9e2",
    layout="wide",
    initial_sidebar_state="expanded"
)

BOMS_PER_PAGE   = 5
STYLES_PER_PAGE = 5

def inject_theme():
    st.markdown(
        """
        <style>
        :root {
            --page-bg: #edf1f6;
            --panel-bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f213f;
            --text-soft: #64748b;
            --border: #d6dee9;
            --blue: #2f62d8;
            --green: #18a166;
            --amber: #d18a00;
            --red: #df4f56;
        }
        .stApp {
            background: linear-gradient(180deg, #e8edf4 0%, var(--page-bg) 100%);
            color: var(--text-main);
        }
        [data-testid="stHeader"] {
            background: transparent;
            border-bottom: 1px solid #d7e0eb;
        }
        [data-testid="stToolbar"], #MainMenu, footer {
            display: none !important;
        }
        [data-testid="stSidebar"] {
            background: #f4f7fb;
            border-right: 1px solid #d7e0eb;
        }
        [data-testid="stSidebar"] * {
            color: var(--text-main);
        }
        .main .block-container {
            max-width: 1250px;
            padding-top: 1.45rem;
            padding-bottom: 1.8rem;
            padding-left: 1.25rem;
            padding-right: 1.25rem;
        }
        [data-testid="stFileUploaderDropzone"] {
            background: #f6f9fd;
            border: 1px dashed #cfd9e6;
            border-radius: 18px;
            min-height: 146px;
        }
        [data-testid="stFileUploaderDropzone"] section {
            padding: 1.2rem;
        }
        [data-testid="stTabs"] button {
            border-radius: 10px;
            border: 1px solid transparent;
            color: #4a5e80;
            font-weight: 600;
            padding: 0.45rem 0.9rem;
            margin-right: 0.25rem;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--blue);
            border-color: #b8c9e8;
            background: #eff4fd;
        }
        .stButton > button, .stDownloadButton > button {
            background: #f3f7fd !important;
            color: #173157 !important;
            border: 1px solid #cddbf0 !important;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            background: #eaf1fb !important;
            color: #10284a !important;
            border: 1px solid #b8cdee !important;
        }
        .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
            background: #f8fbff !important;
            color: #1b355d !important;
            border-color: #cad8ec !important;
        }
        .stTextInput label, .stSelectbox label, .stFileUploader label, .stMultiSelect label,
        .stCheckbox label, .stRadio label, .stTextArea label {
            color: #31527f !important;
        }
        [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {
            color: #1b355d;
        }
        [data-testid="stAppViewContainer"] * {
            color: #1b355d;
        }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
            color: #173157 !important;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #d3dfef;
            border-radius: 14px;
            padding: 0.75rem 0.85rem;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: 14px;
            background: var(--card-bg);
        }
        div[data-baseweb="modal"] > div:first-child {
            background: rgba(12, 18, 30, 0.5) !important;
            backdrop-filter: blur(8px) !important;
        }
        div[data-baseweb="modal"] [role="dialog"] {
            background: #f9fbff !important;
            color: #172f52 !important;
            border: 1px solid #ced9ea !important;
            border-radius: 18px !important;
            box-shadow: 0 20px 42px rgba(18, 33, 58, 0.2) !important;
        }
        div[data-baseweb="modal"] [role="dialog"] * {
            color: #1c355a !important;
        }
        div[data-baseweb="modal"] .stTextInput input {
            background: #ffffff !important;
            color: #173157 !important;
            border: 1px solid #cddbf0 !important;
        }
        div[data-baseweb="modal"] .stButton > button {
            background: #eef4ff !important;
            color: #14315a !important;
            border: 1px solid #c8d8f0 !important;
        }
        .cx-popup-table-wrap {
            border: 1px solid #cfdced;
            border-radius: 12px;
            overflow: auto;
            max-height: 390px;
            background: #ffffff;
        }
        .cx-popup-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: auto;
        }
        .cx-popup-table thead th {
            position: sticky;
            top: 0;
            z-index: 2;
            background: #f2f6fb;
            color: #4a6286;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            border-bottom: 1px solid #dbe5f2;
            padding: 0.55rem 0.6rem;
            text-align: left;
            white-space: normal;
            word-break: break-word;
        }
        .cx-popup-table tbody td {
            border-bottom: 1px solid #e6edf7;
            padding: 0.5rem 0.6rem;
            color: #1b365f;
            font-size: 0.83rem;
            white-space: normal;
            word-break: break-word;
            vertical-align: top;
        }
        .cx-popup-table tbody tr:nth-child(even) {
            background: #fbfdff;
        }
        .cx-title {
            font-size: 1.85rem;
            line-height: 1.1;
            font-weight: 800;
            letter-spacing: -0.01em;
            color: var(--text-main);
            margin: 0;
        }
        .cx-subtitle {
            font-size: 0.95rem;
            color: #587199;
            margin-top: 0.22rem;
            margin-bottom: 0.95rem;
        }
        .cx-divider {
            height: 1px;
            margin: 1rem 0 1.2rem 0;
            background: #d8e1ed;
        }
        .cx-banner {
            border-radius: 14px;
            border: 1px solid #cad6e7;
            background: #f7faff;
            padding: 0.9rem 1rem;
            color: #4b6487;
            font-size: 0.84rem;
            margin-bottom: 0.9rem;
        }
        .cx-banner.warn {
            border-color: #efd79f;
            background: #fff8e7;
            color: #8a6400;
        }
        .cx-meta {
            font-size: 0.72rem;
            color: var(--text-soft);
            margin-bottom: 0.42rem;
            letter-spacing: 0.07em;
            text-transform: uppercase;
        }
        .cx-stats {
            display: grid;
            grid-template-columns: repeat(4, minmax(0,1fr));
            gap: 0.85rem;
            margin-bottom: 1rem;
        }
        .cx-stat-card {
            border: 1px solid var(--border);
            border-radius: 16px;
            background: var(--card-bg);
            padding: 0.95rem;
            text-align: center;
        }
        .cx-stat-number {
            font-size: 2rem;
            line-height: 1;
            font-weight: 800;
        }
        .cx-stat-label {
            margin-top: 0.35rem;
            font-size: 0.76rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: #7a8da9;
            font-weight: 600;
        }
        .cx-upload-hint {
            border: 1px dashed #cad7e8;
            border-radius: 18px;
            background: #f7fafd;
            text-align: center;
            padding: 1.5rem 1rem;
            margin: 0.25rem 0 1.1rem 0;
        }
        .cx-upload-icon {
            width: 48px;
            height: 48px;
            border-radius: 14px;
            background: #e8eef8;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 0.45rem;
            color: #43689b;
            font-weight: 700;
        }
        .cx-upload-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--text-main);
        }
        .cx-upload-subtitle {
            margin-top: 0.25rem;
            color: #6f86a7;
            font-size: 0.85rem;
        }
        .cx-style-card {
            border: 1px solid var(--border);
            border-left: 4px solid #4f89f7;
            border-radius: 16px;
            padding: 1rem 1.05rem;
            background: var(--card-bg);
            margin-bottom: 0.85rem;
        }
        .cx-style-top {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: center;
        }
        .cx-style-id {
            color: var(--blue);
            font-weight: 700;
            font-size: 0.82rem;
            letter-spacing: 0.03em;
        }
        .cx-style-name {
            color: var(--text-main);
            font-size: 1.08rem;
            font-weight: 800;
            margin-top: 0.14rem;
            line-height: 1.25;
        }
        .cx-status {
            border-radius: 999px;
            border: 1px solid;
            padding: 0.18rem 0.56rem;
            font-size: 0.78rem;
            font-weight: 700;
            white-space: nowrap;
        }
        .cx-chip-row {
            margin-top: 0.5rem;
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
        }
        .cx-chip {
            border: 1px solid #d7e1ef;
            background: #f0f5fb;
            color: #2f4668;
            border-radius: 8px;
            padding: 0.22rem 0.55rem;
            font-size: 0.74rem;
            font-weight: 600;
        }
        .cx-row-card {
            border: 1px solid var(--border);
            border-radius: 14px;
            background: var(--card-bg);
            padding: 0.72rem 0.8rem;
            margin-bottom: 0.56rem;
        }
        .cx-style-footer {
            margin-top: 0.7rem;
            padding-top: 0.55rem;
            border-top: 1px solid #dbe4f1;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.6rem;
        }
        .cx-footer-meta {
            color: #587092;
            font-size: 0.95rem;
            font-weight: 600;
            display: inline-flex;
            gap: 0.9rem;
            align-items: center;
        }
        .cx-footer-link {
            color: #6d84a7;
            font-style: italic;
            font-size: 0.9rem;
            white-space: nowrap;
        }
        .cx-list-row {
            border: 1px solid var(--border);
            border-left: 4px solid #4f89f7;
            border-radius: 14px;
            background: var(--card-bg);
            padding: 0.95rem 1rem;
            margin-bottom: 0.65rem;
        }
        .cx-style-card:hover,
        .cx-list-row:hover {
            border-color: #b7cdef;
            box-shadow: 0 4px 14px rgba(58, 96, 158, 0.12);
        }
        .cx-view-toggle {
            margin: 0.35rem 0 0.75rem 0;
        }
        @media (max-width: 980px) {
            .cx-stats {
                grid-template-columns: repeat(2, minmax(0,1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title, subtitle=""):
    sub = f"<div class='cx-subtitle'>{subtitle}</div>" if subtitle else ""
    st.markdown(f"<h2 class='cx-title'>{title}</h2>{sub}", unsafe_allow_html=True)

def render_divider():
    st.markdown("<div class='cx-divider'></div>", unsafe_allow_html=True)

def render_info_banner(message):
    st.markdown(f"<div class='cx-banner'>{message}</div>", unsafe_allow_html=True)

def render_warn_banner(message):
    st.markdown(f"<div class='cx-banner warn'>{message}</div>", unsafe_allow_html=True)

def render_table_meta(df):
    st.markdown(f"<div class='cx-meta'>{len(df)} rows &middot; {len(df.columns)} columns</div>", unsafe_allow_html=True)

def render_validation_summary(ok, partial, err, total):
    st.markdown(
        f"""
        <div class="cx-stats">
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--green);">{ok}</div><div class="cx-stat-label">Validated</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--amber);">{partial}</div><div class="cx-stat-label">Partial</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--red);">{err}</div><div class="cx-stat-label">Errors</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:#334e75;">{total}</div><div class="cx-stat-label">Total Rows</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_upload_hint(title, subtitle, icon="PDF"):
    st.markdown(
        f"""
        <div class="cx-upload-hint">
          <div class="cx-upload-icon">{icon}</div>
          <div class="cx-upload-title">{title}</div>
          <div class="cx-upload-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _status_style(status):
    status_text = str(status or "").lower()
    if "validated" in status_text:
        return "#eaf9f0", "#8fd9b3", "#188d5a", "Validated"
    if "partial" in status_text:
        return "#fff7e6", "#edc96e", "#a06a00", "Partial"
    if "error" in status_text:
        return "#ffeef0", "#f3a2aa", "#b33844", "Error"
    if "parsed" in status_text:
        return "#ecf3ff", "#bcd0f3", "#3c5ea2", "Parsed"
    return "#ecf3ff", "#bcd0f3", "#3c5ea2", "Parsed"

def _style_validation_status(style):
    res = st.session_state.get("validation_result")
    if res is None or res.empty or "Buyer Style Number" not in res.columns or "Validation Status" not in res.columns:
        return "Parsed"
    style_upper = str(style).strip().upper()
    statuses = []
    for _, row in res.iterrows():
        row_style = str(row.get("Buyer Style Number", "")).strip().upper()
        if row_style == style_upper or row_style in style_upper or style_upper in row_style:
            statuses.append(str(row.get("Validation Status", "")))
    if not statuses:
        return "Parsed"
    lowered = [s.lower() for s in statuses]
    if any("error" in s or s.startswith("\u274c") for s in lowered):
        return "Error"
    if any("partial" in s for s in lowered):
        return "Partial"
    if any("validated" in s for s in lowered):
        return "Validated"
    return "Parsed"

def _status_accent_color(status_label):
    sl = str(status_label).lower()
    if sl == "validated":
        return "#3fd2a0"
    if sl == "partial":
        return "#f0b429"
    if sl == "error":
        return "#eb5b63"
    return "#4f89f7"

def render_view_toggle(state_key, default="Grid", label="View"):
    options = ["Grid", "Tile", "List"]
    current = st.session_state.get(state_key, default)
    if current not in options:
        current = default
        st.session_state[state_key] = default
    st.markdown(f"<div class='cx-meta'>{label}</div>", unsafe_allow_html=True)
    st.markdown("<div class='cx-view-toggle'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    cols = [c1, c2, c3]
    for i, opt in enumerate(options):
        with cols[i]:
            if st.button(opt, key=f"{state_key}_{opt}", type="primary" if current == opt else "secondary", use_container_width=True):
                st.session_state[state_key] = opt
                st.rerun()
    return st.session_state.get(state_key, default)

def _style_color_hint(bom_data):
    meta = bom_data.get("metadata", {}) if isinstance(bom_data, dict) else {}
    for k in ("color", "colorway", "colour", "color_name"):
        val = str(meta.get(k, "")).strip()
        if val:
            return val
    cb = bom_data.get("color_bom") if isinstance(bom_data, dict) else None
    if isinstance(cb, pd.DataFrame) and not cb.empty:
        for c in cb.columns:
            cc = str(c).strip()
            if cc and not cc.lower().startswith(("unnamed", "material", "component", "description", "code", "supplier", "row", "col_")):
                return cc
    return "N/A"

def _infer_material_from_row(row, columns):
    priority = [
        "Material Name", "Material", "Material Type", "Shell Material",
        "Fabric", "Body Fabric", "Main Material",
    ]
    for c in priority:
        if c in columns:
            v = str(row.get(c, "")).strip()
            if v and v.lower() not in ("nan", "none"):
                return v
    for c in columns:
        if "material" in str(c).lower():
            v = str(row.get(c, "")).strip()
            if v and v.lower() not in ("nan", "none"):
                return v
    return "N/A"

def _colors_for_style(df, style_col, color_col, style_key):
    if df is None or style_col not in df.columns or color_col not in df.columns:
        return []
    su = str(style_key).strip().upper()
    out = []
    for _, r in df[[style_col, color_col]].dropna(how="all").iterrows():
        s = str(r.get(style_col, "")).strip()
        c = str(r.get(color_col, "")).strip()
        if not s or not c:
            continue
        su2 = s.upper()
        if su2 == su or su2 in su or su in su2:
            if c not in out:
                out.append(c)
    return out

def _render_record_cards(df, max_rows=12):
    if df is None or df.empty:
        render_warn_banner("No rows to display for this section.")
        return
    preview = df.head(max_rows)
    for i, (_, row) in enumerate(preview.iterrows(), start=1):
        items = []
        for col in df.columns:
            val = str(row.get(col, "")).strip()
            if val and val.lower() not in ("nan", "none"):
                items.append((str(col), val))
            if len(items) >= 6:
                break
        fields = "".join([f"<span class='cx-chip'>{k}: {v}</span>" for k, v in items]) if items else "<span class='cx-chip'>No values</span>"
        st.markdown(
            f"""
            <div class="cx-row-card">
              <div class="cx-style-id">Row {i}</div>
              <div class="cx-chip-row">{fields}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if len(df) > max_rows:
        render_info_banner(f"Showing {max_rows} of {len(df)} rows for readability. Use export for full data.")

def _render_popup_table(df):
    if df is None or df.empty:
        render_warn_banner("No rows in this section.")
        return
    headers = "".join(f"<th>{escape(str(c))}</th>" for c in df.columns)
    body_rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{escape(str(v))}</td>" for v in row.tolist())
        body_rows.append(f"<tr>{cells}</tr>")
    st.markdown(
        f"""
        <div class="cx-popup-table-wrap">
          <table class="cx-popup-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{''.join(body_rows)}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_pagination(page_key, current_page, total_pages, key_suffix=""):
    if total_pages <= 1:
        return current_page
    suffix = key_suffix or page_key
    col_prev, col_pills, col_next = st.columns([1, 6, 1])
    with col_prev:
        if st.button("\u2190 Prev", key=f"{suffix}_prev", disabled=current_page == 0):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with col_pills:
        window = 3
        start = max(0, current_page - window)
        end   = min(total_pages, current_page + window + 1)
        pills = "<div style='display:flex;gap:6px;justify-content:center;align-items:center;'>"
        for p in range(start, end):
            active = "page-pill-active" if p == current_page else ""
            pills += f"<div class='page-pill {active}'>{p + 1}</div>"
        pills += "</div>"
        st.markdown(pills, unsafe_allow_html=True)
    with col_next:
        if st.button("Next \u2192", key=f"{suffix}_next", disabled=current_page >= total_pages - 1):
            st.session_state[page_key] = current_page + 1
            st.rerun()
    st.markdown(f"<div style='text-align:center;font-size:0.7rem;color:#5a6080;margin-top:4px;'>Page {current_page + 1} of {total_pages}</div>", unsafe_allow_html=True)
    return st.session_state.get(page_key, current_page)


def render_sidebar():
    with st.sidebar:
        st.markdown("""<div style="font-size:0.95rem;font-weight:800;color:#2457d6;line-height:1.1;margin-bottom:0.2rem;letter-spacing:0.08em;">COLUMBIA</div>
        <div style="font-size:1.7rem;font-weight:800;color:#0f213f;line-height:1.02;margin-bottom:0.16rem;letter-spacing:-0.02em;">BOM Automation</div>
        <div style="font-size:0.8rem;color:#667d9f;margin-bottom:1.1rem;">Trim & Label Validator</div>""", unsafe_allow_html=True)
        bom_dict = st.session_state.get("bom_dict", {})
        if bom_dict:
            st.markdown(f"""<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:700;margin-bottom:0.7rem;background:#eaf8f0;color:#138e59;border:1px solid #98dab8;">&#8226; {len(bom_dict)} BOM{'s' if len(bom_dict)>1 else ''} Loaded</div>""", unsafe_allow_html=True)
            for style, bom in bom_dict.items():
                meta = bom.get("metadata", {})
                st.markdown(f"""<div style="font-size:0.75rem;color:#6d82a1;padding:4px 0;border-bottom:1px solid #d8e1ec;"><span style="color:#3b82f6;font-weight:700;">{style}</span> &nbsp;\xb7&nbsp; {meta.get('season','\u2014')} &nbsp;\xb7&nbsp; {meta.get('production_lo','\u2014')}</div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:700;margin-bottom:0.9rem;background:#edf2f8;color:#6681a4;border:1px solid #d0dceb;">&#8226; No BOM Loaded</div>""", unsafe_allow_html=True)
        with st.expander("How to use", expanded=False):
            st.markdown("""
            **Step 1** \u2014 Upload one or more Columbia BOM PDFs in the **PDF Extraction** tab.
            **Step 2** \u2014 Inspect each parsed section to verify extraction.
            **Step 3** \u2014 Go to **BOM Comparison**, upload your Excel/CSV.
            **Step 4** \u2014 Map columns, configure label dropdowns, run validation, export.
            """)
        render_divider()
        if st.button("\U0001f5d1 Clear All Data", width='stretch'):
            pdf_k = st.session_state.get("pdf_uploader_key", 0) + 1
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.session_state["pdf_uploader_key"] = pdf_k
            st.rerun()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_style_key(style, bom_dict):
    su = style.strip().upper()
    for k in bom_dict:
        if su == k.strip().upper():
            return k
    return None


# ── Conflict dialog ───────────────────────────────────────────────────────────

@st.dialog("Duplicate Style Detected", width="large")
def show_conflict_dialog(conflict_key, info, bom_dict, pdf_bytes_store, pdf_hashes):
    style         = info.get("style", conflict_key.split("__")[0])
    reason        = info.get("conflict_reason", "already_loaded")
    existing_meta = bom_dict.get(info["existing_key"], {}).get("metadata", {})
    new_meta      = info["bom_data"].get("metadata", {}) if isinstance(info.get("bom_data"), dict) else {}

    if reason == "duplicate_file":
        reason_label = "\u26a0 Exact duplicate file uploaded again"
    elif reason == "duplicate_in_batch":
        reason_label = "\u26a0 Same style uploaded twice in this batch"
    else:
        reason_label = "\u26a0 Style already loaded from a previous upload"

    st.markdown(f"**{reason_label}:** `{style}`")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Existing in session**")
        st.markdown(f"Season: `{existing_meta.get('season', '\u2014')}` \u00b7 LO: `{existing_meta.get('production_lo', '\u2014')}`")
    with col2:
        st.markdown(f"**New Upload** \u2014 {info['fname']}")
        st.markdown(f"Season: `{new_meta.get('season', '\u2014')}` \u00b7 LO: `{new_meta.get('production_lo', '\u2014')}`")
    st.divider()
    col_rep, col_keep = st.columns(2)
    with col_rep:
        if st.button("\u21ba Replace", type="primary", use_container_width=True):
            existing_key = info["existing_key"]
            bom_dict[existing_key]        = info["bom_data"]
            pdf_bytes_store[existing_key] = info["raw_bytes"]
            pdf_hashes[info["fname"]]     = info["fhash"]
            st.session_state["bom_dict"]        = bom_dict
            st.session_state["pdf_bytes_store"] = pdf_bytes_store
            st.session_state["pdf_hashes"]      = pdf_hashes
            del st.session_state["pending_conflicts"][conflict_key]
            st.rerun()
    with col_keep:
        if st.button("\u2713 Keep Existing", use_container_width=True):
            pdf_hashes[info["fname"]] = info["fhash"]
            st.session_state["pdf_hashes"] = pdf_hashes
            del st.session_state["pending_conflicts"][conflict_key]
            st.rerun()


@st.dialog("BOM Inspector", width="medium")
def show_bom_inspector(style_key, bom_data):
    meta = bom_data.get("metadata", {})
    bg, border, fg, status_label = _status_style(_style_validation_status(style_key))
    st.markdown(
        f"""
        <div class="cx-style-card" style="border-top:3px solid #3fd2a0;">
          <div class="cx-style-top">
            <div>
              <div class="cx-style-id">{style_key}</div>
              <div class="cx-style-name">{meta.get('design', style_key)}</div>
            </div>
            <div class="cx-status" style="background:{bg};border-color:{border};color:{fg};">{status_label}</div>
          </div>
          <div class="cx-chip-row">
            <span class="cx-chip">Season: {meta.get('season', 'N/A')}</span>
            <span class="cx-chip">LO: {meta.get('production_lo', 'N/A')}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    section_keys = [k for k, v in bom_data.items() if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty]
    if not section_keys:
        render_warn_banner("No parsed sections for this BOM.")
        return

    sec_state_key = f"popup_section_{style_key}"
    if sec_state_key not in st.session_state or st.session_state[sec_state_key] not in section_keys:
        st.session_state[sec_state_key] = section_keys[0]

    tabs_per_row = 4
    for r_start in range(0, len(section_keys), tabs_per_row):
        row_secs = section_keys[r_start:r_start + tabs_per_row]
        row_cols = st.columns(len(row_secs))
        for i, sec in enumerate(row_secs):
            sec_df = bom_data.get(sec, pd.DataFrame())
            label = f"{sec.replace('_', ' ').title()} ({len(sec_df)})"
            btn_type = "primary" if st.session_state[sec_state_key] == sec else "secondary"
            with row_cols[i]:
                if st.button(label, key=f"popup_tab_{style_key}_{sec}", type=btn_type, use_container_width=True):
                    st.session_state[sec_state_key] = sec
                    st.rerun()
    active_sec = st.session_state.get(sec_state_key, section_keys[0])
    filter_key = f"popup_filter_{style_key}"
    search = st.text_input("Filter rows", key=filter_key, placeholder="Filter rows...")
    view_df = bom_data[active_sec].copy()
    if search:
        view_df = view_df[view_df.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)]

    st.markdown(f"<div class='cx-meta'>{active_sec.replace('_', ' ').title()} &middot; {len(view_df)} rows &middot; {len(view_df.columns)} cols</div>", unsafe_allow_html=True)
    st.markdown("<div class='cx-meta' style='margin-top:-0.25rem;'>Scroll horizontally to view all columns.</div>", unsafe_allow_html=True)
    _render_popup_table(view_df)

    c_sp, c_close = st.columns([8, 1])
    with c_close:
        close = st.button("Close", width='stretch')
    if close:
        st.session_state["inspect_popup_style"] = None
        st.rerun()


def render_pdf_tab():
    render_section_header("PDF Extraction", "Upload & inspect BOM sections")
    uploader_key = f"pdf_uploader_{st.session_state.get('pdf_uploader_key', 0)}"
    render_upload_hint(
        "Drop Columbia BOM PDFs here",
        "Each PDF's style is auto-detected and matched to your Excel rows",
        "PDF",
    )
    uploaded_pdfs = st.file_uploader(
        "Drop one or more Columbia BOM PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        key=uploader_key,
        help="Each PDF is matched to Excel rows by its style number",
    )
    if not uploaded_pdfs:
        render_info_banner("Upload one or more Columbia BOM PDFs to start extraction.")
        st.session_state.pop("pending_conflicts", None)
        return

    from concurrent.futures import ThreadPoolExecutor, as_completed

    bom_dict        = st.session_state.get("bom_dict", {})
    pdf_bytes_store = st.session_state.get("pdf_bytes_store", {})
    pdf_hashes      = st.session_state.get("pdf_hashes", {})

    pdf_data_list  = [(f.name, f.read()) for f in uploaded_pdfs]
    current_fnames = {fname for fname, _ in pdf_data_list}

    # Evict stale cached BOMs (files removed from uploader)
    stale_fnames = [fn for fn in list(pdf_hashes.keys()) if fn not in current_fnames]
    stale_hashes = {pdf_hashes.pop(fn) for fn in stale_fnames}
    for style in list(bom_dict.keys()):
        raw = pdf_bytes_store.get(style)
        if raw and hashlib.md5(raw).hexdigest() in stale_hashes:
            bom_dict.pop(style, None)
            pdf_bytes_store.pop(style, None)

    to_parse = []
    for fname, raw_bytes in pdf_data_list:
        fhash = hashlib.md5(raw_bytes).hexdigest()
        if pdf_hashes.get(fname) != fhash:
            to_parse.append((fname, raw_bytes, fhash))

    pending_conflicts = st.session_state.get("pending_conflicts", None)

    if to_parse and not pending_conflicts:
        to_parse_indexed = []
        seen_fhashes = set()
        for idx, (fname, raw_bytes) in enumerate(pdf_data_list):
            fhash = hashlib.md5(raw_bytes).hexdigest()
            if fhash in seen_fhashes:
                to_parse_indexed.append((fname, raw_bytes, fhash, idx, True))
            else:
                if pdf_hashes.get(fname) != fhash:
                    to_parse_indexed.append((fname, raw_bytes, fhash, idx, False))
                seen_fhashes.add(fhash)

        unique_to_parse = [(fname, raw_bytes, fhash, idx) for fname, raw_bytes, fhash, idx, is_dup in to_parse_indexed if not is_dup]
        dup_entries     = [(fname, raw_bytes, fhash, idx) for fname, raw_bytes, fhash, idx, is_dup in to_parse_indexed if is_dup]

        pre_parsed = {}

        if unique_to_parse:
            total_new = len(unique_to_parse)
            progress_bar = st.progress(0, text=f"Parsing {total_new} PDF(s)...")
            status_text  = st.empty()
            done_count   = 0
            with ThreadPoolExecutor(max_workers=min(8, total_new)) as executor:
                def _pre_parse(args):
                    fname, raw_bytes, fhash, idx = args
                    bom_data = parse_bom_pdf(_io.BytesIO(raw_bytes))
                    style = bom_data.get("metadata", {}).get("style") or fname
                    return (fname, idx), style, bom_data, raw_bytes, fhash
                futures = {executor.submit(_pre_parse, args): args[0] for args in unique_to_parse}
                parsed_styles = []
                for future in as_completed(futures):
                    key, style, bom_data, raw_bytes, fhash = future.result()
                    pre_parsed[key] = (style, bom_data, raw_bytes, fhash)
                    parsed_styles.append(style)
                    done_count += 1
                    progress_bar.progress(done_count / total_new, text=f"Parsed {done_count} / {total_new}")
                    status_text.markdown(f"<div style='font-size:0.78rem;color:#9ca3af;'>✓ {', '.join(parsed_styles[-3:])}{'...' if len(parsed_styles) > 3 else ''}</div>", unsafe_allow_html=True)
            progress_bar.progress(1.0, text=f"✅ Done — {len(parsed_styles)} BOM(s) parsed")
            status_text.empty()

        style_seen_this_batch = {}
        conflicts     = {}
        non_conflicts = {}

        for key, (style, bom_data, raw_bytes, fhash) in pre_parsed.items():
            existing_key = _resolve_style_key(style, bom_dict)
            if existing_key is not None:
                conflicts[f"{style}__{key[1]}"] = {
                    "style": style, "fname": key[0], "bom_data": bom_data,
                    "raw_bytes": raw_bytes, "fhash": fhash,
                    "existing_key": existing_key, "conflict_reason": "already_loaded",
                }
            elif style in style_seen_this_batch:
                conflicts[f"{style}__{key[1]}"] = {
                    "style": style, "fname": key[0], "bom_data": bom_data,
                    "raw_bytes": raw_bytes, "fhash": fhash,
                    "existing_key": style, "conflict_reason": "duplicate_in_batch",
                }
            else:
                style_seen_this_batch[style] = key
                non_conflicts[style] = {
                    "fname": key[0], "bom_data": bom_data,
                    "raw_bytes": raw_bytes, "fhash": fhash,
                }

        for fname, raw_bytes, fhash, idx in dup_entries:
            matching_style = next(
                (s for s, info in {**non_conflicts, **{c["style"]: c for c in conflicts.values()}}.items()
                 if hashlib.md5(info["raw_bytes"]).hexdigest() == fhash),
                None,
            )
            if matching_style is None:
                continue
            existing_key = _resolve_style_key(matching_style, bom_dict) or matching_style
            conflicts[f"{matching_style}__{idx}"] = {
                "style": matching_style, "fname": fname,
                "bom_data": bom_dict.get(existing_key, non_conflicts.get(matching_style, {}).get("bom_data", {})),
                "raw_bytes": raw_bytes, "fhash": fhash,
                "existing_key": existing_key, "conflict_reason": "duplicate_file",
            }

        for style, info in non_conflicts.items():
            bom_dict[style]           = info["bom_data"]
            pdf_bytes_store[style]    = info["raw_bytes"]
            pdf_hashes[info["fname"]] = info["fhash"]

        st.session_state["bom_dict"]        = bom_dict
        st.session_state["pdf_bytes_store"] = pdf_bytes_store
        st.session_state["pdf_hashes"]      = pdf_hashes

        if conflicts:
            st.session_state["pending_conflicts"] = conflicts
            st.rerun()
        else:
            st.session_state["pending_conflicts"] = {}

    pending_conflicts = st.session_state.get("pending_conflicts", {})
    if pending_conflicts:
        conflict_key = next(iter(pending_conflicts))
        info = pending_conflicts[conflict_key]
        show_conflict_dialog(conflict_key, info, bom_dict, pdf_bytes_store, pdf_hashes)
        return

    if not bom_dict:
        render_info_banner("Upload one or more Columbia BOM PDFs. Each PDF's style is auto-detected and used to match rows in your Excel.")
        return

    st.markdown(f"""<div class="cx-banner" style="border-color:#9ad8b7;background:#ecf9f2;color:#167f52;">All {len(uploaded_pdfs)} PDF(s) loaded. {len(bom_dict)} BOM(s) in session.</div>""", unsafe_allow_html=True)

    render_divider()
    render_info_banner("Click a style card below to inspect sections and export data.")

    render_divider()
    st.markdown("""<div class="cx-meta">Loaded BOMs</div>""", unsafe_allow_html=True)
    all_styles   = list(bom_dict.keys())
    summary_rows = []
    for style in all_styles:
        bom  = bom_dict[style]
        meta = bom.get("metadata", {})
        sects = [k for k, v in bom.items() if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty]
        status = _style_validation_status(style)
        summary_rows.append({
            "Style": style, "Season": meta.get("season", "\u2014"),
            "Design": meta.get("design", "\u2014"), "LO": meta.get("production_lo", "\u2014"),
            "Color": _style_color_hint(bom),
            "Sections": len(sects),
            "Colorways": len(bom.get("color_bom", pd.DataFrame()).columns) if not bom.get("color_bom", pd.DataFrame()).empty else 0,
            "Status": status,
        })
    if "pdf_inspect_style" not in st.session_state and all_styles:
        st.session_state["pdf_inspect_style"] = all_styles[0]

    count_validated = sum(1 for r in summary_rows if r["Status"] == "Validated")
    count_partial = sum(1 for r in summary_rows if r["Status"] == "Partial")
    count_error = sum(1 for r in summary_rows if r["Status"] == "Error")
    st.markdown(
        f"""
        <div class="cx-stats">
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:#3569de;">{len(summary_rows)}</div><div class="cx-stat-label">BOMS</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--green);">{count_validated}</div><div class="cx-stat-label">VALIDATED</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--amber);">{count_partial}</div><div class="cx-stat-label">PARTIAL</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--red);">{count_error}</div><div class="cx-stat-label">ERRORS</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    view_mode = render_view_toggle("loaded_boms_view", default="Grid", label="Loaded BOM View")

    col_count = 1 if view_mode == "List" else (3 if view_mode == "Tile" else 2)
    deck_cols = st.columns(col_count)
    for idx, row in enumerate(summary_rows):
        style = row["Style"]
        status = row.get("Status", _style_validation_status(style))
        bg, border, fg, label = _status_style(status)
        accent = _status_accent_color(label)
        with deck_cols[idx % col_count]:
            card_class = "cx-list-row" if view_mode == "List" else "cx-style-card"
            st.markdown(
                f"""
                <div class="{card_class}" style="border-left-color:{accent};">
                  <div class="cx-style-top">
                    <div>
                      <div class="cx-style-id">{style}</div>
                      <div class="cx-style-name">{row.get('Design', 'BOM Style')}</div>
                    </div>
                    <div class="cx-status" style="background:{bg};border-color:{border};color:{fg};">{label}</div>
                  </div>
                  <div class="cx-chip-row">
                    <span class="cx-chip">Color {row.get('Color', 'N/A')}</span>
                    <span class="cx-chip">Season {row['Season']}</span>
                    <span class="cx-chip">LO {row['LO']}</span>
                  </div>
                  <div class="cx-style-footer">
                    <div class="cx-footer-meta">
                      <span>&#8862; {row['Sections']} Sections</span>
                      <span>&#9671; {row['Colorways']} Colorways</span>
                    </div>
                    <div class="cx-footer-link">Click to inspect &rarr;</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Click to inspect \u2192", key=f"inspect_card_{style}", use_container_width=True):
                st.session_state["pdf_inspect_style"] = style
                st.session_state["inspect_popup_style"] = style
                st.rerun()

    popup_style = st.session_state.get("inspect_popup_style")
    if popup_style and popup_style in bom_dict:
        show_bom_inspector(popup_style, bom_dict[popup_style])


def _get_components_for_bom(bom_data):
    from parsers.color_bom import extract_color_bom_lookup
    components = []
    seen_names = set()

    cb = bom_data.get("color_bom")
    if cb is not None and not cb.empty:
        lookup = extract_color_bom_lookup(cb)
        comps  = lookup.get("components", {})
        for name, info in comps.items():
            code = str(info.get("material_code", "")).strip()
            if not code:
                import re as _re
                m = _re.search(r'(?<!\d)(\d{3,6})(?!\d)', str(info.get("description", "")))
                code = m.group(1) if m else ""
            label = f"{name} - {code}" if code else name
            norm  = name.strip().lower()
            if norm not in seen_names:
                seen_names.add(norm)
                components.append(label)

    cs = bom_data.get("color_specification")
    if cs is not None and not cs.empty:
        comp_col = cs.columns[0]
        for r in cs[comp_col]:
            val  = str(r).strip()
            norm = val.lower()
            if val and norm not in ("none", "nan", "") and norm not in seen_names:
                seen_names.add(norm)
                components.append(val)

    return components


def _get_label_preview(bom_data, comp_name):
    cs = bom_data.get("color_specification")
    if cs is None or cs.empty or not comp_name:
        return ""
    comp_col = cs.columns[0]
    cw_cols  = [c for c in cs.columns[1:] if c and not str(c).startswith("col_")]
    lookup_name = comp_name.split(" - ")[0].strip() if " - " in comp_name else comp_name
    row_match = cs[cs[comp_col] == lookup_name]
    if row_match.empty:
        return ""
    sample = {}
    for cw in cw_cols[:4]:
        val = str(row_match.iloc[0].get(cw, "")).strip()
        if val and val.lower() not in ("none", "nan", ""):
            sample[cw] = val
    return ", ".join(f"{k}: {v}" for k, v in list(sample.items())[:3])


def _read_comparison_file(file):
    is_excel = file.name.lower().endswith((".xlsx", ".xls"))
    try:
        df   = pd.read_excel(file, header=0) if is_excel else pd.read_csv(file, header=0)
        cols = [str(c).strip() for c in df.columns]
        meaningful = sum(1 for c in cols if c and not c.startswith("Unnamed") and c.lower() not in ("nan", "none"))
        if meaningful >= max(1, len(cols) * 0.4):
            df.columns = cols
            return df[~df.isnull().all(axis=1)].reset_index(drop=True)
    except Exception:
        pass
    if hasattr(file, "seek"):
        file.seek(0)
    raw = pd.read_excel(file, header=None) if is_excel else pd.read_csv(file, header=None)
    header_row_idx = 0
    for i, row in raw.head(10).iterrows():
        non_empty = sum(1 for v in row if str(v).strip() not in ("", "nan", "None"))
        if non_empty >= max(1, len(raw.columns) * 0.5):
            header_row_idx = i
            break
    raw.columns = raw.iloc[header_row_idx].astype(str).str.strip()
    df = raw[header_row_idx + 1:].reset_index(drop=True)
    return df[~df.isnull().all(axis=1)].reset_index(drop=True)


def render_comparison_tab():
    render_section_header("BOM Comparison & Validation", "Auto-fill trim & label data from BOM")
    bom_dict = st.session_state.get("bom_dict", {})
    if not bom_dict:
        render_warn_banner("No BOMs loaded. Upload Columbia BOM PDFs in the PDF Extraction tab first.")
        return

    render_upload_hint(
        "Drop your Comparison Excel or CSV here",
        "Can contain 100+ rows and multiple styles",
        "XLS",
    )
    render_info_banner(f"{len(bom_dict)} BOM(s) loaded and ready for style matching.")

    comp_file = st.file_uploader("Drop your Comparison Excel or CSV here", type=["xlsx", "csv", "xls"], key="cmp_uploader", help="Can contain 100+ rows and multiple styles")
    if comp_file is None:
        return
    cmp_sig = f"{comp_file.name}:{getattr(comp_file, 'size', 0)}"
    prev_sig = st.session_state.get("comparison_file_sig")
    if prev_sig != cmp_sig:
        st.session_state["comparison_file_sig"] = cmp_sig
        if st.session_state.get("inspect_popup_style"):
            st.session_state["inspect_popup_style"] = None
            st.rerun()

    try:
        comp_df = _read_comparison_file(comp_file)
        st.session_state["comparison_raw"] = comp_df
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        return

    render_divider()
    st.markdown("""<div class="cx-meta">Column Mapping</div>""", unsafe_allow_html=True)
    auto = auto_detect_columns(comp_df)
    if auto and auto["confidence"] >= 0.7:
        default_style    = auto["style_col"]
        default_color    = auto["color_col"]
        default_material = auto.get("material_col")
        render_info_banner(f"Auto-detected: Style=\'{default_style}\', Color=\'{default_color}\'")
    else:
        default_style    = list(comp_df.columns)[0]
        default_color    = list(comp_df.columns)[1] if len(comp_df.columns) > 1 else list(comp_df.columns)[0]
        default_material = None
    col_a, col_b, col_c_map = st.columns(3)
    with col_a:
        # Change 5: supports both JDE Style (new) and Buyer Style Number (old)
        style_col = st.selectbox("JDE Style / Style Number column", options=list(comp_df.columns), index=list(comp_df.columns).index(default_style) if default_style in comp_df.columns else 0)
    with col_b:
        # Change 5: supports both Color (new) and Color/Option (old)
        color_col = st.selectbox("Color column", options=list(comp_df.columns), index=list(comp_df.columns).index(default_color) if default_color in comp_df.columns else 0)
    with col_c_map:
        # Change 5/6: Material Name for glove/beanie detection
        mat_options = ["(none)"] + list(comp_df.columns)
        mat_default_idx = mat_options.index(default_material) if default_material in mat_options else 0
        material_col = st.selectbox("Material Name column (Glove/Beanie detection)", options=mat_options, index=mat_default_idx)
        if material_col == "(none)":
            material_col = None

    render_divider()
    render_divider()
    st.markdown("""<div class="cx-meta">Settings - Per Buyer Style</div>""", unsafe_allow_html=True)
    render_info_banner("Expand each style to configure label, hangtag, and sticker assignments.")

    label_selections = st.session_state.get("label_selections", {})
    all_style_keys   = list(bom_dict.keys())
    total_styles     = len(all_style_keys)
    total_lm_pages   = max(1, -(-total_styles // STYLES_PER_PAGE))
    lm_page          = max(0, min(st.session_state.get("label_map_page", 0), total_lm_pages - 1))
    st.session_state["label_map_page"] = lm_page

    st.markdown(f"<div style='font-size:0.72rem;color:#5a6080;margin-bottom:0.75rem;'>Showing styles {lm_page*STYLES_PER_PAGE+1}–{min((lm_page+1)*STYLES_PER_PAGE, total_styles)} of {total_styles}</div>", unsafe_allow_html=True)
    render_pagination("label_map_page", lm_page, total_lm_pages, key_suffix="lm")

    page_style_keys = all_style_keys[lm_page * STYLES_PER_PAGE: (lm_page + 1) * STYLES_PER_PAGE]
    for style_key in page_style_keys:
        bom_data_s = bom_dict[style_key]
        components = _get_components_for_bom(bom_data_s)
        saved      = label_selections.get(style_key, {})
        na_opts    = ["N/A"] + components

        with st.expander(f"⚙ Settings — {style_key}", expanded=False):
            if not components:
                st.warning(f"No label components found for {style_key}.")
                label_selections[style_key] = saved
            else:
                def _best(saved_val, preferred_names, _comps=components):
                    if saved_val and saved_val in _comps:
                        return saved_val
                    for p in preferred_names:
                        for c in _comps:
                            if p.lower() in c.lower():
                                return c
                    return _comps[0]

                # Row 1: Main Label / Additional Main Label
                r1a, r1b = st.columns(2)
                with r1a:
                    main_sel = st.selectbox("Main Label", options=components,
                        index=components.index(_best(saved.get("main_label",""), ["label logo 1","Label 1","Main Label"])) if _best(saved.get("main_label",""), ["label logo 1","Label 1","Main Label"]) in components else 0,
                        key=f"main_label_{style_key}")
                with r1b:
                    add_main_sel = st.selectbox("Additional Main Label", options=na_opts,
                        index=na_opts.index(saved.get("add_main_label","N/A")) if saved.get("add_main_label","N/A") in na_opts else 0,
                        key=f"add_main_label_{style_key}")

                # Row 2: Hangtag / Hangtag2 / Hangtag3
                r2a, r2b, r2c = st.columns(3)
                with r2a:
                    ht_sel = st.selectbox("Hangtag", options=na_opts,
                        index=na_opts.index(saved.get("hangtag","N/A")) if saved.get("hangtag","N/A") in na_opts else 0,
                        key=f"hangtag_{style_key}")
                with r2b:
                    ht2_sel = st.selectbox("Hangtag2", options=na_opts,
                        index=na_opts.index(saved.get("hangtag2","N/A")) if saved.get("hangtag2","N/A") in na_opts else 0,
                        key=f"hangtag2_{style_key}")
                with r2c:
                    ht3_sel = st.selectbox("Hangtag3", options=na_opts,
                        index=na_opts.index(saved.get("hangtag3","N/A")) if saved.get("hangtag3","N/A") in na_opts else 0,
                        key=f"hangtag3_{style_key}")

                # Row 3: Micropack / Size Label / Size Sticker (glove fields)
                r3a, r3b, r3c = st.columns(3)
                with r3a:
                    micro_sel = st.selectbox("Micropack Sticker-Gloves", options=na_opts,
                        index=na_opts.index(saved.get("micropack","N/A")) if saved.get("micropack","N/A") in na_opts else 0,
                        key=f"micropack_{style_key}")
                with r3b:
                    size_label_sel = st.selectbox("Size Label", options=na_opts,
                        index=na_opts.index(saved.get("size_label","N/A")) if saved.get("size_label","N/A") in na_opts else 0,
                        key=f"size_label_{style_key}")
                with r3c:
                    size_sticker_sel = st.selectbox("Size Sticker-Gloves", options=na_opts,
                        index=na_opts.index(saved.get("size_sticker","N/A")) if saved.get("size_sticker","N/A") in na_opts else 0,
                        key=f"size_sticker_{style_key}")

                # Row 4: Care Label / Hangtag RFID / RFID Sticker
                r4a, r4b, r4c = st.columns(3)
                with r4a:
                    care_sel = st.selectbox("Care Label", options=components,
                        index=components.index(_best(saved.get("care_label",""), ["Label 1","Care Label","Label1"])) if _best(saved.get("care_label",""), ["Label 1","Care Label","Label1"]) in components else 0,
                        key=f"care_label_{style_key}")
                with r4b:
                    rfid_sel = st.selectbox("Hangtag (RFID)", options=na_opts,
                        index=na_opts.index(saved.get("hangtag_rfid","N/A")) if saved.get("hangtag_rfid","N/A") in na_opts else 0,
                        key=f"hangtag_rfid_{style_key}")
                with r4c:
                    rfid_sticker_sel = st.selectbox("RFID Sticker", options=na_opts,
                        index=na_opts.index(saved.get("rfid_sticker","N/A")) if saved.get("rfid_sticker","N/A") in na_opts else 0,
                        key=f"rfid_sticker_{style_key}")

                # Row 5: UPC / Content Code & Care Code (auto-filled info)
                r5a, r5b = st.columns(2)
                with r5a:
                    upc_sel = st.selectbox("UPC Sticker (Polybag)", options=na_opts,
                        index=na_opts.index(saved.get("upc_sticker","N/A")) if saved.get("upc_sticker","N/A") in na_opts else 0,
                        key=f"upc_sticker_{style_key}")
                with r5b:
                    rfid_no_msrp_sel = st.selectbox("RFID w/o MSRP", options=na_opts,
                        index=na_opts.index(saved.get("rfid_no_msrp","N/A")) if saved.get("rfid_no_msrp","N/A") in na_opts else 0,
                        key=f"rfid_no_msrp_{style_key}")
                    # st.caption("Content Code / Care Code / Content Code-Gloves / Care Code-Gloves — auto-filled from BOM")

                # Row 6: Free-text fields
                r6a, r6b, r6c, r6d = st.columns(4)
                with r6a:
                    tp_status = st.text_input("TP Status", value=saved.get("tp_status",""), key=f"tp_status_{style_key}")
                with r6b:
                    tp_date   = st.text_input("TP Date",   value=saved.get("tp_date",""),   key=f"tp_date_{style_key}")
                with r6c:
                    prod_status = st.text_input("Product Status", value=saved.get("product_status",""), key=f"prod_status_{style_key}")
                with r6d:
                    remarks = st.text_input("Remarks", value=saved.get("remarks",""), key=f"remarks_{style_key}")

                label_selections[style_key] = {
                    "main_label":     main_sel,
                    "add_main_label": add_main_sel,
                    "hangtag":        ht_sel,
                    "hangtag2":       ht2_sel,
                    "hangtag3":       ht3_sel,
                    "micropack":      micro_sel,
                    "size_label":     size_label_sel,
                    "size_sticker":   size_sticker_sel,
                    "care_label":     care_sel,
                    "hangtag_rfid":   rfid_sel,
                    "rfid_no_msrp":   rfid_no_msrp_sel,
                    "rfid_sticker":   rfid_sticker_sel,
                    "upc_sticker":    upc_sel,
                    "tp_status":      tp_status,
                    "tp_date":        tp_date,
                    "product_status": prod_status,
                    "remarks":        remarks,
                }

    st.session_state["label_selections"] = label_selections

    quick_fields = [
        "main_label", "add_main_label", "hangtag", "hangtag2", "hangtag3", "micropack",
        "size_label", "size_sticker", "care_label", "hangtag_rfid", "rfid_sticker",
        "upc_sticker", "rfid_no_msrp", "tp_status", "tp_date", "product_status", "remarks",
    ]
    quick_labels = {
        "main_label": "Main Label",
        "add_main_label": "Additional Main Label",
        "hangtag": "Hangtag",
        "hangtag2": "Hangtag2",
        "hangtag3": "Hangtag3",
        "micropack": "Micropack Sticker-Gloves",
        "size_label": "Size Label",
        "size_sticker": "Size Sticker-Gloves",
        "care_label": "Care Label",
        "hangtag_rfid": "Hangtag (RFID)",
        "rfid_sticker": "RFID Sticker",
        "upc_sticker": "UPC Sticker (Polybag)",
        "rfid_no_msrp": "RFID w/o MSRP",
        "tp_status": "TP Status",
        "tp_date": "TP Date",
        "product_status": "Product Status",
        "remarks": "Remarks",
    }
    render_divider()
    st.markdown("""<div class="cx-meta">Quick Look - Per Style Settings</div>""", unsafe_allow_html=True)
    for style_key in page_style_keys:
        picks = label_selections.get(style_key, {})
        style_colors = _colors_for_style(comp_df, style_col, color_col, style_key)
        chips = []
        if style_colors:
            shown = ", ".join(style_colors[:10])
            extra = f" (+{len(style_colors) - 10})" if len(style_colors) > 10 else ""
            chips.append(f"<span class='cx-chip'>Colors ({len(style_colors)}): {shown}{extra}</span>")
        else:
            chips.append("<span class='cx-chip'>Colors (0): N/A</span>")
        for f in quick_fields:
            val = str(picks.get(f, "N/A")).strip() or "N/A"
            chips.append(f"<span class='cx-chip'>{quick_labels[f]}: {val}</span>")
        st.markdown(
            f"""
            <div class="cx-style-card">
              <div class="cx-style-id">{style_key}</div>
              <div class="cx-chip-row">{''.join(chips)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    renamed_preview = comp_df.rename(columns={style_col: "Buyer Style Number", color_col: "Color/Option"})
    if "Buyer Style Number" in renamed_preview.columns:
        excel_styles = renamed_preview["Buyer Style Number"].astype(str).str.strip().str.upper().unique()
        matched   = [s for s in excel_styles if any(s == b.upper() or s in b.upper() or b.upper() in s for b in bom_dict)]
        unmatched = [s for s in excel_styles if s not in matched]
        if matched:
            render_info_banner(f"Matched styles: {', '.join(matched)}")
        if unmatched:
            render_warn_banner(f"No BOM found for style(s): {', '.join(unmatched)} \u2014 upload the matching PDF(s)")


    render_divider()
    # Two run modes: Quick (no settings) and Full Settings
    run_col1, run_col2 = st.columns(2)
    with run_col1:
        run_quick    = st.button("\u25b6 Run Quick Validation(Existed NG)", key="run_quick",    help="Validates using BOM data only — no label/hangtag settings required")
    with run_col2:
        run_full     = st.button("\u25b6 Run Full Settings Validation", key="run_full", help="Validates using your configured settings (dropdowns above)")

    def _execute_validation(use_settings: bool):
        rename_map = {style_col: "Buyer Style Number", color_col: "Color/Option"}
        renamed_df = comp_df.rename(columns=rename_map)
        label_sels = st.session_state.get("label_selections", {}) if use_settings else {}
        result_parts = []
        for style_val, group_df in renamed_df.groupby("Buyer Style Number", sort=False):
            style_str = str(style_val).strip().upper()
            matched_bom = None
            matched_bom_key = None
            for bom_style, bom in bom_dict.items():
                bs = str(bom_style).strip().upper()
                if style_str == bs or style_str in bs or bs in style_str:
                    matched_bom     = bom
                    matched_bom_key = bom_style
                    break
            if matched_bom is None:
                group_df = group_df.copy()
                for c in NEW_COLUMNS:
                    if c not in group_df.columns:
                        group_df[c] = ""
                group_df["Validation Status"] = f"\u274c Error: No BOM loaded for style '{style_str}'"
                result_parts.append(group_df)
                continue
            per_style_settings = label_sels.get(matched_bom_key, {}) if use_settings else {}
            bom_with_labels    = dict(matched_bom)
            bom_with_labels["label_settings"]            = per_style_settings
            bom_with_labels["selected_main_label_comp"]  = per_style_settings.get("main_label") if use_settings else None
            bom_with_labels["selected_care_label_comp"]  = per_style_settings.get("care_label") if use_settings else None
            product_type = "standard"
            if material_col and material_col in group_df.columns:
                mat_vals = group_df[material_col].dropna().astype(str)
                if not mat_vals.empty:
                    product_type = get_product_type(mat_vals.iloc[0])
            result_parts.append(validate_and_fill(
                comparison_df=group_df.reset_index(drop=True),
                bom_data=bom_with_labels,
                product_type=product_type,
            ))
        combined = pd.concat(result_parts, ignore_index=True) if result_parts else renamed_df

        if not use_settings:
            # Remap Option 2 internal column names → Option 1 output names
            combined = combined.rename(columns=QUICK_COLUMN_REMAP)
            # Keep original input columns + Option 1 output columns only
            original_cols = [c for c in combined.columns if c not in NEW_COLUMNS and c not in QUICK_COLUMNS
                             and c not in QUICK_COLUMN_REMAP.values()]
            keep = original_cols + [c for c in QUICK_COLUMNS if c in combined.columns]
            combined = combined[keep]

        st.session_state["validation_result"] = combined
        st.session_state["validation_mode"]   = "Full Settings" if use_settings else "Quick"

    if run_quick:
        with st.spinner("Running quick validation (BOM data only)..."):
            _execute_validation(use_settings=False)

    if run_full:
        with st.spinner("Running full validation with configured settings..."):
            _execute_validation(use_settings=True)

def render_results():
    # Change 8: now called as its own tab in main()
    if "validation_result" not in st.session_state:
        render_info_banner("Run validation first to see results here.")
        return
    res  = st.session_state["validation_result"]
    mode = st.session_state.get("validation_mode", "")
    render_section_header("Results & Export", "Validation summary and download")
    if mode:
        mode_color = "#34d399" if mode == "Full Settings" else "#93c5fd"
        mode_bg    = "#ecf9f2"  if mode == "Full Settings" else "#ecf3ff"
        mode_border= "#9ad8b7"  if mode == "Full Settings" else "#b7cdef"
        st.markdown(f"""<div style="display:inline-flex;align-items:center;gap:6px;padding:5px 14px;border-radius:999px;font-size:0.76rem;font-weight:700;margin-bottom:1rem;background:{mode_bg};color:{mode_color};border:1px solid {mode_border};">Mode: {mode}</div>""", unsafe_allow_html=True)
    render_divider()
    st.markdown("""<div class="cx-meta">Validation Summary</div>""", unsafe_allow_html=True)
    status_counts = res["Validation Status"].value_counts(dropna=False).to_dict() if "Validation Status" in res.columns else {}
    ok      = status_counts.get("\u2705 Validated", 0)
    partial = status_counts.get("\u26a0\ufe0f Partial", 0)
    err     = sum(v for k, v in status_counts.items() if str(k).startswith("\u274c"))
    render_validation_summary(ok, partial, err, len(res))
    label_selections = st.session_state.get("label_selections", {})
    quick_fields = [
        "main_label", "add_main_label", "hangtag", "hangtag2", "hangtag3", "micropack",
        "size_label", "size_sticker", "care_label", "hangtag_rfid", "rfid_sticker",
        "upc_sticker", "rfid_no_msrp", "tp_status", "tp_date", "product_status", "remarks",
    ]
    quick_labels = {
        "main_label": "Main Label",
        "add_main_label": "Additional Main Label",
        "hangtag": "Hangtag",
        "hangtag2": "Hangtag2",
        "hangtag3": "Hangtag3",
        "micropack": "Micropack Sticker-Gloves",
        "size_label": "Size Label",
        "size_sticker": "Size Sticker-Gloves",
        "care_label": "Care Label",
        "hangtag_rfid": "Hangtag (RFID)",
        "rfid_sticker": "RFID Sticker",
        "upc_sticker": "UPC Sticker (Polybag)",
        "rfid_no_msrp": "RFID w/o MSRP",
        "tp_status": "TP Status",
        "tp_date": "TP Date",
        "product_status": "Product Status",
        "remarks": "Remarks",
    }
    st.markdown("""<div class="cx-meta">Style Summary</div>""", unsafe_allow_html=True)
    res_view_mode = render_view_toggle("results_view_mode", default="Grid", label="Results Card View")
    res_col_count = 1 if res_view_mode == "List" else (3 if res_view_mode == "Tile" else 2)
    res_cols = st.columns(res_col_count)
    style_col_name = "Buyer Style Number" if "Buyer Style Number" in res.columns else None
    color_col_name = "Color/Option" if "Color/Option" in res.columns else None

    style_groups = []
    if style_col_name:
        for style_key, grp in res.groupby(style_col_name, sort=False):
            g = grp.copy()
            status_series = g["Validation Status"].astype(str) if "Validation Status" in g.columns else pd.Series(dtype=str)
            c_ok = int(status_series.str.contains("Validated", case=False, na=False).sum())
            c_partial = int(status_series.str.contains("Partial", case=False, na=False).sum())
            c_err = int(len(g) - c_ok - c_partial)
            total_colors = int(len(g[color_col_name].dropna().astype(str).unique())) if color_col_name and color_col_name in g.columns else int(len(g))
            style_groups.append((str(style_key), g, c_ok, c_partial, c_err, total_colors))
    else:
        status_series = res["Validation Status"].astype(str) if "Validation Status" in res.columns else pd.Series(dtype=str)
        c_ok = int(status_series.str.contains("Validated", case=False, na=False).sum())
        c_partial = int(status_series.str.contains("Partial", case=False, na=False).sum())
        c_err = int(len(res) - c_ok - c_partial)
        style_groups.append(("N/A", res.copy(), c_ok, c_partial, c_err, int(len(res))))

    if "results_selected_style" not in st.session_state and style_groups:
        st.session_state["results_selected_style"] = style_groups[0][0]

    for idx, (style_key, g, c_ok, c_partial, c_err, total_colors) in enumerate(style_groups):
        accent = "#eb5b63" if c_err > 0 else ("#f0b429" if c_partial > 0 else "#3fd2a0")
        with res_cols[idx % res_col_count]:
            card_class = "cx-list-row" if res_view_mode == "List" else "cx-style-card"
            st.markdown(
                f"""
                <div class="{card_class}" style="border-left-color:{accent};">
                  <div class="cx-style-id">{style_key}</div>
                  <div class="cx-chip-row">
                    <span class="cx-chip">Total Colors: {total_colors}</span>
                    <span class="cx-chip">Validated: {c_ok}</span>
                    <span class="cx-chip">Partial: {c_partial}</span>
                    <span class="cx-chip">Errors: {c_err}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Open style", key=f"open_style_{style_key}", type="tertiary", use_container_width=True):
                st.session_state["results_selected_style"] = style_key
                st.rerun()

    selected_style = st.session_state.get("results_selected_style")
    selected_group = next((x for x in style_groups if x[0] == selected_style), None)
    if selected_group is not None:
        style_key, g, _, _, _, _ = selected_group
        st.markdown(f"""<div class="cx-meta">Style Details - {style_key}</div>""", unsafe_allow_html=True)
        picks = label_selections.get(style_key, {})
        if not picks:
            style_upper = style_key.strip().upper()
            for k, v in label_selections.items():
                ku = str(k).strip().upper()
                if style_upper == ku or style_upper in ku or ku in style_upper:
                    picks = v
                    break
        for _, row in g.iterrows():
            color_val = str(row.get(color_col_name, "N/A")) if color_col_name else "N/A"
            material_val = _infer_material_from_row(row, res.columns)
            status_raw = str(row.get("Validation Status", "Parsed"))
            _, _, _, label = _status_style(status_raw)
            accent = _status_accent_color(label)
            chips = [
                f"<span class='cx-chip'>Style: {style_key}</span>",
                f"<span class='cx-chip'>Color: {color_val}</span>",
                f"<span class='cx-chip'>Material: {material_val}</span>",
            ]
            for f in quick_fields:
                val = str(picks.get(f, "N/A")).strip() or "N/A"
                chips.append(f"<span class='cx-chip'>{quick_labels[f]}: {val}</span>")
            st.markdown(
                f"""
                <div class="cx-style-card" style="border-left-color:{accent};">
                  <div class="cx-style-name">{color_val}</div>
                  <div class="cx-chip-row">{''.join(chips)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    render_divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("\u2b07 Export Results \u2192 CSV", data=export_to_csv(res), file_name="validated_bom.csv", mime="text/csv", width='stretch')
    with c2:
        xls = export_to_excel(result_df=res, original_df=st.session_state.get("comparison_raw", pd.DataFrame()))
        st.download_button("\u2b07 Export Results \u2192 Excel", data=xls, file_name="validated_bom.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')


def main():
    inject_theme()
    render_sidebar()
    # Change 8: 3rd tab for Results & Export
    tab1, tab2, tab3 = st.tabs([
        "  \U0001f4c4  PDF Extraction  ",
        "  \U0001f50d  BOM Comparison & Validation  ",
        "  \U0001f4ca  Results & Export  ",
    ])
    with tab1:
        render_pdf_tab()
    with tab2:
        render_comparison_tab()
    with tab3:
        render_results()

if __name__ == "__main__":
    main()
