import io
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from parsers.pdf_parser import parse_bom_pdf
from validators.filler import validate_and_fill

st.set_page_config(
    page_title="Columbia BOM Automation",
    page_icon="🧢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Tailwind + Custom CSS ─────────────────────────────────────────────────────
st.markdown("""
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    theme: {
      extend: {
        fontFamily: {
          display: ['Inter', 'sans-serif'],
          body:    ['Inter', 'sans-serif'],
          mono:    ['JetBrains Mono', 'monospace'],
        },
        colors: {
          base:    '#0f1117',
          surface: '#13151e',
          border:  '#1e2130',
          muted:   '#5a6080',
          accent:  '#3b82f6',
        }
      }
    }
  }
</script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background:#0f1117;
    color:#e8e8e8;
    font-size: 14px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding: 2rem 2.5rem !important; max-width: 100% !important; }
  section[data-testid="stSidebar"] { background:#13151e; border-right:1px solid #1e2130; }
  section[data-testid="stSidebar"] .block-container { padding:1.5rem 1.2rem !important; }
  [data-testid="stMetric"] { background:#13151e; border:1px solid #1e2130; border-radius:10px; padding:1rem 1.2rem; }
  [data-testid="stMetricLabel"] p {
    font-family: 'Inter', sans-serif !important;
    font-size:0.72rem !important;
    font-weight: 500 !important;
    text-transform:uppercase;
    letter-spacing:0.08em;
    color:#9ca3af !important;
  }
  [data-testid="stMetricValue"] {
    font-family: 'Inter', sans-serif !important;
    font-size:1.4rem !important;
    font-weight:600 !important;
    color:#fff !important;
  }
  .stDataFrame { border-radius:8px; overflow:hidden; border:1px solid #1e2130; }
  .stDataFrame td, .stDataFrame th {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.82rem !important;
  }
  .stButton > button, .stDownloadButton > button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.03em !important;
    text-transform: uppercase !important;
    border-radius: 8px !important;
    border: 1px solid #2a2d3e !important;
    background: #13151e !important;
    color: #e8e8e8 !important;
    transition: all 0.15s ease !important;
    padding: 0.5rem 1.2rem !important;
  }
  .stButton > button:hover, .stDownloadButton > button:hover {
    background: #1e2130 !important;
    border-color: #3b82f6 !important;
    color: #fff !important;
  }
  [data-testid="stFileUploader"] {
    border: 1.5px dashed #2a2d3e !important;
    border-radius: 12px !important;
    background: #13151e !important;
    transition: border-color 0.2s ease;
  }
  [data-testid="stSelectbox"] > div > div {
    background: #13151e !important;
    border: 1px solid #2a2d3e !important;
    border-radius: 8px !important;
    color: #e8e8e8 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.85rem !important;
  }
  [data-testid="stTextInput"] > div > div > input {
    background: #13151e !important;
    border: 1px solid #2a2d3e !important;
    border-radius: 8px !important;
    color: #e8e8e8 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.82rem !important;
  }
  [data-testid="stExpander"] {
    border: 1px solid #1e2130 !important;
    border-radius: 8px !important;
    background: #13151e !important;
  }
  [data-testid="stExpander"] p, [data-testid="stExpander"] li {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.84rem !important;
    line-height: 1.7 !important;
    color: #d1d5db !important;
  }
  button[data-baseweb="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
  }
  p, li, span, div {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════

def render_section_header(title: str, subtitle: str = ""):
    st.markdown(f"""
    <div class="mb-6">
      <h2 style="font-family:'Syne',sans-serif; font-size:1.45rem; font-weight:700;
                 color:#fff; letter-spacing:-0.01em; margin-bottom:0.15rem;">{title}</h2>
      {"<p style='font-size:0.75rem; color:#5a6080; text-transform:uppercase; letter-spacing:0.08em;'>" + subtitle + "</p>" if subtitle else ""}
      <div style="height:2px; background:linear-gradient(90deg,#3b82f6 0%,transparent 70%);
                  margin-top:0.5rem; border:none;"></div>
    </div>
    """, unsafe_allow_html=True)


def render_divider():
    st.markdown('<div style="height:1px; background:#1e2130; margin:1.5rem 0;"></div>', unsafe_allow_html=True)


def render_info_banner(message: str):
    st.markdown(f"""
    <div style="background:#0d1a2e; border:1px solid #1e3a5f; border-left:3px solid #3b82f6;
                border-radius:8px; padding:0.85rem 1.1rem; font-size:0.82rem;
                color:#93c5fd; margin-bottom:1.2rem;">
      ℹ &nbsp;{message}
    </div>""", unsafe_allow_html=True)


def render_warn_banner(message: str):
    st.markdown(f"""
    <div style="background:#1c1500; border:1px solid #3d2e00; border-left:3px solid #f59e0b;
                border-radius:8px; padding:0.85rem 1.1rem; font-size:0.82rem;
                color:#fcd34d; margin-bottom:1.2rem;">
      ⚠ &nbsp;{message}
    </div>""", unsafe_allow_html=True)


def render_table_meta(df: pd.DataFrame):
    st.markdown(f"""
    <div style="font-size:0.72rem; color:#5a6080; margin-bottom:0.5rem;
                letter-spacing:0.05em; text-transform:uppercase;">
      {len(df)} rows &nbsp;·&nbsp; {len(df.columns)} columns
    </div>""", unsafe_allow_html=True)


def render_validation_summary(ok: int, partial: int, err: int, total: int):
    st.markdown(f"""
    <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:1rem; margin-bottom:1.5rem;">
      <div style="background:#0d2218; border:1px solid #1a4a30; border-radius:10px;
                  padding:1rem 1.2rem; text-align:center;">
        <div style="font-family:'Syne',sans-serif; font-size:2rem; font-weight:800;
                    color:#34d399; line-height:1;">{ok}</div>
        <div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:0.1em;
                    margin-top:0.3rem; color:#6b7280;">Validated</div>
      </div>
      <div style="background:#1c1500; border:1px solid #3d2e00; border-radius:10px;
                  padding:1rem 1.2rem; text-align:center;">
        <div style="font-family:'Syne',sans-serif; font-size:2rem; font-weight:800;
                    color:#f59e0b; line-height:1;">{partial}</div>
        <div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:0.1em;
                    margin-top:0.3rem; color:#6b7280;">Partial</div>
      </div>
      <div style="background:#1e0d0d; border:1px solid #4a1a1a; border-radius:10px;
                  padding:1rem 1.2rem; text-align:center;">
        <div style="font-family:'Syne',sans-serif; font-size:2rem; font-weight:800;
                    color:#f87171; line-height:1;">{err}</div>
        <div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:0.1em;
                    margin-top:0.3rem; color:#6b7280;">Errors</div>
      </div>
      <div style="background:#13151e; border:1px solid #1e2130; border-radius:10px;
                  padding:1rem 1.2rem; text-align:center;">
        <div style="font-family:'Syne',sans-serif; font-size:2rem; font-weight:800;
                    color:#9ca3af; line-height:1;">{total}</div>
        <div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:0.1em;
                    margin-top:0.3rem; color:#6b7280;">Total Rows</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_bom_meta_card(meta: dict):
    st.markdown(f"""
    <div style="font-size:0.75rem; color:#6b7280; line-height:2.2; margin-top:0.5rem;">
      <div><span style="color:#9ca3af; display:inline-block; width:80px;">Style</span>
           <span style="color:#e8e8e8; font-family:'DM Mono',monospace;">{meta.get('style','—')}</span></div>
      <div><span style="color:#9ca3af; display:inline-block; width:80px;">Season</span>
           <span style="color:#e8e8e8; font-family:'DM Mono',monospace;">{meta.get('season','—')}</span></div>
      <div><span style="color:#9ca3af; display:inline-block; width:80px;">Design</span>
           <span style="color:#e8e8e8; font-family:'DM Mono',monospace;">{meta.get('design','—')}</span></div>
      <div><span style="color:#9ca3af; display:inline-block; width:80px;">LO</span>
           <span style="color:#e8e8e8; font-family:'DM Mono',monospace;">{meta.get('production_lo','—')}</span></div>
    </div>
    """, unsafe_allow_html=True)


def render_status_badge(loaded: bool):
    if loaded:
        st.markdown("""
        <div style="display:inline-flex; align-items:center; gap:6px; padding:5px 12px;
                    border-radius:20px; font-size:0.72rem; font-weight:500;
                    letter-spacing:0.06em; text-transform:uppercase; margin-bottom:1.2rem;
                    background:#0d2218; color:#34d399; border:1px solid #1a4a30;">
          ⬤ &nbsp;BOM Loaded
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="display:inline-flex; align-items:center; gap:6px; padding:5px 12px;
                    border-radius:20px; font-size:0.72rem; font-weight:500;
                    letter-spacing:0.06em; text-transform:uppercase; margin-bottom:1.2rem;
                    background:#1e1e2e; color:#6b7280; border:1px solid #2a2a3e;">
          ⬤ &nbsp;No BOM Loaded
        </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE SECTIONS
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar():
    with st.sidebar:
        st.markdown("""
        <div style="font-family:'Syne',sans-serif; font-size:1.15rem; font-weight:800;
                    letter-spacing:0.04em; color:#fff; line-height:1.2; margin-bottom:0.2rem;">
          Columbia BOM<br>Automation
        </div>
        <div style="font-size:0.7rem; font-weight:400; color:#5a6080; letter-spacing:0.12em;
                    text-transform:uppercase; margin-bottom:1.5rem;">
          Trim & Label Validator
        </div>
        """, unsafe_allow_html=True)

        pdf_loaded = "bom_data" in st.session_state
        render_status_badge(pdf_loaded)

        with st.expander("How to use", expanded=False):
            st.markdown("""
            **Step 1** — Go to **PDF Extraction** and upload your Columbia BOM PDF.

            **Step 2** — Inspect the parsed sections to verify extraction.

            **Step 3** — Go to **BOM Comparison**, upload your comparison Excel/CSV.

            **Step 4** — Map columns, run validation, export the enriched file.
            """)

        render_divider()

        if st.button("🗑 Clear All Data", use_container_width=True):
            for k in ["bom_data", "comparison_raw", "validation_result"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

        if pdf_loaded:
            render_divider()
            st.markdown("""
            <div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:0.1em;
                        color:#5a6080; margin-bottom:0.5rem;">Loaded BOM</div>
            """, unsafe_allow_html=True)
            render_bom_meta_card(st.session_state["bom_data"].get("metadata", {}))


def render_pdf_tab():
    render_section_header("PDF Extraction", "Upload & inspect BOM sections")

    uploaded_pdf = st.file_uploader(
        "Drop your Columbia BOM PDF here",
        type=["pdf"],
        key="pdf_uploader",
        help="Supports Columbia BOM PDFs with Color BOM, Costing, Care/Content reports"
    )

    if uploaded_pdf is None:
        render_info_banner("Upload a Columbia BOM PDF above to extract and inspect all sections.")
        return

    try:
        with st.spinner("Parsing BOM sections..."):
            bom_data = parse_bom_pdf(uploaded_pdf)
        st.session_state["bom_data"] = bom_data
        meta = bom_data.get("metadata", {})

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Style", meta.get("style", "—"))
        c2.metric("Season", meta.get("season", "—"))
        c3.metric("Design", meta.get("design", "—"))
        c4.metric("Production LO", meta.get("production_lo", "—"))

        render_divider()

        section_keys = [k for k, v in bom_data.items() if k != "metadata" and isinstance(v, pd.DataFrame)]
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
        st.dataframe(view_df, use_container_width=True, height=380)

        render_divider()
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇ Export Section → CSV",
                data=export_to_csv(view_df),
                file_name=f"{section}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with c2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                for k in section_keys:
                    bom_data[k].to_excel(writer, index=False, sheet_name=k[:31])
            st.download_button(
                "⬇ Export All Sections → Excel",
                data=buffer.getvalue(),
                file_name="bom_sections.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    except Exception as e:
        st.error(f"Failed to parse PDF: {e}")


def _read_comparison_file(file) -> pd.DataFrame:
    if file.name.lower().endswith((".xlsx", ".xls")):
        raw = pd.read_excel(file, header=None)
    else:
        raw = pd.read_csv(file, header=None)

    header_row_idx = 0
    for i, row in raw.iterrows():
        non_empty = sum(1 for v in row if str(v).strip() not in ("", "nan", "None"))
        if non_empty >= max(1, len(raw.columns) * 0.5):
            header_row_idx = i
            break

    raw.columns = raw.iloc[header_row_idx].astype(str).str.strip()
    df = raw[header_row_idx + 1:].reset_index(drop=True)
    df = df[~df.isnull().all(axis=1)].reset_index(drop=True)
    return df


def render_comparison_tab():
    render_section_header("BOM Comparison & Validation", "Auto-fill trim & label data from BOM")

    if "bom_data" not in st.session_state:
        render_warn_banner("No BOM loaded. Please upload a Columbia BOM PDF in the PDF Extraction tab first.")
        return

    comp_file = st.file_uploader(
        "Drop your Comparison Excel or CSV here",
        type=["xlsx", "csv", "xls"],
        key="cmp_uploader",
        help="Must contain Buyer Style Number and Color/Option columns"
    )

    if comp_file is not None:
        try:
            comp_df = _read_comparison_file(comp_file)
            st.session_state["comparison_raw"] = comp_df

            render_divider()
            st.markdown("""
            <div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:0.1em;
                        color:#5a6080; margin-bottom:0.75rem;">Column Mapping</div>
            """, unsafe_allow_html=True)

            col_a, col_b = st.columns(2)
            with col_a:
                style_col = st.selectbox(
                    "Buyer Style Number column",
                    options=list(comp_df.columns),
                    help="Column containing the style code e.g. CL2880"
                )
            with col_b:
                color_col = st.selectbox(
                    "Color / Option column",
                    options=list(comp_df.columns),
                    help="Column containing colorway e.g. 010, Black, 278-Dark Stone"
                )

            render_divider()
            render_table_meta(comp_df)
            st.dataframe(comp_df.head(50), use_container_width=True, height=280)

            render_divider()
            if st.button("▶ Run Validation & Auto-Fill"):
                with st.spinner("Matching BOM data and filling columns..."):
                    result_df = validate_and_fill(
                        comparison_df=comp_df.rename(columns={
                            style_col: "Buyer Style Number",
                            color_col: "Color/Option"
                        }),
                        bom_data=st.session_state["bom_data"],
                    )
                    st.session_state["validation_result"] = result_df

        except Exception as e:
            st.error(f"Failed to read comparison file: {e}")

    render_results()


def render_results():
    if "validation_result" not in st.session_state:
        return

    res = st.session_state["validation_result"]

    render_divider()
    st.markdown("""
    <div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:0.1em;
                color:#5a6080; margin-bottom:0.75rem;">Validation Summary</div>
    """, unsafe_allow_html=True)

    status_counts = res["Validation Status"].value_counts(dropna=False).to_dict() if "Validation Status" in res.columns else {}
    ok      = status_counts.get("✅ Validated", 0)
    partial = status_counts.get("⚠️ Partial", 0)
    err     = sum(v for k, v in status_counts.items() if str(k).startswith("❌"))
    render_validation_summary(ok, partial, err, len(res))

    render_table_meta(res)
    st.dataframe(res, use_container_width=True, height=400)

    render_divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇ Export Results → CSV",
            data=export_to_csv(res),
            file_name="validated_bom.csv",
            mime="text/csv",
            use_container_width=True
        )
    with c2:
        xls_bytes = export_to_excel(
            result_df=res,
            original_df=st.session_state.get("comparison_raw", pd.DataFrame())
        )
        st.download_button(
            "⬇ Export Results → Excel",
            data=xls_bytes,
            file_name="validated_bom.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    render_sidebar()
    tab1, tab2 = st.tabs(["  📄  PDF Extraction  ", "  🔍  BOM Comparison & Validation  "])
    with tab1:
        render_pdf_tab()
    with tab2:
        render_comparison_tab()


if __name__ == "__main__":
    main()