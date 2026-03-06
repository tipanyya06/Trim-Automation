"""
tabs/utils.py
All shared UI helpers, render utilities, dialogs, and card builders
used across every tab module. Import everything from here.
"""
import time
from html import escape

import pandas as pd
import streamlit as st

from ui_styles import THEME_CSS

# ── Constants ──────────────────────────────────────────────────────────────────
STYLES_PER_PAGE       = 10
RESULTS_PER_PAGE_GRID = 10
RESULTS_PER_PAGE_TILE = 15
RESULTS_PER_PAGE_LIST = 10

TAB_PDF     = "\U0001f4c4 PDF Extraction"
TAB_COMPARE = "\U0001f50d BOM Comparison & Validation"
TAB_RESULTS = "\U0001f4ca Results & Export"
TAB_QA      = "\U0001f9ea QA Comparison"

QUICK_SETTING_FIELDS = [
    "main_label", "add_main_label", "hangtag", "hangtag2", "hangtag3", "micropack",
    "size_label", "size_sticker", "care_label", "hangtag_rfid", "rfid_sticker",
    "upc_sticker", "rfid_no_msrp", "tp_status", "tp_date", "product_status", "remarks",
]
QUICK_SETTING_LABELS = {
    "main_label":     "Main Label",
    "add_main_label": "Additional Main Label",
    "hangtag":        "Hangtag",
    "hangtag2":       "Hangtag2",
    "hangtag3":       "Hangtag3",
    "micropack":      "Micropack Sticker-Gloves",
    "size_label":     "Size Label",
    "size_sticker":   "Size Sticker-Gloves",
    "care_label":     "Care Label",
    "hangtag_rfid":   "Hangtag (RFID)",
    "rfid_sticker":   "RFID Sticker",
    "upc_sticker":    "UPC Sticker (Polybag)",
    "rfid_no_msrp":   "RFID w/o MSRP",
    "tp_status":      "TP Status",
    "tp_date":        "TP Date",
    "product_status": "Product Status",
    "remarks":        "Remarks",
}
HANGTAG_RFID_COL          = "Hangtag (RFID)"
HANGTAG_RFID_SUPPLIER_COL = "Hangtag (RFID) Supplier"
HANGTAG_RFID_OUTPUT_COLS  = {HANGTAG_RFID_COL, HANGTAG_RFID_SUPPLIER_COL}


# ── Theme ──────────────────────────────────────────────────────────────────────

def inject_theme():
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)


# ── Layout primitives ──────────────────────────────────────────────────────────

def render_section_header(title, subtitle="", compact=False):
    sub_class = "cx-subtitle tight" if compact else "cx-subtitle"
    sub = f"<div class='{sub_class}'>{subtitle}</div>" if subtitle else ""
    st.markdown(f"<h2 class='cx-title'>{title}</h2>{sub}", unsafe_allow_html=True)


def render_divider():
    st.markdown("<div class='cx-divider'></div>", unsafe_allow_html=True)


def render_info_banner(msg):
    st.markdown(f"<div class='cx-banner'>{msg}</div>", unsafe_allow_html=True)


def render_warn_banner(msg):
    st.markdown(f"<div class='cx-banner warn'>{msg}</div>", unsafe_allow_html=True)


