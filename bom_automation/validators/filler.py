from typing import Dict, Any, Optional
import pandas as pd
import re

from parsers.color_bom import extract_color_bom_lookup
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


def _nv(val: Any) -> str:
    s = str(val).strip()
    return "N/A" if (not s or s.lower() in ("none", "nan", "")) else s


def _fix_sup(s: str) -> str:
    """Fix OCR split-words: 'Y K K' -> 'YKK'."""
    if not s:
        return s
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\b([A-Z]{1,3}) ([A-Z]{1,3})\b', r'\1\2', s)
    return s.strip()


def _get_material_code_for_comp(comp: dict) -> str:
    """
    Extract the best material code for a component.

    Priority:
    1. The 'material_code' field stored directly in the component dict (from color_bom parser)
    2. First 3-6 digit number found anywhere in the 'description' field
    3. First 3-6 digit number found in ANY colorway value (colorway cells often hold item codes)

    This is the core fix: previously only (2) was used, missing codes stored in (1) and (3).
    """
    # 1. Direct material_code field (stored by extract_color_bom_lookup)
    mc = str(comp.get("material_code", "")).strip()
    if mc and mc not in ("", "N/A", "nan", "none"):
        return mc

    # 2. Parse from description
    desc = str(comp.get("description", "")).strip()
    if desc:
        found = extract_material_code(desc)
        if found:
            return found

    # 3. Parse from colorway values (e.g. "097022 Columbia RFID Tag")
    for cw_val in comp.get("colorways", {}).values():
        found = extract_material_code(str(cw_val))
        if found:
            return found

    return ""


def _find_supplier(costing_df: pd.DataFrame, code: str) -> str:
    """
    Search costing_detail for a material code and return its supplier.

    Uses flexible matching: tries exact code, zero-stripped code, and
    containment check so codes like 067535 match cells containing "067535"
    even if surrounded by non-word characters or extra whitespace.
    """
    if costing_df is None or costing_df.empty or not code or code == "N/A":
        return "N/A"

    code = str(code).strip()
    code_stripped = code.lstrip("0")  # zero-stripped variant e.g. "67535"

    # Find supplier column
    sup_col = None
    for col in costing_df.columns:
        if "supplier" in str(col).lower() or "vendor" in str(col).lower():
            sup_col = col
            break
    if not sup_col:
        return "N/A"

    def _cell_contains_code(cell_str: str) -> bool:
        s = str(cell_str).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return False
        # Direct containment (handles codes inside longer strings)
        if code in s:
            return True
        # Zero-stripped variant
        if code_stripped and code_stripped in s:
            return True
        # Digits-only extraction match
        digits = re.sub(r'[^\d]', '', s)
        if digits == code or (code_stripped and digits == code_stripped):
            return True
        return False

    # Scan every row: search all non-supplier cells for the code
    for _, row in costing_df.iterrows():
        for col in costing_df.columns:
            if col == sup_col:
                continue
            if _cell_contains_code(str(row.get(col, ""))):
                sup = _fix_sup(str(row.get(sup_col, "")).strip())
                if sup and sup.lower() not in ("", "nan", "none"):
                    return sup
    return "N/A"


