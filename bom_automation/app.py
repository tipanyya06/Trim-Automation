import re
import io
import hashlib
import io as _io
import pandas as pd
import streamlit as st

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from parsers.pdf_parser import parse_bom_pdf
from validators.filler import validate_and_fill, NEW_COLUMNS
from validators.matcher import auto_detect_columns


st.set_page_config(
    page_title="Columbia BOM Automation",
    page_icon="\U0001f9e2",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"] { font-family:'Inter',sans-serif; background:#0f1117; color:#e8e8e8; font-size:14px; -webkit-font-smoothing:antialiased; }
  #MainMenu, footer { visibility:hidden; }
  header[data-testid="stHeader"] { background:#0f1117!important; border-bottom:none!important; }
  button[data-testid="collapsedControl"] { visibility:visible!important; opacity:1!important; background:#13151e!important; border:1px solid #2a2d3e!important; border-radius:8px!important; color:#e8e8e8!important; }
  button[data-testid="collapsedControl"]:hover { border-color:#3b82f6!important; color:#3b82f6!important; }
  button[data-testid="baseButton-header"] { color:#9ca3af!important; }
  button[data-testid="baseButton-header"]:hover { color:#3b82f6!important; }
  .block-container { padding:2rem 2.5rem!important; max-width:100%!important; }
  section[data-testid="stSidebar"] { background:#13151e; border-right:1px solid #1e2130; }
  section[data-testid="stSidebar"] .block-container { padding:1.5rem 1.2rem!important; }
  [data-testid="stMetric"] { background:#13151e; border:1px solid #1e2130; border-radius:10px; padding:1rem 1.2rem; }
  [data-testid="stMetricLabel"] p { font-size:0.72rem!important; font-weight:500!important; text-transform:uppercase; letter-spacing:0.08em; color:#9ca3af!important; }
  [data-testid="stMetricValue"] { font-size:1.4rem!important; font-weight:600!important; color:#fff!important; }
  .stDataFrame { border-radius:8px; overflow:hidden; border:1px solid #1e2130; }
  .stDataFrame td, .stDataFrame th { font-size:0.82rem!important; }
  .stButton > button, .stDownloadButton > button { font-weight:500!important; font-size:0.78rem!important; letter-spacing:0.03em!important; text-transform:uppercase!important; border-radius:8px!important; border:1px solid #2a2d3e!important; background:#13151e!important; color:#e8e8e8!important; transition:all 0.15s ease!important; padding:0.5rem 1.2rem!important; }
  .stButton > button:hover, .stDownloadButton > button:hover { background:#1e2130!important; border-color:#3b82f6!important; color:#fff!important; }
  [data-testid="stFileUploader"] { border:1.5px dashed #2a2d3e!important; border-radius:12px!important; background:#13151e!important; }
  [data-testid="stSelectbox"] > div > div { background:#13151e!important; border:1px solid #2a2d3e!important; border-radius:8px!important; color:#e8e8e8!important; font-size:0.85rem!important; }
  [data-testid="stExpander"] { border:1px solid #1e2130!important; border-radius:8px!important; background:#13151e!important; }
  button[data-baseweb="tab"] { font-size:0.8rem!important; font-weight:500!important; letter-spacing:0.04em!important; text-transform:uppercase!important; }
  .page-pill { display:inline-flex; align-items:center; justify-content:center; width:32px; height:32px; border-radius:8px; font-size:0.78rem; font-weight:600; border:1px solid #2a2d3e; background:#13151e; color:#9ca3af; cursor:pointer; }
  .page-pill-active { background:#1e3a5f!important; border-color:#3b82f6!important; color:#3b82f6!important; }
</style>
""", unsafe_allow_html=True)

BOMS_PER_PAGE   = 5
STYLES_PER_PAGE = 5


def render_section_header(title, subtitle=""):
    st.markdown(f"""<div class="mb-6">
      <h2 style="font-size:1.45rem;font-weight:700;color:#fff;letter-spacing:-0.01em;margin-bottom:0.15rem;">{title}</h2>
      {"<p style='font-size:0.75rem;color:#5a6080;text-transform:uppercase;letter-spacing:0.08em;'>" + subtitle + "</p>" if subtitle else ""}
      <div style="height:2px;background:linear-gradient(90deg,#3b82f6 0%,transparent 70%);margin-top:0.5rem;"></div>
    </div>""", unsafe_allow_html=True)

def render_divider():
    st.markdown('<div style="height:1px;background:#1e2130;margin:1.5rem 0;"></div>', unsafe_allow_html=True)

def render_info_banner(message):
    st.markdown(f"""<div style="background:#0d1a2e;border:1px solid #1e3a5f;border-left:3px solid #3b82f6;border-radius:8px;padding:0.85rem 1.1rem;font-size:0.82rem;color:#93c5fd;margin-bottom:1.2rem;">
      \u2139 &nbsp;{message}</div>""", unsafe_allow_html=True)

def render_warn_banner(message):
    st.markdown(f"""<div style="background:#1c1500;border:1px solid #3d2e00;border-left:3px solid #f59e0b;border-radius:8px;padding:0.85rem 1.1rem;font-size:0.82rem;color:#fcd34d;margin-bottom:1.2rem;">
      \u26a0 &nbsp;{message}</div>""", unsafe_allow_html=True)

def render_table_meta(df):
    st.markdown(f"""<div style="font-size:0.72rem;color:#5a6080;margin-bottom:0.5rem;letter-spacing:0.05em;text-transform:uppercase;">
      {len(df)} rows &nbsp;\xb7&nbsp; {len(df.columns)} columns</div>""", unsafe_allow_html=True)

def render_validation_summary(ok, partial, err, total):
    st.markdown(f"""<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:1.5rem;">
      <div style="background:#0d2218;border:1px solid #1a4a30;border-radius:10px;padding:1rem 1.2rem;text-align:center;"><div style="font-size:2rem;font-weight:800;color:#34d399;line-height:1;">{ok}</div><div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Validated</div></div>
      <div style="background:#1c1500;border:1px solid #3d2e00;border-radius:10px;padding:1rem 1.2rem;text-align:center;"><div style="font-size:2rem;font-weight:800;color:#f59e0b;line-height:1;">{partial}</div><div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Partial</div></div>
      <div style="background:#1e0d0d;border:1px solid #4a1a1a;border-radius:10px;padding:1rem 1.2rem;text-align:center;"><div style="font-size:2rem;font-weight:800;color:#f87171;line-height:1;">{err}</div><div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Errors</div></div>
      <div style="background:#13151e;border:1px solid #1e2130;border-radius:10px;padding:1rem 1.2rem;text-align:center;"><div style="font-size:2rem;font-weight:800;color:#9ca3af;line-height:1;">{total}</div><div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Total Rows</div></div>
    </div>""", unsafe_allow_html=True)


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
        st.markdown("""<div style="font-size:1.15rem;font-weight:800;color:#fff;line-height:1.2;margin-bottom:0.2rem;">Columbia BOM<br>Automation</div>
        <div style="font-size:0.7rem;color:#5a6080;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:1.5rem;">Trim & Label Validator</div>""", unsafe_allow_html=True)
        bom_dict = st.session_state.get("bom_dict", {})
        if bom_dict:
            st.markdown(f"""<div style="display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;font-size:0.72rem;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:0.5rem;background:#0d2218;color:#34d399;border:1px solid #1a4a30;">\u25cf &nbsp;{len(bom_dict)} BOM{'s' if len(bom_dict)>1 else ''} Loaded</div>""", unsafe_allow_html=True)
            for style, bom in bom_dict.items():
                meta = bom.get("metadata", {})
                st.markdown(f"""<div style="font-size:0.72rem;color:#9ca3af;padding:4px 0;border-bottom:1px solid #1e2130;"><span style="color:#3b82f6;font-weight:600;">{style}</span> &nbsp;\xb7&nbsp; {meta.get('season','\u2014')} &nbsp;\xb7&nbsp; {meta.get('production_lo','\u2014')}</div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div style="display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;font-size:0.72rem;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:1.2rem;background:#1e1e2e;color:#6b7280;border:1px solid #2a2a3e;">\u25cf &nbsp;No BOM Loaded</div>""", unsafe_allow_html=True)
        with st.expander("How to use", expanded=False):
            st.markdown("""
            **Step 1** \u2014 Upload one or more Columbia BOM PDFs in the **PDF Extraction** tab.
            **Step 2** \u2014 Inspect each parsed section to verify extraction.
            **Step 3** \u2014 Go to **BOM Comparison**, upload your Excel/CSV.
            **Step 4** \u2014 Map columns, configure label dropdowns, run validation, export.
            """)
        render_divider()
        if st.button("\U0001f5d1 Clear All Data", width='stretch'):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_style_key(style, bom_dict):
    su = style.strip().upper()
    for k in bom_dict:
        if su == k.strip().upper():
            return k
    return None


# ── Conflict dialog — defined BEFORE render_pdf_tab ──────────────────────────

@st.dialog("Duplicate Style Detected", width="large")
def show_conflict_dialog(conflict_key, info, bom_dict, pdf_bytes_store, pdf_hashes):
    style         = info.get("style", conflict_key.split("__")[0])
    reason        = info.get("conflict_reason", "already_loaded")
    existing_meta = bom_dict.get(info["existing_key"], {}).get("metadata", {})
    new_meta      = info["bom_data"].get("metadata", {}) if isinstance(info.get("bom_data"), dict) else {}

    if reason == "duplicate_file":
        reason_label = "⚠ Exact duplicate file uploaded again"
    elif reason == "duplicate_in_batch":
        reason_label = "⚠ Same style uploaded twice in this batch"
    else:
        reason_label = "⚠ Style already loaded from a previous upload"

    st.markdown(f"**{reason_label}:** `{style}`")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Existing in session**")
        st.markdown(f"Season: `{existing_meta.get('season', '—')}` · LO: `{existing_meta.get('production_lo', '—')}`")
    with col2:
        st.markdown(f"**New Upload** — {info['fname']}")
        st.markdown(f"Season: `{new_meta.get('season', '—')}` · LO: `{new_meta.get('production_lo', '—')}`")
    st.divider()
    col_rep, col_keep = st.columns(2)
    with col_rep:
        if st.button("↺ Replace", type="primary", use_container_width=True):
            existing_key = info["existing_key"]
            bom_dict[existing_key]        = info["bom_data"]
            pdf_bytes_store[existing_key] = info["raw_bytes"]
            # Mark this fname as resolved so it won't re-trigger
            pdf_hashes[info["fname"]]     = info["fhash"]
            st.session_state["bom_dict"]        = bom_dict
            st.session_state["pdf_bytes_store"] = pdf_bytes_store
            st.session_state["pdf_hashes"]      = pdf_hashes
            del st.session_state["pending_conflicts"][conflict_key]
            st.rerun()
    with col_keep:
        if st.button("✓ Keep Existing", use_container_width=True):
            # Mark fname as resolved so it won't be re-parsed on next rerun
            pdf_hashes[info["fname"]] = info["fhash"]
            st.session_state["pdf_hashes"] = pdf_hashes
            del st.session_state["pending_conflicts"][conflict_key]
            st.rerun()


def render_pdf_tab():
    render_section_header("PDF Extraction", "Upload & inspect BOM sections")
    uploaded_pdfs = st.file_uploader(
        "Drop one or more Columbia BOM PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
        help="Each PDF is matched to Excel rows by its style number",
    )
    if not uploaded_pdfs:
        render_info_banner("Upload one or more Columbia BOM PDFs. Each PDF's style is auto-detected and used to match rows in your Excel.")
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

    # Only re-parse files whose hash has changed or that are genuinely new
    to_parse = []
    for fname, raw_bytes in pdf_data_list:
        fhash = hashlib.md5(raw_bytes).hexdigest()
        if pdf_hashes.get(fname) != fhash:
            to_parse.append((fname, raw_bytes, fhash))

    pending_conflicts = st.session_state.get("pending_conflicts", None)

    # Only enter parse block for genuinely new/changed files, not on every rerun
    if to_parse and not pending_conflicts:
        to_parse_indexed = []
        seen_fhashes = set()
        for idx, (fname, raw_bytes) in enumerate(pdf_data_list):
            fhash = hashlib.md5(raw_bytes).hexdigest()
            if fhash in seen_fhashes:
                # Exact duplicate content in this batch
                to_parse_indexed.append((fname, raw_bytes, fhash, idx, True))
            else:
                if pdf_hashes.get(fname) != fhash:
                    to_parse_indexed.append((fname, raw_bytes, fhash, idx, False))
                seen_fhashes.add(fhash)

        unique_to_parse = [(fname, raw_bytes, fhash, idx) for fname, raw_bytes, fhash, idx, is_dup in to_parse_indexed if not is_dup]
        dup_entries     = [(fname, raw_bytes, fhash, idx) for fname, raw_bytes, fhash, idx, is_dup in to_parse_indexed if is_dup]

        pre_parsed = {}

        if unique_to_parse:
            with ThreadPoolExecutor(max_workers=min(8, len(unique_to_parse))) as executor:
                def _pre_parse(args):
                    fname, raw_bytes, fhash, idx = args
                    bom_data = parse_bom_pdf(_io.BytesIO(raw_bytes))
                    style = bom_data.get("metadata", {}).get("style") or fname
                    return (fname, idx), style, bom_data, raw_bytes, fhash
                futures = {executor.submit(_pre_parse, args): args[0] for args in unique_to_parse}
                for future in as_completed(futures):
                    key, style, bom_data, raw_bytes, fhash = future.result()
                    pre_parsed[key] = (style, bom_data, raw_bytes, fhash)

        style_seen_this_batch = {}
        conflicts     = {}
        non_conflicts = {}

        for key, (style, bom_data, raw_bytes, fhash) in pre_parsed.items():
            existing_key = _resolve_style_key(style, bom_dict)
            if existing_key is not None:
                conflicts[f"{style}__{key[1]}"] = {
                    "style": style,
                    "fname": key[0],
                    "bom_data": bom_data,
                    "raw_bytes": raw_bytes,
                    "fhash": fhash,
                    "existing_key": existing_key,
                    "conflict_reason": "already_loaded",
                }
            elif style in style_seen_this_batch:
                conflicts[f"{style}__{key[1]}"] = {
                    "style": style,
                    "fname": key[0],
                    "bom_data": bom_data,
                    "raw_bytes": raw_bytes,
                    "fhash": fhash,
                    "existing_key": style,
                    "conflict_reason": "duplicate_in_batch",
                }
            else:
                style_seen_this_batch[style] = key
                non_conflicts[style] = {
                    "fname": key[0],
                    "bom_data": bom_data,
                    "raw_bytes": raw_bytes,
                    "fhash": fhash,
                }

        for fname, raw_bytes, fhash, idx in dup_entries:
            matching_style = next(
                (s for s, info in {**non_conflicts, **{c["style"]: c for c in conflicts.values()}}.items()
                 if hashlib.md5(info["raw_bytes"]).hexdigest() == fhash),
                None,
            )
            if matching_style is None:
                # Already resolved — skip silently
                continue
            existing_key = _resolve_style_key(matching_style, bom_dict) or matching_style
            conflicts[f"{matching_style}__{idx}"] = {
                "style": matching_style,
                "fname": fname,
                "bom_data": bom_dict.get(existing_key, non_conflicts.get(matching_style, {}).get("bom_data", {})),
                "raw_bytes": raw_bytes,
                "fhash": fhash,
                "existing_key": existing_key,
                "conflict_reason": "duplicate_file",
            }

        # Immediately commit non-conflicting styles
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

    # ── Show conflict resolution dialog (one at a time) ──────────────────────
    pending_conflicts = st.session_state.get("pending_conflicts", {})
    if pending_conflicts:
        conflict_key = next(iter(pending_conflicts))
        info = pending_conflicts[conflict_key]
        show_conflict_dialog(conflict_key, info, bom_dict, pdf_bytes_store, pdf_hashes)
        return

    # All resolved — show loaded BOMs UI
    if not bom_dict:
        render_info_banner("Upload one or more Columbia BOM PDFs. Each PDF's style is auto-detected and used to match rows in your Excel.")
        return

    st.markdown(f"""<div style="background:#0d2218;border:1px solid #1a4a30;border-radius:10px;padding:0.85rem 1.1rem;font-size:0.82rem;color:#34d399;margin-bottom:1rem;">\u26a1 All {len(uploaded_pdfs)} PDF(s) loaded \u2014 {len(bom_dict)} BOM(s) in session.</div>""", unsafe_allow_html=True)

    render_divider()
    col_info, col_clear = st.columns([5, 1])
    with col_info:
        render_info_banner(f"Loaded {len(bom_dict)} BOM(s): {', '.join(bom_dict.keys())}")
    with col_clear:
        if st.button("\U0001f5d1 Clear All PDFs", key="clear_pdfs_btn"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#5a6080;margin-bottom:0.75rem;">Loaded BOMs</div>""", unsafe_allow_html=True)
    all_styles   = list(bom_dict.keys())
    summary_rows = []
    for style in all_styles:
        bom  = bom_dict[style]
        meta = bom.get("metadata", {})
        sects = [k for k, v in bom.items() if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty]
        summary_rows.append({
            "Style": style,
            "Season": meta.get("season", "\u2014"),
            "Design": meta.get("design", "\u2014"),
            "LO": meta.get("production_lo", "\u2014"),
            "Sections": len(sects),
            "Colorways": len(bom.get("color_bom", pd.DataFrame()).columns) if not bom.get("color_bom", pd.DataFrame()).empty else 0,
        })
    st.dataframe(pd.DataFrame(summary_rows), width='stretch', height=min(80 + 35 * len(summary_rows), 400))

    render_divider()
    selected_style = st.selectbox("Inspect BOM for style", options=all_styles)
    bom_data = bom_dict[selected_style]
    meta     = bom_data.get("metadata", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Style", meta.get("style", "\u2014"))
    c2.metric("Season", meta.get("season", "\u2014"))
    c3.metric("Design", meta.get("design", "\u2014"))
    c4.metric("Production LO", meta.get("production_lo", "\u2014"))

    render_divider()
    section_keys = [k for k, v in bom_data.items() if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty]
    if not section_keys:
        render_warn_banner("No sections were extracted from this PDF.")
        return

    col_sel, col_search = st.columns([2, 3])
    with col_sel:
        section = st.selectbox("Section", options=section_keys)
    with col_search:
        search = st.text_input("Filter rows", "", placeholder="Search any value...")
    df      = bom_data[section]
    view_df = df.copy()
    if search:
        view_df = view_df[view_df.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)]
    render_table_meta(view_df)
    st.dataframe(view_df, width='stretch', height=380)

    render_divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("\u2b07 Export Section \u2192 CSV", data=export_to_csv(view_df), file_name=f"{selected_style}_{section}.csv", mime="text/csv", width='stretch')
    with c2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            for k in section_keys:
                bom_data[k].to_excel(writer, index=False, sheet_name=k[:31])
        st.download_button("\u2b07 Export All Sections \u2192 Excel", data=buf.getvalue(), file_name=f"{selected_style}_sections.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')


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

    render_info_banner(f"{len(bom_dict)} BOM(s) loaded: {', '.join(bom_dict.keys())} \u2014 each Excel row will be matched to the correct BOM by style number.")

    comp_file = st.file_uploader("Drop your Comparison Excel or CSV here", type=["xlsx", "csv", "xls"], key="cmp_uploader", help="Can contain 100+ rows and multiple styles")
    if comp_file is None:
        render_results()
        return

    try:
        comp_df = _read_comparison_file(comp_file)
        st.session_state["comparison_raw"] = comp_df
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        return

    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#5a6080;margin-bottom:0.75rem;">Column Mapping</div>""", unsafe_allow_html=True)
    auto = auto_detect_columns(comp_df)
    if auto and auto["confidence"] >= 0.7:
        default_style = auto["style_col"]
        default_color = auto["color_col"]
        render_info_banner(f"Auto-detected: Style='{default_style}', Color='{default_color}'")
    else:
        default_style = list(comp_df.columns)[0]
        default_color = list(comp_df.columns)[1] if len(comp_df.columns) > 1 else list(comp_df.columns)[0]

    col_a, col_b = st.columns(2)
    with col_a:
        style_col = st.selectbox("Buyer Style Number column", options=list(comp_df.columns), index=list(comp_df.columns).index(default_style) if default_style in comp_df.columns else 0)
    with col_b:
        color_col = st.selectbox("Color / Option column", options=list(comp_df.columns), index=list(comp_df.columns).index(default_color) if default_color in comp_df.columns else 0)

    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#5a6080;margin-bottom:0.75rem;">Label Mapping \u2014 Per Buyer Style</div>""", unsafe_allow_html=True)
    render_info_banner("Select the correct Main Label and Care Label for each style.")

    label_selections = st.session_state.get("label_selections", {})
    all_style_keys   = list(bom_dict.keys())
    total_styles     = len(all_style_keys)
    total_lm_pages   = max(1, -(-total_styles // STYLES_PER_PAGE))
    lm_page          = max(0, min(st.session_state.get("label_map_page", 0), total_lm_pages - 1))
    st.session_state["label_map_page"] = lm_page

    st.markdown(f"<div style='font-size:0.72rem;color:#5a6080;margin-bottom:0.75rem;'>Showing styles {lm_page*STYLES_PER_PAGE+1}\u2013{min((lm_page+1)*STYLES_PER_PAGE, total_styles)} of {total_styles}</div>", unsafe_allow_html=True)

    render_pagination("label_map_page", lm_page, total_lm_pages, key_suffix="lm")

    page_style_keys = all_style_keys[lm_page * STYLES_PER_PAGE: (lm_page + 1) * STYLES_PER_PAGE]
    for style_key in page_style_keys:
        bom_data   = bom_dict[style_key]
        components = _get_components_for_bom(bom_data)

        if not components:
            st.markdown(f"""<div style="font-size:0.8rem;color:#f59e0b;padding:6px 0;">\u26a0 Style <b>{style_key}</b> \u2014 no label components found.</div>""", unsafe_allow_html=True)
            continue

        st.markdown(f"""<div style="font-size:0.88rem;font-weight:600;color:#3b82f6;margin-top:0.8rem;margin-bottom:0.3rem;border-left:3px solid #3b82f6;padding-left:0.6rem;">{style_key}</div>""", unsafe_allow_html=True)
        saved = label_selections.get(style_key, {})

        def _best_default(saved_val, preferred_names, _comps=components):
            if saved_val and saved_val in _comps:
                return saved_val
            for preferred in preferred_names:
                for comp in _comps:
                    if preferred.lower() in comp.lower():
                        return comp
            return _comps[0]

        # Main Label: auto-select "Label Logo 1" first
        default_main = _best_default(saved.get("main_label", ""), ["label logo 1", "Label 1", "Main Label"])
        # Care Label: prefer care-related components
        default_care = _best_default(saved.get("care_label", ""), ["Label 1", "Care Label", "Label1"])

        col_c, col_d = st.columns(2)
        with col_c:
            main_sel = st.selectbox(f"Main Label \u2014 {style_key}", options=components, index=components.index(default_main) if default_main in components else 0, key=f"main_label_{style_key}")
        with col_d:
            care_sel = st.selectbox(f"Care Label \u2014 {style_key}", options=components, index=components.index(default_care) if default_care in components else 0, key=f"care_label_{style_key}")
        label_selections[style_key] = {"main_label": main_sel, "care_label": care_sel}

    st.session_state["label_selections"] = label_selections

    render_divider()
    render_table_meta(comp_df)
    st.dataframe(comp_df.head(100), width='stretch', height=280)

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
    if st.button("\u25b6 Run Validation & Auto-Fill"):
        with st.spinner("Matching rows to BOMs and filling columns..."):
            renamed_df = comp_df.rename(columns={style_col: "Buyer Style Number", color_col: "Color/Option"})
            label_sels = st.session_state.get("label_selections", {})
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
                per_style_labels = label_sels.get(matched_bom_key, {})
                bom_with_labels  = dict(matched_bom)
                bom_with_labels["selected_main_label_comp"] = per_style_labels.get("main_label")
                bom_with_labels["selected_care_label_comp"] = per_style_labels.get("care_label")
                result_parts.append(validate_and_fill(comparison_df=group_df.reset_index(drop=True), bom_data=bom_with_labels))
            st.session_state["validation_result"] = pd.concat(result_parts, ignore_index=True) if result_parts else renamed_df

    render_results()


def render_results():
    if "validation_result" not in st.session_state:
        return
    res = st.session_state["validation_result"]
    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#5a6080;margin-bottom:0.75rem;">Validation Summary</div>""", unsafe_allow_html=True)
    status_counts = res["Validation Status"].value_counts(dropna=False).to_dict() if "Validation Status" in res.columns else {}
    ok      = status_counts.get("\u2705 Validated", 0)
    partial = status_counts.get("\u26a0\ufe0f Partial", 0)
    err     = sum(v for k, v in status_counts.items() if str(k).startswith("\u274c"))
    render_validation_summary(ok, partial, err, len(res))
    render_table_meta(res)
    st.dataframe(res, width='stretch', height=400)
    render_divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("\u2b07 Export Results \u2192 CSV", data=export_to_csv(res), file_name="validated_bom.csv", mime="text/csv", width='stretch')
    with c2:
        xls = export_to_excel(result_df=res, original_df=st.session_state.get("comparison_raw", pd.DataFrame()))
        st.download_button("\u2b07 Export Results \u2192 Excel", data=xls, file_name="validated_bom.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')


def main():
    render_sidebar()
    tab1, tab2 = st.tabs(["  \U0001f4c4  PDF Extraction  ", "  \U0001f50d  BOM Comparison & Validation  "])
    with tab1:
        render_pdf_tab()
    with tab2:
        render_comparison_tab()

if __name__ == "__main__":
    main()