def render_validation_summary(ok, partial, err, total):
    st.markdown(
        f"""<div class="cx-stats">
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--green);">{ok}</div><div class="cx-stat-label">Validated</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--amber);">{partial}</div><div class="cx-stat-label">Partial</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--red);">{err}</div><div class="cx-stat-label">No Match</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:#334e75;">{total}</div><div class="cx-stat-label">Total Rows</div></div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_validation_progress(ok, partial, err, total):
    s = max(int(total or 0), 1)
    ow = round(ok / s * 100, 2)
    pw = round(partial / s * 100, 2)
    ew = max(0.0, round(100.0 - ow - pw, 2))
    pct = int(round(ok / s * 100))
    st.markdown(
        f"""<div class="cx-progress-card">
          <div class="cx-progress-head"><span>Validation Progress</span><span class="pct">{pct}% Complete</span></div>
          <div class="cx-progress-track">
            <div class="cx-progress-seg ok" style="width:{ow}%;"></div>
            <div class="cx-progress-seg partial" style="width:{pw}%;"></div>
            <div class="cx-progress-seg err" style="width:{ew}%;"></div>
          </div>
          <div class="cx-progress-legend">
            <span><span class="cx-progress-dot" style="background:#10b981;"></span>Validated</span>
            <span><span class="cx-progress-dot" style="background:#f0b429;"></span>Partial</span>
            <span><span class="cx-progress-dot" style="background:#ef4444;"></span>Errors</span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def render_pagination(page_key, current_page, total_pages, key_suffix="", show_page_text=True):
    if total_pages <= 1:
        return current_page
    sfx = key_suffix or page_key
    col_prev, col_pills, col_next = st.columns([1, 6, 1])
    with col_prev:
        if st.button("\u2190 Prev", key=f"{sfx}_prev", disabled=current_page == 0):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with col_pills:
        start = max(0, current_page - 3)
        end   = min(total_pages, current_page + 4)
        pills = "<div style='display:flex;gap:6px;justify-content:center;align-items:center;'>"
        for p in range(start, end):
            cls = "page-pill page-pill-active" if p == current_page else "page-pill"
            pills += f"<div class='{cls}'>{p + 1}</div>"
        pills += "</div>"
        st.markdown(pills, unsafe_allow_html=True)
    with col_next:
        if st.button("Next \u2192", key=f"{sfx}_next", disabled=current_page >= total_pages - 1):
            st.session_state[page_key] = current_page + 1
            st.rerun()
    if show_page_text:
        st.markdown(
            f"<div style='text-align:center;font-size:0.7rem;color:#5a6080;margin-top:2px;'>"
            f"Page {current_page + 1} of {total_pages}</div>",
            unsafe_allow_html=True,
        )
    return st.session_state.get(page_key, current_page)


def render_view_toggle(state_key, default="Grid", label="", **_kwargs):
    """Segmented view toggle. Does NOT clear open styles when switching."""
    options = ["Grid", "Tile", "List"]
    current = st.session_state.get(state_key, default)
    if current not in options:
        current = default
        st.session_state[state_key] = current
    if label:
        st.markdown(f"<div class='cx-meta'>{label}</div>", unsafe_allow_html=True)
    seg_key = f"__seg_{state_key}"

    def _on_change():
        chosen = st.session_state.get(seg_key, default)
        if chosen and st.session_state.get(state_key) != chosen:
            st.session_state[state_key] = chosen

    st.segmented_control(
        label="", options=options, default=current,
        key=seg_key, label_visibility="collapsed", on_change=_on_change,
    )
    return st.session_state.get(state_key, default)


# ── Status helpers ─────────────────────────────────────────────────────────────

def _status_style(status):
    t = str(status or "").lower()
    if "error" in t:
        return "#ffeef0", "#f3a2aa", "#b33844", "Error"
    return "#eaf9f0", "#8fd9b3", "#188d5a", "Validated"


def _status_accent_color(label):
    m = {"validated": "#3fd2a0", "partial": "#f0b429", "error": "#eb5b63"}
    return m.get(str(label).lower(), "#4f89f7")


def _style_validation_status(style):
    res = st.session_state.get("validation_result")
    if res is None or res.empty or "Buyer Style Number" not in res.columns:
        return "Validated"
    su = str(style).strip().upper()
    statuses = [
        str(r.get("Validation Status", ""))
        for _, r in res.iterrows()
        if su in str(r.get("Buyer Style Number", "")).strip().upper()
        or str(r.get("Buyer Style Number", "")).strip().upper() in su
    ]
    lowered = [s.lower() for s in statuses]
    if any("error" in s or s.startswith("\u274c") for s in lowered):
        return "Error"
    return "Validated"


def _status_counts(df):
    s = df["Validation Status"].astype(str) if "Validation Status" in df.columns else pd.Series(dtype=str)
    ok  = int(s.str.contains("Validated", case=False, na=False).sum())
    par = int(s.str.contains("Partial",   case=False, na=False).sum())
    return ok, par, int(len(df) - ok - par)


# ── Data helpers ───────────────────────────────────────────────────────────────

def _resolve_style_key(style, bom_dict):
    su = style.strip().upper()
    return next((k for k in bom_dict if su == k.strip().upper()), None)


def _styles_match(left, right):
    l, r = str(left).strip().upper(), str(right).strip().upper()
    return l == r or l in r or r in l


def _find_matching_bom(style_val, bom_dict):
    ss = str(style_val).strip().upper()
    for k, v in bom_dict.items():
        if _styles_match(ss, k):
            return k, v
    return None, None


def _style_color_hint(bom_data):
    meta = bom_data.get("metadata", {}) if isinstance(bom_data, dict) else {}
    for k in ("color", "colorway", "colour", "color_name"):
        v = str(meta.get(k, "")).strip()
        if v:
            return v
    cb = bom_data.get("color_bom") if isinstance(bom_data, dict) else None
    if isinstance(cb, pd.DataFrame) and not cb.empty:
        for c in cb.columns:
            cc = str(c).strip()
            if cc and not cc.lower().startswith(
                ("unnamed", "material", "component", "description", "code", "supplier", "row", "col_")
            ):
                return cc
    return "N/A"


def _infer_material_from_row(row, columns):
    for c in ("Material Name", "Material", "Material Type", "Shell Material", "Fabric", "Body Fabric", "Main Material"):
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
    return st.session_state.get("__style_colors_cache", {}).get(str(style_key).strip().upper(), [])


def _precompute_style_colors(df, style_col, color_col):
    sig = f"{style_col}:{color_col}:{df.shape}"
    if st.session_state.get("__scc_hash") == sig:
        return
    result = {}
    if df is None or style_col not in df.columns or color_col not in df.columns:
        st.session_state.update(__style_colors_cache=result, __scc_hash=sig)
        return
    for s_val, c_val in zip(df[style_col].astype(str).str.strip(), df[color_col].astype(str).str.strip()):
        if not s_val or not c_val or s_val.lower() in ("nan", "none") or c_val.lower() in ("nan", "none"):
            continue
        su = s_val.upper()
        if su not in result:
            result[su] = []
        if c_val not in result[su]:
            result[su].append(c_val)
    st.session_state.update(__style_colors_cache=result, __scc_hash=sig)


# ── Popup table ────────────────────────────────────────────────────────────────

def _render_popup_table(df):
    if df is None or df.empty:
        render_warn_banner("No rows in this section.")
        return
    heads = "".join(f"<th>{escape(str(c))}</th>" for c in df.columns)
    rows  = "".join(
        f"<tr>{''.join(f'<td>{escape(str(v))}</td>' for v in r.tolist())}</tr>"
        for _, r in df.iterrows()
    )
    st.markdown(
        f'<div class="cx-popup-table-wrap"><table class="cx-popup-table">'
        f'<thead><tr>{heads}</tr></thead><tbody>{rows}</tbody></table></div>',
        unsafe_allow_html=True,
    )


# ── Sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<div style="font-size:0.95rem;font-weight:800;color:#2457d6;line-height:1.1;'
            'margin-bottom:0.2rem;letter-spacing:0.08em;">COLUMBIA</div>'
            '<div style="font-size:1.7rem;font-weight:800;color:#0f213f;line-height:1.02;'
            'margin-bottom:0.16rem;letter-spacing:-0.02em;">BOM Automation</div>'
            '<div style="font-size:0.8rem;color:#667d9f;margin-bottom:1.1rem;">Trim &amp; Label Validator</div>',
            unsafe_allow_html=True,
        )
        bom_dict = st.session_state.get("bom_dict", {})
        if bom_dict:
            st.markdown(
                f'<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;'
                f'border-radius:999px;font-size:0.78rem;font-weight:700;margin-bottom:0.7rem;'
                f'background:#eaf8f0;color:#138e59;border:1px solid #98dab8;">'
                f'&#8226; {len(bom_dict)} BOM{"s" if len(bom_dict) > 1 else ""} Loaded</div>',
                unsafe_allow_html=True,
            )
            for style, bom in bom_dict.items():
                meta = bom.get("metadata", {})
                st.markdown(
                    f'<div style="font-size:0.75rem;color:#6d82a1;padding:4px 0;border-bottom:1px solid #d8e1ec;">'
                    f'<span style="color:#3b82f6;font-weight:700;">{style}</span>'
                    f' &nbsp;\xb7&nbsp; {meta.get("season", "\u2014")}'
                    f' &nbsp;\xb7&nbsp; {meta.get("production_lo", "\u2014")}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;'
                'border-radius:999px;font-size:0.78rem;font-weight:700;margin-bottom:0.9rem;'
                'background:#edf2f8;color:#6681a4;border:1px solid #d0dceb;">&#8226; No BOM Loaded</div>',
                unsafe_allow_html=True,
            )
        if st.button("\U0001f5d1 Clear All Data", width="stretch"):
            pdf_k = st.session_state.get("pdf_uploader_key", 0) + 1
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.session_state["pdf_uploader_key"] = pdf_k
            st.rerun(scope="app")
        st.markdown(
            '<div class="cx-side-bottom"><div class="cx-side-steps">'
            '<div class="cx-side-step"><span class="cx-side-step-num">1</span><span>Upload BOM PDFs</span></div>'
            '<div class="cx-side-step"><span class="cx-side-step-num">2</span><span>Upload your Excel/CSV</span></div>'
            '<div class="cx-side-step"><span class="cx-side-step-num">3</span><span>Map columns &amp; configure</span></div>'
            '<div class="cx-side-step"><span class="cx-side-step-num">4</span><span>Export validated output</span></div>'
            '</div></div>',
            unsafe_allow_html=True,
        )


