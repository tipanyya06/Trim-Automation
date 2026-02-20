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


def _find_supplier(costing_df: pd.DataFrame, code: str) -> str:
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

    def _cell_contains_code(cell_str: str) -> bool:
        s = str(cell_str).strip()
        if not s or s.lower() in ("nan", "none", ""):
            return False
        if code in s:
            return True
        if code_stripped and code_stripped in s:
            return True
        digits = re.sub(r'[^\d]', '', s)
        if digits == code or (code_stripped and digits == code_stripped):
            return True
        return False

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

    # KEY FIX: pass content_report as fallback so care codes can be extracted
    # from the content page when care_report is missing/empty
    care_codes = extract_care_codes(
        bom_data.get("care_report", pd.DataFrame()),
        bom_data.get("content_report", pd.DataFrame()),
    )
    content_codes = extract_content_codes(bom_data.get("content_report", pd.DataFrame()))

    components   = color_bom_lookup.get("components", {})
    sap_codes    = color_bom_lookup.get("SAP_codes", {})
    available_cw = list(sap_codes.keys()) if sap_codes else []

    supplier_lookup = bom_data.get("supplier_lookup", {})
    costing_detail  = bom_data.get("costing_detail", pd.DataFrame())
    bom_style       = str(bom_data.get("metadata", {}).get("style", "")).strip().upper()
    color_spec      = bom_data.get("color_specification")

    for col in NEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""

    def resolve_supplier(mat_code: str) -> str:
        if not mat_code or mat_code == "N/A":
            return "N/A"
        cached = supplier_lookup.get(mat_code, "")
        if cached and cached.lower() not in ("", "nan", "none"):
            return _fix_sup(cached)
        found = _find_supplier(costing_detail, mat_code)
        if found != "N/A":
            supplier_lookup[mat_code] = found
        return found

    def get_code(comp_key: str) -> str:
        comp = components.get(comp_key, {})
        return _get_material_code_for_comp(comp)

    def get_cw_val(comp_key: str, matched_cw: str) -> str:
        comp = components.get(comp_key, {})
        val = comp.get("colorways", {}).get(matched_cw, "")
        return _nv(val)

    def get_color_from_spec(component_name: str, matched_cw: str, raw_color_option: str = "") -> str:
        """Case-insensitive and partial component name matching."""
        if not component_name:
            return ""

        def _extract_prefix(s: str) -> str:
            s = str(s).strip()
            m = re.match(r'[A-Za-z]+-(\d+)', s)
            if m:
                return m.group(1)
            m = re.match(r'(\d+)', s)
            if m:
                return m.group(1)
            return ""

        cw_prefix = _extract_prefix(raw_color_option) or _extract_prefix(matched_cw)
        exact_cw  = matched_cw

        def _lookup_in_df(df: pd.DataFrame) -> str:
            if df is None or df.empty:
                return ""
            comp_col = df.columns[0]
            lookup_name = (
                component_name.split(" - ")[0].strip()
                if " - " in component_name else component_name
            )
            lookup_name_lower = lookup_name.lower()

            # Exact → case-insensitive → partial contains
            row_match = df[df[comp_col] == lookup_name]
            if row_match.empty:
                row_match = df[df[comp_col].str.lower() == lookup_name_lower]
            if row_match.empty:
                row_match = df[
                    df[comp_col].str.lower().str.contains(lookup_name_lower, na=False, regex=False)
                ]
            if row_match.empty:
                return ""

            cw_cols = [c for c in df.columns[1:] if c and not str(c).startswith("col_")]
            skip_vals = {"none", "nan", "stock", "artwork", ""}

            if exact_cw in cw_cols:
                v = str(row_match.iloc[0][exact_cw]).strip()
                if v and v.lower() not in skip_vals:
                    return v
            if cw_prefix:
                for col in cw_cols:
                    col_prefix = str(col).split("-")[0].strip()
                    if col_prefix == cw_prefix:
                        v = str(row_match.iloc[0][col]).strip()
                        if v and v.lower() not in skip_vals:
                            return v
            return ""

        res = _lookup_in_df(bom_data.get("color_bom"))
        if res:
            return res
        return _lookup_in_df(color_spec)

    def _extract_num_prefix(s: str) -> str:
        """Extract 3-digit colorway number from any format."""
        s = str(s).strip()
        m = re.match(r'[A-Za-z]+-(\d{3})', s)
        if m:
            return m.group(1)
        m = re.match(r'(\d{3})', s)
        if m:
            return m.group(1)
        m = re.search(r'(\d{3})', s)
        if m:
            return m.group(1)
        return ""

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

        # ── Style match check ──────────────────────────────────────────────
        buyer_style = str(row.get("Buyer Style Number", "")).strip().upper()
        if buyer_style and bom_style:
            if buyer_style != bom_style and buyer_style not in bom_style and bom_style not in buyer_style:
                result.at[idx, "Validation Status"] = f"❌ Error: Style mismatch ({buyer_style} vs {bom_style})"
                continue

        # ── Colorway matching ──────────────────────────────────────────────
        color_raw  = str(row.get("Color/Option", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw:
            result.at[idx, "Validation Status"] = f"❌ Error: Unknown colorway '{color_raw}'"
            continue

        # Robust cw_num — always prefer a 3-digit number
        cw_num = _extract_num_prefix(matched_cw) or _extract_num_prefix(color_raw)
        if not cw_num:
            cw_num = (
                matched_cw.split("-")[0].strip() if "-" in matched_cw
                else matched_cw.split()[0] if " " in matched_cw
                else matched_cw
            )

        # ── Guard missing label component selections ───────────────────────
        raw_main = bom_data.get("selected_main_label_comp", "")
        raw_care = bom_data.get("selected_care_label_comp", "")

        main_comp, main_id = split_comp(raw_main)
        care_comp, care_id = split_comp(raw_care)

        # ── Material codes ─────────────────────────────────────────────────
        main_code = get_code(main_comp) if main_comp else "N/A"
        care_code_mat = get_code(care_comp) if care_comp else "N/A"

        # ── Colors ────────────────────────────────────────────────────────
        main_color = get_color_from_spec(main_comp, matched_cw, color_raw)
        care_color = get_color_from_spec(care_comp, matched_cw, color_raw)

        # ── Write: Main Label ──────────────────────────────────────────────
        if raw_main:
            result.at[idx, "Main Label"]          = main_id or main_code or "N/A"
            result.at[idx, "Main Label Color"]    = main_color or "N/A"
            result.at[idx, "Main Label Supplier"] = resolve_supplier(main_code)
        else:
            result.at[idx, "Main Label"]          = "N/A"
            result.at[idx, "Main Label Color"]    = "N/A"
            result.at[idx, "Main Label Supplier"] = "N/A"

        # ── Write: Additional Main Label ───────────────────────────────────
        logo_code  = get_code("Label Logo 1")
        logo_color = get_color_from_spec("Label Logo 1", matched_cw, color_raw)
        result.at[idx, "Additional Main Label"]       = logo_code or "N/A"
        result.at[idx, "Additional Main Label Color"] = logo_color or "N/A"

        # ── Write: Care Label ──────────────────────────────────────────────
        if raw_care:
            result.at[idx, "Care Label"]          = care_id or care_code_mat or "N/A"
            result.at[idx, "Care Label Color"]    = care_color or "N/A"
            result.at[idx, "Care Label Supplier"] = resolve_supplier(care_code_mat)
        else:
            result.at[idx, "Care Label"]          = "N/A"
            result.at[idx, "Care Label Color"]    = "N/A"
            result.at[idx, "Care Label Supplier"] = "N/A"

        # ── Write: Content Code / TP FC / Care Code ────────────────────────
        result.at[idx, "Content Code"] = get_content("content_code", matched_cw, cw_num, color_raw)
        result.at[idx, "TP FC"]        = get_content("shell",        matched_cw, cw_num, color_raw)
        result.at[idx, "Care Code"]    = get_care("care_code",       matched_cw, cw_num, color_raw)

        # ── Write: Hangtag ─────────────────────────────────────────────────
        ht_code = get_code("Hangtag Package Part")
        ht_cw   = get_cw_val("Hangtag Package Part", matched_cw)
        result.at[idx, "Hangtag"]          = ht_code or extract_id_only(ht_cw) or "N/A"
        result.at[idx, "Hangtag Supplier"] = resolve_supplier(ht_code)

        # ── Write: RFID — dedicated component keys first ───────────────────
        rfid_code = ""
        rfid_supplier = "N/A"
        for rfid_key in ["RFID Tag", "RFID Label", "RFID Sticker", "Hangtag RFID"]:
            rfid_code = get_code(rfid_key)
            if rfid_code:
                rfid_supplier = resolve_supplier(rfid_code)
                break
        if not rfid_code:
            rfid_comp = components.get("Hangtag Package Part", {})
            rfid_desc = str(rfid_comp.get("description", ""))
            rfid_code = extract_material_code(rfid_desc) or extract_material_code(ht_cw)
            rfid_supplier = resolve_supplier(rfid_code) if rfid_code else resolve_supplier(ht_code)

        result.at[idx, "Hangtag (RFID)"]          = rfid_code or extract_id_only(ht_cw) or "N/A"
        result.at[idx, "Hangtag (RFID) Supplier"]  = rfid_supplier
        result.at[idx, "RFID Sticker"]             = rfid_code or "N/A"
        result.at[idx, "RFID Sticker Supplier"]    = rfid_supplier

        # ── Write: UPC Sticker ─────────────────────────────────────────────
        upc_code = get_code("Packaging 3")
        upc_cw   = get_cw_val("Packaging 3", matched_cw)
        result.at[idx, "UPC Sticker (Polybag)"] = upc_code or extract_id_only(upc_cw) or "N/A"
        result.at[idx, "UPC Sticker Supplier"]  = resolve_supplier(upc_code)

        # ── Validation status ──────────────────────────────────────────────
        not_found = sum(1 for c in NEW_COLUMNS[:-1] if str(result.at[idx, c]) == "N/A")
        if not_found == 0:
            result.at[idx, "Validation Status"] = "✅ Validated"
        elif not_found < len(NEW_COLUMNS) - 1:
            result.at[idx, "Validation Status"] = "⚠️ Partial"
        else:
            result.at[idx, "Validation Status"] = "❌ Error: No BOM data matched"

    return result