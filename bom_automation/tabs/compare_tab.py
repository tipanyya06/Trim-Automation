"""tabs/compare_tab.py — BOM Comparison & Validation tab."""
from html import escape
import io as _io
import re as _re
import pandas as pd
import streamlit as st

from validators.matcher import auto_detect_columns, get_product_type
from validators.filler import validate_and_fill, NEW_COLUMNS, QUICK_COLUMNS, QUICK_COLUMN_REMAP
from exporters.excel_exporter import export_to_excel
from exporters.csv_exporter import export_to_csv
from .utils import (
    render_section_header, render_divider, render_info_banner, render_warn_banner,
    render_pagination, render_view_toggle,
    _status_style, _status_accent_color, _style_color_hint,
    _style_validation_status, _resolve_style_key,
    _styles_match, _find_matching_bom, _infer_material_from_row,
    _precompute_style_colors, _colors_for_style,
    show_conflict_dialog, show_bom_inspector, show_validation_complete_dialog,
    STYLES_PER_PAGE, QUICK_SETTING_FIELDS, QUICK_SETTING_LABELS,
    HANGTAG_RFID_OUTPUT_COLS,
)
def _get_components_for_bom(bom_data):
    from parsers.color_bom import extract_color_bom_lookup
    components = []
    seen_names = set()

    # ── 1. Color BOM components ───────────────────────────────────────────────
    cb = bom_data.get("color_bom")
    if cb is not None and not cb.empty:
        lookup = extract_color_bom_lookup(cb)
        comps  = lookup.get("components", {})
        cd_enrich = bom_data.get("costing_detail")
        for name, info in comps.items():
            code = str(info.get("material_code", "")).strip()
            if not code:
                m = _re.search(r'(?<!\d)(\d{5,7})(?!\d)', str(info.get("description", "")))
                code = m.group(1) if m else ""
            if not code:
                for cw_val in info.get("colorways", {}).values():
                    cv = str(cw_val).strip()
                    if _re.match(r'^\d{5,7}$', cv):
                        code = cv
                        break
            if not code:
                comp_col = cb.columns[0]
                row_match = cb[cb[comp_col].astype(str).str.strip().str.lower() == name.lower()]
                if not row_match.empty:
                    for col in cb.columns[1:]:
                        cv = str(row_match.iloc[0][col]).strip()
                        if _re.match(r'^\d{5,7}$', cv):
                            code = cv
                            break
            if not code and cd_enrich is not None and not cd_enrich.empty:
                desc_col_c = next(
                    (c for c in cd_enrich.columns if "desc" in str(c).lower()),
                    cd_enrich.columns[0],
                )
                name_lower = name.lower()
                for _, crow in cd_enrich.iterrows():
                    row_desc = str(crow.get(desc_col_c, "")).strip().lower()
                    if name_lower in row_desc or row_desc in name_lower:
                        for col in cd_enrich.columns:
                            cv = str(crow.get(col, "")).strip()
                            if _re.match(r'^\d{5,7}$', cv):
                                code = cv
                                break
                    if code:
                        break
                if not code:
                    for _, crow in cd_enrich.iterrows():
                        row_desc = str(crow.get(desc_col_c, "")).strip()
                        if name_lower in row_desc.lower():
                            m = _re.search(r'\b(\d{5,7})\b', row_desc)
                            if m:
                                code = m.group(1)
                                break
            label = f"{name} - {code}" if code else name
            norm  = name.strip().lower()
            if norm not in seen_names:
                seen_names.add(norm)
                components.append(label)

    # ── 2. Color specification sheet ──────────────────────────────────────────
    cs = bom_data.get("color_specification")
    if cs is not None and not cs.empty:
        comp_col = cs.columns[0]
        for r in cs[comp_col]:
            val  = str(r).strip()
            norm = val.lower()
            if val and norm not in ("none", "nan", "") and norm not in seen_names:
                seen_names.add(norm)
                components.append(val)

    # ── 3. Costing detail ─────────────────────────────────────────────────────
    cd = bom_data.get("costing_detail")
    if cd is not None and not cd.empty:
        desc_col = next(
            (c for c in cd.columns if "desc" in str(c).lower()),
            cd.columns[0] if len(cd.columns) > 0 else None,
        )
        mat_col = next(
            (c for c in cd.columns
             if str(c).lower() in ("material", "material code", "mat code", "mat")),
            None,
        )
        if desc_col:
            for _, crow in cd.iterrows():
                desc = str(crow.get(desc_col, "")).strip()
                norm = desc.lower()
                if not desc or norm in ("none", "nan", "") or norm in seen_names:
                    continue
                code = str(crow.get(mat_col, "")).strip() if mat_col else ""
                if not code or not _re.match(r'^\d+$', code):
                    for col in cd.columns:
                        candidate = str(crow.get(col, "")).strip()
                        if _re.match(r'^\d{5,7}$', candidate):
                            code = candidate
                            break
                if not code:
                    m = _re.search(r'\b(\d{5,7})\b', desc)
                    code = m.group(1) if m else ""
                seen_names.add(norm)
                label = f"{desc} - {code}" if code else desc
                components.append(label)

    # ── 4. RFID Sticker explicit injection ────────────────────────────────────
    _RFID_CODES_PRIORITY = ("121612", "123130")
    _rfid_injected = set()
    if cd is not None and not cd.empty:
        desc_col_rfid = next(
            (c for c in cd.columns if "desc" in str(c).lower()),
            cd.columns[0] if len(cd.columns) > 0 else None,
        )
        if desc_col_rfid:
            for _, crow in cd.iterrows():
                desc = str(crow.get(desc_col_rfid, "")).strip()
                if "rfid" not in desc.lower():
                    continue
                code = ""
                for col in cd.columns:
                    candidate = str(crow.get(col, "")).strip()
                    if _re.match(r'^\d{5,7}$', candidate):
                        code = candidate
                        break
                if code and code not in _rfid_injected:
                    label = f"RFID Sticker - {code}"
                    if label not in components:
                        components.append(label)
                    _rfid_injected.add(code)

            for _, crow in cd.iterrows():
                for col in cd.columns:
                    candidate = str(crow.get(col, "")).strip()
                    if candidate in _RFID_CODES_PRIORITY and candidate not in _rfid_injected:
                        label = f"RFID Sticker - {candidate}"
                        if label not in components:
                            components.append(label)
                        _rfid_injected.add(candidate)

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
def _ensure_default_settings_for_styles(style_keys, bom_dict, show_hangtag_rfid):
    """Seed per-style settings so validation works even if settings UI was not opened."""
    label_selections = st.session_state.get("label_selections", {})

    def _pick_option(options, *keywords, fallback=None):
        for kw in keywords:
            kw_l = str(kw).lower()
            for opt in options:
                if kw_l in str(opt).lower():
                    return opt
        return fallback if fallback is not None else (options[0] if options else "N/A")

    def _best(saved_val, preferred_names, _comps, exclude_alt=False):
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
        return _comps[0] if _comps else "N/A"

    for style_key in style_keys:
        if style_key in label_selections and label_selections[style_key]:
            continue
        bom_data_s = bom_dict.get(style_key)
        if not bom_data_s:
            continue
        components = _get_components_for_bom(bom_data_s)
        if not components:
            continue
        na_opts = ["N/A"] + components

        main_sel = _best("", ["label logo 1", "hat components", "hat component", "direct embroidery", "label 1", "main label"], components, exclude_alt=True)
        care_sel = _best("", ["label 1 -", "label 1", "care content label", "care label"], components, exclude_alt=True)
        hangtag_default = _pick_option(na_opts, "hangtag package part", "hangtag", fallback="N/A")
        rfid_sticker_default = _pick_option(na_opts, "121612", "123130", "rfid sticker", "rfid tag", fallback="N/A")
        upc_default = _pick_option(na_opts, "980010", "packaging 3", "upc", "polybag", fallback="N/A")

        label_selections[style_key] = {
            "main_label":                main_sel,
            "add_main_label":            "N/A",
            "hangtag":                   hangtag_default,
            "hangtag2":                  "N/A",
            "hangtag3":                  "N/A",
            "micropack":                 "N/A",
            "size_label":                "N/A",
            "size_sticker":              "N/A",
            "care_label":                care_sel,
            "hangtag_rfid":              "N/A" if not show_hangtag_rfid else "N/A",
            "rfid_no_msrp":              "N/A",
            "rfid_sticker":              rfid_sticker_default,
            "upc_sticker":               upc_default,
            "main_label_fallback":       "N/A",
            "use_main_label_fallback":   False,
            "main_label_fallback2":      "N/A",
            "use_main_label_fallback2":  False,
            "main_label_fallback3":      "N/A",
            "use_main_label_fallback3":  False,
            "tp_status":                 "",
            "tp_date":                   "",
            "product_status":            "",
            "remarks":                   "",
        }

    st.session_state["label_selections"] = label_selections


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
    _ensure_default_settings_for_styles(all_style_keys, bom_dict, show_hangtag_rfid)
    label_selections = st.session_state.get("label_selections", {})
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
        _bom_sig = id(bom_data_s)
        _cache_sig_key = f"_comp_cache_sig_{style_key}"
        if st.session_state.get(_cache_sig_key) != _bom_sig or style_key not in _comp_cache:
            _comp_cache[style_key] = _get_components_for_bom(bom_data_s)
            st.session_state[_cache_sig_key] = _bom_sig
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
                    main_options = ["N/A"] + components
                    _main_default = saved.get("main_label", "") if saved.get("main_label", "") in main_options else _main_default
                    main_sel = st.selectbox("Main Label", options=main_options,
                        index=main_options.index(_main_default) if _main_default in main_options else 0,
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
                    # ── FIX: Care Label default must prefer "Label 1" variants ─────
                    # Previously _best searched ["label 1 -", "label 1", "care label"]
                    # but exclude_alt=True could block valid "Label 1" matches if the
                    # component name happened to start with "alt".  More importantly,
                    # the search order now explicitly puts "label 1 -" first (with code
                    # suffix) to match "Label 1 - 067535" before the bare "Label 1",
                    # and falls back gracefully.  exclude_alt is kept True to prevent
                    # alt-components from being auto-selected as care label.
                    _care_default = _best(
                        saved.get("care_label", ""),
                        ["label 1 -", "label 1", "care content label", "care label"],
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
                    rfid_sticker_default = _pick_option(
                        na_opts,
                        "121612",
                        "123130",
                        "rfid sticker",
                        "rfid tag",
                        fallback="N/A",
                    )
                    rfid_sticker_sel = st.selectbox("RFID Sticker", options=na_opts,
                        index=na_opts.index(rfid_sticker_default) if rfid_sticker_default in na_opts else 0,
                        key=f"rfid_sticker_{style_key}")

                r5a, r5b = st.columns(2)
                with r5a:
                    upc_default = _pick_option(
                        na_opts, "980010", "packaging 3", "upc", "polybag", fallback="N/A",
                    )
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
                    "<b>in order</b>. Fallback 4 (colorway name) activates automatically when "
                    "Fallback 1, 2, or 3 is enabled."
                    "</div>",
                    unsafe_allow_html=True,
                )

                _main_norm = str(main_sel).strip().lower()
                if ("hat component" in _main_norm) or ("117027" in _main_norm):
                    fb1_auto = next((o for o in na_opts if "alt hat component 1a" in str(o).lower()), None)
                    fb2_auto = next((o for o in na_opts if "alt hat component 1b" in str(o).lower()), None)
                    fb3_auto = next((o for o in na_opts if "alt hat component 1c" in str(o).lower()), None)

                    def _is_na(v):
                        return str(v).strip().lower() in ("", "n/a", "none", "nan")

                    fb1_empty = (fb1_auto is None) or _is_na(saved.get("main_label_fallback", ""))
                    fb2_empty = (fb2_auto is None) or _is_na(saved.get("main_label_fallback2", ""))

                    if fb1_auto:
                        st.session_state[f"main_label_fallback_{style_key}"] = fb1_auto
                        st.session_state[f"use_main_label_fallback_{style_key}"] = True
                    if fb2_auto:
                        st.session_state[f"main_label_fallback2_{style_key}"] = fb2_auto
                        st.session_state[f"use_main_label_fallback2_{style_key}"] = True
                    if fb3_auto and fb1_empty and fb2_empty:
                        st.session_state[f"main_label_fallback3_{style_key}"] = fb3_auto
                        st.session_state[f"use_main_label_fallback3_{style_key}"] = True

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

                fb3_col_a, fb3_col_b = st.columns([3, 1])
                with fb3_col_a:
                    fb3_sel = st.selectbox(
                        "Fallback 3 ??? Alt component for color lookup",
                        options=na_opts,
                        index=na_opts.index(saved.get("main_label_fallback3", "N/A"))
                            if saved.get("main_label_fallback3", "N/A") in na_opts else 0,
                        key=f"main_label_fallback3_{style_key}",
                    )
                with fb3_col_b:
                    use_fb3 = st.checkbox(
                        "Enable",
                        value=bool(saved.get("use_main_label_fallback3", False)),
                        key=f"use_main_label_fallback3_{style_key}",
                    )


                st.markdown(
                    "<div style='font-size:0.78rem;color:#3a5278;padding:0.38rem 0 0.1rem 0;"
                    "font-weight:600;'>"
                    "Fallback 4 — Use colorway name (strip numeric prefix) "
                    "<span style='font-size:0.7rem;color:#7090b4;font-weight:400;'>"
                    "— auto-enabled when FB1, FB2, or FB3 is on</span>"
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
                    "main_label_fallback3":        fb3_sel,
                    "use_main_label_fallback3":    use_fb3,
                    "tp_status":      tp_status,
                    "tp_date":        tp_date,
                    "product_status": prod_status,
                    "remarks":        remarks,
                }

    st.session_state["label_selections"] = label_selections

    render_pagination("label_map_page", lm_page, total_lm_pages, key_suffix="lm", show_page_text=True)

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

    render_divider()
    st.markdown("""<div class="cx-meta">Quick Look — Per Style Settings</div>""", unsafe_allow_html=True)

    quick_display_fields = [f for f in QUICK_SETTING_FIELDS if show_hangtag_rfid or f != "hangtag_rfid"]

    CMP_PER_PAGE = 10
    total_cmp_pages = max(1, -(-len(page_style_keys) // CMP_PER_PAGE))
    cmp_page_key = "cmp_ql_page"
    cmp_page = max(0, min(st.session_state.get(cmp_page_key, 0), total_cmp_pages - 1))
    st.session_state[cmp_page_key] = cmp_page

    cmp_page_style_keys = page_style_keys[cmp_page * CMP_PER_PAGE: (cmp_page + 1) * CMP_PER_PAGE]

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

        fields_html = ""
        fields_html += _chip("Colors", str(len(style_colors)))
        fields_html += _chip("Excel Rows", str(excel_match_count))
        fields_html += _chip("Material", material_val)
        for f in quick_display_fields:
            fields_html += _chip(QUICK_SETTING_LABELS[f], picks.get(f, "N/A"))

        card_html = (
            f"<div style='border-left:4px solid {accent};border-radius:10px;"
            f"padding:14px 16px 12px;background:#fff;"
            f"box-shadow:0 1px 6px rgba(0,0,0,0.08);margin-bottom:10px;'>"
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"margin-bottom:10px;'>"
            f"<span style='font-size:1rem;font-weight:800;color:#1a2b45;"
            f"letter-spacing:-0.01em;'>{escape(style_key)}</span>"
            f"<span style='font-size:0.68rem;font-weight:700;padding:3px 10px;"
            f"border-radius:999px;background:{bom_bg};border:1px solid {bom_bdr};"
            f"color:{bom_fg};white-space:nowrap;'>{bom_label}</span>"
            f"</div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:5px;'>"
            f"{fields_html}"
            f"</div>"
            f"</div>"
        )

        with ql_cols[idx % 2]:
            st.markdown(card_html, unsafe_allow_html=True)

    render_pagination(cmp_page_key, cmp_page, total_cmp_pages, key_suffix="cmp_ql", show_page_text=True)

    color_debug = st.session_state.get("__color_debug", [])
    if color_debug:
        with st.expander("Color Lookup Debug", expanded=False):
            st.dataframe(pd.DataFrame(color_debug), use_container_width=True, hide_index=True)

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
        label_sels_norm = {str(k).strip().upper(): v for k, v in label_sels.items()}
        result_parts = []
        missing_settings = []
        color_debug = []
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
            if use_settings and not per_style_settings:
                per_style_settings = label_sels_norm.get(str(matched_bom_key).strip().upper(), {})
            if use_settings and not per_style_settings:
                for _k, _v in label_sels.items():
                    if _styles_match(str(_k), str(matched_bom_key)):
                        per_style_settings = _v
                        break
            if use_settings and not per_style_settings:
                missing_settings.append(matched_bom_key)

            # ── FIX: Defensive care label passthrough ─────────────────────────
            # When use_settings=True but per_style_settings is empty (e.g. the
            # settings expander for this style was never rendered due to pagination,
            # or validation was triggered before Streamlit committed widget values),
            # label_settings["care_label"] is missing and filler.py falls back to
            # its auto-detect — which is now robust.  However, we also explicitly
            # propagate selected_care_label_comp from the settings dict so the
            # bom_data.get("selected_care_label_comp") fallback in filler.py has
            # a value even when _ls("care_label") returns "".
            bom_with_labels = dict(matched_bom)
            bom_with_labels["label_settings"]            = per_style_settings
            bom_with_labels["selected_main_label_comp"]  = per_style_settings.get("main_label")  if use_settings else None
            # KEY FIX: pass care_label through selected_care_label_comp so the
            # bom_data fallback path in filler.py always has a value to work with.
            bom_with_labels["selected_care_label_comp"]  = per_style_settings.get("care_label")  if use_settings else None
            bom_with_labels["_debug_color"]              = color_debug

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
                if "error" in raw_status or "no match" in raw_status or "no bom loaded" in raw_status:
                    return "❌ Error: No match"
                existing = str(row.get("Validation Status", "")).strip()
                if existing:
                    return existing
                _core = ["Main Label", "Main Label Supplier", "Care Label",
                         "Care Supplier", "Content Code", "Care Code"]
                has_core_na = any(
                    str(row.get(c, "")).strip().upper() == "N/A"
                    for c in _core if c in row.index
                )
                return "⚠️ Partial" if has_core_na else "✅ Validated"
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
        st.session_state["__color_debug"]    = color_debug
        if use_settings and missing_settings:
            uniq = sorted(set(missing_settings))
            msg = "Missing saved settings for style(s): " + ", ".join(uniq[:20]) + (" ..." if len(uniq) > 20 else "") + ". These styles fell back to auto-detect defaults."
            render_warn_banner(msg)

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