# ── Dialogs ────────────────────────────────────────────────────────────────────

@st.dialog("Duplicate Style Detected", width="large")
def show_conflict_dialog(conflict_key, info, bom_dict, pdf_bytes_store, pdf_hashes):
    style  = info.get("style", conflict_key.split("__")[0])
    reason = info.get("conflict_reason", "already_loaded")
    em     = bom_dict.get(info["existing_key"], {}).get("metadata", {})
    nm     = info["bom_data"].get("metadata", {}) if isinstance(info.get("bom_data"), dict) else {}
    labels = {
        "duplicate_file":     "\u26a0 Exact duplicate file uploaded again",
        "duplicate_in_batch": "\u26a0 Same style uploaded twice in this batch",
    }
    st.markdown(f"**{labels.get(reason, chr(9888)+' Style already loaded')}:** `{style}`")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Existing in session**")
        st.markdown(f"Season: `{em.get('season', '—')}` · LO: `{em.get('production_lo', '—')}`")
    with c2:
        st.markdown(f"**New Upload** — {info['fname']}")
        st.markdown(f"Season: `{nm.get('season', '—')}` · LO: `{nm.get('production_lo', '—')}`")
    st.divider()
    cr, ck = st.columns(2)
    with cr:
        if st.button("\u21ba Replace", type="primary", use_container_width=True):
            ek = info["existing_key"]
            bom_dict[ek] = info["bom_data"]
            pdf_bytes_store[ek] = info["raw_bytes"]
            pdf_hashes[info["fname"]] = info["fhash"]
            st.session_state.update(bom_dict=bom_dict, pdf_bytes_store=pdf_bytes_store, pdf_hashes=pdf_hashes)
            del st.session_state["pending_conflicts"][conflict_key]
            st.rerun()
    with ck:
        if st.button("\u2713 Keep Existing", use_container_width=True):
            pdf_hashes[info["fname"]] = info["fhash"]
            st.session_state["pdf_hashes"] = pdf_hashes
            del st.session_state["pending_conflicts"][conflict_key]
            st.rerun()


