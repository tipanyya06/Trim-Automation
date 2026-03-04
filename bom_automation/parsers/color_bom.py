from typing import Dict, Any
import re
import pandas as pd


def extract_color_bom_lookup(color_bom_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Build nested lookup dict from Color BOM table. Best-effort header detection.
    Expected columns include 'Component', 'Details', 'Usage' and per-colorway columns.

    BUG FIX: material code token extraction previously capped at len <= 6, which
    silently dropped 7-digit Columbia material codes (e.g. 1234567).
    Fixed range: 4 <= len <= 7  (3-digit tokens are almost always quantities, not codes).
    """
    if color_bom_df is None or color_bom_df.empty:
        return {"SAP_codes": {}, "components": {}}

    cols = [c.strip() for c in color_bom_df.columns]
    df = color_bom_df.copy()
    df.columns = cols

    # Identify colorway columns as those that include '-' and a number prefix
    colorway_cols = [c for c in cols if '-' in c and c.split('-', 1)[0].isdigit()]

    lookup = {"SAP_codes": {}, "components": {}}

    # Try to find SAP Material Code row
    sap_row = None
    if 'Component' in df.columns:
        sap_row = df[df['Component'].str.contains('SAP Material Code', case=False, na=False)]
    if sap_row is not None and not sap_row.empty:
        row = sap_row.iloc[0]
        for cw in colorway_cols:
            val = str(row.get(cw, '')).strip()
            if val:
                lookup["SAP_codes"][cw] = val

    # Build components
    component_col = 'Component' if 'Component' in df.columns else df.columns[0]
    details_col   = 'Details'   if 'Details'   in df.columns else None
    usage_col     = 'Usage'     if 'Usage'     in df.columns else None

    for _, row in df.iterrows():
        comp = str(row.get(component_col, '')).strip()
        if not comp or 'sap material code' in comp.lower():
            continue
        details = str(row.get(details_col, '')).strip() if details_col else ''
        usage   = str(row.get(usage_col,   '')).strip() if usage_col   else ''

        # ── FIX: extract material code token ─────────────────────────────────
        # Original: 3 <= len(t) <= 6  — missed all 7-digit codes.
        # Fix:      4 <= len(t) <= 7  — 3-digit tokens are quantities, not codes;
        #                               Columbia codes go up to 7 digits.
        material_code = ''
        for tok in details.replace('[', '(').replace(']', ')').split():
            t = tok.strip('() ,;')
            if t.isdigit() and 4 <= len(t) <= 7:
                material_code = t
                break

        colorways = {cw: str(row.get(cw, '')).strip() for cw in colorway_cols if cw in row}
        lookup["components"][comp] = {
            "material_code": material_code,
            "description":   details,
            "usage":         usage,
            "colorways":     colorways,
        }

    return lookup


# ── Supplier helpers (unchanged) ──────────────────────────────────────────────

def find_supplier_by_code(costing_detail_df: pd.DataFrame, material_code: str) -> str:
    """
    Search costing detail for material_code and return supplier.
    Uses flexible matching: direct containment + zero-stripped variant.
    """
    if costing_detail_df is None or costing_detail_df.empty or not material_code:
        return "N/A"

    material_code = str(material_code).strip()
    if not material_code or material_code.lower() == "n/a":
        return "N/A"

    code_stripped = material_code.lstrip("0")

    df = costing_detail_df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    supplier_col = None
    for col in df.columns:
        if col == "supplier":
            supplier_col = col
            break
    if not supplier_col:
        for col in df.columns:
            if "supplier" in col or "vendor" in col:
                supplier_col = col
                break
    if not supplier_col:
        return "N/A"

    def _clean_supplier(val: str) -> str:
        val = val.strip()
        if not val or val.lower() in ("nan", "none", ""):
            return ""
        prev = None
        while prev != val:
            prev = val
            val = re.sub(r'(?<![a-zA-Z])([A-Z]) ([A-Z])(?![a-zA-Z])', r'\1\2', val)
        return val.strip()

    def _cell_matches(cell_str: str) -> bool:
        s = str(cell_str).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return False
        if material_code in s:
            return True
        if code_stripped and code_stripped in s:
            return True
        digits = re.sub(r'[^\d]', '', s)
        if digits == material_code or (code_stripped and digits == code_stripped):
            return True
        return False

    all_cols = list(df.columns)
    for _, row in df.iterrows():
        for col in all_cols:
            if col == supplier_col:
                continue
            if _cell_matches(str(row.get(col, ''))):
                supplier = _clean_supplier(str(row.get(supplier_col, '')))
                if supplier:
                    return supplier

    return "N/A"


def extract_supplier_lookup(costing_detail_df: pd.DataFrame) -> Dict[str, dict]:
    """Return {material_code: {supplier, country_of_origin, description}}"""
    if costing_detail_df is None or costing_detail_df.empty:
        return {}

    df = costing_detail_df.copy()
    cols     = {c.lower(): c for c in df.columns}
    mat_col  = cols.get('material') or cols.get('material code') or None
    desc_col = cols.get('description') or cols.get('desc') or None
    supp_col = cols.get('supplier') or cols.get('vendor') or None
    coo_col  = cols.get('country of origin') or cols.get('origin') or None

    out: Dict[str, dict] = {}
    for _, row in df.iterrows():
        material = str(row.get(mat_col, '')).strip() if mat_col else ''

        if not material and desc_col:
            m = re.search(r'(?<!\d)(\d{3,7})(?!\d)', str(row.get(desc_col, '')))
            material = m.group(1) if m else ''

        if not material:
            continue

        supplier = str(row.get(supp_col, '')).strip() if supp_col else ''
        if supplier.lower() in ("", "nan", "none"):
            supplier = ''

        out[material] = {
            "supplier":          supplier,
            "country_of_origin": str(row.get(coo_col,  '')).strip() if coo_col  else '',
            "description":       str(row.get(desc_col, '')).strip() if desc_col else '',
        }
        # Also register zero-stripped variant
        stripped = material.lstrip("0")
        if stripped and stripped != material:
            out[stripped] = out[material]

    return out