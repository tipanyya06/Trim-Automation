import re
import io
import pandas as pd
import streamlit as st

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from parsers.pdf_parser import parse_bom_pdf
from validators.filler import validate_and_fill, NEW_COLUMNS
from validators.matcher import auto_detect_columns


st.set_page_config(
    page_title="Columbia BOM Automation",
    page_icon="🧢",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"] { font-family:'Inter',sans-serif; background:#0f1117; color:#e8e8e8; font-size:14px; -webkit-font-smoothing:antialiased; }
  /* Hide menu and footer but NOT the header — the sidebar toggle lives inside it */
  #MainMenu, footer { visibility:hidden; }
  header[data-testid="stHeader"] { background:#0f1117 !important; border-bottom:none !important; }
  /* Style the sidebar toggle button so it's always clearly visible */
  button[data-testid="collapsedControl"] {
    visibility:visible !important; opacity:1 !important;
    background:#13151e !important; border:1px solid #2a2d3e !important;
    border-radius:8px !important; color:#e8e8e8 !important;
  }
  button[data-testid="collapsedControl"]:hover {
    border-color:#3b82f6 !important; color:#3b82f6 !important;
  }
  /* Also make the in-sidebar collapse arrow visible */
  button[data-testid="baseButton-header"] {
    color:#9ca3af !important;
  }
  button[data-testid="baseButton-header"]:hover {
    color:#3b82f6 !important;
  }
  .block-container { padding:2rem 2.5rem !important; max-width:100% !important; }
  section[data-testid="stSidebar"] { background:#13151e; border-right:1px solid #1e2130; }
  section[data-testid="stSidebar"] .block-container { padding:1.5rem 1.2rem !important; }
  [data-testid="stMetric"] { background:#13151e; border:1px solid #1e2130; border-radius:10px; padding:1rem 1.2rem; }
  [data-testid="stMetricLabel"] p { font-size:0.72rem !important; font-weight:500 !important; text-transform:uppercase; letter-spacing:0.08em; color:#9ca3af !important; }
  [data-testid="stMetricValue"] { font-size:1.4rem !important; font-weight:600 !important; color:#fff !important; }
  .stDataFrame { border-radius:8px; overflow:hidden; border:1px solid #1e2130; }
  .stDataFrame td, .stDataFrame th { font-size:0.82rem !important; }
  .stButton > button, .stDownloadButton > button {
    font-weight:500 !important; font-size:0.78rem !important; letter-spacing:0.03em !important;
    text-transform:uppercase !important; border-radius:8px !important; border:1px solid #2a2d3e !important;
    background:#13151e !important; color:#e8e8e8 !important; transition:all 0.15s ease !important; padding:0.5rem 1.2rem !important;
  }
  .stButton > button:hover, .stDownloadButton > button:hover { background:#1e2130 !important; border-color:#3b82f6 !important; color:#fff !important; }
  [data-testid="stFileUploader"] { border:1.5px dashed #2a2d3e !important; border-radius:12px !important; background:#13151e !important; }
  [data-testid="stSelectbox"] > div > div { background:#13151e !important; border:1px solid #2a2d3e !important; border-radius:8px !important; color:#e8e8e8 !important; font-size:0.85rem !important; }
  [data-testid="stExpander"] { border:1px solid #1e2130 !important; border-radius:8px !important; background:#13151e !important; }
  button[data-baseweb="tab"] { font-size:0.8rem !important; font-weight:500 !important; letter-spacing:0.04em !important; text-transform:uppercase !important; }
  .page-pill {
    display:inline-flex; align-items:center; justify-content:center;
    width:32px; height:32px; border-radius:8px; font-size:0.78rem; font-weight:600;
    border:1px solid #2a2d3e; background:#13151e; color:#9ca3af; cursor:pointer;
  }
  .page-pill-active {
    background:#1e3a5f !important; border-color:#3b82f6 !important; color:#3b82f6 !important;
  }
</style>
""", unsafe_allow_html=True)

BOMS_PER_PAGE       = 5   # PDF tab: BOMs shown per page
STYLES_PER_PAGE     = 5   # Label mapping: styles shown per page


# ── UI helpers ────────────────────────────────────────────────────────────────

def render_section_header(title, subtitle=""):
    st.markdown(f"""
    <div class="mb-6">
      <h2 style="font-size:1.45rem;font-weight:700;color:#fff;letter-spacing:-0.01em;margin-bottom:0.15rem;">{title}</h2>
      {"<p style='font-size:0.75rem;color:#5a6080;text-transform:uppercase;letter-spacing:0.08em;'>" + subtitle + "</p>" if subtitle else ""}
      <div style="height:2px;background:linear-gradient(90deg,#3b82f6 0%,transparent 70%);margin-top:0.5rem;"></div>
    </div>""", unsafe_allow_html=True)

def render_divider():
    st.markdown('<div style="height:1px;background:#1e2130;margin:1.5rem 0;"></div>', unsafe_allow_html=True)

def render_info_banner(message):
    st.markdown(f"""<div style="background:#0d1a2e;border:1px solid #1e3a5f;border-left:3px solid #3b82f6;
                border-radius:8px;padding:0.85rem 1.1rem;font-size:0.82rem;color:#93c5fd;margin-bottom:1.2rem;">
      ℹ &nbsp;{message}</div>""", unsafe_allow_html=True)

def render_warn_banner(message):
    st.markdown(f"""<div style="background:#1c1500;border:1px solid #3d2e00;border-left:3px solid #f59e0b;
                border-radius:8px;padding:0.85rem 1.1rem;font-size:0.82rem;color:#fcd34d;margin-bottom:1.2rem;">
      ⚠ &nbsp;{message}</div>""", unsafe_allow_html=True)

def render_table_meta(df):
    st.markdown(f"""<div style="font-size:0.72rem;color:#5a6080;margin-bottom:0.5rem;letter-spacing:0.05em;text-transform:uppercase;">
      {len(df)} rows &nbsp;·&nbsp; {len(df.columns)} columns</div>""", unsafe_allow_html=True)

def render_validation_summary(ok, partial, err, total):
    st.markdown(f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:1.5rem;">
      <div style="background:#0d2218;border:1px solid #1a4a30;border-radius:10px;padding:1rem 1.2rem;text-align:center;">
        <div style="font-size:2rem;font-weight:800;color:#34d399;line-height:1;">{ok}</div>
        <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Validated</div>
      </div>
      <div style="background:#1c1500;border:1px solid #3d2e00;border-radius:10px;padding:1rem 1.2rem;text-align:center;">
        <div style="font-size:2rem;font-weight:800;color:#f59e0b;line-height:1;">{partial}</div>
        <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Partial</div>
      </div>
      <div style="background:#1e0d0d;border:1px solid #4a1a1a;border-radius:10px;padding:1rem 1.2rem;text-align:center;">
        <div style="font-size:2rem;font-weight:800;color:#f87171;line-height:1;">{err}</div>
        <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Errors</div>
      </div>
      <div style="background:#13151e;border:1px solid #1e2130;border-radius:10px;padding:1rem 1.2rem;text-align:center;">
        <div style="font-size:2rem;font-weight:800;color:#9ca3af;line-height:1;">{total}</div>
        <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:0.3rem;color:#6b7280;">Total Rows</div>
      </div>
    </div>""", unsafe_allow_html=True)


def render_pagination(page_key: str, current_page: int, total_pages: int, key_suffix: str = ""):
    """Render prev / page-number pills / next controls. Use key_suffix to avoid duplicate keys."""
    if total_pages <= 1:
        return current_page

    suffix = key_suffix or page_key
    col_prev, col_pills, col_next = st.columns([1, 6, 1])

    with col_prev:
        if st.button("← Prev", key=f"{suffix}_prev", disabled=current_page == 0):
            st.session_state[page_key] = current_page - 1
            st.rerun()

    with col_pills:
        window = 3
        start = max(0, current_page - window)
        end   = min(total_pages, current_page + window + 1)
        pills_html = "<div style='display:flex;gap:6px;justify-content:center;align-items:center;'>"
        for p in range(start, end):
            active = "page-pill-active" if p == current_page else ""
            pills_html += f"<div class='page-pill {active}'>{p + 1}</div>"
        pills_html += "</div>"
        st.markdown(pills_html, unsafe_allow_html=True)

    with col_next:
        if st.button("Next →", key=f"{suffix}_next", disabled=current_page >= total_pages - 1):
            st.session_state[page_key] = current_page + 1
            st.rerun()

    st.markdown(
        f"<div style='text-align:center;font-size:0.7rem;color:#5a6080;margin-top:4px;'>"
        f"Page {current_page + 1} of {total_pages}</div>",
        unsafe_allow_html=True,
    )
    return st.session_state.get(page_key, current_page)


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("""<div style="font-size:1.15rem;font-weight:800;color:#fff;line-height:1.2;margin-bottom:0.2rem;">
          Columbia BOM<br>Automation</div>
        <div style="font-size:0.7rem;color:#5a6080;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:1.5rem;">
          Trim & Label Validator</div>""", unsafe_allow_html=True)

        bom_dict = st.session_state.get("bom_dict", {})
        loaded = len(bom_dict) > 0

        if loaded:
            st.markdown(f"""<div style="display:inline-flex;align-items:center;gap:6px;padding:5px 12px;
                border-radius:20px;font-size:0.72rem;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;
                margin-bottom:0.5rem;background:#0d2218;color:#34d399;border:1px solid #1a4a30;">
              ⬤ &nbsp;{len(bom_dict)} BOM{'s' if len(bom_dict)>1 else ''} Loaded</div>""", unsafe_allow_html=True)
            for style, bom in bom_dict.items():
                meta = bom.get("metadata", {})
                st.markdown(f"""<div style="font-size:0.72rem;color:#9ca3af;padding:4px 0;border-bottom:1px solid #1e2130;">
                  <span style="color:#3b82f6;font-weight:600;">{style}</span>
                  &nbsp;·&nbsp; {meta.get('season','—')} &nbsp;·&nbsp; {meta.get('production_lo','—')}</div>""",
                  unsafe_allow_html=True)
        else:
            st.markdown("""<div style="display:inline-flex;align-items:center;gap:6px;padding:5px 12px;
                border-radius:20px;font-size:0.72rem;font-weight:500;letter-spacing:0.06em;text-transform:uppercase;
                margin-bottom:1.2rem;background:#1e1e2e;color:#6b7280;border:1px solid #2a2a3e;">
              ⬤ &nbsp;No BOM Loaded</div>""", unsafe_allow_html=True)

        with st.expander("How to use", expanded=False):
            st.markdown("""
            **Step 1** — Upload one or more Columbia BOM PDFs in the **PDF Extraction** tab.
            
            **Step 2** — Inspect each parsed section to verify extraction.
            
            **Step 3** — Go to **BOM Comparison**, upload your Excel/CSV (can have 100+ rows, multiple styles).
            
            **Step 4** — Map columns, configure label dropdowns **per style**, run validation, export.
            """)

        render_divider()
        if st.button("🗑 Clear All Data", width='stretch'):
            for k in ["bom_dict", "comparison_raw", "validation_result",
                      "label_selections", "pdf_bytes_store", "pdf_hashes",
                      "pdf_tab_page", "label_map_page"]:
                st.session_state.pop(k, None)
            st.rerun()


# ── PDF Extraction Tab ────────────────────────────────────────────────────────

def render_pdf_tab():
    render_section_header("PDF Extraction", "Upload & inspect BOM sections")

    uploaded_pdfs = st.file_uploader(
        "Drop one or more Columbia BOM PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
        help="Each PDF is matched to Excel rows by its style number — no hardcoding needed"
    )

    if not uploaded_pdfs:
        render_info_banner("Upload one or more Columbia BOM PDFs. Each PDF's style is auto-detected and used to match rows in your Excel.")
        return

    # ── Parse & cache ──────────────────────────────────────────────────────────
    bom_dict         = st.session_state.get("bom_dict", {})
    pdf_bytes_store  = st.session_state.get("pdf_bytes_store", {})
    pdf_hashes       = st.session_state.get("pdf_hashes", {})

    import hashlib, io as _io
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pdf_data_list = [(f.name, f.read()) for f in uploaded_pdfs]
    to_parse = []
    for fname, raw_bytes in pdf_data_list:
        fhash = hashlib.md5(raw_bytes).hexdigest()
        if pdf_hashes.get(fname) != fhash:
            to_parse.append((fname, raw_bytes, fhash))

    newly_parsed, errors = [], []

    if to_parse:
        def _parse_one(args):
            fname, raw_bytes, fhash = args
            bom_data = parse_bom_pdf(_io.BytesIO(raw_bytes))
            style = bom_data.get("metadata", {}).get("style") or fname
            return style, bom_data, raw_bytes, fhash, fname

        total        = len(to_parse)
        cached_count = len(uploaded_pdfs) - total

        st.markdown(f"""
        <div style="background:#13151e;border:1px solid #1e2130;border-radius:12px;padding:1.2rem 1.5rem;margin-bottom:1rem;">
          <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;color:#5a6080;margin-bottom:0.5rem;">Parsing BOMs</div>
          <div style="font-size:1rem;font-weight:600;color:#fff;margin-bottom:0.25rem;">
            {total} PDF(s) to parse{"  ·  " + str(cached_count) + " cached" if cached_count else ""}
          </div>
          <div style="font-size:0.78rem;color:#9ca3af;">Processing in parallel — please wait...</div>
        </div>""", unsafe_allow_html=True)

        progress_bar = st.progress(0, text="Starting...")
        status_text  = st.empty()
        done_count   = 0

        with ThreadPoolExecutor(max_workers=min(8, total)) as executor:
            futures = {executor.submit(_parse_one, args): args[0] for args in to_parse}
            for future in as_completed(futures):
                try:
                    style, bom_data, raw_bytes, fhash, fname = future.result()
                    bom_dict[style]        = bom_data
                    pdf_bytes_store[style] = raw_bytes
                    pdf_hashes[fname]      = fhash
                    newly_parsed.append(style)
                except Exception as e:
                    errors.append(f"Failed: {futures[future]}: {e}")
                done_count += 1
                progress_bar.progress(done_count / total, text=f"Parsed {done_count} / {total}")
                status_text.markdown(
                    f"<div style='font-size:0.78rem;color:#9ca3af;margin-top:0.25rem;'>"
                    f"✓ {', '.join(newly_parsed[-3:])}"
                    f"{'...' if len(newly_parsed) > 3 else ''}</div>",
                    unsafe_allow_html=True
                )

        progress_bar.progress(1.0, text=f"✅ Done — {len(newly_parsed)} BOM(s) parsed")
        status_text.empty()
        for err in errors:
            st.error(err)
    else:
        st.markdown(f"""
        <div style="background:#0d2218;border:1px solid #1a4a30;border-radius:10px;
             padding:0.85rem 1.1rem;font-size:0.82rem;color:#34d399;margin-bottom:1rem;">
          ⚡ All {len(uploaded_pdfs)} PDF(s) already parsed — loaded from cache instantly.
        </div>""", unsafe_allow_html=True)

    st.session_state["bom_dict"]        = bom_dict
    st.session_state["pdf_bytes_store"] = pdf_bytes_store
    st.session_state["pdf_hashes"]      = pdf_hashes

    if not bom_dict:
        return

    # ── Clear all PDFs button ──────────────────────────────────────────────────
    render_divider()
    col_info, col_clear = st.columns([5, 1])
    with col_info:
        render_info_banner(f"Loaded {len(bom_dict)} BOM(s): {', '.join(bom_dict.keys())}")
    with col_clear:
        if st.button("🗑 Clear All PDFs", key="clear_pdfs_btn"):
            for k in ["bom_dict", "pdf_bytes_store", "pdf_hashes",
                      "pdf_tab_page", "validation_result", "label_selections"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── BOM summary table (no pagination — just show all) ─────────────────────
    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;
                color:#5a6080;margin-bottom:0.75rem;">Loaded BOMs</div>""", unsafe_allow_html=True)

    all_styles   = list(bom_dict.keys())

    summary_rows = []
    for style in all_styles:
        bom  = bom_dict[style]
        meta = bom.get("metadata", {})
        sections_with_data = [
            k for k, v in bom.items()
            if k not in ("metadata", "supplier_lookup")
            and isinstance(v, pd.DataFrame) and not v.empty
        ]
        summary_rows.append({
            "Style":     style,
            "Season":    meta.get("season", "—"),
            "Design":    meta.get("design", "—"),
            "LO":        meta.get("production_lo", "—"),
            "Sections":  len(sections_with_data),
            "Colorways": len(bom.get("color_bom", pd.DataFrame()).columns)
                         if not bom.get("color_bom", pd.DataFrame()).empty else 0,
        })

    st.dataframe(pd.DataFrame(summary_rows), width='stretch',
                 height=min(80 + 35 * len(summary_rows), 400))

    # ── Inspect individual BOM ────────────────────────────────────────────────
    render_divider()
    selected_style = st.selectbox("Inspect BOM for style", options=all_styles)
    bom_data = bom_dict[selected_style]
    meta     = bom_data.get("metadata", {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Style",         meta.get("style", "—"))
    c2.metric("Season",        meta.get("season", "—"))
    c3.metric("Design",        meta.get("design", "—"))
    c4.metric("Production LO", meta.get("production_lo", "—"))

    render_divider()
    section_keys = [
        k for k, v in bom_data.items()
        if k not in ("metadata", "supplier_lookup")
        and isinstance(v, pd.DataFrame) and not v.empty
    ]
    if not section_keys:
        render_warn_banner("No sections were extracted from this PDF.")
        return

    col_sel, col_search = st.columns([2, 3])
    with col_sel:
        section = st.selectbox("Section", options=section_keys)
    with col_search:
        search = st.text_input("Filter rows", "", placeholder="Search any value...")

    df = bom_data[section]
    view_df = df.copy()
    if search:
        view_df = view_df[view_df.apply(
            lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1
        )]

    render_table_meta(view_df)
    st.dataframe(view_df, width='stretch', height=380)

    render_divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇ Export Section → CSV", data=export_to_csv(view_df),
                           file_name=f"{selected_style}_{section}.csv", mime="text/csv", width='stretch')
    with c2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            for k in section_keys:
                bom_data[k].to_excel(writer, index=False, sheet_name=k[:31])
        st.download_button("⬇ Export All Sections → Excel", data=buf.getvalue(),
                           file_name=f"{selected_style}_sections.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width='stretch')


# ── Helpers for label component extraction ───────────────────────────────────

def _get_components_for_bom(bom_data: dict) -> list:
    from parsers.color_bom import extract_color_bom_lookup
    cb = bom_data.get("color_bom")
    if cb is not None and not cb.empty:
        lookup = extract_color_bom_lookup(cb)
        comps  = lookup.get("components", {})
        if comps:
            result = []
            for name, info in comps.items():
                code = str(info.get("material_code", "")).strip()
                if not code:
                    import re
                    desc = str(info.get("description", ""))
                    m    = re.search(r'(?<!\d)(\d{3,6})(?!\d)', desc)
                    code = m.group(1) if m else ""
                label = f"{name} - {code}" if code else name
                result.append(label)
            return result

    cs = bom_data.get("color_specification")
    if cs is None or cs.empty:
        return []
    comp_col = cs.columns[0]
    return [
        str(r).strip()
        for r in cs[comp_col]
        if str(r).strip() and str(r).strip().lower() not in ("none", "nan", "")
    ]


def _filter_label_components(components: list) -> list:
    """
    Remove 'Label Logo 1' entries from the dropdown list.
    Keeps everything else (Label 1, Care Label, Hangtag, etc.)
    """
    return [
        c for c in components
        if "label logo 1" not in c.lower()
    ]


def _get_label_preview(bom_data: dict, comp_name: str) -> str:
    cs = bom_data.get("color_specification")
    if cs is None or cs.empty or not comp_name:
        return ""
    comp_col      = cs.columns[0]
    colorway_cols = [c for c in cs.columns[1:] if c and not c.startswith("col_")]
    lookup_name   = comp_name.split(" - ")[0].strip() if " - " in comp_name else comp_name
    row_match     = cs[cs[comp_col] == lookup_name]
    if row_match.empty:
        return ""
    sample = {}
    for cw in colorway_cols[:4]:
        val = str(row_match.iloc[0].get(cw, "")).strip()
        if val and val.lower() not in ("none", "nan", ""):
            sample[cw] = val
    return ", ".join(f"{k}: {v}" for k, v in list(sample.items())[:3])


# ── Comparison Tab ────────────────────────────────────────────────────────────

def _read_comparison_file(file) -> pd.DataFrame:
    is_excel = file.name.lower().endswith((".xlsx", ".xls"))
    try:
        df   = pd.read_excel(file, header=0) if is_excel else pd.read_csv(file, header=0)
        cols = [str(c).strip() for c in df.columns]
        meaningful = sum(1 for c in cols if c and not c.startswith("Unnamed") and c.lower() not in ("nan","none"))
        if meaningful >= max(1, len(cols) * 0.4):
            df.columns = cols
            return df[~df.isnull().all(axis=1)].reset_index(drop=True)
    except Exception:
        pass
    file.seek(0) if hasattr(file, "seek") else None
    raw = pd.read_excel(file, header=None, nrows=None) if is_excel else pd.read_csv(file, header=None)
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

    render_info_banner(
        f"{len(bom_dict)} BOM(s) loaded: {', '.join(bom_dict.keys())} "
        "— each Excel row will be matched to the correct BOM by style number."
    )

    comp_file = st.file_uploader(
        "Drop your Comparison Excel or CSV here",
        type=["xlsx", "csv", "xls"], key="cmp_uploader",
        help="Can contain 100+ rows and multiple styles — each row matched automatically"
    )

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
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;
                color:#5a6080;margin-bottom:0.75rem;">Column Mapping</div>""", unsafe_allow_html=True)

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
        style_col = st.selectbox(
            "Buyer Style Number column", options=list(comp_df.columns),
            index=list(comp_df.columns).index(default_style) if default_style in comp_df.columns else 0
        )
    with col_b:
        color_col = st.selectbox(
            "Color / Option column", options=list(comp_df.columns),
            index=list(comp_df.columns).index(default_color) if default_color in comp_df.columns else 0
        )

    # ── Per-BOM label mapping — paginated ────────────────────────────────────
    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;
                color:#5a6080;margin-bottom:0.75rem;">Label Mapping — Per Buyer Style</div>""",
                unsafe_allow_html=True)
    render_info_banner(
        "Select the correct Main Label and Care Label for each style. "
        "'Label Logo 1' entries are excluded from dropdowns automatically."
    )

    label_selections = st.session_state.get("label_selections", {})
    all_style_keys   = list(bom_dict.keys())
    total_styles     = len(all_style_keys)
    total_lm_pages   = max(1, -(-total_styles // STYLES_PER_PAGE))
    lm_page          = st.session_state.get("label_map_page", 0)
    lm_page          = max(0, min(lm_page, total_lm_pages - 1))
    st.session_state["label_map_page"] = lm_page

    # Show page counter
    st.markdown(
        f"<div style='font-size:0.72rem;color:#5a6080;margin-bottom:0.75rem;'>"
        f"Showing styles {lm_page * STYLES_PER_PAGE + 1}–"
        f"{min((lm_page + 1) * STYLES_PER_PAGE, total_styles)} of {total_styles}</div>",
        unsafe_allow_html=True,
    )

    # ── Pagination controls TOP ────────────────────────────────────────────────
    render_pagination("label_map_page", lm_page, total_lm_pages, key_suffix="lm_top")

    # ── Only render the current page slice ────────────────────────────────────
    page_style_keys = all_style_keys[lm_page * STYLES_PER_PAGE : (lm_page + 1) * STYLES_PER_PAGE]

    for style_key in page_style_keys:
        bom_data   = bom_dict[style_key]
        all_comps  = _get_components_for_bom(bom_data)
        components = _filter_label_components(all_comps)

        if not components:
            st.markdown(
                f"""<div style="font-size:0.8rem;color:#f59e0b;padding:6px 0;">
                ⚠ Style <b>{style_key}</b> — no label components found.</div>""",
                unsafe_allow_html=True
            )
            continue

        st.markdown(
            f"""<div style="font-size:0.88rem;font-weight:600;color:#3b82f6;
            margin-top:0.8rem;margin-bottom:0.3rem;border-left:3px solid #3b82f6;padding-left:0.6rem;">
            {style_key}</div>""",
            unsafe_allow_html=True
        )

        saved = label_selections.get(style_key, {})

        def _best_default(saved_val, preferred_names, _comps=components):
            if saved_val and saved_val in _comps:
                return saved_val
            for preferred in preferred_names:
                for comp in _comps:
                    if preferred.lower() in comp.lower():
                        return comp
            return _comps[0]

        default_main = _best_default(saved.get("main_label", ""), ["Logo Label", "Main Label"])
        default_care = _best_default(saved.get("care_label", ""), ["Label 1", "Care Label", "Label1"])

        col_c, col_d = st.columns(2)
        with col_c:
            main_sel = st.selectbox(
                f"Main Label — {style_key}", options=components,
                index=components.index(default_main) if default_main in components else 0,
                key=f"main_label_{style_key}"
            )
        with col_d:
            care_sel = st.selectbox(
                f"Care Label — {style_key}", options=components,
                index=components.index(default_care) if default_care in components else 0,
                key=f"care_label_{style_key}"
            )

        label_selections[style_key] = {"main_label": main_sel, "care_label": care_sel}

    st.session_state["label_selections"] = label_selections

    # ── Pagination controls BOTTOM ─────────────────────────────────────────────
    render_pagination("label_map_page", lm_page, total_lm_pages, key_suffix="lm_bottom")

    # ── File preview ──────────────────────────────────────────────────────────
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
            render_warn_banner(f"No BOM found for style(s): {', '.join(unmatched)} — upload the matching PDF(s)")

    render_divider()
    if st.button("▶ Run Validation & Auto-Fill"):
        with st.spinner("Matching rows to BOMs and filling columns..."):
            renamed_df = comp_df.rename(columns={style_col: "Buyer Style Number", color_col: "Color/Option"})
            label_sels = st.session_state.get("label_selections", {})

            result_parts = []
            for style_val, group_df in renamed_df.groupby("Buyer Style Number", sort=False):
                style_str    = str(style_val).strip().upper()
                matched_bom  = None
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
                    group_df["Validation Status"] = f"❌ Error: No BOM loaded for style '{style_str}'"
                    result_parts.append(group_df)
                    continue

                per_style_labels = label_sels.get(matched_bom_key, {})
                bom_with_labels  = dict(matched_bom)
                bom_with_labels["selected_main_label_comp"] = per_style_labels.get("main_label")
                bom_with_labels["selected_care_label_comp"] = per_style_labels.get("care_label")

                result_parts.append(validate_and_fill(
                    comparison_df=group_df.reset_index(drop=True),
                    bom_data=bom_with_labels,
                ))

            st.session_state["validation_result"] = (
                pd.concat(result_parts, ignore_index=True) if result_parts else renamed_df
            )

    render_results()


def render_results():
    if "validation_result" not in st.session_state:
        return
    res = st.session_state["validation_result"]
    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;
                color:#5a6080;margin-bottom:0.75rem;">Validation Summary</div>""", unsafe_allow_html=True)
    status_counts = res["Validation Status"].value_counts(dropna=False).to_dict() if "Validation Status" in res.columns else {}
    ok      = status_counts.get("✅ Validated", 0)
    partial = status_counts.get("⚠️ Partial", 0)
    err     = sum(v for k, v in status_counts.items() if str(k).startswith("❌"))
    render_validation_summary(ok, partial, err, len(res))
    render_table_meta(res)
    st.dataframe(res, width='stretch', height=400)
    render_divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇ Export Results → CSV", data=export_to_csv(res),
                           file_name="validated_bom.csv", mime="text/csv", width='stretch')
    with c2:
        xls = export_to_excel(result_df=res, original_df=st.session_state.get("comparison_raw", pd.DataFrame()))
        st.download_button("⬇ Export Results → Excel", data=xls, file_name="validated_bom.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width='stretch')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    render_sidebar()
    tab1, tab2 = st.tabs(["  📄  PDF Extraction  ", "  🔍  BOM Comparison & Validation  "])
    with tab1:
        render_pdf_tab()
    with tab2:
        render_comparison_tab()

if __name__ == "__main__":
    main()