@st.dialog("BOM Inspector", width="large")
def show_bom_inspector(style_key, bom_data):
    meta = bom_data.get("metadata", {})
    bg, border, fg, lbl = _status_style(_style_validation_status(style_key))
    st.markdown(
        f'<div class="cx-style-card" style="border-top:3px solid #3fd2a0;">'
        f'<div class="cx-style-top"><div>'
        f'<div class="cx-style-id">{style_key}</div>'
        f'<div class="cx-style-name">{meta.get("design", style_key)}</div>'
        f'</div><div class="cx-status" style="background:{bg};border-color:{border};color:{fg};">{lbl}</div></div>'
        f'<div class="cx-chip-row">'
        f'<span class="cx-chip">Season: {meta.get("season", "N/A")}</span>'
        f'<span class="cx-chip">LO: {meta.get("production_lo", "N/A")}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    section_keys = [
        k for k, v in bom_data.items()
        if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty
    ]
    section_keys = list(section_keys)
    section_keys.append("parsed_pages")
    if not section_keys:
        render_warn_banner("No parsed sections for this BOM.")
        return
    ssk = f"popup_section_{style_key}"
    if ssk not in st.session_state or st.session_state[ssk] not in section_keys:
        st.session_state[ssk] = section_keys[0]
    for i in range(0, len(section_keys), 4):
        cols = st.columns(len(section_keys[i:i+4]))
        for j, sec in enumerate(section_keys[i:i+4]):
            if sec == "parsed_pages":
                label = "Parsed Pages"
            else:
                label = f"{sec.replace('_', ' ').title()} ({len(bom_data.get(sec, pd.DataFrame()))})"
            with cols[j]:
                if st.button(label, key=f"popup_tab_{style_key}_{sec}",
                             type="primary" if st.session_state[ssk] == sec else "secondary",
                             use_container_width=True):
                    st.session_state[ssk] = sec
                    st.rerun()
    active = st.session_state.get(ssk, section_keys[0])
    if active == "parsed_pages":
        page_sections = bom_data.get("page_sections", [])
        df_pages = pd.DataFrame(page_sections) if page_sections else pd.DataFrame([{
            "Page": "N/A", "Section": "N/A", "Tables": "N/A", "Title": "N/A",
        }])
        st.markdown(
            f"<div class='cx-meta'>Parsed Pages &middot; {len(df_pages)} rows &middot; {len(df_pages.columns)} cols</div>",
            unsafe_allow_html=True,
        )
        _render_popup_table(df_pages)
        _, cc = st.columns([8, 1])
        with cc:
            if st.button("Close", width="stretch"):
                st.session_state["inspect_popup_style"] = None
                st.rerun()
        return
    search = st.text_input("Filter rows", key=f"popup_filter_{style_key}", placeholder="Filter rows...")
    vdf    = bom_data[active].copy()
    if active == "costing_detail" and not vdf.empty:
        pref = ["component", "material", "description", "supplier", "country of origin"]
        nm   = {str(c).strip().lower(): c for c in vdf.columns}
        keep = [nm[c] for c in pref if c in nm]
        if keep:
            vdf = vdf[keep]
    elif active == "color_bom" and not vdf.empty:
        drop = [c for c in vdf.columns if "line" in str(c).lower() and "slot" in str(c).lower()]
        if drop:
            vdf = vdf.drop(columns=drop, errors="ignore")
    if search:
        vdf = vdf[vdf.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)]
    st.markdown(
        f"<div class='cx-meta'>{active.replace('_', ' ').title()} "
        f"&middot; {len(vdf)} rows &middot; {len(vdf.columns)} cols</div>"
        "<div class='cx-meta' style='margin-top:-0.25rem;'>Scroll horizontally to view all columns.</div>",
        unsafe_allow_html=True,
    )
    _render_popup_table(vdf)
    _, cc = st.columns([8, 1])
    with cc:
        if st.button("Close", width="stretch"):
            st.session_state["inspect_popup_style"] = None
            st.rerun()


