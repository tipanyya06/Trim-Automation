"""
app.py — Columbia BOM Automation entry point.

Structure:
    app.py                  ← this file (page config + wiring only)
    ui_styles.py            ← all THEME_CSS
    tabs/
        __init__.py         ← re-exports all render_*() functions
        utils.py            ← shared helpers, constants, dialogs, card builders
        pdf_tab.py          ← 📄 PDF Extraction
        compare_tab.py      ← 🔍 BOM Comparison & Validation
        results_tab.py      ← 📊 Results & Export
        qa_tab.py           ← 🧪 QA Comparison
"""
import sys
import streamlit as st

# Set page config early, before importing other modules
try:
    st.set_page_config(
        page_title="Columbia BOM Automation",
        page_icon="\U0001f9e2",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception as e:
    print(f"Warning: Page config error (non-fatal): {e}", file=sys.stderr)

# Import tab modules with error handling
try:
    from tabs.utils import (
        TAB_PDF, TAB_COMPARE, TAB_RESULTS, TAB_QA,
        inject_theme, render_sidebar,
    )
    from tabs import (
        render_pdf_tab,
        render_comparison_tab,
        render_results,
        render_qa_tab,
    )
except ImportError as e:
    st.error(f"Failed to load app modules: {e}")
    st.stop()


def main():
    try:
        inject_theme()
        render_sidebar()
        tab_labels  = [TAB_PDF, TAB_COMPARE, TAB_RESULTS, TAB_QA]
        default_tab = st.session_state.pop("next_active_tab", None)
        default_tab = default_tab if default_tab in tab_labels else None
        tab1, tab2, tab3, tab4 = st.tabs(tab_labels, default=default_tab)
        with tab1:
            render_pdf_tab()
        with tab2:
            render_comparison_tab()
        with tab3:
            render_results()
        with tab4:
            render_qa_tab()
    except Exception as e:
        st.error(f"Application error: {str(e)}")
        import traceback
        st.error(traceback.format_exc())


if __name__ == "__main__":
    main()