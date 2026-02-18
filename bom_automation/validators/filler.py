from typing import Dict, Any
import pandas as pd

from parsers.color_bom import extract_color_bom_lookup
from parsers.costing import find_supplier_by_code
from parsers.care_content import extract_care_codes, extract_content_codes
from validators.matcher import normalize_colorway, extract_material_code, extract_id_only

NEW_COLUMNS = [
    "Main Label",
    "Main Label Color",
    "Main Label Supplier",
    "Additional Main Label",
    "Additional Main Label Color",
    "Care Label",
    "Care Label Color",
    "Care Label Supplier",
    "Content Code",
    "TP FC",
    "Care Code",
    "Hangtag",
    "Hangtag Supplier",
    "Hangtag (RFID)",
    "Hangtag (RFID) Supplier",
    "RFID Sticker",
    "RFID Sticker Supplier",
    "UPC Sticker (Polybag)",
    "UPC Sticker Supplier",
    "Validation Status",
]


def _normalize_value(val: Any) -> str:
    """Convert None, 'None', empty to N/A. Keep Stock, Artwork as-is."""
    s = str(val).strip()
    if not s or s.lower() in ("none", "nan", ""):
        return "N/A"
    return s


def _get_fob(costing_summary_df: pd.DataFrame, colorway_identifier: str) -> str:
    """Extract Total FOB from costing summary."""
    if costing_summary_df is None or costing_summary_df.empty:
        return "N/A"
    
    df = costing_summary_df.copy()
    cols_lower = {c.lower(): c for c in df.columns}
    
    # Find colorway column
    cw_col = None
    for key in ["colorway number", "colorway no", "color way number", "color"]:
        if key in cols_lower:
            cw_col = cols_lower[key]
            break
    
    # Find FOB column
    fob_col = None
    for key in ["total fob", "fob total", "total", "fob"]:
        if key in cols_lower:
            fob_col = cols_lower[key]
            break
    
    if not cw_col or not fob_col:
        return "N/A"
    
    # Match by colorway
    for _, row in df.iterrows():
        cw_val = str(row.get(cw_col, '')).strip()
        if colorway_identifier in cw_val or cw_val in colorway_identifier:
            return _normalize_value(row.get(fob_col, ''))
    
    return "N/A"


