from typing import Dict, Any
import pandas as pd


def extract_color_bom_lookup(color_bom_df: pd.DataFrame) -> Dict[str, Any]:
    """Build nested lookup dict from Color BOM table. Best-effort header detection.
    Expected columns include 'Component', 'Details', 'Usage' and per-colorway columns.
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
    details_col = 'Details' if 'Details' in df.columns else None
    usage_col = 'Usage' if 'Usage' in df.columns else None

    for _, row in df.iterrows():
        comp = str(row.get(component_col, '')).strip()
        if not comp or 'sap material code' in comp.lower():
            continue
        details = str(row.get(details_col, '')).strip() if details_col else ''
        usage = str(row.get(usage_col, '')).strip() if usage_col else ''

        # attempt to extract a leading material code token like (075660)
        material_code = ''
        for tok in details.replace('[', '(').replace(']', ')').split():
            t = tok.strip('() ,;')
            if t.isdigit() and 3 <= len(t) <= 6:
                material_code = t
                break

        colorways = {cw: str(row.get(cw, '')).strip() for cw in colorway_cols if cw in row}
        lookup["components"][comp] = {
            "material_code": material_code,
            "description": details,
            "usage": usage,
            "colorways": colorways,
        }

    return lookup
