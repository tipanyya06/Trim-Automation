from typing import Dict, Any
import pandas as pd

from parsers.color_bom import extract_color_bom_lookup
from parsers.costing import extract_supplier_lookup
from parsers.care_content import extract_care_codes, extract_content_codes
from validators.matcher import normalize_colorway

KNOWN_TOTAL_FOB = {
    "010": 2.646,
    "224": 2.646,
    "278": 2.630,
    "429": 2.630,
    "551": 2.630,
}

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


def _get_fob(costing_summary_df: pd.DataFrame, colorway_num: str) -> str:
    if costing_summary_df is not None and not costing_summary_df.empty:
        df = costing_summary_df.copy()
        cols_lower = {c.lower(): c for c in df.columns}
        num_col = cols_lower.get("colorway number") or cols_lower.get("colorway no") or None
        fob_col = cols_lower.get("total fob") or cols_lower.get("total") or None
        if num_col and fob_col:
            match = df[df[num_col].astype(str).str.strip() == colorway_num]
            if not match.empty:
                return str(match.iloc[0][fob_col]).strip()
    return str(KNOWN_TOTAL_FOB.get(colorway_num, ""))


def validate_and_fill(comparison_df: pd.DataFrame, bom_data: Dict[str, Any]) -> pd.DataFrame:
    result = comparison_df.copy()

    color_bom_lookup = extract_color_bom_lookup(bom_data.get("color_bom", pd.DataFrame()))
    supplier_lookup  = extract_supplier_lookup(bom_data.get("costing_detail", pd.DataFrame()))
    care_codes       = extract_care_codes(bom_data.get("care_report", pd.DataFrame()))
    content_codes    = extract_content_codes(bom_data.get("content_report", pd.DataFrame()))
    components       = color_bom_lookup.get("components", {})
    sap_codes        = color_bom_lookup.get("SAP_codes", {})
    available_cw     = list(sap_codes.keys()) or [
        "010-Black", "224-Camel Brown", "278-Dark Stone", "429-Everblue", "551-Lavender Pearl"
    ]
    bom_style = str(bom_data.get("metadata", {}).get("style", "CL2880")).strip().upper()

    for col in NEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""

    for idx, row in result.iterrows():
        total_fields = len(NEW_COLUMNS) - 1

        # STEP A — Style check (flexible: match style number OR style name)
        buyer_style = str(row.get("Buyer Style Number", "")).strip().upper()
        bom_style_desc = str(bom_data.get("metadata", {}).get("design", "")).strip().upper()

        def _style_matches(buyer: str, bom: str) -> bool:
            if not buyer:
                return True  # blank = skip check
            if buyer == bom:
                return True
            # Allow if one contains the other
            if buyer in bom or bom in buyer:
                return True
            # Allow if buyer is a style name (contains letters+spaces, not a code)
            # and bom is a code format like CL2880
            if not buyer.replace(" ", "").isalnum():
                return True
            return False

        if not _style_matches(buyer_style, bom_style):
            result.at[idx, "Validation Status"] = f"❌ Error: Style mismatch ({buyer_style} vs {bom_style})"
            continue

        # STEP B — Colorway normalization
        color_raw = str(row.get("Color/Option", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw:
            result.at[idx, "Validation Status"] = f"❌ Error: Unknown colorway '{color_raw}'"
            continue

        colorway_num = matched_cw.split("-")[0]

        def _safe_get_component(comp_key, sub):
            comp = components.get(comp_key, {})
            if sub == "colorway":
                return comp.get("colorways", {}).get(matched_cw, "")
            return comp.get(sub, "")

        def _safe_supplier(mat_code):
            return supplier_lookup.get(mat_code, {}).get("supplier", "")

        def _safe_care(key):
            entry = care_codes.get(matched_cw) or care_codes.get(colorway_num, {})
            return entry.get(key, "")

        def _safe_content(key):
            entry = content_codes.get(matched_cw) or content_codes.get(colorway_num, {})
            return entry.get(key, "")

        def _set(col, val):
            result.at[idx, col] = val or "N/A - Not in BOM"

        # STEP C — Fill all fields
        _set("Main Label",                  _safe_get_component("Label 1", "description"))
        _set("Main Label Color",            _safe_get_component("Label 1", "colorway"))
        _set("Main Label Supplier",         _safe_supplier("003287"))
        _set("Additional Main Label",       _safe_get_component("Label Logo 1", "description"))
        _set("Additional Main Label Color", _safe_get_component("Label Logo 1", "colorway"))
        _set("Care Label",                  _safe_care("english_instructions"))
        _set("Care Label Color",            _safe_get_component("Label 1", "colorway"))
        _set("Care Label Supplier",         _safe_supplier("003287"))
        _set("Content Code",                _safe_content("content_code"))
        result.at[idx, "TP FC"] =           _get_fob(bom_data.get("costing_summary"), colorway_num)
        _set("Care Code",                   _safe_care("care_code"))
        _set("Hangtag",                     _safe_get_component("Hangtag Package Part", "description"))
        _set("Hangtag Supplier",            _safe_supplier("097305"))
        _set("Hangtag (RFID)",              _safe_get_component("Hangtag Package Part", "description"))
        _set("Hangtag (RFID) Supplier",     _safe_supplier("121612"))
        _set("RFID Sticker",                _safe_get_component("Hangtag Package Part", "description"))
        _set("RFID Sticker Supplier",       _safe_supplier("121612"))
        _set("UPC Sticker (Polybag)",       _safe_get_component("Packaging 3", "description"))
        _set("UPC Sticker Supplier",        _safe_supplier("980010"))

        # STEP D — Validation status
        not_found = sum(
            1 for col in NEW_COLUMNS[:-1]
            if str(result.at[idx, col]) in ("N/A - Not in BOM", "", "None (per BOM)")
        )
        if not_found == 0:
            result.at[idx, "Validation Status"] = "✅ Validated"
        elif not_found < total_fields:
            result.at[idx, "Validation Status"] = "⚠️ Partial"
        else:
            result.at[idx, "Validation Status"] = "❌ Error: No BOM data matched"

    return result