def validate_and_fill(comparison_df: pd.DataFrame, bom_data: Dict[str, Any]) -> pd.DataFrame:
    result = comparison_df.copy()
    
    color_bom_lookup = extract_color_bom_lookup(bom_data.get("color_bom", pd.DataFrame()))
    care_codes       = extract_care_codes(bom_data.get("care_report", pd.DataFrame()))
    content_codes    = extract_content_codes(bom_data.get("content_report", pd.DataFrame()))
    components       = color_bom_lookup.get("components", {})
    sap_codes        = color_bom_lookup.get("SAP_codes", {})
    available_cw     = list(sap_codes.keys()) if sap_codes else []
    
    # Get supplier lookup from costing detail
    supplier_lookup = bom_data.get("supplier_lookup", {})
    
    # Debug: Check if costing_detail has data
    costing_detail_df = bom_data.get("costing_detail", pd.DataFrame())
    # print(f"DEBUG: costing_detail shape: {costing_detail_df.shape}, supplier_lookup len: {len(supplier_lookup)}")
    
    bom_style = str(bom_data.get("metadata", {}).get("style", "")).strip().upper()
    
    for col in NEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""
    
    for idx, row in result.iterrows():
        # Style check (flexible)
        buyer_style = str(row.get("Buyer Style Number", "")).strip().upper()
        if buyer_style and bom_style and buyer_style != bom_style:
            if not (buyer_style in bom_style or bom_style in buyer_style):
                result.at[idx, "Validation Status"] = f"❌ Error: Style mismatch ({buyer_style} vs {bom_style})"
                continue
        
        # Colorway normalization
        color_raw = str(row.get("Color/Option", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw:
            result.at[idx, "Validation Status"] = f"❌ Error: Unknown colorway '{color_raw}'"
            continue
        
        colorway_num = matched_cw.split("-")[0] if "-" in matched_cw else matched_cw.split()[0] if " " in matched_cw else matched_cw
        
        def _get_comp(comp_key, sub):
            comp = components.get(comp_key, {})
            if sub == "colorway":
                return _normalize_value(comp.get("colorways", {}).get(matched_cw, ""))
            elif sub == "material_code":
                desc = comp.get("description", "")
                return extract_material_code(desc)
            return _normalize_value(comp.get(sub, ""))
        
        def _get_supplier(mat_code):
            if not mat_code or mat_code == "N/A":
                return "N/A"
            # First try the supplier lookup from costing detail
            if mat_code in supplier_lookup:
                return supplier_lookup[mat_code]
            # Fallback to find_supplier_by_code for additional searching
            return find_supplier_by_code(bom_data.get("costing_detail", pd.DataFrame()), mat_code)
        
        def _get_care(key):
            entry = care_codes.get(matched_cw) or care_codes.get(colorway_num, {})
            return _normalize_value(entry.get(key, ""))
        
        def _get_content(key):
            entry = content_codes.get(matched_cw) or content_codes.get(colorway_num, {})
            return _normalize_value(entry.get(key, ""))
        
        # ── Resolve label component from Color Specification selection ──────
        def _get_color_spec_value(component_name: str) -> str:
            """Get the color value for a specific component + colorway from color_specification."""
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
            # Find column matching current colorway
            for cw_col in colorway_cols:
                if matched_cw in cw_col or cw_col in matched_cw:
                    val = str(row_match.iloc[0].get(cw_col, "")).strip()
                    if val and val.lower() not in ("none", "nan", ""):
                        return val
            # Fallback: first non-empty value
            for cw_col in colorway_cols:
                val = str(row_match.iloc[0].get(cw_col, "")).strip()
                if val and val.lower() not in ("none", "nan", ""):
                    return val
            return ""

        selected_main_comp = bom_data.get("selected_main_label_comp")
        selected_care_comp = bom_data.get("selected_care_label_comp")

        # Extract ID from dropdown selection (format: "Label Logo 1 - 075660" → ID is "075660")
        main_comp_id = selected_main_comp.split(" - ")[-1].strip() if selected_main_comp and " - " in str(selected_main_comp) else ""
        care_comp_id = selected_care_comp.split(" - ")[-1].strip() if selected_care_comp and " - " in str(selected_care_comp) else ""
        
        # Extract component name for BOM lookups (format: "Label Logo 1 - 075660" → name is "Label Logo 1")
        main_comp_name = selected_main_comp.split(" - ")[0].strip() if selected_main_comp and " - " in str(selected_main_comp) else selected_main_comp
        care_comp_name = selected_care_comp.split(" - ")[0].strip() if selected_care_comp and " - " in str(selected_care_comp) else selected_care_comp

        # Get BOM data using component names for colors and suppliers
        main_label_code = _get_comp(main_comp_name, "material_code") if main_comp_name else "N/A"
        main_label_colorway = _get_comp(main_comp_name, "colorway") if main_comp_name else "N/A"
        main_label_color = _get_color_spec_value(main_comp_name) if main_comp_name else main_label_colorway

        care_label_code = _get_comp(care_comp_name, "material_code") if care_comp_name else "N/A"
        care_label_colorway = _get_comp(care_comp_name, "colorway") if care_comp_name else "N/A"
        care_label_color = _get_color_spec_value(care_comp_name) if care_comp_name else care_label_colorway

        # Fill all fields - use selected IDs from dropdown
        result.at[idx, "Main Label"] = main_comp_id if main_comp_id else "N/A"
        result.at[idx, "Main Label Color"] = main_label_color if main_label_color and main_label_color != "N/A" else main_label_colorway
        result.at[idx, "Main Label Supplier"] = _get_supplier(main_label_code)
        
        logo_code = _get_comp("Label Logo 1", "material_code")
        logo_colorway = _get_comp("Label Logo 1", "colorway")
        result.at[idx, "Additional Main Label"] = extract_id_only(logo_colorway) if not logo_code or logo_code == "N/A" else logo_code
        result.at[idx, "Additional Main Label Color"] = logo_colorway
        
        # Care Label: use selected ID from dropdown (NOT care instructions)
        result.at[idx, "Care Label"] = care_comp_id if care_comp_id else "N/A"
        result.at[idx, "Care Label Color"] = care_label_color if care_label_color and care_label_color != "N/A" else care_label_colorway
        result.at[idx, "Care Label Supplier"] = _get_supplier(care_label_code)
        
        result.at[idx, "Content Code"] = _get_content("content_code")
        result.at[idx, "TP FC"] = _get_content("shell")
        result.at[idx, "Care Code"] = _get_care("care_code")
        
        hangtag_code = _get_comp("Hangtag Package Part", "material_code")
        hangtag_colorway = _get_comp("Hangtag Package Part", "colorway")
        result.at[idx, "Hangtag"] = extract_id_only(hangtag_colorway) if not hangtag_code or hangtag_code == "N/A" else hangtag_code
        result.at[idx, "Hangtag Supplier"] = _get_supplier(hangtag_code)
        
        rfid_description = str(components.get("Hangtag Package Part", {}).get("description", ""))
        rfid_code = extract_material_code(rfid_description)
        result.at[idx, "Hangtag (RFID)"] = extract_id_only(rfid_description) if not rfid_code else rfid_code
        result.at[idx, "Hangtag (RFID) Supplier"] = _get_supplier(rfid_code)
        result.at[idx, "RFID Sticker"] = extract_id_only(rfid_description) if not rfid_code else rfid_code
        result.at[idx, "RFID Sticker Supplier"] = _get_supplier(rfid_code)
        
        upc_code = _get_comp("Packaging 3", "material_code")
        upc_colorway = _get_comp("Packaging 3", "colorway")
        result.at[idx, "UPC Sticker (Polybag)"] = extract_id_only(upc_colorway) if not upc_code or upc_code == "N/A" else upc_code
        result.at[idx, "UPC Sticker Supplier"] = _get_supplier(upc_code)
        
        # Validation status
        not_found = sum(1 for col in NEW_COLUMNS[:-1] if str(result.at[idx, col]) == "N/A")
        if not_found == 0:
            result.at[idx, "Validation Status"] = "✅ Validated"
        elif not_found < len(NEW_COLUMNS) - 1:
            result.at[idx, "Validation Status"] = "⚠️ Partial"
        else:
            result.at[idx, "Validation Status"] = "❌ Error: No BOM data matched"
    
    return result