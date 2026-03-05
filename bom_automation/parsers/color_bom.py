from typing import Dict, Any
import re
import pandas as pd


def extract_color_bom_lookup(color_bom_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Build nested lookup dict from Color BOM table. Best-effort header detection.
    Expected columns include 'Component', 'Details', 'Usage' and per-colorway columns.

    BUG FIX 1: material code token extraction previously capped at len <= 6, which
    silently dropped 7-digit Columbia material codes (e.g. 1234567).
    Fixed range: 4 <= len(t) <= 7  (3-digit tokens are almost always quantities, not codes).

    BUG FIX 2: multi-page Color BOMs have continuation rows where the Component cell
    is blank — the color data for that row belongs to the preceding named component.
    Previously these rows were silently skipped (the `if not comp: continue` guard),
    so any colorway columns that only appeared on page 2 of the BOM were never
    populated for those components (e.g. Alt Hat Component 1C colors 447/342/310/845/256).
    Fix: forward-fill the component column before iterating rows.
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

    # ── BUG FIX 2: forward-fill blank component names ────────────────────────
    # When the Color BOM spans multiple Excel pages/tables that are concatenated
    # into one DataFrame, continuation rows carry color data for the same
    # component but have an empty Component cell.  Forward-filling propagates
    # the last seen component name down to those rows so their colorway values
    # are captured correctly.
    #
    # We only ffill values that are genuinely empty (empty string, "None",
    # "nan") so that real blank rows between components are not mis-assigned.
    _comp_series = df[component_col].astype(str).str.strip()
    _empty_mask  = _comp_series.isin(["", "None", "nan"])
    _comp_filled = _comp_series.copy()
    _comp_filled[_empty_mask] = pd.NA        # mark truly-empty cells as NA
    _comp_filled = _comp_filled.ffill()      # propagate last non-NA value downward
    df = df.copy()
    df[component_col] = _comp_filled.fillna("") # restore empty string for rows before first comp
    # ── END BUG FIX 2 ────────────────────────────────────────────────────────

    for _, row in df.iterrows():
        comp = str(row.get(component_col, '')).strip()
        if not comp or 'sap material code' in comp.lower():
            continue
        details = str(row.get(details_col, '')).strip() if details_col else ''
        usage   = str(row.get(usage_col,   '')).strip() if usage_col   else ''

        # ── FIX 1: extract material code token ───────────────────────────────
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

        if comp in lookup["components"]:
            # ── Continuation row: merge colorway values into existing entry ──
            # For each colorway column on this row, only overwrite if the
            # existing value is empty — the first (page-1) row wins for shared
            # columns, and page-2-only columns get filled in here.
            existing_cw = lookup["components"][comp]["colorways"]
            for cw, val in colorways.items():
                if val and val.lower() not in ("", "none", "nan"):
                    if not existing_cw.get(cw) or existing_cw[cw].lower() in ("", "none", "nan"):
                        existing_cw[cw] = val
            # Also backfill material_code if the first row didn't capture it
            if material_code and not lookup["components"][comp]["material_code"]:
                lookup["components"][comp]["material_code"] = material_code
        else:
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