def validate_and_fill(comparison_df: pd.DataFrame, bom_data: Dict[str, Any]) -> pd.DataFrame:
    result = comparison_df.copy()

    color_bom_lookup = extract_color_bom_lookup(bom_data.get("color_bom", pd.DataFrame()))
    care_codes    = extract_care_codes(bom_data.get("care_report", pd.DataFrame()))
    content_codes = extract_content_codes(bom_data.get("content_report", pd.DataFrame()))
    components    = color_bom_lookup.get("components", {})
    sap_codes     = color_bom_lookup.get("SAP_codes", {})
    available_cw  = list(sap_codes.keys()) if sap_codes else []

    supplier_lookup = bom_data.get("supplier_lookup", {})
    costing_detail  = bom_data.get("costing_detail", pd.DataFrame())
    bom_style       = str(bom_data.get("metadata", {}).get("style", "")).strip().upper()
    color_spec      = bom_data.get("color_specification")

    for col in NEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""

    def resolve_supplier(mat_code: str) -> str:
        """
        Two-stage supplier lookup:
        1. Pre-built dict from parse time (fast)
        2. Full scan of costing_detail DataFrame (fallback)
        """
        if not mat_code or mat_code == "N/A":
            return "N/A"
        cached = supplier_lookup.get(mat_code, "")
        if cached and cached.lower() not in ("", "nan", "none"):
            return _fix_sup(cached)
        found = _find_supplier(costing_detail, mat_code)
        if found != "N/A":
            supplier_lookup[mat_code] = found  # cache it
        return found

    def get_code(comp_key: str) -> str:
        """Get material code for a component using all available sources."""
        comp = components.get(comp_key, {})
        return _get_material_code_for_comp(comp)

    def get_cw_val(comp_key: str, matched_cw: str) -> str:
        """Get colorway display value from color_bom for a specific colorway."""
        comp = components.get(comp_key, {})
        val = comp.get("colorways", {}).get(matched_cw, "")
        return _nv(val)

    def get_color_from_spec(component_name: str, matched_cw: str) -> str:
        """
        Look up the color for a component + colorway.
        Primary source: color_bom (image 2 table — has the actual per-colorway colors).
        Fallback: color_specification table.
        Never falls back to a different colorway's color.
        """
        if not component_name:
            return ""

        cw_prefix = matched_cw.split("-")[0].strip() if "-" in matched_cw else matched_cw

        def _lookup_in_df(df: pd.DataFrame) -> str:
            if df is None or df.empty:
                return ""
            comp_col = df.columns[0]
            # strip " - code" suffix if present (from dropdown format)
            lookup_name = component_name.split(" - ")[0].strip() if " - " in component_name else component_name
            row_match = df[df[comp_col] == lookup_name]
            if row_match.empty:
                return ""
            cw_cols = [c for c in df.columns[1:] if c and not str(c).startswith("col_")]
            # 1. Exact column name match
            if matched_cw in cw_cols:
                v = str(row_match.iloc[0][matched_cw]).strip()
                if v and v.lower() not in ("none", "nan", "stock", "artwork", ""):
                    return v
            # 2. Numeric prefix match (e.g. "009" matches "009-Black")
            for col in cw_cols:
                col_prefix = str(col).split("-")[0].strip()
                if col_prefix == cw_prefix:
                    v = str(row_match.iloc[0][col]).strip()
                    if v and v.lower() not in ("none", "nan", "stock", "artwork", ""):
                        return v
            return ""

        # Try color_bom first (has the actual colorway color values)
        color_bom_df = bom_data.get("color_bom")
        result = _lookup_in_df(color_bom_df)
        if result:
            return result

        # Fallback: color_specification
        return _lookup_in_df(color_spec)

    def get_care(key: str, matched_cw: str, cw_num: str) -> str:
        e = care_codes.get(matched_cw) or care_codes.get(cw_num, {})
        return _nv(e.get(key, ""))

    def get_content(key: str, matched_cw: str, cw_num: str) -> str:
        e = content_codes.get(matched_cw) or content_codes.get(cw_num, {})
        return _nv(e.get(key, ""))

    # Label comp name/id split helper
    def split_comp(sel: str):
        if sel and " - " in str(sel):
            parts = str(sel).rsplit(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        return (str(sel) if sel else ""), ""

    for idx, row in result.iterrows():

        # ── Style match check ─────────────────────────────────────────────
        buyer_style = str(row.get("Buyer Style Number", "")).strip().upper()
        if buyer_style and bom_style:
            if buyer_style != bom_style and buyer_style not in bom_style and bom_style not in buyer_style:
                result.at[idx, "Validation Status"] = f"❌ Error: Style mismatch ({buyer_style} vs {bom_style})"
                continue

        # ── Colorway matching ─────────────────────────────────────────────
        color_raw  = str(row.get("Color/Option", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw:
            result.at[idx, "Validation Status"] = f"❌ Error: Unknown colorway '{color_raw}'"
            continue

        cw_num = (
            matched_cw.split("-")[0].strip() if "-" in matched_cw
            else matched_cw.split()[0] if " " in matched_cw
            else matched_cw
        )

        # ── Label component selections from UI ────────────────────────────
        main_comp, main_id = split_comp(bom_data.get("selected_main_label_comp", ""))
        care_comp, care_id = split_comp(bom_data.get("selected_care_label_comp", ""))

        # ── Material codes (using improved _get_material_code_for_comp) ───
        main_code = get_code(main_comp) if main_comp else "N/A"
        care_code = get_code(care_comp) if care_comp else "N/A"

        # ── Colors — from color_specification only (exact colorway match) ──
        # Do NOT fall back to color_bom colorway value — that contains fabric/material
        # descriptions for non-label components, not label colors.
        main_color = get_color_from_spec(main_comp, matched_cw)
        care_color = get_color_from_spec(care_comp, matched_cw)

        # ── Write: Main Label ─────────────────────────────────────────────
        result.at[idx, "Main Label"]          = main_id or main_code or "N/A"
        result.at[idx, "Main Label Color"]    = main_color or "N/A"
        result.at[idx, "Main Label Supplier"] = resolve_supplier(main_code)

        # ── Write: Additional Main Label ──────────────────────────────────
        logo_code  = get_code("Label Logo 1")
        logo_color = get_color_from_spec("Label Logo 1", matched_cw)
        result.at[idx, "Additional Main Label"]       = logo_code or "N/A"
        result.at[idx, "Additional Main Label Color"] = logo_color or "N/A"

        # ── Write: Care Label ─────────────────────────────────────────────
        result.at[idx, "Care Label"]          = care_id or care_code or "N/A"
        result.at[idx, "Care Label Color"]    = care_color or "N/A"
        result.at[idx, "Care Label Supplier"] = resolve_supplier(care_code)

        # ── Write: Care / Content codes ───────────────────────────────────
        result.at[idx, "Content Code"] = get_content("content_code", matched_cw, cw_num)
        result.at[idx, "TP FC"]        = get_content("shell",        matched_cw, cw_num)
        result.at[idx, "Care Code"]    = get_care("care_code",       matched_cw, cw_num)

        # ── Write: Hangtag ────────────────────────────────────────────────
        ht_code = get_code("Hangtag Package Part")
        ht_cw   = get_cw_val("Hangtag Package Part", matched_cw)
        result.at[idx, "Hangtag"]          = ht_code or extract_id_only(ht_cw) or "N/A"
        result.at[idx, "Hangtag Supplier"] = resolve_supplier(ht_code)

        # ── Write: Hangtag RFID ───────────────────────────────────────────
        # RFID is typically a separate component; fall back to Hangtag Part description
        rfid_comp = components.get("Hangtag Package Part", {})
        rfid_desc = str(rfid_comp.get("description", ""))
        rfid_code = extract_material_code(rfid_desc)
        # Also try colorway value of hangtag for RFID code
        if not rfid_code:
            rfid_code = extract_material_code(ht_cw)
        result.at[idx, "Hangtag (RFID)"]         = rfid_code or extract_id_only(rfid_desc) or "N/A"
        result.at[idx, "Hangtag (RFID) Supplier"] = resolve_supplier(rfid_code or ht_code)
        result.at[idx, "RFID Sticker"]            = rfid_code or extract_id_only(rfid_desc) or "N/A"
        result.at[idx, "RFID Sticker Supplier"]   = resolve_supplier(rfid_code or ht_code)

        # ── Write: UPC Sticker ────────────────────────────────────────────
        upc_code = get_code("Packaging 3")
        upc_cw   = get_cw_val("Packaging 3", matched_cw)
        result.at[idx, "UPC Sticker (Polybag)"] = upc_code or extract_id_only(upc_cw) or "N/A"
        result.at[idx, "UPC Sticker Supplier"]  = resolve_supplier(upc_code)

        # ── Validation status ─────────────────────────────────────────────
        not_found = sum(1 for c in NEW_COLUMNS[:-1] if str(result.at[idx, c]) == "N/A")
        if not_found == 0:
            result.at[idx, "Validation Status"] = "✅ Validated"
        elif not_found < len(NEW_COLUMNS) - 1:
            result.at[idx, "Validation Status"] = "⚠️ Partial"
        else:
            result.at[idx, "Validation Status"] = "❌ Error: No BOM data matched"

    return result