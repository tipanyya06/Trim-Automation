import hashlib
import io as _io
import time
from html import escape
import pandas as pd
import streamlit as st

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from parsers.pdf_parser import parse_bom_pdf
from validators.matcher import auto_detect_columns, get_product_type
from validators.filler import validate_and_fill, NEW_COLUMNS, QUICK_COLUMNS, QUICK_COLUMN_REMAP
from ui_styles import THEME_CSS


st.set_page_config(
    page_title="Columbia BOM Automation",
    page_icon="\U0001f9e2",
    layout="wide",
    initial_sidebar_state="expanded"
)

STYLES_PER_PAGE = 5
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

def render_view_toggle(state_key, default="Grid", label="View", clear_state_keys=None, icon_only=False, right_align=False):
    options = ["Grid", "Tile", "List"]
    display_labels = {"Grid": "\u25a6 Grid", "Tile": "\u25a4 Tile", "List": "\u2630 List"}
    icon_labels = {"Grid": "\u25a6", "Tile": "\u25a4", "List": "\u2630"}
    current = st.session_state.get(state_key, default)
    if current not in options:
        current = default
        st.session_state[state_key] = default
    if label:
        st.markdown(f"<div class='cx-meta'>{label}</div>", unsafe_allow_html=True)
    st.markdown("<div class='cx-view-toggle'></div>", unsafe_allow_html=True)
    if right_align:
        cols = st.columns([9, 1, 1, 1])[1:]
    else:
        cols = st.columns(3)
    for i, opt in enumerate(options):
        with cols[i]:
            btn_label = icon_labels.get(opt, opt) if icon_only else display_labels.get(opt, opt)
            gray_only_toggles = {"loaded_boms_view", "results_view_mode"}
            btn_type = "secondary" if state_key in gray_only_toggles else ("primary" if current == opt else "secondary")
            if st.button(btn_label, key=f"{state_key}_{opt}", type=btn_type, use_container_width=not icon_only):
                st.session_state[state_key] = opt
                for k in (clear_state_keys or []):
                    st.session_state[k] = None
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
            st.rerun()
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

    # Keep Costing BOM focused on the key business columns.
    if active_sec == "costing_detail" and not view_df.empty:
        preferred_cols = ["component", "material", "description", "supplier", "country of origin"]
        normalized = {str(c).strip().lower(): c for c in view_df.columns}
        keep = [normalized[c] for c in preferred_cols if c in normalized]
        if keep:
            view_df = view_df[keep]
    elif active_sec == "color_bom" and not view_df.empty:
        # Hide "line slot" helper columns in Color BOM display.
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