@st.dialog("Validation Complete", width="small", dismissible=False)
def show_validation_complete_dialog():
    st.markdown("<div class='cx-meta'>Validation finished</div>", unsafe_allow_html=True)
    msg = st.empty()
    for sec in (3, 2, 1):
        msg.markdown(
            f"<div style='font-size:0.86rem;color:#4f688c;margin-bottom:0.6rem;'>"
            f"Validation completed successfully. Closing in {sec}...</div>",
            unsafe_allow_html=True,
        )
        time.sleep(1)
    st.session_state["post_validation_prompt"] = False
    st.rerun(scope="app")


# ── Detail card builder ────────────────────────────────────────────────────────

_DETAIL_GROUPS = [
    ("Label",   [("Main Label","Main Label"),("Main Label Color","Main Label Color"),
                 ("Main Label Supplier","Main Label Supplier"),("Care Label","Care Label"),
                 ("Care Label Color","Care Label Color"),("Care Supplier","Care Supplier")]),
    ("Hangtag", [("Hangtag","Hangtag"),("Hangtag Supplier","Hangtag Supplier"),
                 ("Hangtag 2","Hangtag 2"),("Hangtag 3","Hangtag3"),
                 ("RFID w/o MSRP","RFID w/o MSRP"),("RFID w/o MSRP Sup","RFID w/o MSRP Supplier")]),
    ("Sticker", [("RFID Sticker","RFID Stickers"),("RFID Sticker Sup","RFID Stickers Supplier"),
                 ("UPC Bag Sticker","UPC Bag Sticker (Polybag)"),("UPC Supplier","UPC Supplier")]),
    ("Content", [("Content Code","Content Code"),("TP FC","TP FC"),("Care Code","Care Code")]),
]
_EXTRA_GROUPS = {
    "Labels":   ["Main Label", "Additional Main Label", "Care Label"],
    "Hangtags": ["Hangtag", "Hangtag2", "Hangtag3", "Hangtag (RFID)", "RFID w/o MSRP"],
    "Stickers": ["Micropack Sticker-Gloves", "Size Label", "Size Sticker-Gloves",
                 "RFID Sticker", "UPC Sticker (Polybag)"],
    "Status":   ["TP Status", "TP Date", "Product Status", "Remarks"],
}


