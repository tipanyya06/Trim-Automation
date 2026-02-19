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
  #MainMenu, footer, header { visibility:hidden; }
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
</style>
""", unsafe_allow_html=True)


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
        if st.button("🗑 Clear All Data", use_container_width=True):
            for k in ["bom_dict", "comparison_raw", "validation_result",
                      "label_selections"]:
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

    # Parse and store all PDFs
    bom_dict = st.session_state.get("bom_dict", {})
    newly_parsed = []
    with st.spinner(f"Parsing {len(uploaded_pdfs)} PDF(s)..."):
        for pdf_file in uploaded_pdfs:
            try:
                bom_data = parse_bom_pdf(pdf_file)
                style = bom_data.get("metadata", {}).get("style") or pdf_file.name
                bom_dict[style] = bom_data
                newly_parsed.append(style)
            except Exception as e:
                st.error(f"Failed to parse {pdf_file.name}: {e}")
    st.session_state["bom_dict"] = bom_dict

    if not bom_dict:
        return

    render_info_banner(f"Loaded {len(bom_dict)} BOM(s): {', '.join(bom_dict.keys())}")

    # ── Summary table of all loaded BOMs ─────────────────────────────────────
    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;
                color:#5a6080;margin-bottom:0.75rem;">Loaded BOMs</div>""", unsafe_allow_html=True)

    summary_rows = []
    for style, bom in bom_dict.items():
        meta = bom.get("metadata", {})
        sections_with_data = [k for k, v in bom.items()
                               if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty]
        summary_rows.append({
            "Style":        style,
            "Season":       meta.get("season", "—"),
            "Design":       meta.get("design", "—"),
            "LO":           meta.get("production_lo", "—"),
            "Sections":     len(sections_with_data),
            "Colorways":    len(bom.get("color_bom", pd.DataFrame()).columns) if not bom.get("color_bom", pd.DataFrame()).empty else 0,
        })
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, height=min(80 + 35 * len(summary_rows), 300))

    # ── Inspect individual BOM ────────────────────────────────────────────────
    render_divider()
    selected_style = st.selectbox("Inspect BOM for style", options=list(bom_dict.keys()))
    bom_data = bom_dict[selected_style]
    meta = bom_data.get("metadata", {})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Style",  meta.get("style", "—"))
    c2.metric("Season", meta.get("season", "—"))
    c3.metric("Design", meta.get("design", "—"))
    c4.metric("Production LO", meta.get("production_lo", "—"))

    render_divider()
    section_keys = [k for k, v in bom_data.items()
                    if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty]
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
        st.download_button("⬇ Export Section → CSV", data=export_to_csv(view_df),
                           file_name=f"{selected_style}_{section}.csv", mime="text/csv", use_container_width=True)
    with c2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            for k in section_keys:
                bom_data[k].to_excel(writer, index=False, sheet_name=k[:31])
        st.download_button("⬇ Export All Sections → Excel", data=buf.getvalue(),
                           file_name=f"{selected_style}_sections.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)




# ── Helpers for label component extraction ───────────────────────────────────

def _get_components_for_bom(bom_data: dict) -> list:
    """Return list of component names from the color_specification of a BOM."""
    cs = bom_data.get("color_specification")
    if cs is None or cs.empty:
        return []
    comp_col = cs.columns[0]
    return [
        str(r).strip()
        for r in cs[comp_col]
        if str(r).strip() and str(r).strip().lower() not in ("none", "nan", "")
    ]


def _get_label_preview(bom_data: dict, comp_name: str, matched_cw: str = None) -> str:
    """Return a short color preview string for a component + colorway."""
    cs = bom_data.get("color_specification")
    if cs is None or cs.empty or not comp_name:
        return ""
    comp_col = cs.columns[0]
    colorway_cols = [c for c in cs.columns[1:] if c and not c.startswith("col_")]
    row_match = cs[cs[comp_col] == comp_name]
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
    raw = pd.read_excel(file, header=None) if file.name.lower().endswith((".xlsx", ".xls")) else pd.read_csv(file, header=None)
    header_row_idx = 0
    for i, row in raw.iterrows():
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

    # ── Per-BOM label mapping ─────────────────────────────────────────────────
    render_divider()
    st.markdown("""<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;
                color:#5a6080;margin-bottom:0.75rem;">Label Mapping — Per Buyer Style</div>""",
                unsafe_allow_html=True)
    render_info_banner(
        "Each loaded BOM has its own label component options. "
        "Select the correct Main Label and Care Label component for each style below."
    )

    label_selections = st.session_state.get("label_selections", {})

    for style_key, bom_data in bom_dict.items():
        components = _get_components_for_bom(bom_data)
        if not components:
            st.markdown(
                f"""<div style="font-size:0.8rem;color:#f59e0b;padding:6px 0;">
                ⚠ Style <b>{style_key}</b> — no color specification components found.</div>""",
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

        # Smart defaults: "Label Logo 1" for Main Label, "Label 1" for Care Label
        # Priority: 1) previously saved user selection  2) preferred name match  3) first item
        def _best_default(saved_val, preferred_names):
            if saved_val and saved_val in components:
                return saved_val
            for preferred in preferred_names:
                for comp in components:
                    if preferred.lower() in comp.lower():
                        return comp
            return components[0]

        default_main = _best_default(
            saved.get("main_label", ""),
            ["Label Logo 1", "Logo Label", "Label Logo"]
        )
        default_care = _best_default(
            saved.get("care_label", ""),
            ["Label 1", "Care Label", "Label1"]
        )

        col_c, col_d = st.columns(2)
        with col_c:
            main_sel = st.selectbox(
                f"Main Label — {style_key}",
                options=components,
                index=components.index(default_main) if default_main in components else 0,
                key=f"main_label_{style_key}"
            )
        with col_d:
            care_sel = st.selectbox(
                f"Care Label — {style_key}",
                options=components,
                index=components.index(default_care) if default_care in components else 0,
                key=f"care_label_{style_key}"
            )

        # Show color preview for selected components
        main_preview = _get_label_preview(bom_data, main_sel)
        care_preview = _get_label_preview(bom_data, care_sel)
        if main_preview:
            render_info_banner(f"Main Label colors → {main_preview}")
        if care_preview and care_sel != main_sel:
            render_info_banner(f"Care Label colors → {care_preview}")

        label_selections[style_key] = {"main_label": main_sel, "care_label": care_sel}

    st.session_state["label_selections"] = label_selections

    # ── File preview ──────────────────────────────────────────────────────────
    render_divider()
    render_table_meta(comp_df)
    st.dataframe(comp_df.head(100), use_container_width=True, height=280)

    # Show which styles in the Excel map to loaded BOMs
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
                style_str = str(style_val).strip().upper()
                matched_bom = None
                matched_bom_key = None

                for bom_style, bom in bom_dict.items():
                    bs = str(bom_style).strip().upper()
                    if style_str == bs or style_str in bs or bs in style_str:
                        matched_bom = bom
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

                # Attach per-style label selections
                per_style_labels = label_sels.get(matched_bom_key, {})
                bom_with_labels = dict(matched_bom)
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
    st.dataframe(res, use_container_width=True, height=400)
    render_divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇ Export Results → CSV", data=export_to_csv(res),
                           file_name="validated_bom.csv", mime="text/csv", use_container_width=True)
    with c2:
        xls = export_to_excel(result_df=res, original_df=st.session_state.get("comparison_raw", pd.DataFrame()))
        st.download_button("⬇ Export Results → Excel", data=xls, file_name="validated_bom.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)


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