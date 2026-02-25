from typing import Dict, Any, Optional
import pandas as pd
import re

from parsers.color_bom import extract_color_bom_lookup
from parsers.care_content import extract_care_codes, extract_content_codes
from validators.matcher import normalize_colorway, extract_material_code, extract_id_only, get_product_type

# ── Known supplier lists per field type (Changes 3 & 4) ──────────────────────
_KNOWN_HANGTAG_SUPPLIERS    = {"avery", "bao shen", "hangsan"}
_KNOWN_MAIN_LABEL_SUPPLIERS = {"avery", "bao shen", "hangsan", "hanyang", "next gen", "joint tack"}

NEW_COLUMNS = [
    "Main Label", "Main Label Color", "Main Label Supplier",
    "Main Label 2- Gloves", "Main Label Color2", "Main Label Supplier2",
    "Hangtag", "Hangtag Supplier",
    "Hangtag 2", "Hangtag Supplier2",
    "Hangtag3", "Hangtag Supplier3",
    "Micropak Sticker -Gloves", "Micropak Sticker Supplier",
    "Size Label Woven - Gloves", "Size Label Supplier",
    "Size Sticker -Gloves", "Size Sticker Supplier -Gloves",
    "Care Label", "Care Label Color",
    "Content Code -Gloves", "TP FC - Gloves", "Care Code-Gloves",
    "Content Code", "TP FC", "Care Code",
    "Care Supplier",
    "RFID w/o MSRP", "RFID w/o MSRP Supplier",
    "RFID Stickers", "RFID Stickers Supplier",
    "UPC Bag Sticker (Polybag)", "UPC Supplier",
    "TP STATUS", "TP DATE", "PRODUCT STATUS", "REMARKS",
    "Validation Status",
]
# ── Option 1: Quick Run output columns ───────────────────────────────────────
QUICK_COLUMNS = [
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

# Maps Option 2 internal names → Option 1 output names
QUICK_COLUMN_REMAP = {
    "Main Label 2- Gloves":       "Additional Main Label",
    "Main Label Color2":          "Additional Main Label Color",
    "Care Supplier":              "Care Label Supplier",
    "RFID w/o MSRP":              "Hangtag (RFID)",
    "RFID w/o MSRP Supplier":     "Hangtag (RFID) Supplier",
    "RFID Stickers":              "RFID Sticker",
    "RFID Stickers Supplier":     "RFID Sticker Supplier",
    "UPC Bag Sticker (Polybag)":  "UPC Sticker (Polybag)",
    "UPC Supplier":               "UPC Sticker Supplier",
}


def _nv(val: Any) -> str:
    s = str(val).strip()
    return "N/A" if (not s or s.lower() in ("none", "nan", "")) else s


def _fix_sup(s: str) -> str:
    """Fix OCR-split acronyms: 'Y K K' -> 'YKK'."""
    if not s:
        return s
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\b([A-Z]{1,3}) ([A-Z]{1,3})\b', r'\1\2', s)
    return s.strip()


def _check_fgv_contractor(supplier_raw: str) -> bool:
    """Change 2: True if supplier string contains both FGV and Contractor → must return N/A."""
    sl = supplier_raw.lower()
    return "fgv" in sl and "contractor" in sl


def _match_known_supplier(supplier_raw: str, field_type: str) -> str:
    """
    Changes 3 & 4: Match raw supplier string against known lists per field type.
    Returns matched name (title-cased) or original if no match.
    field_type: 'hangtag' | 'main_label' | 'care_label' | 'other'
    """
    if not supplier_raw or supplier_raw == "N/A":
        return supplier_raw
    sl = supplier_raw.lower()
    known = (
        _KNOWN_HANGTAG_SUPPLIERS    if field_type == "hangtag"
        else _KNOWN_MAIN_LABEL_SUPPLIERS if field_type in ("main_label", "care_label")
        else set()
    )
    for name in known:
        if name in sl:
            return name.title()
    return supplier_raw


def _get_material_code_for_comp(comp: dict) -> str:
    mc = str(comp.get("material_code", "")).strip()
    if mc and mc not in ("", "N/A", "nan", "none"):
        return mc
    desc = str(comp.get("description", "")).strip()
    if desc:
        found = extract_material_code(desc)
        if found:
            return found
    for cw_val in comp.get("colorways", {}).values():
        found = extract_material_code(str(cw_val))
        if found:
            return found
    return ""


def _find_supplier_in_costing(costing_df: pd.DataFrame, code: str) -> str:
    """Search costing detail rows for a material code and return the supplier."""
    if costing_df is None or costing_df.empty or not code or code == "N/A":
        return "N/A"
    code = str(code).strip()
    code_stripped = code.lstrip("0")
    sup_col = None
    for col in costing_df.columns:
        if "supplier" in str(col).lower() or "vendor" in str(col).lower():
            sup_col = col
            break
    if not sup_col:
        return "N/A"

    def _cell_has_code(cell_str: str) -> bool:
        s = str(cell_str).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return False
        if code in s:
            return True
        if code_stripped and code_stripped in s:
            return True
        digits = re.sub(r'[^\d]', '', s)
        return digits == code or (bool(code_stripped) and digits == code_stripped)

    for _, row in costing_df.iterrows():
        for col in costing_df.columns:
            if col == sup_col:
                continue
            if _cell_has_code(str(row.get(col, ""))):
                sup = _fix_sup(str(row.get(sup_col, "")).strip())
                if sup and sup.lower() not in ("", "nan", "none"):
                    return sup
    return "N/A"


def _validate_hangtag_from_costing(costing_df: pd.DataFrame) -> str:
    """
    Change 7: Scan costing BOM description for 'hangtag', validate hierarchy.
    Returns material code if hierarchy is valid, 'N/A' if FGV+Contractor, '' if not found.
    """
    if costing_df is None or costing_df.empty:
        return ""
    desc_col = sup_col = mat_col = None
    for col in costing_df.columns:
        cl = str(col).lower()
        if ("description" in cl or "desc" in cl) and desc_col is None:
            desc_col = col
        if ("supplier" in cl or "vendor" in cl) and sup_col is None:
            sup_col = col
        if cl in ("material", "material code") and mat_col is None:
            mat_col = col
    if not desc_col:
        return ""
    for _, row in costing_df.iterrows():
        desc = str(row.get(desc_col, "")).strip()
        if "hangtag" not in desc.lower():
            continue
        supplier = _fix_sup(str(row.get(sup_col, "")).strip()) if sup_col else ""
        # Change 2: FGV + Contractor hierarchy
        if supplier and _check_fgv_contractor(supplier):
            return "N/A"
        code = ""
        if mat_col:
            code = str(row.get(mat_col, "")).strip()
        if not code:
            code = extract_material_code(desc)
        if code:
            return code
    return ""


def validate_and_fill(
    comparison_df: pd.DataFrame,
    bom_data: Dict[str, Any],
    product_type: str = "standard",
) -> pd.DataFrame:
    result = comparison_df.copy()

    color_bom_lookup = extract_color_bom_lookup(bom_data.get("color_bom", pd.DataFrame()))
    care_codes    = extract_care_codes(
        bom_data.get("care_report",    pd.DataFrame()),
        bom_data.get("content_report", pd.DataFrame()),
    )
    content_codes = extract_content_codes(bom_data.get("content_report", pd.DataFrame()))

    components      = color_bom_lookup.get("components", {})
    sap_codes       = color_bom_lookup.get("SAP_codes", {})
    available_cw    = list(sap_codes.keys()) if sap_codes else []
    supplier_lookup = bom_data.get("supplier_lookup", {})
    costing_detail  = bom_data.get("costing_detail", pd.DataFrame())
    bom_style       = str(bom_data.get("metadata", {}).get("style", "")).strip().upper()
    color_spec      = bom_data.get("color_specification")

    # Change 7: pre-scan costing BOM for hangtag code once per BOM
    costing_hangtag_code = _validate_hangtag_from_costing(costing_detail)

    # Settings passed in from the UI per style (Change 1)
    label_settings = bom_data.get("label_settings", {})

    for col in NEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""

    # ── Unified supplier resolver (Changes 2, 3, 4) ───────────────────────────
    def resolve_supplier(mat_code: str, field_type: str = "other") -> str:
        if not mat_code or mat_code == "N/A":
            return "N/A"
        cached = supplier_lookup.get(mat_code, "")
        if cached and cached.lower() not in ("", "nan", "none"):
            raw = _fix_sup(cached)
        else:
            raw = _find_supplier_in_costing(costing_detail, mat_code)
            if raw != "N/A":
                supplier_lookup[mat_code] = raw
        # Change 2: FGV + Contractor hierarchy check
        if raw and _check_fgv_contractor(raw):
            return "N/A"
        # Changes 3/4: match against known supplier list for field type
        return _match_known_supplier(raw, field_type)

    def get_code(comp_key: str) -> str:
        return _get_material_code_for_comp(components.get(comp_key, {}))

    def get_cw_val(comp_key: str, matched_cw: str) -> str:
        return _nv(components.get(comp_key, {}).get("colorways", {}).get(matched_cw, ""))

    def get_color_from_spec(component_name: str, matched_cw: str, raw_color_option: str = "") -> str:
        if not component_name:
            return ""

        def _extract_prefix(s: str) -> str:
            s = str(s).strip()
            m = re.match(r'[A-Za-z]+-(\d+)', s)
            if m:
                return m.group(1)
            m = re.match(r'(\d+)', s)
            return m.group(1) if m else ""

        cw_prefix = _extract_prefix(raw_color_option) or _extract_prefix(matched_cw)
        exact_cw  = matched_cw

        def _lookup_in_df(df: pd.DataFrame) -> str:
            if df is None or df.empty:
                return ""
            comp_col = df.columns[0]
            lookup_name = component_name.split(" - ")[0].strip() if " - " in component_name else component_name
            lookup_name_lower = lookup_name.lower()
            row_match = df[df[comp_col] == lookup_name]
            if row_match.empty:
                row_match = df[df[comp_col].str.lower() == lookup_name_lower]
            if row_match.empty:
                row_match = df[df[comp_col].str.lower().str.contains(lookup_name_lower, na=False, regex=False)]
            if row_match.empty:
                return ""
            cw_cols   = [c for c in df.columns[1:] if c and not str(c).startswith("col_")]
            skip_vals = {"none", "nan", "stock", "artwork", ""}
            if exact_cw in cw_cols:
                v = str(row_match.iloc[0][exact_cw]).strip()
                if v and v.lower() not in skip_vals:
                    return v
            if cw_prefix:
                for col in cw_cols:
                    if str(col).split("-")[0].strip() == cw_prefix:
                        v = str(row_match.iloc[0][col]).strip()
                        if v and v.lower() not in skip_vals:
                            return v
            return ""

        res = _lookup_in_df(bom_data.get("color_bom"))
        return res if res else _lookup_in_df(color_spec)

    def _extract_num_prefix(s: str) -> str:
        s = str(s).strip()
        for pattern in [r'[A-Za-z]+-(\d{3})', r'^(\d{3})']:
            m = re.match(pattern, s)
            if m:
                return m.group(1)
        m = re.search(r'(\d{3})', s)
        return m.group(1) if m else ""

    def get_care(key: str, matched_cw: str, cw_num: str, raw: str = "") -> str:
        raw_prefix = _extract_num_prefix(raw)
        cw_num_stripped = cw_num.lstrip("0") or cw_num
        e = (
            care_codes.get(matched_cw)
            or care_codes.get(cw_num)
            or care_codes.get(cw_num_stripped)
            or (care_codes.get(raw_prefix) if raw_prefix else None)
            or care_codes.get("__default__")
            or {}
        )
        return _nv(e.get(key, ""))

    def get_content(key: str, matched_cw: str, cw_num: str, raw: str = "") -> str:
        raw_prefix = _extract_num_prefix(raw)
        cw_num_stripped = cw_num.lstrip("0") or cw_num
        e = (
            content_codes.get(matched_cw)
            or content_codes.get(cw_num)
            or content_codes.get(cw_num_stripped)
            or (content_codes.get(raw_prefix) if raw_prefix else None)
            or content_codes.get("__default__")
            or {}
        )
        return _nv(e.get(key, ""))

    def split_comp(sel: str):
        if sel and " - " in str(sel):
            parts = str(sel).rsplit(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        return (str(sel) if sel else ""), ""

    for idx, row in result.iterrows():

        # ── Style match ────────────────────────────────────────────────────
        # Support both old "Buyer Style Number" and new "JDE Style" column (Change 5)
        buyer_style = str(
            row.get("Buyer Style Number", "") or row.get("JDE Style", "")
        ).strip().upper()
        if buyer_style and bom_style:
            if buyer_style != bom_style and buyer_style not in bom_style and bom_style not in buyer_style:
                result.at[idx, "Validation Status"] = f"❌ Error: Style mismatch ({buyer_style} vs {bom_style})"
                continue

        # ── Colorway matching ──────────────────────────────────────────────
        # Support both old "Color/Option" and new "Color" column (Change 5)
        color_raw  = str(row.get("Color/Option", "") or row.get("Color", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw:
            result.at[idx, "Validation Status"] = f"❌ Error: Unknown colorway '{color_raw}'"
            continue

        cw_num = _extract_num_prefix(matched_cw) or _extract_num_prefix(color_raw)
        if not cw_num:
            cw_num = (
                matched_cw.split("-")[0].strip() if "-" in matched_cw
                else matched_cw.split()[0] if " " in matched_cw
                else matched_cw
            )

        # ── Change 6: detect product type per row from Material Name ───────
        mat_name         = str(row.get("Material Name", "") or "").strip()
        row_product_type = get_product_type(mat_name) if mat_name else product_type
        is_glove         = (row_product_type == "glove")

        # ── Component selections from Settings UI (Change 1) ───────────────
        raw_main         = label_settings.get("main_label", "")     or bom_data.get("selected_main_label_comp", "")
        raw_care         = label_settings.get("care_label", "")     or bom_data.get("selected_care_label_comp", "")
        raw_add_main     = label_settings.get("add_main_label", "")
        raw_ht           = label_settings.get("hangtag", "")
        raw_ht2          = label_settings.get("hangtag2", "")
        raw_ht3          = label_settings.get("hangtag3", "")
        raw_micro        = label_settings.get("micropack", "")
        raw_size_label   = label_settings.get("size_label", "")
        raw_size_sticker = label_settings.get("size_sticker", "")
        raw_rfid_no_msrp = label_settings.get("rfid_no_msrp", "")
        raw_rfid         = label_settings.get("hangtag_rfid", "")
        raw_rfid_sticker = label_settings.get("rfid_sticker", "")
        raw_upc          = label_settings.get("upc_sticker", "")

        main_comp, main_id   = split_comp(raw_main)
        care_comp, care_id   = split_comp(raw_care)
        ht_comp,   ht_id     = split_comp(raw_ht)
        ht2_comp,  ht2_id    = split_comp(raw_ht2)
        ht3_comp,  ht3_id    = split_comp(raw_ht3)

        # ── Material codes ─────────────────────────────────────────────────
        main_code         = get_code(main_comp)     if main_comp     else "N/A"
        care_code_mat     = get_code(care_comp)     if care_comp     else "N/A"
        logo_code         = get_code(raw_add_main.split(" - ")[0]) if raw_add_main and raw_add_main != "N/A" else get_code("Label Logo 1")
        micro_code        = get_code(raw_micro.split(" - ")[0])    if raw_micro    and raw_micro    != "N/A" else "N/A"
        size_label_code   = get_code(raw_size_label.split(" - ")[0])   if raw_size_label   and raw_size_label   != "N/A" else "N/A"
        size_sticker_code = get_code(raw_size_sticker.split(" - ")[0]) if raw_size_sticker and raw_size_sticker != "N/A" else "N/A"

        # Hangtag from settings → costing BOM validation (Change 7)
        ht_cw   = get_cw_val("Hangtag Package Part", matched_cw)
        ht_code = ht_id or get_code(ht_comp) if (ht_comp or ht_id) else get_code("Hangtag Package Part")
        if costing_hangtag_code == "N/A":
            ht_code = "N/A"   # FGV+Contractor hierarchy failed
        elif costing_hangtag_code:
            ht_code = costing_hangtag_code  # costing BOM code takes precedence

        ht2_code = ht2_id or (get_code(ht2_comp) if ht2_comp else "")
        ht3_code = ht3_id or (get_code(ht3_comp) if ht3_comp else "")

        # RFID
        rfid_code = rfid_supplier = ""
        if raw_rfid and raw_rfid != "N/A":
            rfid_comp_name, rfid_code = split_comp(raw_rfid)
            if not rfid_code:
                rfid_code = get_code(rfid_comp_name)
        if not rfid_code:
            for rfid_key in ["RFID Tag", "RFID Label", "RFID Sticker", "Hangtag RFID"]:
                rfid_code = get_code(rfid_key)
                if rfid_code:
                    break
        if not rfid_code:
            rfid_code = extract_material_code(str(components.get("Hangtag Package Part", {}).get("description", ""))) or extract_material_code(ht_cw)
        rfid_supplier = resolve_supplier(rfid_code) if rfid_code else resolve_supplier(ht_code)

        rfid_sticker_code = rfid_sticker_sup = ""
        if raw_rfid_sticker and raw_rfid_sticker != "N/A":
            rs_comp, rfid_sticker_code = split_comp(raw_rfid_sticker)
            if not rfid_sticker_code:
                rfid_sticker_code = get_code(rs_comp)
        rfid_sticker_code = rfid_sticker_code or rfid_code
        rfid_sticker_sup  = resolve_supplier(rfid_sticker_code)

        upc_code = get_code(raw_upc.split(" - ")[0]) if raw_upc and raw_upc != "N/A" else get_code("Packaging 3")
        upc_cw   = get_cw_val("Packaging 3", matched_cw)
        
        # RFID w/o MSRP — from settings, same fallback chain as raw_rfid, no fallback if empty
        rfid_no_msrp_code = rfid_no_msrp_sup = ""
        if raw_rfid_no_msrp and raw_rfid_no_msrp != "N/A":
            rn_comp, rfid_no_msrp_code = split_comp(raw_rfid_no_msrp)
            if not rfid_no_msrp_code:
                rfid_no_msrp_code = get_code(rn_comp)
            if not rfid_no_msrp_code:
                for rfid_key in ["RFID Tag", "RFID Label", "RFID Sticker", "Hangtag RFID"]:
                    rfid_no_msrp_code = get_code(rfid_key)
                    if rfid_no_msrp_code:
                        break
            if not rfid_no_msrp_code:
                rfid_no_msrp_code = (
                    extract_material_code(str(components.get("Hangtag Package Part", {}).get("description", "")))
                    or extract_material_code(ht_cw)
                )
            rfid_no_msrp_sup = resolve_supplier(rfid_no_msrp_code, "other") if rfid_no_msrp_code else "N/A"
        else:
            rfid_no_msrp_code = "N/A"
            rfid_no_msrp_sup  = "N/A"

        # ── Colors ────────────────────────────────────────────────────────
        main_color = get_color_from_spec(main_comp, matched_cw, color_raw)
        care_color = get_color_from_spec(care_comp, matched_cw, color_raw)
        logo_color = get_color_from_spec("Label Logo 1", matched_cw, color_raw)

        # ── Write all columns (exact names match NEW_COLUMNS / export header) ──

        # Main Label (cols 1-3)
        result.at[idx, "Main Label"]          = main_id or main_code or "N/A"
        result.at[idx, "Main Label Color"]    = main_color or "N/A"
        result.at[idx, "Main Label Supplier"] = resolve_supplier(main_code, "main_label")

        # Main Label 2 - Gloves (cols 4-6): additional/logo label, glove-specific
        result.at[idx, "Main Label 2- Gloves"]   = logo_code  if is_glove else "N/A"
        result.at[idx, "Main Label Color2"]      = logo_color if is_glove else "N/A"
        result.at[idx, "Main Label Supplier2"]   = resolve_supplier(logo_code, "main_label") if is_glove else "N/A"

        # Hangtag, Hangtag 2, Hangtag3 (cols 7-12)
        result.at[idx, "Hangtag"]           = ht_code or extract_id_only(ht_cw) or "N/A"
        result.at[idx, "Hangtag Supplier"]  = resolve_supplier(ht_code or extract_id_only(ht_cw), "hangtag")
        result.at[idx, "Hangtag 2"]         = ht2_code or "N/A"
        result.at[idx, "Hangtag Supplier2"] = resolve_supplier(ht2_code, "hangtag") if ht2_code else "N/A"
        result.at[idx, "Hangtag3"]          = ht3_code or "N/A"
        result.at[idx, "Hangtag Supplier3"] = resolve_supplier(ht3_code, "hangtag") if ht3_code else "N/A"

        # Micropak / Size Label / Size Sticker — glove-only fields (cols 13-18)
        result.at[idx, "Micropak Sticker -Gloves"]    = micro_code        if is_glove else "N/A"
        result.at[idx, "Micropak Sticker Supplier"]   = resolve_supplier(micro_code) if is_glove else "N/A"
        result.at[idx, "Size Label Woven - Gloves"]   = size_label_code   if is_glove else "N/A"
        result.at[idx, "Size Label Supplier"]         = resolve_supplier(size_label_code) if is_glove else "N/A"
        result.at[idx, "Size Sticker -Gloves"]        = size_sticker_code if is_glove else "N/A"
        result.at[idx, "Size Sticker Supplier -Gloves"] = resolve_supplier(size_sticker_code) if is_glove else "N/A"
    
        # Care Label (cols 19-20)
        result.at[idx, "Care Label"]       = care_id or care_code_mat or "N/A"
        result.at[idx, "Care Label Color"] = care_color or "N/A"

        # Glove-specific content/care codes (cols 21-23)
        if is_glove:
            result.at[idx, "Content Code -Gloves"] = get_content("content_code", matched_cw, cw_num, color_raw)
            result.at[idx, "TP FC - Gloves"]       = get_content("shell",        matched_cw, cw_num, color_raw)
            result.at[idx, "Care Code-Gloves"]     = get_care("care_code",       matched_cw, cw_num, color_raw)
        else:
            result.at[idx, "Content Code -Gloves"] = "N/A"
            result.at[idx, "TP FC - Gloves"]       = "N/A"
            result.at[idx, "Care Code-Gloves"]     = "N/A"

        # Standard content/care codes (cols 24-26)
        result.at[idx, "Content Code"] = get_content("content_code", matched_cw, cw_num, color_raw)
        result.at[idx, "TP FC"]        = get_content("shell",        matched_cw, cw_num, color_raw)
        result.at[idx, "Care Code"]    = get_care("care_code",       matched_cw, cw_num, color_raw)

        # Care Supplier (col 27)
        result.at[idx, "Care Supplier"] = resolve_supplier(care_code_mat, "care_label")

        
        # RFID w/o MSRP / RFID Stickers (cols 28-31)
        result.at[idx, "RFID w/o MSRP"]          = rfid_no_msrp_code
        result.at[idx, "RFID w/o MSRP Supplier"] = rfid_no_msrp_sup
        result.at[idx, "RFID Stickers"]           = rfid_sticker_code or "N/A"
        result.at[idx, "RFID Stickers Supplier"]  = rfid_sticker_sup  or "N/A"

        # UPC Bag Sticker (cols 32-33)
        result.at[idx, "UPC Bag Sticker (Polybag)"] = upc_code or extract_id_only(upc_cw) or "N/A"
        result.at[idx, "UPC Supplier"]              = resolve_supplier(upc_code)

        # Free-text fields from Settings UI (cols 34-37)
        for field, key in [("TP STATUS", "tp_status"), ("TP DATE", "tp_date"),
                           ("PRODUCT STATUS", "product_status"), ("REMARKS", "remarks")]:
            if not str(result.at[idx, field]).strip():
                result.at[idx, field] = label_settings.get(key, "")

        # ── Validation status ──────────────────────────────────────────────
        core_cols = [
            "Main Label", "Main Label Supplier", "Care Label", "Care Supplier",
            "Content Code", "Care Code", "Hangtag", "Hangtag Supplier",
        ]
        not_found = sum(1 for c in core_cols if str(result.at[idx, c]) in ("N/A", "", "nan"))
        if not_found == 0:
            result.at[idx, "Validation Status"] = "✅ Validated"
        elif not_found < len(core_cols):
            result.at[idx, "Validation Status"] = "⚠️ Partial"
        else:
            result.at[idx, "Validation Status"] = "❌ Error: No BOM data matched"

    return result