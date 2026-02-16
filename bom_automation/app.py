import io
import pandas as pd
import streamlit as st

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from parsers.pdf_parser import parse_bom_pdf
from validators.filler import validate_and_fill

st.set_page_config(page_title="Columbia BOM Automation Tool", page_icon="🧢", layout="wide")

# Sidebar
with st.sidebar:
    st.markdown("## 🧢 Columbia BOM Automation")
    with st.expander("How to use", expanded=False):
        st.markdown(
            "1. Upload a BOM PDF in the PDF Extraction tab and inspect sections.\n"
            "2. Switch to the Comparison tab, upload your comparison file, map columns.\n"
            "3. Run validation and export enriched Excel/CSV."
        )
    pdf_loaded = "bom_data" in st.session_state
    st.markdown(f"PDF loaded: {'✅' if pdf_loaded else '❌'}")
    if st.button("Clear All Data"):
        for k in ["bom_data", "comparison_raw", "validation_result"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()


tab1, tab2 = st.tabs(["📄 PDF Extraction", "🔍 BOM Comparison & Validation"])

# TAB 1 - PDF Extraction
with tab1:
    st.markdown("### PDF Extraction")
    uploaded_pdf = st.file_uploader("Drop BOM PDF here", type=["pdf"], key="pdf_uploader")

    if uploaded_pdf is not None:
        try:
            with st.spinner("Parsing BOM PDF..."):
                bom_data = parse_bom_pdf(uploaded_pdf)
            st.session_state["bom_data"] = bom_data
            meta = bom_data.get("metadata", {})

            # Metadata card
            cols = st.columns(4)
            cols[0].metric("Style", meta.get("style", "-"))
            cols[1].metric("Season", meta.get("season", "-"))
            cols[2].metric("Design", meta.get("design", "-"))
            cols[3].metric("Production LO", meta.get("production_lo", "-"))

            # Section selector
            section_keys = [k for k, v in bom_data.items() if k != "metadata" and isinstance(v, pd.DataFrame)]
            if section_keys:
                section = st.selectbox("Select a section to view", options=section_keys)
                df = bom_data[section]

                # Simple search filter
                search = st.text_input("Row filter (contains)", "")
                view_df = df.copy()
                if search:
                    view_df = view_df[view_df.apply(
                        lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1
                    )]

                st.dataframe(view_df, use_container_width=True)

                c1, c2 = st.columns(2)
                with c1:
                    csv_bytes = export_to_csv(view_df)
                    st.download_button(
                        "⬇ Export This Section to CSV",
                        data=csv_bytes,
                        file_name=f"{section}.csv",
                        mime="text/csv"
                    )
                with c2:
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                        for k in section_keys:
                            bom_data[k].to_excel(writer, index=False, sheet_name=k[:31])
                    st.download_button(
                        "⬇ Export All Sections to Excel",
                        data=buffer.getvalue(),
                        file_name="bom_sections.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

        except Exception as e:
            st.error(f"Failed to parse PDF: {e}")

# TAB 2 - Comparison & Validation
with tab2:
    st.markdown("### BOM Comparison & Validation")
    if "bom_data" not in st.session_state:
        st.warning("Please upload a BOM PDF in the PDF Extraction tab first.")
    else:
        comp_file = st.file_uploader(
            "Drop Comparison Excel/CSV here",
            type=["xlsx", "csv", "xls"],
            key="cmp_uploader"
        )
        if comp_file is not None:
            try:
                if comp_file.name.lower().endswith((".xlsx", ".xls")):
                    comp_df = pd.read_excel(comp_file)
                else:
                    comp_df = pd.read_csv(comp_file)
                st.session_state["comparison_raw"] = comp_df

                st.markdown("#### Column Mapping")
                style_col = st.selectbox("Which column is 'Buyer Style Number'?", options=list(comp_df.columns))
                color_col = st.selectbox("Which column is 'Color/Option'?", options=list(comp_df.columns))

                st.markdown("#### Preview")
                st.dataframe(comp_df.head(50), use_container_width=True)

                if st.button("▶ Run Validation & Auto-Fill"):
                    with st.spinner("Validating and filling BOM data..."):
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

        if "validation_result" in st.session_state:
            res = st.session_state["validation_result"]
            st.markdown("#### Results")
            st.dataframe(res, use_container_width=True)

            status_counts = res["Validation Status"].value_counts(dropna=False).to_dict() if "Validation Status" in res.columns else {}
            ok      = status_counts.get("✅ Validated", 0)
            partial = status_counts.get("⚠️ Partial", 0)
            err     = sum(v for k, v in status_counts.items() if str(k).startswith("❌"))
            c1, c2, c3 = st.columns(3)
            c1.metric("Validated", ok)
            c2.metric("Partial", partial)
            c3.metric("Errors", err)

            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "⬇ Export Result to CSV",
                    data=export_to_csv(res),
                    file_name="validated_bom.csv",
                    mime="text/csv",
                )
            with c2:
                xls_bytes = export_to_excel(
                    result_df=res,
                    original_df=st.session_state.get("comparison_raw", pd.DataFrame())
                )
                st.download_button(
                    "⬇ Export Result to Excel",
                    data=xls_bytes,
                    file_name="validated_bom.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )