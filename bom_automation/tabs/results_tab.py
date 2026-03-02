"""tabs/results_tab.py — Results & Export tab."""
from html import escape
import pandas as pd
import streamlit as st

from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from .utils import (
    RESULTS_PER_PAGE_GRID, RESULTS_PER_PAGE_TILE, RESULTS_PER_PAGE_LIST,
    render_section_header, render_divider, render_info_banner, render_warn_banner,
    render_validation_summary, render_validation_progress,
    render_pagination, render_view_toggle,
    _status_style, _status_accent_color, _style_validation_status,
    _infer_material_from_row, _colors_for_style, _precompute_style_colors,
    _status_counts, _build_detail_card_html,
)

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