@st.dialog("Confirm Validation", width="small", dismissible=False)
def show_validation_confirm_dialog(mode_key):
    is_full = str(mode_key).lower() == "full"
    label = "Trim (Purchasing)" if is_full else "Quick Trim (Planning)"
    detail = "Use configured per-style settings and run full validation." if is_full else "Run fast validation from BOM extraction only."
    st.markdown(f"<div class='cx-meta'>{label}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:0.86rem;color:#4f688c;margin-bottom:0.6rem;'>{detail}</div>", unsafe_allow_html=True)
    c_cancel, c_confirm = st.columns(2)
    with c_cancel:
        if st.button("Cancel", key=f"cancel_run_{mode_key}", use_container_width=True):
            st.session_state["pending_validation_run"] = None
            st.rerun()
    with c_confirm:
        if st.button("Confirm", key=f"confirm_run_{mode_key}", type="primary", use_container_width=True):
            st.session_state["validation_to_execute"] = mode_key
            st.session_state["pending_validation_run"] = None
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
    st.rerun()


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
            # Refresh sidebar/status badges immediately after successful parse.
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
    view_mode = render_view_toggle(
        "loaded_boms_view",
        default="Grid",
        label="Loaded BOM View",
        clear_state_keys=["inspect_popup_style"],
        icon_only=False,
        right_align=False,
    )

    col_count = 1 if view_mode == "List" else (3 if view_mode == "Tile" else 2)
    deck_cols = st.columns(col_count)
    for idx, row in enumerate(summary_rows):
        style = row["Style"]
        status = row.get("Status", _style_validation_status(style))
        bg, border, fg, label = _status_style(status)
        accent = _status_accent_color(label)
        list_index_badge = (
            f"<span class='cx-index-badge'>{idx + 1}</span>"
            if view_mode == "List" else ""
        )
        card_height_class = " cx-bom-card-compact" if view_mode != "List" else ""
        with deck_cols[idx % col_count]:
            card_class = "cx-list-row" if view_mode == "List" else "cx-style-card"
            st.markdown(
                f"""
                <div class="{card_class}{card_height_class}" style="border-left-color:{accent};">
                  <div class="cx-style-top">
                    <div>
                      <div class="cx-style-id cx-style-id-row">{list_index_badge}<span>{style}</span></div>
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
                      <span><span class="cx-count-num">&#8862; {row['Sections']}</span> <span class="cx-count-label">Sections</span></span>
                      <span><span class="cx-count-num">&#9671; {row['Colorways']}</span> <span class="cx-count-label">Colorways</span></span>
                    </div>
                    <div class="cx-footer-hint">Click to inspect</div>
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
            lambda v: "PT BSN" if isinstance(v, str) and v.strip().lower() == "bao shen" else v
        )
    return out


def render_comparison_tab():
    render_section_header("BOM Comparison & Validation")
    if st.session_state.get("post_validation_prompt"):
        show_validation_complete_dialog()
        return

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
        st.session_state["comparison_upload_bytes"] = raw_bytes
        st.session_state["comparison_upload_name"] = comp_file.name
        st.session_state["comparison_upload_size"] = len(raw_bytes)
    else:
        cached_bytes = st.session_state.get("comparison_upload_bytes")
        cached_name = st.session_state.get("comparison_upload_name")
        if not cached_bytes or not cached_name:
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
        comp_df = _normalize_supplier_names(_read_comparison_file(comp_file))
        st.session_state["comparison_raw"] = comp_df
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        return

    st.markdown("<div style='height:0;'></div>", unsafe_allow_html=True)
    mapping_card = st.container(border=True, key="column_mapping_card")
    with mapping_card:
        st.markdown("""<div class="cx-meta" style="margin-bottom:0.35rem;">Column Mapping</div>""", unsafe_allow_html=True)
        auto = auto_detect_columns(comp_df)
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
        show_hangtag_rfid = "buyer style" in str(style_col).strip().lower()
        st.session_state["show_hangtag_rfid"] = show_hangtag_rfid

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

    render_pagination("label_map_page", lm_page, total_lm_pages, key_suffix="lm", show_page_text=False)
    st.markdown("<div style='height:0.15rem;'></div>", unsafe_allow_html=True)

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
                def _pick_option(options, *keywords, fallback=None):
                    for kw in keywords:
                        kw_l = str(kw).lower()
                        for opt in options:
                            if kw_l in str(opt).lower():
                                return opt
                    return fallback if fallback is not None else (options[0] if options else "N/A")

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

                # Row 4: Care Label / Hangtag (RFID) / RFID Sticker
                if show_hangtag_rfid:
                    r4a, r4b, r4c = st.columns(3)
                else:
                    r4a, r4c = st.columns(2)
                with r4a:
                    care_sel = st.selectbox("Care Label", options=components,
                        index=components.index(_best(saved.get("care_label",""), ["Label 1","Care Label","Label1"])) if _best(saved.get("care_label",""), ["Label 1","Care Label","Label1"]) in components else 0,
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

                # Row 5: UPC / Content Code & Care Code (auto-filled info)
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

    quick_display_fields = [f for f in QUICK_SETTING_FIELDS if show_hangtag_rfid or f != "hangtag_rfid"]
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
        for f in quick_display_fields:
            val = str(picks.get(f, "N/A")).strip() or "N/A"
            chips.append(f"<span class='cx-chip'>{QUICK_SETTING_LABELS[f]}: {val}</span>")
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
        matched   = [s for s in excel_styles if any(_styles_match(s, b) for b in bom_dict)]
        unmatched = [s for s in excel_styles if s not in matched]
        if matched:
            render_info_banner(f"Matched styles: {', '.join(matched)}")
        if unmatched:
            render_warn_banner(f"No BOM found for style(s): {', '.join(unmatched)} \u2014 upload the matching PDF(s)")


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
        run_quick = st.button(
            "\u25b6 Quick Trim (Planning)",
            key="run_quick",
            type="primary",
            use_container_width=True,
        )
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
        run_full = st.button(
            "\u25b6 Trim (Purchasing)",
            key="run_full",
            type="primary",
            use_container_width=True,
        )

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
            # Remap Option 2 internal column names → Option 1 output names
            combined = combined.rename(columns=QUICK_COLUMN_REMAP)
            # Keep original input columns + Option 1 output columns only
            original_cols = [c for c in combined.columns if c not in NEW_COLUMNS and c not in QUICK_COLUMNS
                             and c not in QUICK_COLUMN_REMAP.values()]
            keep = original_cols + [c for c in QUICK_COLUMNS if c in combined.columns]
            combined = combined[keep]

        # Business rule for status:
        # - Validated: no "N/A"
        # - Partial: has at least one "N/A"
        # - Error: no match / existing error
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

        st.session_state["validation_result"] = combined
        st.session_state["validation_mode"]   = "Trim (Purchasing)" if use_settings else "Quick Trim (Planning)"

    if run_quick:
        st.session_state["pending_validation_run"] = "quick"
        st.rerun()

    if run_full:
        st.session_state["pending_validation_run"] = "full"
        st.rerun()

    pending_mode = st.session_state.get("pending_validation_run")
    if pending_mode:
        show_validation_confirm_dialog(pending_mode)
        return

    execute_mode = st.session_state.pop("validation_to_execute", None)
    if execute_mode:
        if execute_mode == "full":
            with st.spinner("Running Trim (Purchasing)..."):
                _execute_validation(use_settings=True)
        else:
            with st.spinner("Running Quick Trim (Planning)..."):
                _execute_validation(use_settings=False)
        st.session_state["post_validation_prompt"] = True
        st.rerun()

def render_results():
    # Change 8: now called as its own tab in main()
    if "validation_result" not in st.session_state:
        render_info_banner("Run validation first to see results here.")
        return
    res  = st.session_state["validation_result"]
    mode = st.session_state.get("validation_mode", "")
    xls = export_to_excel(result_df=res, original_df=st.session_state.get("comparison_raw", pd.DataFrame()))
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
    label_selections = st.session_state.get("label_selections", {})
    show_hangtag_rfid = bool(st.session_state.get("show_hangtag_rfid", False))
    quick_display_fields = [f for f in QUICK_SETTING_FIELDS if show_hangtag_rfid or f != "hangtag_rfid"]
    res_view_mode = render_view_toggle(
        "results_view_mode",
        default="Grid",
        label="",
        clear_state_keys=["inspect_popup_style"],
    )
    res_col_count = 1 if res_view_mode == "List" else (3 if res_view_mode == "Tile" else 2)
    res_cols = st.columns(res_col_count)
    style_col_name = "Buyer Style Number" if "Buyer Style Number" in res.columns else None
    color_col_name = "Color/Option" if "Color/Option" in res.columns else None

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

    if "results_selected_style" not in st.session_state:
        st.session_state["results_selected_style"] = None

    selected_style = st.session_state.get("results_selected_style")
    for idx, (style_key, g, c_ok, c_partial, c_err, total_colors) in enumerate(style_groups):
        accent = "#eb5b63" if c_err > 0 else ("#f0b429" if c_partial > 0 else "#3fd2a0")
        with res_cols[idx % res_col_count]:
            card_class = "cx-list-row" if res_view_mode == "List" else "cx-style-card"
            st.markdown(
                f"""
                <div class="{card_class}" style="border-left-color:{accent};">
                  <div class="cx-style-id">{style_key}</div>
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
            is_open = selected_style == style_key
            button_label = "Close style" if is_open else "Open style"
            if st.button(button_label, key=f"open_style_{style_key}", type="tertiary", use_container_width=True):
                st.session_state["results_selected_style"] = None if is_open else style_key
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
            for f in quick_display_fields:
                val = str(picks.get(f, "N/A")).strip() or "N/A"
                chips.append(f"<span class='cx-chip'>{QUICK_SETTING_LABELS[f]}: {val}</span>")
            st.markdown(
                f"""
                <div class="cx-style-card" style="border-left-color:{accent};">
                  <div class="cx-style-name">{color_val}</div>
                  <div class="cx-chip-row">{''.join(chips)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
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
    # Change 8: 3rd tab for Results & Export
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



