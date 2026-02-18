from typing import Dict
import re
import pandas as pd


def find_supplier_by_code(costing_detail_df: pd.DataFrame, material_code: str) -> str:
    """
    Search costing detail for material_code and return supplier.
    Material codes like 003287, 075660, 097305 should find their suppliers in the Costing BOM.
    """
    if costing_detail_df is None or costing_detail_df.empty or not material_code:
        return "N/A"

    material_code = str(material_code).strip()
    if not material_code or material_code.lower() == "n/a":
        return "N/A"

    df = costing_detail_df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # Locate supplier column
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

    # Locate material column
    material_col = None
    for col in df.columns:
        if col == "material":
            material_col = col
            break
    if not material_col:
        for col in df.columns:
            if "material" in col:
                material_col = col
                break

    pattern = re.compile(r'\b' + re.escape(material_code) + r'\b')

    # Strategy 1: match in dedicated material column
    if material_col:
        for _, row in df.iterrows():
            cell_val = str(row.get(material_col, '')).strip()
            if cell_val == material_code or pattern.search(cell_val):
                supplier = str(row.get(supplier_col, '')).strip()
                if supplier and supplier.lower() not in ("", "nan", "none"):
                    return supplier

    # Strategy 2: scan every cell in each row for the material code
    for _, row in df.iterrows():
        for col in df.columns:
            cell_val = str(row.get(col, '')).strip()
            if pattern.search(cell_val):
                supplier = str(row.get(supplier_col, '')).strip()
                if supplier and supplier.lower() not in ("", "nan", "none"):
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

        # Fall back to extracting a numeric code from the description
        if not material and desc_col:
            m = re.search(r'\b(\d{3,6})\b', str(row.get(desc_col, '')))
            material = m.group(1) if m else ''

        if not material:
            continue

        supplier = str(row.get(supp_col, '')).strip() if supp_col else ''
        # Only skip truly empty / NaN values — keep "Contractor", "unassigned", etc.
        if supplier.lower() in ("", "nan", "none"):
            supplier = ''

        out[material] = {
            "supplier":          supplier,
            "country_of_origin": str(row.get(coo_col,  '')).strip() if coo_col  else '',
            "description":       str(row.get(desc_col, '')).strip() if desc_col else '',
        }

    return out