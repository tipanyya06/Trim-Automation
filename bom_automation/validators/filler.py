from typing import Dict, Any
import pandas as pd

from parsers.color_bom import extract_color_bom_lookup
from parsers.costing import find_supplier_by_code
from parsers.care_content import extract_care_codes, extract_content_codes
from validators.matcher import normalize_colorway, extract_material_code, extract_id_only

NEW_COLUMNS = [
    "Main Label", "Main Label Color", "Main Label Supplier",
    "Additional Main Label", "Additional Main Label Color",
    "Care Label", "Care Label Color", "Care Label Supplier",
    "Content Code", "TP FC", "Care Code",
    "Hangtag", "Hangtag Supplier",
    "Hangtag (RFID)", "Hangtag (RFID) Supplier",
    "RFID Sticker", "RFID Sticker Supplier",
    "UPC Sticker (Polybag)", "UPC Sticker Supplier",
    "Validation Status",
]


def _normalize_value(val: Any) -> str:
    s = str(val).strip()
    if not s or s.lower() in ("none", "nan", ""):
        return "N/A"
    return s


def validate_and_fill(comparison_df: pd.DataFrame, bom_data: Dict[str, Any]) -> pd.DataFrame:
    result = comparison_df.copy()

    color_bom_lookup = extract_color_bom_lookup(bom_data.get("color_bom", pd.DataFrame()))
    care_codes       = extract_care_codes(bom_data.get("care_report", pd.DataFrame()))
    content_codes    = extract_content_codes(bom_data.get("content_report", pd.DataFrame()))
    components       = color_bom_lookup.get("components", {})
    sap_codes        = color_bom_lookup.get("SAP_codes", {})
    available_cw     = list(sap_codes.keys()) if sap_codes else []
    supplier_lookup  = bom_data.get("supplier_lookup", {})
    costing_detail   = bom_data.get("costing_detail", pd.DataFrame())
    bom_style        = str(bom_data.get("metadata", {}).get("style", "")).strip().upper()

    for col in NEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""

    def _resolve_supplier(mat_code: str) -> str:
        """
        Two-stage supplier resolution:
        1. Fast dict lookup built at parse time
        2. Full scan of costing_detail DataFrame
        """
        if not mat_code or mat_code == "N/A":
            return "N/A"
        # Stage 1: pre-built lookup
        if mat_code in supplier_lookup:
            return supplier_lookup[mat_code]
        # Stage 2: full scan
        result_sup = find_supplier_by_code(costing_detail, mat_code)
        # Cache hit for next time
        if result_sup and result_sup != "N/A":
            supplier_lookup[mat_code] = result_sup
        return result_sup

    for idx, row in result.iterrows():
        buyer_style = str(row.get("Buyer Style Number", "")).strip().upper()
        if buyer_style and bom_style and buyer_style != bom_style:
            if not (buyer_style in bom_style or bom_style in buyer_style):
                result.at[idx, "Validation Status"] = f"❌ Error: Style mismatch ({buyer_style} vs {bom_style})"
                continue

        color_raw  = str(row.get("Color/Option", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw:
            result.at[idx, "Validation Status"] = f"❌ Error: Unknown colorway '{color_raw}'"
            continue

        colorway_num = matched_cw.split("-")[0].strip() if "-" in matched_cw else matched_cw.split()[0] if " " in matched_cw else matched_cw

        def _get_comp(comp_key, sub):
            comp = components.get(comp_key, {})
            if sub == "colorway":
                return _normalize_value(comp.get("colorways", {}).get(matched_cw, ""))
            elif sub == "material_code":
                return extract_material_code(comp.get("description", ""))
            return _normalize_value(comp.get(sub, ""))

        def _get_care(key):
            entry = care_codes.get(matched_cw) or care_codes.get(colorway_num, {})
            return _normalize_value(entry.get(key, ""))

        def _get_content(key):
            entry = content_codes.get(matched_cw) or content_codes.get(colorway_num, {})
            return _normalize_value(entry.get(key, ""))

        def _color_spec_value(component_name):
            if not component_name:
                return ""
            cs = bom_data.get("color_specification")
            if cs is None or cs.empty:
                return ""
            comp_col = cs.columns[0]
            colorway_cols = [c for c in cs.columns[1:] if c and not c.startswith("col_")]
            row_match = cs[cs[comp_col] == component_name]
            if row_match.empty:
                return ""
            # Try matched colorway first
            for cw_col in colorway_cols:
                if matched_cw in cw_col or cw_col in matched_cw:
                    val = str(row_match.iloc[0].get(cw_col, "")).strip()
                    if val and val.lower() not in ("none", "nan", ""):
                        return val
            # Fall back to first non-empty
            for cw_col in colorway_cols:
                val = str(row_match.iloc[0].get(cw_col, "")).strip()
                if val and val.lower() not in ("none", "nan", ""):
                    return val
            return ""

        # ── Label resolution ──────────────────────────────────────────────────
        selected_main = bom_data.get("selected_main_label_comp")
        selected_care = bom_data.get("selected_care_label_comp")

        def _split_comp(sel):
            if sel and " - " in str(sel):
                parts = str(sel).rsplit(" - ", 1)
                return parts[0].strip(), parts[1].strip()
            return (sel or ""), ""

        main_comp_name, main_comp_id = _split_comp(selected_main)
        care_comp_name, care_comp_id = _split_comp(selected_care)

        main_label_code  = _get_comp(main_comp_name, "material_code") if main_comp_name else "N/A"
        main_label_color = _color_spec_value(main_comp_name) or _get_comp(main_comp_name, "colorway")
        care_label_code  = _get_comp(care_comp_name, "material_code") if care_comp_name else "N/A"
        care_label_color = _color_spec_value(care_comp_name) or _get_comp(care_comp_name, "colorway")

        result.at[idx, "Main Label"]          = main_comp_id or main_label_code or "N/A"
        result.at[idx, "Main Label Color"]    = main_label_color or "N/A"
        result.at[idx, "Main Label Supplier"] = _resolve_supplier(main_label_code)

        logo_code     = _get_comp("Label Logo 1", "material_code")
        logo_colorway = _get_comp("Label Logo 1", "colorway")
        result.at[idx, "Additional Main Label"]       = logo_code or extract_id_only(logo_colorway) or "N/A"
        result.at[idx, "Additional Main Label Color"] = logo_colorway

        result.at[idx, "Care Label"]          = care_comp_id or care_label_code or "N/A"
        result.at[idx, "Care Label Color"]    = care_label_color or "N/A"
        result.at[idx, "Care Label Supplier"] = _resolve_supplier(care_label_code)

        result.at[idx, "Content Code"] = _get_content("content_code")
        result.at[idx, "TP FC"]        = _get_content("shell")
        result.at[idx, "Care Code"]    = _get_care("care_code")

        hangtag_code     = _get_comp("Hangtag Package Part", "material_code")
        hangtag_colorway = _get_comp("Hangtag Package Part", "colorway")
        result.at[idx, "Hangtag"]          = hangtag_code or extract_id_only(hangtag_colorway) or "N/A"
        result.at[idx, "Hangtag Supplier"] = _resolve_supplier(hangtag_code)

        rfid_desc = str(components.get("Hangtag Package Part", {}).get("description", ""))
        rfid_code = extract_material_code(rfid_desc)
        result.at[idx, "Hangtag (RFID)"]          = rfid_code or extract_id_only(rfid_desc) or "N/A"
        result.at[idx, "Hangtag (RFID) Supplier"]  = _resolve_supplier(rfid_code)
        result.at[idx, "RFID Sticker"]             = rfid_code or extract_id_only(rfid_desc) or "N/A"
        result.at[idx, "RFID Sticker Supplier"]    = _resolve_supplier(rfid_code)

        upc_code     = _get_comp("Packaging 3", "material_code")
        upc_colorway = _get_comp("Packaging 3", "colorway")
        result.at[idx, "UPC Sticker (Polybag)"] = upc_code or extract_id_only(upc_colorway) or "N/A"
        result.at[idx, "UPC Sticker Supplier"]  = _resolve_supplier(upc_code)

        not_found = sum(1 for col in NEW_COLUMNS[:-1] if str(result.at[idx, col]) == "N/A")
        if not_found == 0:
            result.at[idx, "Validation Status"] = "✅ Validated"
        elif not_found < len(NEW_COLUMNS) - 1:
            result.at[idx, "Validation Status"] = "⚠️ Partial"
        else:
            result.at[idx, "Validation Status"] = "❌ Error: No BOM data matched"

    return result