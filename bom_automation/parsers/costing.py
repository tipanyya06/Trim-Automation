from typing import Dict
import re
import pandas as pd


def find_supplier_by_code(costing_detail_df: pd.DataFrame, material_code: str) -> str:
    """
    Search costing detail for material_code and return supplier.
    Handles split words, varied column names, and embedded codes in description cells.
    """
    if costing_detail_df is None or costing_detail_df.empty or not material_code:
        return "N/A"

    material_code = str(material_code).strip()
    if not material_code or material_code.lower() == "n/a":
        return "N/A"

    df = costing_detail_df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # ── Locate supplier column ────────────────────────────────────────────────
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

    # ── Locate material/description columns to search ─────────────────────────
    search_cols = []
    for col in df.columns:
        if any(kw in col for kw in ("material", "description", "desc", "code", "item", "ref")):
            search_cols.append(col)
    # Also search ALL columns as last resort
    all_cols = list(df.columns)

    pattern = re.compile(r'\b' + re.escape(material_code) + r'\b')

    def _clean_supplier(val: str) -> str:
        """Fix split words like 'Y K K' → 'YKK', strip noise."""
        val = val.strip()
        if not val or val.lower() in ("nan", "none", ""):
            return ""
        # Fix single-letter spaced words: "Y K K" → "YKK"
        prev = None
        while prev != val:
            prev = val
            val = re.sub(r'(?<![a-zA-Z])([A-Z]) ([A-Z])(?![a-zA-Z])', r'\1\2', val)
        # Fix lowercase split: "bel cro" → "belcro" (only for known short splits)
        val = re.sub(r'([a-z]) ([a-z])', lambda m: m.group(1) + m.group(2), val)
        return val.strip()

    # Strategy 1: search in dedicated material/description columns
    for col in search_cols:
        for _, row in df.iterrows():
            cell_val = str(row.get(col, '')).strip()
            if cell_val == material_code or pattern.search(cell_val):
                supplier = _clean_supplier(str(row.get(supplier_col, '')))
                if supplier:
                    return supplier

    # Strategy 2: scan every cell in each row for the material code
    for _, row in df.iterrows():
        found_in_row = False
        for col in all_cols:
            if col == supplier_col:
                continue
            cell_val = str(row.get(col, '')).strip()
            if pattern.search(cell_val):
                found_in_row = True
                break
        if found_in_row:
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
            m = re.search(r'\b(\d{3,6})\b', str(row.get(desc_col, '')))
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

    return out