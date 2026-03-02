import hashlib
import io as _io
import time
from html import escape
import pandas as pd
import streamlit as st

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from parsers.pdf_parser import parse_bom_pdf as _parse_bom_pdf_raw


@st.cache_data(show_spinner=False, max_entries=50)
def _parse_bom_pdf_cached(raw_bytes: bytes):
    """Cache parsed BOM by file content hash — avoids re-parsing same PDF."""
    import io as _cache_io
    return _parse_bom_pdf_raw(_cache_io.BytesIO(raw_bytes))
from validators.matcher import auto_detect_columns, get_product_type
from validators.filler import validate_and_fill, NEW_COLUMNS, QUICK_COLUMNS, QUICK_COLUMN_REMAP
from ui_styles import THEME_CSS


st.set_page_config(
    page_title="Columbia BOM Automation",
    page_icon="\U0001f9e2",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Settings: 10 styles per page
STYLES_PER_PAGE = 10
# Results: Grid=10, Tile=15, List=10 (was 9999)
RESULTS_PER_PAGE_GRID = 10
RESULTS_PER_PAGE_TILE = 15
RESULTS_PER_PAGE_LIST = 10  # FIX: was 9999, now 10

TAB_PDF = "\U0001f4c4 PDF Extraction"
TAB_COMPARE = "\U0001f50d BOM Comparison & Validation"
TAB_RESULTS = "\U0001f4ca Results & Export"
QUICK_SETTING_FIELDS = [
    "main_label", "add_main_label", "hangtag", "hangtag2", "hangtag3", "micropack",
    "size_label", "size_sticker", "care_label", "hangtag_rfid", "rfid_sticker",
    "upc_sticker", "rfid_no_msrp", "tp_status", "tp_date", "product_status", "remarks",
]
QUICK_SETTING_LABELS = {
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
HANGTAG_RFID_COL = "Hangtag (RFID)"
HANGTAG_RFID_SUPPLIER_COL = "Hangtag (RFID) Supplier"
HANGTAG_RFID_OUTPUT_COLS = {HANGTAG_RFID_COL, HANGTAG_RFID_SUPPLIER_COL}

def inject_theme():
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)


def render_section_header(title, subtitle="", compact=False):
    sub_class = "cx-subtitle tight" if compact else "cx-subtitle"
    sub = f"<div class='{sub_class}'>{subtitle}</div>" if subtitle else ""
    st.markdown(f"<h2 class='cx-title'>{title}</h2>{sub}", unsafe_allow_html=True)

def render_divider():
    st.markdown("<div class='cx-divider'></div>", unsafe_allow_html=True)

def render_info_banner(message):
    st.markdown(f"<div class='cx-banner'>{message}</div>", unsafe_allow_html=True)

def render_warn_banner(message):
    st.markdown(f"<div class='cx-banner warn'>{message}</div>", unsafe_allow_html=True)

def render_validation_summary(ok, partial, err, total):
    st.markdown(
        f"""
        <div class="cx-stats">
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--green);">{ok}</div><div class="cx-stat-label">Validated</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--amber);">{partial}</div><div class="cx-stat-label">Partial</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--red);">{err}</div><div class="cx-stat-label">No Match</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:#334e75;">{total}</div><div class="cx-stat-label">Total Rows</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_validation_progress(ok, partial, err, total):
    total_safe = max(int(total or 0), 1)
    ok_w = round((ok / total_safe) * 100, 2)
    partial_w = round((partial / total_safe) * 100, 2)
    err_w = max(0.0, round(100.0 - ok_w - partial_w, 2))
    complete_pct = int(round((ok / total_safe) * 100))
    st.markdown(
        f"""
        <div class="cx-progress-card">
          <div class="cx-progress-head">
            <span>Validation Progress</span>
            <span class="pct">{complete_pct}% Complete</span>
          </div>
          <div class="cx-progress-track">
            <div class="cx-progress-seg ok" style="width:{ok_w}%;"></div>
            <div class="cx-progress-seg partial" style="width:{partial_w}%;"></div>
            <div class="cx-progress-seg err" style="width:{err_w}%;"></div>
          </div>
          <div class="cx-progress-legend">
            <span><span class="cx-progress-dot" style="background:#10b981;"></span>Validated</span>
            <span><span class="cx-progress-dot" style="background:#f0b429;"></span>Partial</span>
            <span><span class="cx-progress-dot" style="background:#ef4444;"></span>Errors</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _status_style(status):
    status_text = str(status or "").lower()
    if "validated" in status_text:
        return "#eaf9f0", "#8fd9b3", "#188d5a", "Validated"
    if "partial" in status_text:
        return "#eaf9f0", "#8fd9b3", "#188d5a", "Validated"
    if "error" in status_text:
        return "#ffeef0", "#f3a2aa", "#b33844", "Error"
    if "parsed" in status_text:
        return "#eaf9f0", "#8fd9b3", "#188d5a", "Validated"
    return "#eaf9f0", "#8fd9b3", "#188d5a", "Validated"

def _style_validation_status(style):
    res = st.session_state.get("validation_result")
    if res is None or res.empty or "Buyer Style Number" not in res.columns or "Validation Status" not in res.columns:
        return "Validated"
    style_upper = str(style).strip().upper()
    statuses = []
    for _, row in res.iterrows():
        row_style = str(row.get("Buyer Style Number", "")).strip().upper()
        if row_style == style_upper or row_style in style_upper or style_upper in row_style:
            statuses.append(str(row.get("Validation Status", "")))
    if not statuses:
        return "Validated"
    lowered = [s.lower() for s in statuses]
    if any("error" in s or s.startswith("\u274c") for s in lowered):
        return "Error"
    if any("validated" in s for s in lowered) or any("partial" in s for s in lowered):
        return "Validated"
    return "Validated"

def _status_accent_color(status_label):
    sl = str(status_label).lower()
    if sl == "validated":
        return "#3fd2a0"
    if sl == "partial":
        return "#f0b429"
    if sl == "error":
        return "#eb5b63"
    return "#4f89f7"


# ── FIX 1: View toggle — preserve open style when switching views ─────────────
def render_view_toggle(state_key, default="Grid", label="", clear_state_keys=None, icon_only=False, right_align=False):
    """
    Instant view toggle using st.segmented_control.
    FIX: Does NOT clear selected/open style when switching views.
    The clear_state_keys param is now ignored to prevent closing open styles.
    """
    options = ["Grid", "Tile", "List"]

    current = st.session_state.get(state_key, default)
    if current not in options:
        current = default
        st.session_state[state_key] = current

    if label:
        st.markdown(f"<div class='cx-meta'>{label}</div>", unsafe_allow_html=True)

    _seg_key = f"__seg_{state_key}"

    def _on_change():
        chosen = st.session_state.get(_seg_key, default)
        prev   = st.session_state.get(state_key, default)
        if chosen and prev != chosen:
            st.session_state[state_key] = chosen
            # FIX 1: Do NOT clear open/selected styles when switching view mode
            # (removed the loop that cleared clear_state_keys)

    st.segmented_control(
        label="",
        options=options,
        default=current,
        key=_seg_key,
        label_visibility="collapsed",
        on_change=_on_change,
    )
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
    """Look up from precomputed cache built by _precompute_style_colors."""
    cache = st.session_state.get("__style_colors_cache", {})
    return cache.get(str(style_key).strip().upper(), [])


def _precompute_style_colors(df, style_col, color_col):
    """Build a dict of style -> [colors] in a single pass. Cache by df sig."""
    sig = f"{style_col}:{color_col}:{df.shape}"
    if st.session_state.get("__scc_hash") == sig:
        return
    result = {}
    if df is None or style_col not in df.columns or color_col not in df.columns:
        st.session_state["__style_colors_cache"] = result
        st.session_state["__scc_hash"] = sig
        return
    for s_val, c_val in zip(
        df[style_col].astype(str).str.strip(),
        df[color_col].astype(str).str.strip()
    ):
        if not s_val or not c_val or s_val.lower() in ("nan","none") or c_val.lower() in ("nan","none"):
            continue
        su = s_val.upper()
        if su not in result:
            result[su] = []
        if c_val not in result[su]:
            result[su].append(c_val)
    st.session_state["__style_colors_cache"] = result
    st.session_state["__scc_hash"] = sig

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


# ── FIX: Faster pagination — avoid clearing unrelated state ──────────────────
def render_pagination(page_key, current_page, total_pages, key_suffix="", show_page_text=True):
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
    if show_page_text:
        st.markdown(f"<div style='text-align:center;font-size:0.7rem;color:#5a6080;margin-top:2px;'>Page {current_page + 1} of {total_pages}</div>", unsafe_allow_html=True)
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
        if st.button("\U0001f5d1 Clear All Data", width='stretch'):
            pdf_k = st.session_state.get("pdf_uploader_key", 0) + 1
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.session_state["pdf_uploader_key"] = pdf_k
            st.rerun(scope="app")
        st.markdown(
            """
            <div class="cx-side-bottom">
              <div class="cx-side-steps">
                <div class="cx-side-step"><span class="cx-side-step-num">1</span><span>Upload BOM PDFs</span></div>
                <div class="cx-side-step"><span class="cx-side-step-num">2</span><span>Upload your excel/CSV</span></div>
                <div class="cx-side-step"><span class="cx-side-step-num">3</span><span>Map columns &amp; configure</span></div>
                <div class="cx-side-step"><span class="cx-side-step-num">4</span><span>Export validated output</span></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_style_key(style, bom_dict):
    su = style.strip().upper()
    for k in bom_dict:
        if su == k.strip().upper():
            return k
    return None


def _styles_match(left, right):
    lsu = str(left).strip().upper()
    rsu = str(right).strip().upper()
    return lsu == rsu or lsu in rsu or rsu in lsu


def _find_matching_bom(style_val, bom_dict):
    style_str = str(style_val).strip().upper()
    for bom_style, bom in bom_dict.items():
        if _styles_match(style_str, bom_style):
            return bom_style, bom
    return None, None


def _status_counts(df):
    status_series = df["Validation Status"].astype(str) if "Validation Status" in df.columns else pd.Series(dtype=str)
    c_ok = int(status_series.str.contains("Validated", case=False, na=False).sum())
    c_partial = int(status_series.str.contains("Partial", case=False, na=False).sum())
    c_err = int(len(df) - c_ok - c_partial)
    return c_ok, c_partial, c_err


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


@st.dialog("BOM Inspector", width="large")
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

    if active_sec == "costing_detail" and not view_df.empty:
        preferred_cols = ["component", "material", "description", "supplier", "country of origin"]
        normalized = {str(c).strip().lower(): c for c in view_df.columns}
        keep = [normalized[c] for c in preferred_cols if c in normalized]
        if keep:
            view_df = view_df[keep]
    elif active_sec == "color_bom" and not view_df.empty:
        drop_cols = [
            c for c in view_df.columns
            if "line" in str(c).strip().lower() and "slot" in str(c).strip().lower()
        ]
        if drop_cols:
            view_df = view_df.drop(columns=drop_cols, errors="ignore")

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


@st.dialog("Validation Complete", width="small", dismissible=False)
def show_validation_complete_dialog():
    st.markdown("<div class='cx-meta'>Validation finished</div>", unsafe_allow_html=True)
    msg = st.empty()
    for sec in (3, 2, 1):
        msg.markdown(
            f"<div style='font-size:0.86rem;color:#4f688c;margin-bottom:0.6rem;'>Validation completed successfully. Closing in {sec}...</div>",
            unsafe_allow_html=True,
        )
        time.sleep(1)
    st.session_state["post_validation_prompt"] = False
    st.rerun(scope="app")


# ─────────────────────────────────────────────────────────────────────────────
# SHARED DETAIL CARD BUILDER (used in both Results & Comparison tabs)
# ─────────────────────────────────────────────────────────────────────────────

_DETAIL_GROUPS = [
    ("Label",   [
        ("Main Label",          "Main Label"),
        ("Main Label Color",    "Main Label Color"),
        ("Main Label Supplier", "Main Label Supplier"),
        ("Care Label",          "Care Label"),
        ("Care Label Color",    "Care Label Color"),
        ("Care Supplier",       "Care Supplier"),
    ]),
    ("Hangtag", [
        ("Hangtag",             "Hangtag"),
        ("Hangtag Supplier",    "Hangtag Supplier"),
        ("Hangtag 2",           "Hangtag 2"),
        ("Hangtag 3",           "Hangtag3"),
        ("RFID w/o MSRP",       "RFID w/o MSRP"),
        ("RFID w/o MSRP Sup",   "RFID w/o MSRP Supplier"),
    ]),
    ("Sticker", [
        ("RFID Sticker",        "RFID Stickers"),
        ("RFID Sticker Sup",    "RFID Stickers Supplier"),
        ("UPC Bag Sticker",     "UPC Bag Sticker (Polybag)"),
        ("UPC Supplier",        "UPC Supplier"),
    ]),
    ("Content", [
        ("Content Code",        "Content Code"),
        ("TP FC",               "TP FC"),
        ("Care Code",           "Care Code"),
    ]),
]

def _field_val(row, col):
    v = str(row.get(col, "")).strip()
    return v if v and v.lower() not in ("nan", "none", "") else "N/A"

def _val_color(v):
    if v == "N/A":
        return "#b0b8c8"
    return "#1a2b45"

def _build_detail_card_html(row, accent, color_val, material_val, status_raw, res_cols_set, extra_fields=None):
    """
    Build a rich detail card. extra_fields is an optional dict of {label: value}
    for settings fields (main_label, hangtag, etc.) shown in the Comparison tab.
    """
    if "✅" in status_raw:
        sbg, sfg = "#d1fae5", "#065f46"
    elif "⚠️" in status_raw:
        sbg, sfg = "#fef9c3", "#854d0e"
    else:
        sbg, sfg = "#fee2e2", "#991b1b"

    html = (
        f"<div style='border-left:4px solid {accent};border-radius:10px;"
        f"padding:14px 16px 12px;margin-bottom:10px;background:#fff;"
        f"box-shadow:0 1px 6px rgba(0,0,0,0.08);'>"
        # Top row: color + status badge
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<div style='font-size:1rem;font-weight:700;color:#1a2b45;'>{escape(color_val)}</div>"
        f"<span style='font-size:0.68rem;font-weight:700;padding:3px 10px;border-radius:999px;"
        f"background:{sbg};color:{sfg};'>{escape(status_raw)}</span>"
        f"</div>"
        # Material row
        f"<div style='font-size:0.74rem;color:#6b7a99;margin-bottom:10px;'>"
        f"<span style='font-weight:700;color:#4a5568;'>Material:</span> {escape(material_val)}</div>"
    )

    # Validated BOM field groups (only shown in Results tab or if present)
    for grp_label, fields in _DETAIL_GROUPS:
        avail = [(lbl, col) for lbl, col in fields if col in res_cols_set]
        if not avail:
            continue
        vals = [(lbl, _field_val(row, col)) for lbl, col in avail]
        has_data = any(v != "N/A" for _, v in vals)
        if not has_data:
            continue

        html += (
            f"<div style='margin-bottom:8px;'>"
            f"<div style='font-size:0.61rem;font-weight:800;letter-spacing:0.08em;"
            f"text-transform:uppercase;color:#94a3b8;margin-bottom:4px;'>{grp_label}</div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>"
        )
        for lbl, v in vals:
            vc = _val_color(v)
            bg = "#f1f5f9" if v != "N/A" else "#f8fafc"
            html += (
                f"<div style='display:inline-flex;flex-direction:column;padding:4px 8px;"
                f"border-radius:6px;background:{bg};border:1px solid #e2e8f0;min-width:80px;max-width:180px;'>"
                f"<span style='font-size:0.57rem;color:#94a3b8;font-weight:600;"
                f"letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;overflow:hidden;"
                f"text-overflow:ellipsis;'>{escape(lbl)}</span>"
                f"<span style='font-size:0.74rem;font-weight:600;color:{vc};"
                f"margin-top:1px;word-break:break-word;'>{escape(v)}</span>"
                f"</div>"
            )
        html += "</div></div>"

    # Extra settings fields (Comparison tab Quick Look with improved styling)
    if extra_fields:
        # Group extra fields into logical clusters
        _extra_groups = {
            "Labels": ["Main Label", "Additional Main Label", "Care Label"],
            "Hangtags": ["Hangtag", "Hangtag2", "Hangtag3", "Hangtag (RFID)", "RFID w/o MSRP"],
            "Stickers": ["Micropack Sticker-Gloves", "Size Label", "Size Sticker-Gloves",
                         "RFID Sticker", "UPC Sticker (Polybag)"],
            "Status": ["TP Status", "TP Date", "Product Status", "Remarks"],
        }
        for grp_label, grp_keys in _extra_groups.items():
            grp_vals = [(k, extra_fields[k]) for k in grp_keys if k in extra_fields]
            has_data = any(v not in ("N/A", "", None) for _, v in grp_vals)
            if not grp_vals or not has_data:
                continue
            html += (
                f"<div style='margin-bottom:8px;'>"
                f"<div style='font-size:0.61rem;font-weight:800;letter-spacing:0.08em;"
                f"text-transform:uppercase;color:#94a3b8;margin-bottom:4px;'>{grp_label}</div>"
                f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>"
            )
            for lbl, v in grp_vals:
                display_v = str(v).strip() if v and str(v).strip() not in ("", "N/A", "nan", "None") else "N/A"
                vc = _val_color(display_v)
                bg = "#f1f5f9" if display_v != "N/A" else "#f8fafc"
                html += (
                    f"<div style='display:inline-flex;flex-direction:column;padding:4px 8px;"
                    f"border-radius:6px;background:{bg};border:1px solid #e2e8f0;min-width:80px;max-width:180px;'>"
                    f"<span style='font-size:0.57rem;color:#94a3b8;font-weight:600;"
                    f"letter-spacing:0.04em;text-transform:uppercase;white-space:nowrap;overflow:hidden;"
                    f"text-overflow:ellipsis;'>{escape(lbl)}</span>"
                    f"<span style='font-size:0.74rem;font-weight:600;color:{vc};"
                    f"margin-top:1px;word-break:break-word;'>{escape(display_v)}</span>"
                    f"</div>"
                )
            html += "</div></div>"

    html += "</div>"
    return html


def render_pdf_tab():
    render_section_header("PDF Extraction", "Click any card to view all section data & key IDs", compact=True)
    uploader_key = f"pdf_uploader_{st.session_state.get('pdf_uploader_key', 0)}"
    uploaded_pdfs = st.file_uploader(
        "Click to add PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key=uploader_key,
        help="Upload one or more PDFs. Each PDF is matched to Excel rows by style number.",
        label_visibility="collapsed",
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
                    bom_data = _parse_bom_pdf_cached(raw_bytes)
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
            st.rerun()

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
    count_error = sum(1 for r in summary_rows if r["Status"] == "Error")
    st.markdown(
        f"""
        <div class="cx-stats" style="grid-template-columns: repeat(3, minmax(0,1fr));">
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:#3569de;">{len(summary_rows)}</div><div class="cx-stat-label">BOMS</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--green);">{count_validated}</div><div class="cx-stat-label">VALIDATED</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--red);">{count_error}</div><div class="cx-stat-label">ERRORS</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # FIX 1: View toggle — no longer clears inspect_popup_style
    view_mode = render_view_toggle(
        "loaded_boms_view",
        default="Grid",
        label="Loaded BOM View",
        clear_state_keys=None,  # FIX: don't clear open style
        icon_only=False,
        right_align=False,
    )

    # FIX 2: List shows max 10 items per page
    BOMS_PER_PAGE_GRID = 10
    BOMS_PER_PAGE_TILE = 15
    BOMS_PER_PAGE_LIST = 10
    bom_per_page = BOMS_PER_PAGE_LIST if view_mode == "List" else (BOMS_PER_PAGE_TILE if view_mode == "Tile" else BOMS_PER_PAGE_GRID)
    total_bom_pages = max(1, -(-len(summary_rows) // bom_per_page))
    bom_page_key = "loaded_boms_page"
    bom_page = max(0, min(st.session_state.get(bom_page_key, 0), total_bom_pages - 1))
    st.session_state[bom_page_key] = bom_page

    page_summary_rows = summary_rows[bom_page * bom_per_page: (bom_page + 1) * bom_per_page]

    col_count = 1 if view_mode == "List" else (3 if view_mode == "Tile" else 2)
    deck_cols = st.columns(col_count)
    for idx, row in enumerate(page_summary_rows):
        style = row["Style"]
        global_idx = bom_page * bom_per_page + idx + 1
        status = row.get("Status", _style_validation_status(style))
        bg, border, fg, label = _status_style(status)
        accent = _status_accent_color(label)

        with deck_cols[idx % col_count]:
            if view_mode == "List":
                # FIX 2: Rich list row design
                st.markdown(
                    f"""
                    <div class="cx-list-row" style="
                        border-left:4px solid {accent};
                        border-radius:10px;
                        padding:12px 16px;
                        margin-bottom:6px;
                        background:#fff;
                        box-shadow:0 1px 4px rgba(0,0,0,0.07);
                        display:flex;
                        align-items:center;
                        gap:14px;
                    ">
                        <span style="
                            font-size:0.7rem;font-weight:800;color:#9aabbd;
                            min-width:22px;text-align:right;
                        ">{global_idx}</span>
                        <div style="flex:1;min-width:0;">
                            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                                <span style="font-size:0.95rem;font-weight:800;color:#1a2b45;letter-spacing:-0.01em;">{style}</span>
                                <span style="font-size:0.68rem;font-weight:700;padding:2px 9px;border-radius:999px;
                                    background:{bg};border:1px solid {border};color:{fg};white-space:nowrap;">{label}</span>
                            </div>
                            <div style="font-size:0.75rem;color:#5a6a82;margin-top:2px;margin-bottom:5px;
                                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                                {row.get('Design','—')}
                            </div>
                            <div style="display:flex;flex-wrap:wrap;gap:4px;">
                                <span class="cx-chip">Color: {row.get('Color','N/A')}</span>
                                <span class="cx-chip">Season: {row['Season']}</span>
                                <span class="cx-chip">LO: {row['LO']}</span>
                                <span class="cx-chip">&#8862; {row['Sections']} Sections</span>
                                <span class="cx-chip">&#9671; {row['Colorways']} Colorways</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                # Grid / Tile card — FIX 2: rich card design
                number_badge = f"<span style='font-size:0.7rem;color:#9aabbd;font-weight:600;margin-right:4px;'>#{global_idx}</span>"
                st.markdown(
                    f"""
                    <div class="cx-style-card" style="
                        border-left:4px solid {accent};
                        border-radius:10px;
                        padding:14px 16px 10px;
                        background:#fff;
                        box-shadow:0 1px 6px rgba(0,0,0,0.08);
                        margin-bottom:8px;
                    ">
                      <div class="cx-style-top">
                        <div>
                          <div class="cx-style-id cx-style-id-row">{number_badge}<span>{style}</span></div>
                          <div class="cx-style-name" style="margin-top:2px;font-size:0.8rem;color:#5a6a82;">{row.get('Design','BOM Style')}</div>
                        </div>
                        <div class="cx-status" style="background:{bg};border-color:{border};color:{fg};">{label}</div>
                      </div>
                      <div class="cx-chip-row" style="margin-top:8px;">
                        <span class="cx-chip">Color: {row.get('Color','N/A')}</span>
                        <span class="cx-chip">Season: {row['Season']}</span>
                        <span class="cx-chip">LO: {row['LO']}</span>
                      </div>
                      <div class="cx-style-footer" style="margin-top:8px;border-top:1px solid #f0f4f8;padding-top:8px;">
                        <div class="cx-footer-meta">
                          <span><span class="cx-count-num">&#8862; {row['Sections']}</span> <span class="cx-count-label">Sections</span></span>
                          <span><span class="cx-count-num">&#9671; {row['Colorways']}</span> <span class="cx-count-label">Colorways</span></span>
                        </div>
                        <div class="cx-footer-hint" style="font-size:0.68rem;color:#9aabbd;">Click to inspect</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            hitbox_prefix = "card_hit_list" if view_mode == "List" else "card_hit_grid"
            with st.container(key=f"{hitbox_prefix}_{idx}"):
                inspect_click = st.button(" ", key=f"inspect_card_{style}", use_container_width=True)
            if inspect_click:
                st.session_state["pdf_inspect_style"] = style
                st.session_state["inspect_popup_style"] = style
                st.rerun()

    # FIX 3: Pagination below cards
    render_pagination(bom_page_key, bom_page, total_bom_pages, key_suffix="bom_pg", show_page_text=True)

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


def _normalize_supplier_names(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    supplier_cols = [c for c in out.columns if "supplier" in str(c).strip().lower()]
    for col in supplier_cols:
        out[col] = out[col].apply(
            lambda v: "PT BSN" if isinstance(v, str) and "bao shen" in v.strip().lower() else v
        )
    return out


def render_comparison_tab():
    render_section_header("BOM Comparison & Validation")
    if st.session_state.get("post_validation_prompt"):
        show_validation_complete_dialog()

    bom_dict = st.session_state.get("bom_dict", {})
    if not bom_dict:
        render_warn_banner("No BOMs loaded. Upload Columbia BOM PDFs in the PDF Extraction tab first.")
        return

    comp_file = st.file_uploader(
        "Drop your Comparison Excel or CSV here",
        type=["xlsx", "csv", "xls"],
        key="cmp_uploader",
        help="Can contain 100+ rows and multiple styles",
    )
    if comp_file is not None:
        raw_bytes = comp_file.getvalue()
        new_sig = f"{comp_file.name}:{len(raw_bytes)}"
        if st.session_state.get("comparison_upload_sig") != new_sig:
            st.session_state.pop("validation_result", None)
            st.session_state.pop("validation_mode", None)
        st.session_state["comparison_upload_bytes"] = raw_bytes
        st.session_state["comparison_upload_name"] = comp_file.name
        st.session_state["comparison_upload_size"] = len(raw_bytes)
        st.session_state["comparison_upload_sig"] = new_sig
    else:
        cached_bytes = st.session_state.get("comparison_upload_bytes")
        cached_name  = st.session_state.get("comparison_upload_name")
        if not cached_bytes or not cached_name:
            st.session_state.pop("validation_result", None)
            st.session_state.pop("validation_mode", None)
            st.session_state.pop("comparison_upload_sig", None)
            return
        restored = _io.BytesIO(cached_bytes)
        restored.name = cached_name
        comp_file = restored

    cmp_sig = f"{comp_file.name}:{getattr(comp_file, 'size', st.session_state.get('comparison_upload_size', 0))}"
    prev_sig = st.session_state.get("comparison_file_sig")
    if prev_sig != cmp_sig:
        st.session_state["comparison_file_sig"] = cmp_sig
        if st.session_state.get("inspect_popup_style"):
            st.session_state["inspect_popup_style"] = None
            st.rerun()

    try:
        _upload_sig = st.session_state.get("comparison_upload_sig", "")
        if st.session_state.get("__norm_hash") != _upload_sig or "__norm_cache" not in st.session_state:
            _raw_df = _read_comparison_file(comp_file)
            comp_df = _normalize_supplier_names(_raw_df)
            st.session_state["__norm_cache"] = comp_df
            st.session_state["__norm_hash"]  = _upload_sig
        else:
            comp_df = st.session_state["__norm_cache"]
        st.session_state["comparison_raw"] = comp_df
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        return

    st.markdown("<div style='height:0;'></div>", unsafe_allow_html=True)
    mapping_card = st.container(border=True, key="column_mapping_card")
    with mapping_card:
        st.markdown("""<div class="cx-meta" style="margin-bottom:0.35rem;">Column Mapping</div>""", unsafe_allow_html=True)
        _adc_key = "__adc_" + str(list(comp_df.columns)) + str(comp_df.shape)
        if st.session_state.get("__adc_hash") != _adc_key:
            auto = auto_detect_columns(comp_df)
            st.session_state["__adc_cache"] = auto
            st.session_state["__adc_hash"]  = _adc_key
        else:
            auto = st.session_state["__adc_cache"]
        auto_detected_note = ""
        if auto and auto["confidence"] >= 0.7:
            default_style    = auto["style_col"]
            default_color    = auto["color_col"]
            default_material = auto.get("material_col")
            auto_detected_note = (
                f"<div class='cx-meta' style='margin-top:-0.08rem;margin-bottom:0.45rem;letter-spacing:0;text-transform:none;'>"
                f"Auto-selected columns: Style = <b>{escape(str(default_style))}</b>, "
                f"Color = <b>{escape(str(default_color))}</b>"
                f"{', Material = <b>' + escape(str(default_material)) + '</b>' if default_material else ''}"
                f"</div>"
            )
        else:
            default_style    = list(comp_df.columns)[0]
            default_color    = list(comp_df.columns)[1] if len(comp_df.columns) > 1 else list(comp_df.columns)[0]
            default_material = None
        if auto_detected_note:
            st.markdown(auto_detected_note, unsafe_allow_html=True)
        col_a, col_b, col_c_map = st.columns(3, gap="medium")
        with col_a:
            style_col = st.selectbox("JDE Style / Style Number column", options=list(comp_df.columns), index=list(comp_df.columns).index(default_style) if default_style in comp_df.columns else 0)
        with col_b:
            color_col = st.selectbox("Color column", options=list(comp_df.columns), index=list(comp_df.columns).index(default_color) if default_color in comp_df.columns else 0)
        with col_c_map:
            mat_options = ["(none)"] + list(comp_df.columns)
            mat_default_idx = mat_options.index(default_material) if default_material in mat_options else 0
            material_col = st.selectbox("Material Name column (Glove/Beanie detection)", options=mat_options, index=mat_default_idx)
            if material_col == "(none)":
                material_col = None
        show_hangtag_rfid = "buyer style" in str(style_col).strip().lower()
        st.session_state["show_hangtag_rfid"] = show_hangtag_rfid
        _precompute_style_colors(comp_df, style_col, color_col)

    st.markdown("<div style='height:0;'></div>", unsafe_allow_html=True)
    label_selections = st.session_state.get("label_selections", {})
    all_style_keys   = list(bom_dict.keys())
    total_styles     = len(all_style_keys)
    total_lm_pages   = max(1, -(-total_styles // STYLES_PER_PAGE))
    lm_page          = max(0, min(st.session_state.get("label_map_page", 0), total_lm_pages - 1))
    st.session_state["label_map_page"] = lm_page

    start_idx = lm_page * STYLES_PER_PAGE + 1 if total_styles else 0
    end_idx = min((lm_page + 1) * STYLES_PER_PAGE, total_styles)
    settings_header = st.container(border=True, key="settings_header_card")
    with settings_header:
        st.markdown(
            f"""
            <div class="cx-settings-head">
              <div class="cx-settings-left">
                <div class="cx-settings-title">Settings - Per Buyer Style</div>
                <div class="cx-settings-sub">Expand each style to configure label, hangtag, and sticker assignments.</div>
              </div>
              <div class="cx-settings-right">
                <span class="cx-settings-count">Showing styles {start_idx}–{end_idx} of {total_styles}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    page_style_keys = all_style_keys[lm_page * STYLES_PER_PAGE: (lm_page + 1) * STYLES_PER_PAGE]
    for style_key in page_style_keys:
        bom_data_s = bom_dict[style_key]
        _comp_cache = st.session_state.setdefault("_comp_cache", {})
        if style_key not in _comp_cache:
            _comp_cache[style_key] = _get_components_for_bom(bom_data_s)
        components = _comp_cache[style_key]
        saved      = label_selections.get(style_key, {})
        na_opts    = ["N/A"] + components

        _meta_s   = bom_data_s.get("metadata", {})
        _smu_type = str(_meta_s.get("smu_type", _meta_s.get("SMU Type", "N/A"))).strip()
        _smu_type = _smu_type if _smu_type and _smu_type.lower() not in ("", "nan", "none") else "N/A"
        _search_parts = [
            str(_meta_s.get("style_description", "")),
            str(_meta_s.get("description", "")),
            str(_meta_s.get("design", "")),
            style_key,
        ] + [str(c) for c in components]
        _cb_s = bom_data_s.get("color_bom")
        if isinstance(_cb_s, pd.DataFrame) and not _cb_s.empty:
            _search_parts += [str(v) for v in _cb_s.iloc[:, 0].dropna()]
        _search_str = " ".join(_search_parts).lower()

        if "glove" in _search_str or "mitt" in _search_str:
            _prod_type_label = "Gloves"
        elif (
            "beanie" in _search_str or "cuffed" in _search_str
            or "whirlibird" in _search_str
            or ("hat" in _search_str and "component" in _search_str)
        ):
            _prod_type_label = "Beanie"
        elif "jacket" in _search_str or "vest" in _search_str or "parka" in _search_str or "anorak" in _search_str:
            _prod_type_label = "Jacket"
        elif "pant" in _search_str or "short" in _search_str or "bib" in _search_str:
            _prod_type_label = "Pants"
        elif "sock" in _search_str:
            _prod_type_label = "Socks"
        elif "boot" in _search_str or "shoe" in _search_str or "footwear" in _search_str:
            _prod_type_label = "Footwear"
        elif "bag" in _search_str or "backpack" in _search_str:
            _prod_type_label = "Bag"
        else:
            _prod_type_label = ""
        _expander_label = f"⚙ Settings — {style_key}"
        if _prod_type_label:
            _expander_label += f" · {_prod_type_label}"
        _expander_label += f" · SMU: {_smu_type}"

        with st.expander(_expander_label, expanded=False):
            if not components:
                st.warning(f"No label components found for {style_key}.")
                label_selections[style_key] = saved
            else:
                def _pick_option(options, *keywords, fallback=None):
                    for kw in keywords:
                        kw_l = str(kw).lower()
                        for opt in options:
                            if kw_l in str(opt).lower():
                                return opt
                    return fallback if fallback is not None else (options[0] if options else "N/A")

                def _best(saved_val, preferred_names, _comps=components, exclude_alt=False):
                    if saved_val and saved_val in _comps:
                        return saved_val
                    for p in preferred_names:
                        p_l = p.lower()
                        for c in _comps:
                            c_l = c.lower()
                            if p_l in c_l:
                                if exclude_alt and c_l.startswith("alt"):
                                    continue
                                return c
                    return _comps[0]

                r1a, r1b = st.columns(2)
                with r1a:
                    _main_default = _best(
                        saved.get("main_label", ""),
                        ["label logo 1", "hat components", "hat component", "direct embroidery", "label 1", "main label"],
                        exclude_alt=True,
                    )
                    main_sel = st.selectbox("Main Label", options=components,
                        index=components.index(_main_default) if _main_default in components else 0,
                        key=f"main_label_{style_key}")
                with r1b:
                    add_main_sel = st.selectbox("Additional Main Label", options=na_opts,
                        index=na_opts.index(saved.get("add_main_label","N/A")) if saved.get("add_main_label","N/A") in na_opts else 0,
                        key=f"add_main_label_{style_key}")

                r2a, r2b, r2c = st.columns(3)
                with r2a:
                    hangtag_default = _pick_option(na_opts, "hangtag package part", "hangtag", fallback="N/A")
                    ht_sel = st.selectbox("Hangtag", options=na_opts,
                        index=na_opts.index(hangtag_default) if hangtag_default in na_opts else 0,
                        key=f"hangtag_{style_key}")
                with r2b:
                    ht2_sel = st.selectbox("Hangtag2", options=na_opts,
                        index=na_opts.index(saved.get("hangtag2","N/A")) if saved.get("hangtag2","N/A") in na_opts else 0,
                        key=f"hangtag2_{style_key}")
                with r2c:
                    ht3_sel = st.selectbox("Hangtag3", options=na_opts,
                        index=na_opts.index(saved.get("hangtag3","N/A")) if saved.get("hangtag3","N/A") in na_opts else 0,
                        key=f"hangtag3_{style_key}")

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

                if show_hangtag_rfid:
                    r4a, r4b, r4c = st.columns(3)
                else:
                    r4a, r4c = st.columns(2)
                with r4a:
                    _care_default = _best(
                        saved.get("care_label", ""),
                        ["label 1 -", "label 1", "care label"],
                        exclude_alt=True,
                    )
                    care_sel = st.selectbox("Care Label", options=components,
                        index=components.index(_care_default) if _care_default in components else 0,
                        key=f"care_label_{style_key}")
                if show_hangtag_rfid:
                    with r4b:
                        rfid_sel = st.selectbox("Hangtag (RFID)", options=na_opts,
                            index=na_opts.index(saved.get("hangtag_rfid","N/A")) if saved.get("hangtag_rfid","N/A") in na_opts else 0,
                            key=f"hangtag_rfid_{style_key}")
                else:
                    rfid_sel = "N/A"
                with r4c:
                    rfid_sticker_default = _pick_option(na_opts, "123130", "121612", "rfid sticker", fallback="N/A")
                    rfid_sticker_sel = st.selectbox("RFID Sticker", options=na_opts,
                        index=na_opts.index(rfid_sticker_default) if rfid_sticker_default in na_opts else 0,
                        key=f"rfid_sticker_{style_key}")

                r5a, r5b = st.columns(2)
                with r5a:
                    upc_default = _pick_option(na_opts, "packaging 3", fallback="N/A")
                    upc_sel = st.selectbox("UPC Sticker (Polybag)", options=na_opts,
                        index=na_opts.index(upc_default) if upc_default in na_opts else 0,
                        key=f"upc_sticker_{style_key}")
                with r5b:
                    rfid_no_msrp_sel = st.selectbox("RFID w/o MSRP", options=na_opts,
                        index=na_opts.index(saved.get("rfid_no_msrp","N/A")) if saved.get("rfid_no_msrp","N/A") in na_opts else 0,
                        key=f"rfid_no_msrp_{style_key}")

                st.markdown(
                    "<div style='margin-top:0.7rem;margin-bottom:0.35rem;"
                    "font-size:0.72rem;font-weight:700;letter-spacing:0.07em;"
                    "text-transform:uppercase;color:#4a6286;border-top:1px solid #dce6f2;"
                    "padding-top:0.6rem;'>"
                    "Main Label Color — Fallback Settings"
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    "<div style='font-size:0.78rem;color:#5f7a9e;margin-bottom:0.5rem;line-height:1.45;'>"
                    "When the primary component lookup returns no color, these fallbacks are tried "
                    "<b>in order</b>. Fallback 3 (colorway name) activates automatically when "
                    "Fallback 1 or Fallback 2 is enabled."
                    "</div>",
                    unsafe_allow_html=True,
                )

                _main_norm = str(main_sel).strip().lower()
                if ("hat component" in _main_norm) or ("117027" in _main_norm):
                    fb1_auto = next((o for o in na_opts if "alt hat component 1a" in str(o).lower()), None)
                    fb2_auto = next((o for o in na_opts if "alt hat component 1b" in str(o).lower()), None)
                    if fb1_auto:
                        st.session_state[f"main_label_fallback_{style_key}"] = fb1_auto
                        st.session_state[f"use_main_label_fallback_{style_key}"] = True
                    if fb2_auto:
                        st.session_state[f"main_label_fallback2_{style_key}"] = fb2_auto
                        st.session_state[f"use_main_label_fallback2_{style_key}"] = True

                fb1_col_a, fb1_col_b = st.columns([3, 1])
                with fb1_col_a:
                    fb1_sel = st.selectbox(
                        "Fallback 1 — Alt component for color lookup",
                        options=na_opts,
                        index=na_opts.index(saved.get("main_label_fallback", "N/A"))
                            if saved.get("main_label_fallback", "N/A") in na_opts else 0,
                        key=f"main_label_fallback_{style_key}",
                    )
                with fb1_col_b:
                    use_fb1 = st.checkbox(
                        "Enable",
                        value=bool(saved.get("use_main_label_fallback", False)),
                        key=f"use_main_label_fallback_{style_key}",
                    )

                fb2_col_a, fb2_col_b = st.columns([3, 1])
                with fb2_col_a:
                    fb2_sel = st.selectbox(
                        "Fallback 2 — Alt component for color lookup",
                        options=na_opts,
                        index=na_opts.index(saved.get("main_label_fallback2", "N/A"))
                            if saved.get("main_label_fallback2", "N/A") in na_opts else 0,
                        key=f"main_label_fallback2_{style_key}",
                    )
                with fb2_col_b:
                    use_fb2 = st.checkbox(
                        "Enable",
                        value=bool(saved.get("use_main_label_fallback2", False)),
                        key=f"use_main_label_fallback2_{style_key}",
                    )

                st.markdown(
                    "<div style='font-size:0.78rem;color:#3a5278;padding:0.38rem 0 0.1rem 0;"
                    "font-weight:600;'>"
                    "Fallback 3 — Use colorway name (strip numeric prefix) "
                    "<span style='font-size:0.7rem;color:#7090b4;font-weight:400;'>"
                    "— auto-enabled when FB1 or FB2 is on</span>"
                    "</div>"
                    "<div style='font-size:0.74rem;color:#7090b4;line-height:1.35;margin-bottom:0.3rem;'>"
                    "e.g. matched colorway <code>262-Canoe, Mountains</code> "
                    "→ color becomes <b>Canoe, Mountains</b>"
                    "</div>",
                    unsafe_allow_html=True,
                )

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
                    "main_label":                main_sel,
                    "add_main_label":            add_main_sel,
                    "hangtag":                   ht_sel,
                    "hangtag2":                  ht2_sel,
                    "hangtag3":                  ht3_sel,
                    "micropack":                 micro_sel,
                    "size_label":                size_label_sel,
                    "size_sticker":              size_sticker_sel,
                    "care_label":                care_sel,
                    "hangtag_rfid":              rfid_sel,
                    "rfid_no_msrp":              rfid_no_msrp_sel,
                    "rfid_sticker":              rfid_sticker_sel,
                    "upc_sticker":               upc_sel,
                    "main_label_fallback":         fb1_sel,
                    "use_main_label_fallback":     use_fb1,
                    "main_label_fallback2":        fb2_sel,
                    "use_main_label_fallback2":    use_fb2,
                    "tp_status":      tp_status,
                    "tp_date":        tp_date,
                    "product_status": prod_status,
                    "remarks":        remarks,
                }

    st.session_state["label_selections"] = label_selections

    # ── Pagination BELOW the last settings expander ────────────────────────────
    render_pagination("label_map_page", lm_page, total_lm_pages, key_suffix="lm", show_page_text=True)

    # FIX: Matched/unmatched info
    _match_sig = str(sorted(bom_dict.keys())) + ":" + style_col + ":" + str(comp_df.shape)
    if st.session_state.get("__match_hash") != _match_sig:
        _bom_keys    = list(bom_dict.keys())
        _excel_styles = comp_df[style_col].astype(str).str.strip().str.upper().unique()
        _matched   = [s for s in _excel_styles if any(_styles_match(s, b) for b in _bom_keys)]
        _unmatched = [s for s in _excel_styles if not any(_styles_match(s, b) for b in _bom_keys)]
        st.session_state["__matched_styles"]   = _matched
        st.session_state["__unmatched_styles"] = _unmatched
        st.session_state["__match_hash"]       = _match_sig
    if st.session_state.get("__matched_styles"):
        render_info_banner(f"Matched styles: {', '.join(st.session_state['__matched_styles'])}")
    if st.session_state.get("__unmatched_styles"):
        render_warn_banner(f"No BOM found for style(s): {', '.join(st.session_state['__unmatched_styles'])} — upload the matching PDF(s)")

    # ── Quick Look — Per Style Settings (always-visible cards, no open/close) ──
    render_divider()
    st.markdown("""<div class="cx-meta">Quick Look — Per Style Settings</div>""", unsafe_allow_html=True)

    quick_display_fields = [f for f in QUICK_SETTING_FIELDS if show_hangtag_rfid or f != "hangtag_rfid"]

    # Pagination — 10 per page, two columns, no view toggle needed here
    CMP_PER_PAGE = 10
    total_cmp_pages = max(1, -(-len(page_style_keys) // CMP_PER_PAGE))
    cmp_page_key = "cmp_ql_page"
    cmp_page = max(0, min(st.session_state.get(cmp_page_key, 0), total_cmp_pages - 1))
    st.session_state[cmp_page_key] = cmp_page

    cmp_page_style_keys = page_style_keys[cmp_page * CMP_PER_PAGE: (cmp_page + 1) * CMP_PER_PAGE]

    # Two-column grid for the cards
    ql_col_a, ql_col_b = st.columns(2, gap="medium")
    ql_cols = [ql_col_a, ql_col_b]

    for idx, style_key in enumerate(cmp_page_style_keys):
        picks = label_selections.get(style_key, {})
        style_colors = _colors_for_style(comp_df, style_col, color_col, style_key)
        excel_match_count = int(comp_df[style_col].astype(str).str.strip().str.upper()
                                .eq(style_key.strip().upper()).sum())
        _, matched_bom = _find_matching_bom(style_key, bom_dict)
        bom_loaded = matched_bom is not None
        accent = "#3fd2a0" if bom_loaded else "#eb5b63"
        bom_bg    = "#eaf9f0" if bom_loaded else "#ffeef0"
        bom_bdr   = "#8fd9b3" if bom_loaded else "#f3a2aa"
        bom_fg    = "#188d5a" if bom_loaded else "#b33844"
        bom_label = "BOM Loaded" if bom_loaded else "No BOM"

        # Infer material from first matched row
        matched_rows = comp_df[comp_df[style_col].astype(str).str.strip().str.upper() == style_key.strip().upper()]
        material_val = "N/A"
        if not matched_rows.empty:
            material_val = _infer_material_from_row(matched_rows.iloc[0], comp_df.columns)

        def _chip(label, val, key=None):
            v = str(val).strip() if val and str(val).strip() not in ("", "N/A", "nan", "None") else "N/A"
            vc = "#1a2b45" if v != "N/A" else "#b0b8c8"
            bg = "#f1f5f9" if v != "N/A" else "#f8fafc"
            return (
                f"<div style='display:inline-flex;flex-direction:column;padding:5px 9px;"
                f"border-radius:7px;background:{bg};border:1px solid #e2e8f0;"
                f"min-width:90px;margin-bottom:4px;'>"
                f"<span style='font-size:0.57rem;color:#94a3b8;font-weight:700;"
                f"letter-spacing:0.05em;text-transform:uppercase;white-space:nowrap;"
                f"overflow:hidden;text-overflow:ellipsis;'>{escape(label)}</span>"
                f"<span style='font-size:0.76rem;font-weight:600;color:{vc};"
                f"margin-top:1px;word-break:break-word;'>{escape(v)}</span>"
                f"</div>"
            )

        # Build all field chips
        fields_html = ""
        # ── Header info chips ──────────────────────────────────────────────
        fields_html += _chip("Colors", str(len(style_colors)))
        fields_html += _chip("Excel Rows", str(excel_match_count))
        fields_html += _chip("Material", material_val)
        # ── Settings chips — all QUICK_SETTING_FIELDS ──────────────────────
        for f in quick_display_fields:
            fields_html += _chip(QUICK_SETTING_LABELS[f], picks.get(f, "N/A"))

        card_html = (
            f"<div style='border-left:4px solid {accent};border-radius:10px;"
            f"padding:14px 16px 12px;background:#fff;"
            f"box-shadow:0 1px 6px rgba(0,0,0,0.08);margin-bottom:10px;'>"
            # Title row
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"margin-bottom:10px;'>"
            f"<span style='font-size:1rem;font-weight:800;color:#1a2b45;"
            f"letter-spacing:-0.01em;'>{escape(style_key)}</span>"
            f"<span style='font-size:0.68rem;font-weight:700;padding:3px 10px;"
            f"border-radius:999px;background:{bom_bg};border:1px solid {bom_bdr};"
            f"color:{bom_fg};white-space:nowrap;'>{bom_label}</span>"
            f"</div>"
            # All chips
            f"<div style='display:flex;flex-wrap:wrap;gap:5px;'>"
            f"{fields_html}"
            f"</div>"
            f"</div>"
        )

        with ql_cols[idx % 2]:
            st.markdown(card_html, unsafe_allow_html=True)

    # ── Pagination BELOW the card deck ─────────────────────────────────────────
    render_pagination(cmp_page_key, cmp_page, total_cmp_pages, key_suffix="cmp_ql", show_page_text=True)

    render_divider()
    st.markdown("""<div class="cx-meta">Run Validation</div>""", unsafe_allow_html=True)
    run_col1, run_col2 = st.columns(2)
    with run_col1:
        st.markdown(
            """
            <div class="cx-run-card">
              <div class="cx-run-title">Quick Trim (Planning)</div>
              <div class="cx-run-sub">Fast run using BOM extraction only. Existed NG from Planning.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        run_quick = st.button("\u25b6 Quick Trim (Planning)", key="run_quick", type="primary", use_container_width=True)
    with run_col2:
        st.markdown(
            """
            <div class="cx-run-card">
              <div class="cx-run-title">Trim (Purchasing)</div>
              <div class="cx-run-sub">Run from the scratch for Purchasing Order.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        run_full = st.button("\u25b6 Trim (Purchasing)", key="run_full", type="primary", use_container_width=True)

    def _execute_validation(use_settings: bool):
        rename_map = {style_col: "Buyer Style Number", color_col: "Color/Option"}
        renamed_df = comp_df.rename(columns=rename_map)
        label_sels = st.session_state.get("label_selections", {}) if use_settings else {}
        result_parts = []
        for style_val, group_df in renamed_df.groupby("Buyer Style Number", sort=False):
            style_str = str(style_val).strip().upper()
            matched_bom_key, matched_bom = _find_matching_bom(style_str, bom_dict)
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
            combined = combined.rename(columns=QUICK_COLUMN_REMAP)
            original_cols = [c for c in combined.columns if c not in NEW_COLUMNS and c not in QUICK_COLUMNS
                             and c not in QUICK_COLUMN_REMAP.values()]
            keep = original_cols + [c for c in QUICK_COLUMNS if c in combined.columns]
            combined = combined[keep]

        status_scan_cols = [
            c for c in (NEW_COLUMNS + QUICK_COLUMNS)
            if c in combined.columns and c != "Validation Status"
            and (show_hangtag_rfid or c not in HANGTAG_RFID_OUTPUT_COLS)
        ]
        if status_scan_cols:
            def _normalize_status(row):
                raw_status = str(row.get("Validation Status", "")).strip().lower()
                if ("error" in raw_status) or ("no match" in raw_status) or ("no bom loaded" in raw_status):
                    return "\u274c Error: No match"
                has_na = any(str(row.get(col, "")).strip().upper() == "N/A" for col in status_scan_cols)
                return "\u26a0\ufe0f Partial" if has_na else "\u2705 Validated"
            combined["Validation Status"] = combined.apply(_normalize_status, axis=1)
        if not show_hangtag_rfid:
            combined = combined.drop(columns=list(HANGTAG_RFID_OUTPUT_COLS), errors="ignore")

        _skip_fill_cols = {"Validation Status"}
        for _col in combined.columns:
            if _col in _skip_fill_cols:
                continue
            combined[_col] = combined[_col].apply(
                lambda v: "N/A"
                if (
                    v is None
                    or (isinstance(v, float) and pd.isna(v))
                    or str(v).strip() in ("", "nan", "None", "NaN")
                )
                else v
            )
        st.session_state["validation_result"] = combined
        st.session_state["validation_mode"]   = "Trim (Purchasing)" if use_settings else "Quick Trim (Planning)"

    if run_quick:
        with st.spinner("Running Quick Trim (Planning)..."):
            _execute_validation(use_settings=False)
        st.session_state["post_validation_prompt"] = True
        st.rerun(scope="app")

    if run_full:
        with st.spinner("Running Trim (Purchasing)..."):
            _execute_validation(use_settings=True)
        st.session_state["post_validation_prompt"] = True
        st.rerun(scope="app")


def render_results():
    if "validation_result" not in st.session_state:
        render_info_banner("Run validation first to see results here.")
        return
    res  = st.session_state["validation_result"]
    mode = st.session_state.get("validation_mode", "")

    _xls_hash = str(id(res)) + str(res.shape)
    if st.session_state.get("__xls_hash") != _xls_hash:
        st.session_state["__xls_cache"] = export_to_excel(
            result_df=res,
            original_df=st.session_state.get("comparison_raw", pd.DataFrame())
        )
        st.session_state["__xls_hash"] = _xls_hash
    xls = st.session_state["__xls_cache"]
    st.markdown(
        "<div class='cx-results-title-wrap'><h2 class='cx-title'>Results & Export</h2></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='cx-results-gap'></div>", unsafe_allow_html=True)
    if mode:
        mode_class = "full" if mode == "Trim (Purchasing)" else "quick"
        st.markdown(
            f"""<div class="cx-meta cx-summary-row">
            <span>Validation Summary</span>
            <span class="cx-mode-badge {mode_class}">Mode: {mode}</span>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("""<div class="cx-meta cx-meta-compact">Validation Summary</div>""", unsafe_allow_html=True)

    status_counts = res["Validation Status"].value_counts(dropna=False).to_dict() if "Validation Status" in res.columns else {}
    ok      = status_counts.get("\u2705 Validated", 0)
    partial = status_counts.get("\u26a0\ufe0f Partial", 0)
    err     = sum(v for k, v in status_counts.items() if str(k).startswith("\u274c"))
    render_validation_summary(ok, partial, err, len(res))
    render_validation_progress(ok, partial, err, len(res))

    label_selections  = st.session_state.get("label_selections", {})
    show_hangtag_rfid = bool(st.session_state.get("show_hangtag_rfid", False))

    # FIX 1: View toggle — does NOT close open styles
    res_view_mode = render_view_toggle(
        "results_view_mode",
        default="Grid",
        label="",
        clear_state_keys=None,  # FIX: don't clear selected style
    )

    style_col_name = "Buyer Style Number" if "Buyer Style Number" in res.columns else None
    color_col_name = "Color/Option" if "Color/Option" in res.columns else None

    _sg_cache_key = "__style_groups_cache"
    _sg_hash_key  = "__style_groups_hash"
    _res_hash = str(len(res)) + str(list(res.columns)) + str(res.shape)
    if st.session_state.get(_sg_hash_key) != _res_hash or _sg_cache_key not in st.session_state:
        style_groups = []
        if style_col_name:
            for style_key, grp in res.groupby(style_col_name, sort=False):
                g = grp.copy()
                c_ok, c_partial, c_err = _status_counts(g)
                total_colors = int(len(g[color_col_name].dropna().astype(str).unique())) if color_col_name and color_col_name in g.columns else int(len(g))
                style_groups.append((str(style_key), g, c_ok, c_partial, c_err, total_colors))
        else:
            c_ok, c_partial, c_err = _status_counts(res)
            style_groups.append(("N/A", res.copy(), c_ok, c_partial, c_err, int(len(res))))
        st.session_state[_sg_cache_key] = style_groups
        st.session_state[_sg_hash_key]  = _res_hash
    else:
        style_groups = st.session_state[_sg_cache_key]

    total_result_styles = len(style_groups)

    per_page = RESULTS_PER_PAGE_LIST if res_view_mode == "List" else (RESULTS_PER_PAGE_TILE if res_view_mode == "Tile" else RESULTS_PER_PAGE_GRID)
    total_res_pages = max(1, -(-total_result_styles // per_page))

    res_page_key = "results_page"
    res_page = max(0, min(st.session_state.get(res_page_key, 0), total_res_pages - 1))
    st.session_state[res_page_key] = res_page

    page_style_groups = style_groups[res_page * per_page: (res_page + 1) * per_page]

    # ── FIX 4 (restored): column count follows view mode ──────────────────────
    res_col_count = 1 if res_view_mode == "List" else (3 if res_view_mode == "Tile" else 2)
    res_cols = st.columns(res_col_count)

    if "results_selected_style" not in st.session_state:
        st.session_state["results_selected_style"] = None

    selected_style = st.session_state.get("results_selected_style")

    for idx, (style_key, g, c_ok, c_partial, c_err, total_colors) in enumerate(page_style_groups):
        # Global index for numbering
        global_idx = res_page * per_page + idx + 1
        accent = "#eb5b63" if c_err > 0 else ("#f0b429" if c_partial > 0 else "#3fd2a0")
        is_open = selected_style == style_key

        with res_cols[idx % res_col_count]:
            if res_view_mode == "List":
                card_class = "cx-list-row"
                number_badge = f"<span class='cx-index-badge'>{global_idx}</span>"
            else:
                card_class = "cx-style-card"
                number_badge = f"<span style='font-size:0.7rem;color:#9aabbd;font-weight:600;margin-right:6px;'>#{global_idx}</span>"

            st.markdown(
                f"""
                <div class="{card_class}" style="border-left-color:{accent};">
                  <div class="cx-style-id cx-style-id-row">{number_badge}<span>{style_key}</span></div>
                  <div class="cx-chip-row">
                    <span class="cx-chip">No. Colors: {total_colors}</span>
                    <span class="cx-chip">Validated: {c_ok}</span>
                    <span class="cx-chip">Partial: {c_partial}</span>
                    <span class="cx-chip">No Match: {c_err}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            button_label = "Close style" if is_open else "Open style"
            if st.button(button_label, key=f"open_style_{style_key}", type="tertiary", use_container_width=True):
                st.session_state["results_selected_style"] = None if is_open else style_key
                st.rerun()

    # ── Open style detail — render below card grid ─────────────────────────────
    selected_style = st.session_state.get("results_selected_style")
    selected_group = next((x for x in page_style_groups if x[0] == selected_style), None)
    if selected_group is not None:
        style_key, g, _, _, _, _ = selected_group
        st.markdown(f"""<div class="cx-meta" style="margin-top:1rem;">Style Details — {style_key}</div>""", unsafe_allow_html=True)
        picks = label_selections.get(style_key, {})
        if not picks:
            style_upper = style_key.strip().upper()
            for k, v in label_selections.items():
                ku = str(k).strip().upper()
                if style_upper == ku or style_upper in ku or ku in style_upper:
                    picks = v
                    break

        detail_col_count = 1 if res_view_mode == "List" else (3 if res_view_mode == "Tile" else 2)

        # ── Restored original detail card builder (inline) ────────────────────
        _DETAIL_GROUPS_LOCAL = [
            ("Label",   [
                ("Main Label",          "Main Label"),
                ("Main Label Color",    "Main Label Color"),
                ("Main Label Supplier", "Main Label Supplier"),
                ("Care Label",          "Care Label"),
                ("Care Label Color",    "Care Label Color"),
                ("Care Supplier",       "Care Supplier"),
            ]),
            ("Hangtag", [
                ("Hangtag",             "Hangtag"),
                ("Hangtag Supplier",    "Hangtag Supplier"),
                ("Hangtag 2",           "Hangtag 2"),
                ("Hangtag 3",           "Hangtag3"),
                ("RFID w/o MSRP",       "RFID w/o MSRP"),
                ("RFID w/o MSRP Sup",   "RFID w/o MSRP Supplier"),
            ]),
            ("Sticker", [
                ("RFID Sticker",        "RFID Stickers"),
                ("RFID Sticker Sup",    "RFID Stickers Supplier"),
                ("UPC Bag Sticker",     "UPC Bag Sticker (Polybag)"),
                ("UPC Supplier",        "UPC Supplier"),
            ]),
            ("Content", [
                ("Content Code",        "Content Code"),
                ("TP FC",               "TP FC"),
                ("Care Code",           "Care Code"),
            ]),
        ]

        def _fv(row, col):
            v = str(row.get(col, "")).strip()
            return v if v and v.lower() not in ("nan", "none", "") else "N/A"

        def _vc(v):
            return "#b0b8c8" if v == "N/A" else "#1a2b45"

        def _build_detail_card(row, card_class, accent, color_val, material_val, status_raw, res_cols_local):
            if "✅" in status_raw:
                sbg, sfg = "#d1fae5", "#065f46"
            elif "⚠️" in status_raw:
                sbg, sfg = "#fef9c3", "#854d0e"
            else:
                sbg, sfg = "#fee2e2", "#991b1b"

            html = (
                f"<div class='{card_class}' style='border-top:3px solid {accent};border-radius:10px;"
                f"padding:14px 16px 10px;margin-bottom:10px;background:#fff;"
                f"box-shadow:0 1px 4px rgba(0,0,0,0.07);'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;'>"
                f"<div style='font-size:1rem;font-weight:700;color:#1a2b45;'>{escape(color_val)}</div>"
                f"<span style='font-size:0.7rem;font-weight:700;padding:3px 10px;border-radius:999px;"
                f"background:{sbg};color:{sfg};'>{escape(status_raw)}</span>"
                f"</div>"
                f"<div style='font-size:0.75rem;color:#6b7a99;margin-bottom:10px;'>"
                f"<span style='font-weight:600;color:#4a5568;'>Material:</span> {escape(material_val)}</div>"
            )

            for grp_label, fields in _DETAIL_GROUPS_LOCAL:
                avail = [(lbl, col) for lbl, col in fields if col in res_cols_local]
                if not avail:
                    continue
                vals = [(lbl, _fv(row, col)) for lbl, col in avail]
                if not any(v != "N/A" for _, v in vals):
                    continue
                html += (
                    f"<div style='margin-bottom:8px;'>"
                    f"<div style='font-size:0.62rem;font-weight:800;letter-spacing:0.08em;"
                    f"text-transform:uppercase;color:#94a3b8;margin-bottom:4px;'>{grp_label}</div>"
                    f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>"
                )
                for lbl, v in vals:
                    bg = "#f1f5f9" if v != "N/A" else "#f8fafc"
                    html += (
                        f"<div style='display:inline-flex;flex-direction:column;padding:4px 8px;"
                        f"border-radius:6px;background:{bg};border:1px solid #e2e8f0;min-width:80px;'>"
                        f"<span style='font-size:0.58rem;color:#94a3b8;font-weight:600;"
                        f"letter-spacing:0.04em;text-transform:uppercase;'>{escape(lbl)}</span>"
                        f"<span style='font-size:0.75rem;font-weight:600;color:{_vc(v)};"
                        f"margin-top:1px;word-break:break-word;'>{escape(v)}</span>"
                        f"</div>"
                    )
                html += "</div></div>"
            html += "</div>"
            return html

        col_html = [""] * detail_col_count
        res_cols_set = set(res.columns)
        for d_idx, (_, row) in enumerate(g.iterrows()):
            color_val    = str(row.get(color_col_name, "N/A")) if color_col_name else "N/A"
            material_val = _infer_material_from_row(row, res.columns)
            status_raw   = str(row.get("Validation Status", "Parsed"))
            _, _, _, lbl  = _status_style(status_raw)
            accent_d = _status_accent_color(lbl)
            card_class_d = "cx-list-row" if res_view_mode == "List" else "cx-style-card"
            col_html[d_idx % detail_col_count] += _build_detail_card(
                row, card_class_d, accent_d, color_val, material_val, status_raw, res_cols_set
            )

        detail_cols = st.columns(detail_col_count)
        for ci, html in enumerate(col_html):
            if html:
                with detail_cols[ci]:
                    st.markdown(html, unsafe_allow_html=True)

    # ── Pagination BELOW the per-style card deck ───────────────────────────────
    render_pagination(res_page_key, res_page, total_res_pages, key_suffix="res", show_page_text=True)

    with st.container(key="results_actions_bottom"):
        c_csv, c_xls = st.columns([1, 1], gap="small")
        with c_csv:
            st.download_button("\u2b73 Export CSV", data=export_to_csv(res), file_name="validated_bom.csv", mime="text/csv", use_container_width=True, type="secondary")
        with c_xls:
            st.download_button("\u2b73 Export Excel", data=xls, file_name="validated_bom.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")
    render_divider()


def main():
    inject_theme()
    render_sidebar()
    tab_labels = [TAB_PDF, TAB_COMPARE, TAB_RESULTS]
    default_tab = st.session_state.pop("next_active_tab", None)
    default_tab = default_tab if default_tab in tab_labels else None
    tab1, tab2, tab3 = st.tabs(tab_labels, default=default_tab)
    with tab1:
        render_pdf_tab()
    with tab2:
        render_comparison_tab()
    with tab3:
        render_results()

if __name__ == "__main__":
    main()