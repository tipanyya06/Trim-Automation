from typing import Dict
import re
import pandas as pd


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
    cols = {c.lower(): c for c in df.columns}
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