def _field_val(row, col):
    v = str(row.get(col, "")).strip()
    return v if v and v.lower() not in ("nan", "none", "") else "N/A"


def _val_color(v):
    return "#b0b8c8" if v == "N/A" else "#1a2b45"


def _chip_tile(lbl, v):
    vc = _val_color(v)
    bg = "#f1f5f9" if v != "N/A" else "#f8fafc"
    return (
        f"<div style='display:inline-flex;flex-direction:column;padding:4px 8px;"
        f"border-radius:6px;background:{bg};border:1px solid #e2e8f0;min-width:80px;max-width:180px;'>"
        f"<span style='font-size:0.57rem;color:#94a3b8;font-weight:600;letter-spacing:0.04em;"
        f"text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{escape(lbl)}</span>"
        f"<span style='font-size:0.74rem;font-weight:600;color:{vc};margin-top:1px;word-break:break-word;'>"
        f"{escape(v)}</span></div>"
    )


def _grp_block(grp_label, chips_html):
    return (
        f"<div style='margin-bottom:8px;'>"
        f"<div style='font-size:0.61rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;"
        f"color:#94a3b8;margin-bottom:4px;'>{grp_label}</div>"
        f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>{chips_html}</div></div>"
    )


def _build_detail_card_html(row, accent, color_val, material_val, status_raw,
                             res_cols_set, extra_fields=None):
    """Build a rich detail card for Results and Comparison tabs."""
    sbg, sfg = ("#d1fae5", "#065f46") if "\u2705" in status_raw else \
               (("#fef9c3", "#854d0e") if "\u26a0\ufe0f" in status_raw else ("#fee2e2", "#991b1b"))

    html = (
        f"<div style='border-left:4px solid {accent};border-radius:10px;"
        f"padding:14px 16px 12px;margin-bottom:10px;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,0.08);'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<div style='font-size:1rem;font-weight:700;color:#1a2b45;'>{escape(color_val)}</div>"
        f"<span style='font-size:0.68rem;font-weight:700;padding:3px 10px;border-radius:999px;"
        f"background:{sbg};color:{sfg};'>{escape(status_raw)}</span></div>"
        f"<div style='font-size:0.74rem;color:#6b7a99;margin-bottom:10px;'>"
        f"<span style='font-weight:700;color:#4a5568;'>Material:</span> {escape(material_val)}</div>"
    )
    for grp_label, fields in _DETAIL_GROUPS:
        avail = [(lbl, col) for lbl, col in fields if col in res_cols_set]
        if not avail:
            continue
        vals = [(lbl, _field_val(row, col)) for lbl, col in avail]
        if not any(v != "N/A" for _, v in vals):
            continue
        html += _grp_block(grp_label, "".join(_chip_tile(lbl, v) for lbl, v in vals))
    if extra_fields:
        for grp_label, grp_keys in _EXTRA_GROUPS.items():
            grp_vals = [(k, extra_fields[k]) for k in grp_keys if k in extra_fields]
            if not grp_vals or not any(v not in ("N/A", "", None) for _, v in grp_vals):
                continue
            dv_chips = "".join(
                _chip_tile(lbl, str(v).strip() if v and str(v).strip() not in ("", "N/A", "nan", "None") else "N/A")
                for lbl, v in grp_vals
            )
            html += _grp_block(grp_label, dv_chips)
    html += "</div>"
    return html
