from typing import Dict
import pandas as pd


def extract_supplier_lookup(costing_detail_df: pd.DataFrame) -> Dict[str, dict]:
    """Return { material_code: {supplier, country_of_origin, description} }"""
    if costing_detail_df is None or costing_detail_df.empty:
        return {}

    df = costing_detail_df.copy()
    # Normalize columns
    cols = {c.lower(): c for c in df.columns}
    comp_col = cols.get('component') or 'Component'
    mat_col = cols.get('material') or 'Material'
    desc_col = cols.get('description') or 'Description'
    supp_col = cols.get('supplier') or 'Supplier'
    coo_col = cols.get('country of origin') or 'Country of Origin'

    out: Dict[str, dict] = {}
    for _, row in df.iterrows():
        material = str(row.get(mat_col, '')).strip()
        if not material:
            # try to parse digits out of description
            material = ''
        # material code is often numeric in parentheses inside description
        if not material and desc_col in df.columns:
            import re
            m = re.search(r"\((\d{3,6})\)", str(row.get(desc_col, '')))
            if m:
                material = m.group(1)

        if not material:
            continue
        out[material] = {
            "supplier": str(row.get(supp_col, '')).strip(),
            "country_of_origin": str(row.get(coo_col, '')).strip(),
            "description": str(row.get(desc_col, '')).strip(),
        }
    return out
