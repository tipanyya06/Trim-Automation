from typing import Dict, Any, Optional
import pandas as pd
import re

from parsers.color_bom import extract_color_bom_lookup
from parsers.care_content import extract_care_codes, extract_content_codes
from validators.matcher import normalize_colorway, extract_material_code, extract_id_only, get_product_type
from parsers.detail_sketch import get_sketch_color
<<<<<<< HEAD

# ── Known supplier canonical names per field type ─────────────────────────────
_KNOWN_HANGTAG_SUPPLIER_MAP: dict[str, str] = {
    "avery":    "Avery Dennison Global",
    "bao shen": "PT BSN",
    "hangsan":  "Hangsan",
}
_KNOWN_MAIN_LABEL_SUPPLIER_MAP: dict[str, str] = {
    "avery":      "Avery Dennison Global",
    "bao shen":   "PT BSN",
    "hangsan":    "Hangsan",
    "hanyang":    "Hanyang",
    "next gen":   "Next Gen Packaging Global",
    "nextgen":    "Next Gen Packaging Global",
    "joint tack": "Joint Tack",
}
_SUPPLIER_ALIASES: list[tuple[str, str]] = [
    ("bao shen", "PT BSN"),
]

_COLOR_REDIRECT_VALUES = {"artwork", "stock", "standard", "std"}


def _normalize_supplier_alias(supplier: str) -> str:
    if not supplier or supplier == "N/A":
        return supplier
    sl = supplier.lower()
    for fragment, canonical in _SUPPLIER_ALIASES:
        if fragment in sl:
            return canonical
    return supplier
=======
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938


# ── Supplier alias normalization ──────────────────────────────────────────────
# Maps any substring match (lowercased) → canonical display name.
# Applied as a final pass on every resolved supplier value.
_SUPPLIER_ALIASES: list[tuple[str, str]] = [
    ("bao shen", "PT BSN"),   # "Bao Shen" and "Bao Shen (Apparel)" → PT BSN
]


def _normalize_supplier_alias(supplier: str) -> str:
    """
    Normalize supplier names using the alias table.
    e.g. "Bao Shen (Apparel)" → "PT BSN", "Bao Shen" → "PT BSN".
    """
    if not supplier or supplier == "N/A":
        return supplier
    sl = supplier.lower()
    for fragment, canonical in _SUPPLIER_ALIASES:
        if fragment in sl:
            return canonical
    return supplier

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


# ── Utility helpers ───────────────────────────────────────────────────────────

def _nv(val) -> str:
    s = str(val).strip()
    return "N/A" if (not s or s.lower() in ("none", "nan", "")) else s


def _is_empty(val) -> bool:
    return str(val).strip().lower() in ("", "none", "nan", "n/a")


def _fix_sup(s: str) -> str:
    """Collapse broken supplier name fragments (e.g. 'Next Gen' split across cells)."""
    if not s:
        return s
    prev = None
    while prev != s:
        prev = s
        s = re.sub(
            r'([a-z]{3,})\s+([a-z]{1,3})(?=\s|$)',
            lambda m: (
                m.group(1) + m.group(2)
                if not re.search(r'[aeiou]', m.group(2)) or len(m.group(2)) == 1
                else m.group(0)
            ),
            s,
        )
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\b([A-Z]{1,3}) ([A-Z]{1,3})\b', r'\1\2', s)
    return s.strip()


def _normalize_ws(s: str) -> str:
    return re.sub(r'\s+', ' ', str(s)).strip().lower()


def _comp_names_match(a: str, b: str) -> bool:
    na = _normalize_ws(a)
    nb = _normalize_ws(b)
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    sa = re.sub(r'\s+', '', na)
    sb = re.sub(r'\s+', '', nb)
    if sa and sb and (sa == sb or sa in sb or sb in sa):
        return True
    return False


def _check_fgv_contractor(supplier_raw: str) -> bool:
    sl = supplier_raw.lower()
    return "fgv" in sl and "contractor" in sl


def _match_known_supplier(supplier_raw: str, field_type: str) -> str:
    if not supplier_raw or supplier_raw == "N/A":
        return supplier_raw
    sl = supplier_raw.lower()
    sup_map = (
        _KNOWN_HANGTAG_SUPPLIER_MAP if field_type == "hangtag"
        else _KNOWN_MAIN_LABEL_SUPPLIER_MAP if field_type in ("main_label", "care_label")
        else {}
    )
    for fragment, canonical in sup_map.items():
        if fragment in sl:
            return canonical
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
    # FIX: if ALL colorway values are the same numeric code (e.g. Hangtag Package Part
    # stores "121612" in every colorway cell), treat that as the material code.
    cw_vals = [str(v).strip() for v in comp.get("colorways", {}).values()]
    numeric_vals = [v for v in cw_vals if re.match(r'^\d{5,7}$', v)]
    if numeric_vals and len(set(numeric_vals)) == 1:
        return numeric_vals[0]
    # Also return any numeric colorway value if description gave nothing
    for v in numeric_vals:
        return v
    return ""


<<<<<<< HEAD
=======
_COLOR_REDIRECT_VALUES = {"artwork", "stock", "standard", "std"}


>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
def _strip_numeric_prefix(color_name: str) -> str:
    s = str(color_name).strip()
    m = re.match(r'^\d+[-\s]+(.+)$', s)
    return m.group(1).strip() if m else s


<<<<<<< HEAD
def _extract_id_from_settings_string(raw: str) -> str:
    """Extract trailing numeric code from 'Component Name - 123456' style strings."""
    if not raw or raw in ("N/A", ""):
        return ""
    if " - " in raw:
        parts = raw.rsplit(" - ", 1)
        candidate = parts[-1].strip()
        if re.match(r'^\d+$', candidate):
            return candidate
    m = re.search(r'(\d{4,7})\s*$', raw.strip())
    return m.group(1) if m else ""


def _extract_code_from_comp_name(comp_name: str) -> str:
    if not comp_name:
        return ""
    m = re.search(r'[-–]\s*(\d{4,7})\s*$', comp_name.strip())
    if m:
        return m.group(1)
    m = re.search(r'(\d{4,7})\s*$', comp_name.strip())
    return m.group(1) if m else ""


def _find_target_col(df, matched_cw: str):
=======
def _find_target_col(df: "pd.DataFrame", matched_cw: str) -> "Optional[str]":
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
    cw_cols = [c for c in df.columns[1:] if c]
    if matched_cw in cw_cols:
        return matched_cw
    num_prefix = re.match(r'^(\d+)', str(matched_cw) or "")
    num_prefix = num_prefix.group(1) if num_prefix else ""
    if num_prefix:
        for col in cw_cols:
            col_num = re.match(r'^(\d+)', str(col))
            if col_num and col_num.group(1) == num_prefix:
                return col
    cw_words = set(re.split(r'[\s,/\-]+', matched_cw.lower()))
    best_col, best_overlap = None, 0
    for col in cw_cols:
        col_words = set(re.split(r'[\s,/\-]+', str(col).lower()))
        overlap = len(cw_words & col_words)
        if overlap > best_overlap:
            best_overlap, best_col = overlap, col
    return best_col if best_overlap > 0 else None


<<<<<<< HEAD
# ── Costing helpers ───────────────────────────────────────────────────────────

def _find_supplier_in_costing(costing_df, code: str) -> str:
=======
def _extract_code_from_comp_name(comp_name: str) -> str:
    if not comp_name:
        return ""
    m = re.search(r'[-–]\s*(\d{4,7})\s*$', comp_name.strip())
    if m:
        return m.group(1)
    m = re.search(r'(\d{4,7})\s*$', comp_name.strip())
    return m.group(1) if m else ""


def _resolve_alt_component_color(
    fallback_comp: str,
    fallback_raw_sel: str,
    matched_cw: str,
    color_raw: str,
    color_bom_df,
    color_spec_df,
    get_color_fn,
    sketch_data: dict = None,
) -> tuple:
    if not fallback_comp:
        return ("", "")

    comp_code = _extract_code_from_comp_name(fallback_raw_sel or fallback_comp)

    if not comp_code:
        for df in (color_bom_df, color_spec_df):
            if df is None or df.empty:
                continue
            comp_col = df.columns[0]
            row_match = df[df[comp_col].apply(
                lambda v: _comp_names_match(str(v).split(" - ")[0] if " - " in str(v) else str(v), fallback_comp)
            )]
            if not row_match.empty:
                full_name = str(row_match.iloc[0][comp_col])
                comp_code = _extract_code_from_comp_name(full_name)
                if comp_code:
                    break
            if not comp_code and not row_match.empty:
                import re as _re
                for col in df.columns[1:]:
                    cell = str(row_match.iloc[0].get(col, ""))
                    m = _re.search(r'\b(\d{5,7})\b', cell)
                    if m:
                        comp_code = m.group(1)
                        break
            if comp_code:
                break

    for df in (color_bom_df, color_spec_df):
        if df is None or df.empty:
            continue
        comp_col = df.columns[0]

        row_match = df[
            df[comp_col].apply(lambda v: _comp_names_match(str(v), fallback_comp))
        ]
        if row_match.empty:
            def _match_split(v):
                name_part = str(v).split(" - ")[0].strip() if " - " in str(v) else str(v)
                return _comp_names_match(name_part, fallback_comp)
            row_match = df[df[comp_col].apply(_match_split)]

        if row_match.empty:
            continue

        target_col = _find_target_col(df, matched_cw)
        if target_col is None:
            continue

        cell_val   = str(row_match.iloc[0].get(target_col, "")).strip()
        cell_lower = cell_val.lower()

        if not cell_val or cell_lower in ("", "none", "nan"):
            return ("", "")

        if cell_lower in _COLOR_REDIRECT_VALUES:
            if sketch_data and comp_code:
                sketch_color = get_sketch_color(sketch_data, comp_code, matched_cw)
                if sketch_color:
                    return (comp_code, sketch_color)
            color = _strip_numeric_prefix(matched_cw or target_col)
            return (comp_code, color)

        return (comp_code, cell_val)

    return ("", "")


def _resolve_main_label_color_with_fallback(
    primary_comp: str,
    fallback_comp: str,
    fallback_raw_sel: str,
    fallback_comp2: str,
    fallback_raw_sel2: str,
    matched_cw: str,
    color_raw: str,
    color_bom_df,
    color_spec_df,
    get_color_fn,
    use_fb1: bool = False,
    use_fb2: bool = False,
    use_colorway_name: bool = False,
    sketch_data: dict = None,
) -> tuple:
    primary_color = get_color_fn(primary_comp, matched_cw, color_raw)
    if primary_color and primary_color.lower() not in ("n/a", ""):
        return ("", primary_color)

    if use_fb1 and fallback_comp:
        fb1_code, fb1_color = _resolve_alt_component_color(
            fallback_comp, fallback_raw_sel,
            matched_cw, color_raw, color_bom_df, color_spec_df, get_color_fn,
            sketch_data=sketch_data,
        )
        if fb1_code:
            if fb1_color and fb1_color.lower() not in ("n/a", ""):
                return (fb1_code, fb1_color)
            if use_fb2 and fallback_comp2:
                _, fb2_color = _resolve_alt_component_color(
                    fallback_comp2, fallback_raw_sel2,
                    matched_cw, color_raw, color_bom_df, color_spec_df, get_color_fn,
                    sketch_data=sketch_data,
                )
                if fb2_color and fb2_color.lower() not in ("n/a", ""):
                    return (fb1_code, fb2_color)
            if use_colorway_name and matched_cw:
                stripped = _strip_numeric_prefix(matched_cw)
                if stripped and stripped.lower() not in ("n/a", ""):
                    return (fb1_code, stripped)
            return (fb1_code, "")

    if use_fb2 and fallback_comp2:
        fb2_code, fb2_color = _resolve_alt_component_color(
            fallback_comp2, fallback_raw_sel2,
            matched_cw, color_raw, color_bom_df, color_spec_df, get_color_fn,
            sketch_data=sketch_data,
        )
        if fb2_code:
            if fb2_color and fb2_color.lower() not in ("n/a", ""):
                return (fb2_code, fb2_color)
            if use_colorway_name and matched_cw:
                stripped = _strip_numeric_prefix(matched_cw)
                if stripped and stripped.lower() not in ("n/a", ""):
                    return (fb2_code, stripped)
            return (fb2_code, "")

    if use_colorway_name and matched_cw:
        stripped = _strip_numeric_prefix(matched_cw)
        if stripped and stripped.lower() not in ("n/a", ""):
            return ("", stripped)

    return ("", "")


def _find_supplier_in_costing(costing_df: pd.DataFrame, code: str) -> str:
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
    if costing_df is None or costing_df.empty or not code or code == "N/A":
        return "N/A"
    code = str(code).strip()
    code_stripped = code.lstrip("0")
    sup_col = None
    # Broader search: supplier, vendor, factory, manufacturer, source, mfr
    _SUP_KEYWORDS = ("supplier", "vendor", "factory", "manufacturer", "source", "mfr")
    for col in costing_df.columns:
        cl = str(col).lower()
        if any(kw in cl for kw in _SUP_KEYWORDS):
            sup_col = col
            break
    if not sup_col:
        # Last resort: take the last text column that isn't a code/number column
        for col in reversed(costing_df.columns):
            sample = costing_df[col].dropna().astype(str)
            if sample.empty:
                continue
            # A supplier column has mostly non-numeric values
            non_numeric = sum(1 for v in sample if not re.match(r'^\d+$', v.strip()))
            if non_numeric > len(sample) * 0.5:
                sup_col = col
                break
    if not sup_col:
        return "N/A"

    def _cell_has_code(cell_str):
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


<<<<<<< HEAD
def _find_code_in_costing_by_desc(costing_df, *keywords) -> str:
    """
    Scan costing_detail for a row whose description contains ALL given keywords,
    then return the first numeric material code found in that row.
    Used as a last-resort fallback when get_code() misses packaging components.
    """
=======
def _validate_hangtag_from_costing(costing_df: pd.DataFrame) -> str:
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
    if costing_df is None or costing_df.empty:
        return ""
    desc_col = None
    for col in costing_df.columns:
        cl = str(col).lower()
        if "description" in cl or "desc" in cl:
            desc_col = col
            break
    if not desc_col:
        # Try scanning every cell in every column
        desc_col = costing_df.columns[0]

    for _, row in costing_df.iterrows():
        desc = str(row.get(desc_col, "")).lower()
        if all(kw.lower() in desc for kw in keywords):
            # Look for a numeric material code in any cell of this row
            for col in costing_df.columns:
                candidate = str(row.get(col, "")).strip()
                if re.match(r'^\d{5,7}$', candidate):
                    return candidate
            # Also try extracting from description itself
            m = re.search(r'\b(\d{5,7})\b', str(row.get(desc_col, "")))
            if m:
                return m.group(1)
    return ""


def _scan_costing_for_component(costing_df, *search_terms) -> str:
    """
    Generic costing scan: returns first numeric code found in any row whose
    ANY cell contains at least one of the search_terms (case-insensitive).
    """
    if costing_df is None or costing_df.empty:
        return ""
    for _, row in costing_df.iterrows():
        row_text = " ".join(str(v) for v in row.values).lower()
        if any(term.lower() in row_text for term in search_terms):
            for col in costing_df.columns:
                candidate = str(row.get(col, "")).strip()
                if re.match(r'^\d{5,7}$', candidate):
                    return candidate
    return ""


def _validate_hangtag_from_costing(costing_df) -> str:
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


<<<<<<< HEAD
# ── Embroidery / Jacquard detection ──────────────────────────────────────────

def _is_embroidery_label(raw_main_setting: str) -> bool:
    return "embroidery" in str(raw_main_setting).lower()


def _is_jacquard_label(main_comp: str, components: dict) -> bool:
    needle = "jacquard"
    comp = components.get(main_comp)
    if comp is None:
        for k, v in components.items():
            if _comp_names_match(k, main_comp):
                comp = v
                break
    if comp is None:
        return False
    if needle in str(comp.get("description", "")).lower():
        return True
    for cw_val in comp.get("colorways", {}).values():
        if str(cw_val).strip().lower() == needle:
            return True
    return False


def _derive_main_label_display(
    raw_main: str,
    main_comp: str,
    resolved_color: str = "",
    comp_description: str = "",
) -> str:
    combined_name = (str(raw_main) + " " + str(main_comp) + " " + str(comp_description)).lower()
    if "embroidery" in combined_name:
        return "Embroidery"
    if "jacquard" in combined_name:
        return "Jacquard"
    if str(resolved_color).strip().lower() == "jacquard":
        return "Jacquard"
    return main_comp if main_comp else raw_main


# ── Color resolution helpers ──────────────────────────────────────────────────

def _resolve_alt_component_color(
    fallback_comp, fallback_raw_sel, matched_cw, color_raw,
    color_bom_df, color_spec_df, get_color_fn, sketch_data=None,
):
    if not fallback_comp:
        return ("", "")
    comp_code = _extract_code_from_comp_name(fallback_raw_sel or fallback_comp)
    if not comp_code:
        for df in (color_bom_df, color_spec_df):
            if df is None or df.empty:
                continue
            comp_col = df.columns[0]
            row_match = df[df[comp_col].apply(
                lambda v: _comp_names_match(str(v).split(" - ")[0] if " - " in str(v) else str(v), fallback_comp)
            )]
            if not row_match.empty:
                full_name = str(row_match.iloc[0][comp_col])
                comp_code = _extract_code_from_comp_name(full_name)
                if comp_code:
                    break
            if not comp_code and not row_match.empty:
                for col in df.columns[1:]:
                    cell = str(row_match.iloc[0].get(col, ""))
                    m = re.search(r'\b(\d{5,7})\b', cell)
                    if m:
                        comp_code = m.group(1)
                        break
            if comp_code:
                break

    for df in (color_bom_df, color_spec_df):
        if df is None or df.empty:
            continue
        comp_col = df.columns[0]
        row_match = df[df[comp_col].apply(lambda v: _comp_names_match(str(v), fallback_comp))]
        if row_match.empty:
            def _ms(v):
                np_ = str(v).split(" - ")[0].strip() if " - " in str(v) else str(v)
                return _comp_names_match(np_, fallback_comp)
            row_match = df[df[comp_col].apply(_ms)]
        if row_match.empty:
            continue
        target_col = _find_target_col(df, matched_cw)
        if target_col is None:
            continue
        cell_val = str(row_match.iloc[0].get(target_col, "")).strip()
        cell_lower = cell_val.lower()
        if not cell_val or cell_lower in ("", "none", "nan"):
            return ("", "")
        if cell_lower in _COLOR_REDIRECT_VALUES:
            if sketch_data and comp_code:
                sketch_color = get_sketch_color(sketch_data, comp_code, matched_cw)
                if sketch_color:
                    return (comp_code, sketch_color)
            color = _strip_numeric_prefix(matched_cw or target_col)
            return (comp_code, color)
        return (comp_code, cell_val)
    return ("", "")


def _resolve_main_label_color_with_fallback(
    primary_comp, fallback_comp, fallback_raw_sel,
    fallback_comp2, fallback_raw_sel2,
    matched_cw, color_raw, color_bom_df, color_spec_df, get_color_fn,
    use_fb1=False, use_fb2=False, use_colorway_name=False, sketch_data=None,
):
    primary_color = get_color_fn(primary_comp, matched_cw, color_raw)
    # If redirect value, convert to colorway name immediately
    if primary_color and primary_color.lower() in _COLOR_REDIRECT_VALUES:
        primary_color = _strip_numeric_prefix(matched_cw)
    if primary_color and primary_color.lower() not in ("n/a", ""):
        return ("", primary_color)

    if use_fb1 and fallback_comp:
        fb1_code, fb1_color = _resolve_alt_component_color(
            fallback_comp, fallback_raw_sel, matched_cw, color_raw,
            color_bom_df, color_spec_df, get_color_fn, sketch_data=sketch_data,
        )
        if fb1_code:
            if fb1_color and fb1_color.lower() not in ("n/a", ""):
                return (fb1_code, fb1_color)
            if use_fb2 and fallback_comp2:
                _, fb2_color = _resolve_alt_component_color(
                    fallback_comp2, fallback_raw_sel2, matched_cw, color_raw,
                    color_bom_df, color_spec_df, get_color_fn, sketch_data=sketch_data,
                )
                if fb2_color and fb2_color.lower() not in ("n/a", ""):
                    return (fb1_code, fb2_color)
            if use_colorway_name and matched_cw:
                stripped = _strip_numeric_prefix(matched_cw)
                if stripped and stripped.lower() not in ("n/a", ""):
                    return (fb1_code, stripped)
            return (fb1_code, "")

    if use_fb2 and fallback_comp2:
        fb2_code, fb2_color = _resolve_alt_component_color(
            fallback_comp2, fallback_raw_sel2, matched_cw, color_raw,
            color_bom_df, color_spec_df, get_color_fn, sketch_data=sketch_data,
        )
        if fb2_code:
            if fb2_color and fb2_color.lower() not in ("n/a", ""):
                return (fb2_code, fb2_color)
            if use_colorway_name and matched_cw:
                stripped = _strip_numeric_prefix(matched_cw)
                if stripped and stripped.lower() not in ("n/a", ""):
                    return (fb2_code, stripped)
            return (fb2_code, "")

    if use_colorway_name and matched_cw:
        stripped = _strip_numeric_prefix(matched_cw)
        if stripped and stripped.lower() not in ("n/a", ""):
            return ("", stripped)

    return ("", "")


# ── Main entry point ──────────────────────────────────────────────────────────

=======
def _extract_id_from_settings_string(raw: str) -> str:
    """
    Extract the numeric ID from a settings string like 'Component Name - 123456'.
    Returns the ID portion, or '' if not found.
    """
    if not raw or raw in ("N/A", ""):
        return ""
    if " - " in raw:
        parts = raw.rsplit(" - ", 1)
        candidate = parts[-1].strip()
        if re.match(r'^\d+$', candidate):
            return candidate
    # fallback: last numeric token
    m = re.search(r'(\d{4,7})\s*$', raw.strip())
    return m.group(1) if m else ""


>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
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
    sketch_data     = bom_data.get("detail_sketch", {})

    costing_hangtag_code = _validate_hangtag_from_costing(costing_detail)
    label_settings = bom_data.get("label_settings", {})

    for col in NEW_COLUMNS:
        if col not in result.columns:
            result[col] = ""

<<<<<<< HEAD
    # ── Closures ──────────────────────────────────────────────────────────────

=======
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
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
        if raw and _check_fgv_contractor(raw):
            return "N/A"
        matched = _match_known_supplier(raw, field_type)
        return _normalize_supplier_alias(matched)

    def get_code(comp_key: str) -> str:
<<<<<<< HEAD
        """Look up material code from color BOM components dict."""
        if not comp_key:
            return ""
=======
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        if comp_key in components:
            return _get_material_code_for_comp(components[comp_key])
        for k, v in components.items():
            if _comp_names_match(k, comp_key):
                return _get_material_code_for_comp(v)
        return ""
<<<<<<< HEAD

    def get_code_with_costing_fallback(comp_key: str, *costing_keywords) -> str:
        """
        Like get_code() but when the color BOM has no match (e.g. packaging components),
        falls back to scanning costing_detail rows by keyword.
        """
        code = get_code(comp_key)
        if code:
            return code
        if costing_keywords:
            code = _find_code_in_costing_by_desc(costing_detail, *costing_keywords)
        return code
=======
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938

    def get_cw_val(comp_key: str, matched_cw: str) -> str:
        comp = components.get(comp_key)
        if comp is None:
            for k, v in components.items():
                if _comp_names_match(k, comp_key):
                    comp = v
                    break
        if comp is None:
            return ""
        return _nv(comp.get("colorways", {}).get(matched_cw, ""))

    def get_color_from_spec(component_name: str, matched_cw: str, raw_color_option: str = "") -> str:
        if not component_name:
            return ""

        def _extract_prefix(s):
            s = str(s).strip()
            m = re.match(r'[A-Za-z]+-(\d+)', s)
            if m:
                return m.group(1)
            m = re.match(r'(\d+)', s)
            return m.group(1) if m else ""

        cw_prefix = _extract_prefix(raw_color_option) or _extract_prefix(matched_cw)
        exact_cw  = matched_cw

        def _lookup_in_df(df):
            if df is None or df.empty:
                return ""
            comp_col = df.columns[0]
            lookup_name = component_name.split(" - ")[0].strip() if " - " in component_name else component_name
<<<<<<< HEAD
            lookup_lower = lookup_name.strip().lower()

            # FIX: use strict matching priority to avoid false positives.
            # _comp_names_match is too loose for short names like "Label Logo 1"
            # which can substring-match vendor/store text rows in the color BOM.
            # Priority: 1) exact (case-insensitive), 2) startswith, 3) _comp_names_match
            def _strict_match(v):
                raw = str(v).split(" - ")[0].strip() if " - " in str(v) else str(v)
                raw_lower = raw.strip().lower()
                # Exact match
                if raw_lower == lookup_lower:
                    return True
                # Startswith (handles "Label Logo 1 - 079660" when searching "Label Logo 1")
                if raw_lower.startswith(lookup_lower) or lookup_lower.startswith(raw_lower):
                    return True
                return False

            row_match = df[df[comp_col].apply(_strict_match)]
            # Fall back to loose match only if strict found nothing
            if row_match.empty:
                row_match = df[df[comp_col].apply(
                    lambda v: _comp_names_match(
                        str(v).split(" - ")[0] if " - " in str(v) else str(v), lookup_name
                    )
                )]
                # Reject loose matches whose cell value looks like non-color data
                # (e.g. contains "store", "outlet", "retail" — vendor/channel text)
                _non_color_hints = ("store", "outlet", "retail", "channel", "vendor", "factory")
                if not row_match.empty:
                    cw_cols_check = [c for c in df.columns[1:] if c]
                    def _row_has_bad_color(r):
                        for col in cw_cols_check:
                            cv = str(r.get(col, "")).lower()
                            if any(h in cv for h in _non_color_hints):
                                return True
                        return False
                    good_rows = row_match[~row_match.apply(_row_has_bad_color, axis=1)]
                    row_match = good_rows if not good_rows.empty else pd.DataFrame()
=======

            row_match = df[df[comp_col].apply(lambda v: _comp_names_match(str(v).split(" - ")[0] if " - " in str(v) else str(v), lookup_name))]

>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
            if row_match.empty:
                return ""
            cw_cols = [c for c in df.columns[1:] if c and not str(c).startswith("col_")]
            _skip = {"none", "nan", ""} | _COLOR_REDIRECT_VALUES

            def _accept(v):
                return v.lower() not in _skip

            if exact_cw in cw_cols:
                v = str(row_match.iloc[0][exact_cw]).strip()
                if v and _accept(v):
                    return v
                # If redirect, resolve to colorway name
                if v.lower() in _COLOR_REDIRECT_VALUES:
                    return _strip_numeric_prefix(matched_cw)
            if cw_prefix:
                for col in cw_cols:
                    if str(col).split("-")[0].strip() == cw_prefix:
                        v = str(row_match.iloc[0][col]).strip()
                        if v and _accept(v):
                            return v
                        if v.lower() in _COLOR_REDIRECT_VALUES:
                            return _strip_numeric_prefix(matched_cw)
            return ""

        res = _lookup_in_df(bom_data.get("color_bom"))
        if not res:
            res = _lookup_in_df(color_spec)
        return res

    def _extract_num_prefix(s: str) -> str:
        s = str(s).strip()
        for pattern in [r'[A-Za-z]+-(\d{3})', r'^(\d{3})']:
            m = re.match(pattern, s)
            if m:
                return m.group(1)
        m = re.search(r'(\d{3})', s)
        return m.group(1) if m else ""

    def get_care(key, matched_cw, cw_num, raw=""):
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

    def get_content(key, matched_cw, cw_num, raw=""):
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

    def _resolve_settings_code(raw_setting: str, *costing_fallback_keywords) -> str:
        """
        Unified code resolver for any settings field formatted as 'Name - Code'.
        1. Extract trailing code from settings string directly.
        2. Fall back to get_code() via components dict.
        3. Fall back to costing_detail keyword scan.
        Returns empty string if nothing found.
        """
        if not raw_setting or raw_setting in ("N/A", ""):
            return ""
        # Step 1: extract ID directly from the settings string
        code = _extract_id_from_settings_string(raw_setting)
        if code:
            return code
        # Step 2: try components dict
        comp_name = raw_setting.split(" - ")[0].strip()
        code = get_code(comp_name)
        if code:
            return code
        # Step 3: costing fallback
        if costing_fallback_keywords:
            code = _find_code_in_costing_by_desc(costing_detail, *costing_fallback_keywords)
        if not code:
            code = _scan_costing_for_component(costing_detail, comp_name)
        return code

    def _auto_comp_with_code(search_keys) -> str:
        """
        Find the first matching component key from components dict.
        Uses startswith matching so 'packaging 3' finds 'Packaging 3 - 980010'.
        Falls back to costing_detail when not in color BOM.
        """
        _ckl = {k.lower(): k for k in components}
        for _try in search_keys:
            if _try in _ckl:
                return _ckl[_try]
            for k_lower, k_orig in _ckl.items():
                if k_lower.startswith(_try):
                    return k_orig
        # Not in color BOM — scan costing_detail rows
        for _try in search_keys:
            _code = _find_code_in_costing_by_desc(costing_detail, _try)
            if _code:
                _label = _try.title()
                return f"{_label} - {_code}"
        return ""

    # ── Per-row processing ────────────────────────────────────────────────────

    for idx, row in result.iterrows():

<<<<<<< HEAD
        # ── Style validation ──────────────────────────────────────────────────
=======
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        buyer_style = str(
            row.get("Buyer Style Number", "") or row.get("JDE Style", "")
        ).strip().upper()
        if buyer_style and bom_style:
            if buyer_style != bom_style and buyer_style not in bom_style and bom_style not in buyer_style:
                result.at[idx, "Validation Status"] = f"❌ Error: Style mismatch ({buyer_style} vs {bom_style})"
                continue

<<<<<<< HEAD
        # ── Colorway matching ─────────────────────────────────────────────────
        color_raw  = str(row.get("Color/Option", "") or row.get("Color", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw and available_cw:
            num_only = re.match(r'^(\d+)$', str(color_raw).strip())
=======
        color_raw  = str(row.get("Color/Option", "") or row.get("Color", "")).strip()
        matched_cw = normalize_colorway(color_raw, available_cw)
        if not matched_cw and available_cw:
            cw_raw_stripped = str(color_raw).strip()
            num_only = re.match(r'^(\d+)$', cw_raw_stripped)
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
            if num_only:
                num = num_only.group(1)
                for cw in available_cw:
                    cw_num_m = re.match(r'^(\d+)', str(cw))
                    if cw_num_m and cw_num_m.group(1) == num:
                        matched_cw = cw
                        break
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

        mat_name         = str(row.get("Material Name", "") or "").strip()
        row_product_type = get_product_type(mat_name) if mat_name else product_type
        is_glove         = (row_product_type == "glove")

<<<<<<< HEAD
        # ── Read label settings (with alias key fallbacks) ────────────────────
        def _ls(*keys) -> str:
            """Get first non-empty value from label_settings trying multiple key aliases."""
            for k in keys:
                v = label_settings.get(k, "")
                if v and v not in ("N/A", ""):
                    return v
            return ""

        raw_main         = _ls("main_label") or bom_data.get("selected_main_label_comp", "")
        raw_care         = _ls("care_label") or bom_data.get("selected_care_label_comp", "")
        raw_add_main     = _ls("add_main_label", "additional_main_label")
        raw_ht           = _ls("hangtag")
        raw_ht2          = _ls("hangtag2")
        raw_ht3          = _ls("hangtag3")
        raw_micro        = _ls("micropack", "micropak")
        raw_size_label   = _ls("size_label")
        raw_size_sticker = _ls("size_sticker")
        raw_rfid_no_msrp = _ls("rfid_no_msrp", "rfid_wo_msrp")
        raw_rfid         = _ls("hangtag_rfid", "rfid_hangtag")
        # FIX: try all known key aliases for rfid_sticker
        raw_rfid_sticker = _ls(
            "rfid_sticker", "rfid_sticker_gloves", "hangtag_rfid_sticker",
            "rfid_tag", "rfid_label",
        )
        # FIX: try all known key aliases for upc_sticker
        raw_upc = _ls(
            "upc_sticker", "upc_bag", "upc_polybag", "upc",
            "polybag_sticker", "upc_sticker_polybag",
        )

        # ── Auto-detect primary component when settings are empty ─────────────
        # FIX: use startswith matching so "label logo 1" finds "Label Logo 1 - 079660"
        def _find_comp_startswith(search_keys):
            _ckl = {k.lower(): k for k in components}
            for _try in search_keys:
                # Exact match first
                if _try in _ckl:
                    return _ckl[_try]
                # Startswith match — handles "Label Logo 1 - 079660" when searching "label logo 1"
                for k_lower, k_orig in _ckl.items():
                    if k_lower.startswith(_try):
                        return k_orig
            return ""

        _settings_have_main = bool(raw_main)
        if not _settings_have_main and components:
            _found = _find_comp_startswith([
                "label logo 1", "hat component", "hat components",
                "direct embroidery", "label 1",
            ])
            raw_main = _found if _found else next(iter(components), "")

        _settings_have_care = bool(raw_care)
        if not _settings_have_care and components:
            _found = _find_comp_startswith(["label 1", "care label"])
            if _found:
                raw_care = _found

        # ── Auto-detect RFID sticker when settings are empty ──────────────────
        if not raw_rfid_sticker:
            _auto = _auto_comp_with_code(
                ["hangtag package part", "rfid sticker", "rfid tag", "rfid label"]
            )
            if _auto:
                raw_rfid_sticker = _auto

        # ── Auto-detect UPC when settings are empty ───────────────────────────
        if not raw_upc:
            _auto = _auto_comp_with_code(
                ["packaging 3", "upc sticker", "upc bag", "polybag"]
            )
            if _auto:
                raw_upc = _auto

        # ── Fallback settings ─────────────────────────────────────────────────
=======
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

>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        raw_main_fallback  = label_settings.get("main_label_fallback", "")
        use_main_fallback  = bool(label_settings.get("use_main_label_fallback", False))
        main_fallback_comp = (
            raw_main_fallback.split(" - ")[0].strip()
            if raw_main_fallback and raw_main_fallback not in ("N/A", "") else ""
        )

        raw_main_fallback2  = label_settings.get("main_label_fallback2", "")
        use_main_fallback2  = bool(label_settings.get("use_main_label_fallback2", False))
        main_fallback_comp2 = (
            raw_main_fallback2.split(" - ")[0].strip()
            if raw_main_fallback2 and raw_main_fallback2 not in ("N/A", "") else ""
        )

<<<<<<< HEAD
        main_comp, main_id = split_comp(raw_main)
        care_comp, care_id = split_comp(raw_care)
        ht_comp,   ht_id   = split_comp(raw_ht)
        ht2_comp,  ht2_id  = split_comp(raw_ht2)
        ht3_comp,  ht3_id  = split_comp(raw_ht3)
=======
        use_colorway_name_fallback = use_main_fallback or use_main_fallback2
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938

        # ── Embroidery / Jacquard flags ───────────────────────────────────────
        _is_embroidery = _is_embroidery_label(raw_main)
        _is_jacquard   = (not _is_embroidery) and _is_jacquard_label(main_comp, components)
        _suppress      = _is_embroidery or _is_jacquard

<<<<<<< HEAD
        # Main label code: use explicit ID from settings when present
        if main_id:
            main_code = main_id
        else:
            main_code = get_code(main_comp) if main_comp else "N/A"

        care_code_mat = care_id if care_id else (get_code(care_comp) if care_comp else "N/A")

        # Additional main label (gloves)
        logo_code = (
            get_code(raw_add_main.split(" - ")[0]) if raw_add_main
            else get_code("Label Logo 1")
        )
        micro_code        = _resolve_settings_code(raw_micro)        if raw_micro        else "N/A"
        size_label_code   = _resolve_settings_code(raw_size_label)   if raw_size_label   else "N/A"
        size_sticker_code = _resolve_settings_code(raw_size_sticker) if raw_size_sticker else "N/A"

        # ── Hangtag code ──────────────────────────────────────────────────────
=======
        main_code         = get_code(main_comp)     if main_comp     else "N/A"

        # ── FIX: Care code — prefer the explicit ID from settings string ──────
        # split_comp already gives us care_id (e.g. "003287" from "Label 1 - 003287")
        # Use that directly; only fall back to get_code() when no ID is present.
        care_code_mat = care_id if care_id else (get_code(care_comp) if care_comp else "N/A")

        logo_code         = get_code(raw_add_main.split(" - ")[0]) if raw_add_main and raw_add_main != "N/A" else get_code("Label Logo 1")
        micro_code        = get_code(raw_micro.split(" - ")[0])    if raw_micro    and raw_micro    != "N/A" else "N/A"
        size_label_code   = get_code(raw_size_label.split(" - ")[0])   if raw_size_label   and raw_size_label   != "N/A" else "N/A"
        size_sticker_code = get_code(raw_size_sticker.split(" - ")[0]) if raw_size_sticker and raw_size_sticker != "N/A" else "N/A"

>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        ht_cw   = get_cw_val("Hangtag Package Part", matched_cw)
        ht_code = ht_id or get_code(ht_comp) if (ht_comp or ht_id) else get_code("Hangtag Package Part")
        if costing_hangtag_code == "N/A":
            ht_code = "N/A"
        elif costing_hangtag_code:
            ht_code = costing_hangtag_code

        ht2_code = ht2_id or (get_code(ht2_comp) if ht2_comp else "")
        ht3_code = ht3_id or (get_code(ht3_comp) if ht3_comp else "")

<<<<<<< HEAD
=======
        # ── RFID (Hangtag RFID / w/o MSRP) ───────────────────────────────────
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

        # ── FIX: RFID Sticker — extract code from settings string directly ────
        # Previously split_comp() was used but the code part was then passed to
        # get_code() (a component-name lookup) instead of being used as-is.
        rfid_sticker_code = rfid_sticker_sup = ""
        if raw_rfid_sticker and raw_rfid_sticker != "N/A":
            rs_comp, rs_id = split_comp(raw_rfid_sticker)
            # rs_id is the numeric code already (e.g. "121612")
            rfid_sticker_code = rs_id if rs_id else get_code(rs_comp)
        if not rfid_sticker_code:
            rfid_sticker_code = rfid_code
        rfid_sticker_sup = resolve_supplier(rfid_sticker_code)

        # ── FIX: UPC — extract code from settings string directly ─────────────
        # "Packaging 3 - 980010" → upc_code = "980010" without needing get_code()
        upc_code = _extract_id_from_settings_string(raw_upc) if raw_upc and raw_upc != "N/A" else ""
        if not upc_code:
            # fallback: look up from components dict
            upc_comp_name = raw_upc.split(" - ")[0].strip() if raw_upc and raw_upc != "N/A" else "Packaging 3"
            upc_code = get_code(upc_comp_name) or get_code("Packaging 3")
        upc_cw = get_cw_val("Packaging 3", matched_cw)

>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        # ── RFID w/o MSRP ─────────────────────────────────────────────────────
        rfid_no_msrp_code = rfid_no_msrp_sup = ""
        if raw_rfid_no_msrp:
            rfid_no_msrp_code = _resolve_settings_code(raw_rfid_no_msrp)
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

<<<<<<< HEAD
        # ── RFID Hangtag (w/ MSRP) ────────────────────────────────────────────
        rfid_code = ""
        if raw_rfid:
            rfid_comp_name, rfid_id = split_comp(raw_rfid)
            rfid_code = rfid_id if rfid_id else get_code(rfid_comp_name)
        if not rfid_code:
            for rfid_key in ["RFID Tag", "RFID Label", "RFID Sticker", "Hangtag RFID"]:
                rfid_code = get_code(rfid_key)
                if rfid_code:
                    break
        if not rfid_code:
            rfid_code = (
                extract_material_code(str(components.get("Hangtag Package Part", {}).get("description", "")))
                or extract_material_code(ht_cw)
            )
        rfid_supplier = resolve_supplier(rfid_code) if rfid_code else resolve_supplier(ht_code)

        # ── FIX: RFID Sticker — unified resolver avoids key-mismatch N/A ─────
        rfid_sticker_code = ""
        if raw_rfid_sticker:
            rfid_sticker_code = _resolve_settings_code(
                raw_rfid_sticker, "rfid sticker", "rfid tag", "hangtag package"
            )
        # FIX: if still empty, scan costing_detail specifically for
        # "Hangtag Package Part" or "RFID" rows — these are separate from the
        # printed hangtag row (which _validate_hangtag_from_costing already found).
        # The RFID sticker code (e.g. 121612 / 123130) lives in that distinct row.
        if not rfid_sticker_code:
            rfid_sticker_code = _find_code_in_costing_by_desc(
                costing_detail, "hangtag package"
            )
        if not rfid_sticker_code:
            rfid_sticker_code = _find_code_in_costing_by_desc(
                costing_detail, "rfid"
            )
        if not rfid_sticker_code:
            rfid_sticker_code = _scan_costing_for_component(
                costing_detail, "hangtag package part", "rfid sticker", "rfid tag"
            )
        if not rfid_sticker_code:
            # absolute last resort: reuse rfid hangtag code
            rfid_sticker_code = rfid_code
        rfid_sticker_sup = resolve_supplier(rfid_sticker_code) if rfid_sticker_code else "N/A"

        # ── FIX: UPC Sticker — costing fallback for packaging components ──────
        upc_code = ""
        if raw_upc:
            upc_code = _resolve_settings_code(
                raw_upc, "packaging 3", "upc", "polybag"
            )
        if not upc_code:
            # Direct costing scan by common packaging keywords
            upc_code = _find_code_in_costing_by_desc(costing_detail, "packaging 3")
            if not upc_code:
                upc_code = _scan_costing_for_component(costing_detail, "polybag", "upc bag", "packaging 3")
        upc_cw = get_cw_val("Packaging 3", matched_cw)

        # ── Auto-alt-scan for main label color fallbacks ───────────────────────
        _user_set_fb1 = bool(main_fallback_comp)
        _user_set_fb2 = bool(main_fallback_comp2)

        if not _user_set_fb1 or not _user_set_fb2:
            _cb_df = bom_data.get("color_bom")
            if _cb_df is not None and not _cb_df.empty:
                _comp_col = _cb_df.columns[0]
                _alt_names = [
                    str(v).strip() for v in _cb_df[_comp_col]
                    if str(v).strip().lower().startswith("alt")
                ]
                if not _user_set_fb1 and len(_alt_names) > 0:
                    raw_main_fallback  = _alt_names[0]
                    main_fallback_comp = _alt_names[0].split(" - ")[0].strip()
                    use_main_fallback  = True
                if not _user_set_fb2 and len(_alt_names) > 1:
                    raw_main_fallback2  = _alt_names[1]
                    main_fallback_comp2 = _alt_names[1].split(" - ")[0].strip()
                    use_main_fallback2  = True

        use_colorway_name_fallback = use_main_fallback or use_main_fallback2

        _effective_fb1     = main_fallback_comp
        _effective_fb1_raw = raw_main_fallback or _effective_fb1
        _effective_fb2     = main_fallback_comp2
        _effective_fb2_raw = raw_main_fallback2 or _effective_fb2

        # ── Main label color resolution ───────────────────────────────────────
=======
        # ── Auto-detect fallback components from color BOM ────────────────────
        _auto_fb1_comp = _auto_fb1_raw = ""
        _auto_fb2_comp = _auto_fb2_raw = ""
        _cb_df = bom_data.get("color_bom")
        if _cb_df is not None and not _cb_df.empty:
            _comp_col = _cb_df.columns[0]
            _alt_names = [
                str(v).strip() for v in _cb_df[_comp_col]
                if str(v).strip().lower().startswith("alt")
            ]
            if len(_alt_names) > 0:
                _auto_fb1_raw  = _alt_names[0]
                _auto_fb1_comp = _alt_names[0].split(" - ")[0].strip()
                use_main_fallback = True
            if len(_alt_names) > 1:
                _auto_fb2_raw  = _alt_names[1]
                _auto_fb2_comp = _alt_names[1].split(" - ")[0].strip()
                use_main_fallback2 = True

        _effective_fb1     = main_fallback_comp or _auto_fb1_comp
        _effective_fb1_raw = raw_main_fallback  or _auto_fb1_raw or _effective_fb1
        _effective_fb2     = main_fallback_comp2 or _auto_fb2_comp
        _effective_fb2_raw = raw_main_fallback2  or _auto_fb2_raw or _effective_fb2

>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        resolved_main_code, main_color = _resolve_main_label_color_with_fallback(
            primary_comp=main_comp,
            fallback_comp=_effective_fb1,
            fallback_raw_sel=_effective_fb1_raw,
            fallback_comp2=_effective_fb2,
            fallback_raw_sel2=_effective_fb2_raw,
            matched_cw=matched_cw,
            color_raw=color_raw,
            color_bom_df=bom_data.get("color_bom"),
            color_spec_df=color_spec,
            get_color_fn=get_color_from_spec,
<<<<<<< HEAD
            use_fb1=use_main_fallback,
            use_fb2=use_main_fallback2,
            use_colorway_name=use_colorway_name_fallback,
            sketch_data=sketch_data,
        )

        # ── Effective main code priority ──────────────────────────────────────
        _is_hat_comp = any(
            kw in str(main_comp).lower()
            for kw in ("hat component", "hat components", "alt hat")
        )
        _main_id_is_pin = bool(main_id) and not _is_hat_comp

        if _main_id_is_pin:
            effective_main_code = main_id
        elif resolved_main_code:
            effective_main_code = resolved_main_code
        else:
            effective_main_code = main_code or "N/A"

        # Late jacquard check
        if not _suppress and str(main_color).strip().lower() == "jacquard":
            _suppress = True

        if _suppress:
            _comp_resolved = components.get(main_comp)
            if _comp_resolved is None:
                for k, v in components.items():
                    if _comp_names_match(k, main_comp):
                        _comp_resolved = v
                        break
            _comp_desc = str((_comp_resolved or {}).get("description", ""))
            if _comp_resolved is not None or _is_embroidery:
                effective_main_code = _derive_main_label_display(
                    raw_main, main_comp,
                    resolved_color=main_color,
                    comp_description=_comp_desc,
                )
                main_color = ""
            else:
                _suppress = False
=======
            use_fb1=True,
            use_fb2=True,
            use_colorway_name=True,
            sketch_data=sketch_data,
        )

        if resolved_main_code:
            effective_main_code = resolved_main_code
        else:
            effective_main_code = main_id or main_code or "N/A"
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938

        care_color = get_color_from_spec(care_comp, matched_cw, color_raw)
        logo_color = get_color_from_spec("Label Logo 1", matched_cw, color_raw)

<<<<<<< HEAD
        # ── Write output columns ──────────────────────────────────────────────
=======
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        result.at[idx, "Main Label"]          = effective_main_code
        result.at[idx, "Main Label Color"]    = "N/A" if _suppress else (main_color or "N/A")
        result.at[idx, "Main Label Supplier"] = "N/A" if _suppress else resolve_supplier(effective_main_code, "main_label")

<<<<<<< HEAD
        result.at[idx, "Main Label 2- Gloves"]  = logo_code  if is_glove else "N/A"
        result.at[idx, "Main Label Color2"]     = logo_color if is_glove else "N/A"
        result.at[idx, "Main Label Supplier2"]  = resolve_supplier(logo_code, "main_label") if is_glove else "N/A"
=======
        result.at[idx, "Main Label 2- Gloves"]   = logo_code  if is_glove else "N/A"
        result.at[idx, "Main Label Color2"]      = logo_color if is_glove else "N/A"
        result.at[idx, "Main Label Supplier2"]   = resolve_supplier(logo_code, "main_label") if is_glove else "N/A"
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938

        result.at[idx, "Hangtag"]           = ht_code or extract_id_only(ht_cw) or "N/A"
        result.at[idx, "Hangtag Supplier"]  = resolve_supplier(ht_code or extract_id_only(ht_cw), "hangtag")
        result.at[idx, "Hangtag 2"]         = ht2_code or "N/A"
        result.at[idx, "Hangtag Supplier2"] = resolve_supplier(ht2_code, "hangtag") if ht2_code else "N/A"
        result.at[idx, "Hangtag3"]          = ht3_code or "N/A"
        result.at[idx, "Hangtag Supplier3"] = resolve_supplier(ht3_code, "hangtag") if ht3_code else "N/A"

<<<<<<< HEAD
        result.at[idx, "Micropak Sticker -Gloves"]      = micro_code        if is_glove else "N/A"
        result.at[idx, "Micropak Sticker Supplier"]     = resolve_supplier(micro_code) if is_glove else "N/A"
        result.at[idx, "Size Label Woven - Gloves"]     = size_label_code   if is_glove else "N/A"
        result.at[idx, "Size Label Supplier"]           = resolve_supplier(size_label_code) if is_glove else "N/A"
        result.at[idx, "Size Sticker -Gloves"]          = size_sticker_code if is_glove else "N/A"
=======
        result.at[idx, "Micropak Sticker -Gloves"]    = micro_code        if is_glove else "N/A"
        result.at[idx, "Micropak Sticker Supplier"]   = resolve_supplier(micro_code) if is_glove else "N/A"
        result.at[idx, "Size Label Woven - Gloves"]   = size_label_code   if is_glove else "N/A"
        result.at[idx, "Size Label Supplier"]         = resolve_supplier(size_label_code) if is_glove else "N/A"
        result.at[idx, "Size Sticker -Gloves"]        = size_sticker_code if is_glove else "N/A"
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        result.at[idx, "Size Sticker Supplier -Gloves"] = resolve_supplier(size_sticker_code) if is_glove else "N/A"

        result.at[idx, "Care Label"]       = care_id or care_code_mat or "N/A"
        result.at[idx, "Care Label Color"] = care_color or "N/A"

        if is_glove:
            result.at[idx, "Content Code -Gloves"] = get_content("content_code", matched_cw, cw_num, color_raw)
            result.at[idx, "TP FC - Gloves"]       = get_content("shell",        matched_cw, cw_num, color_raw)
            result.at[idx, "Care Code-Gloves"]     = get_care("care_code",       matched_cw, cw_num, color_raw)
        else:
            result.at[idx, "Content Code -Gloves"] = "N/A"
            result.at[idx, "TP FC - Gloves"]       = "N/A"
            result.at[idx, "Care Code-Gloves"]     = "N/A"

        result.at[idx, "Content Code"] = get_content("content_code", matched_cw, cw_num, color_raw)
        result.at[idx, "TP FC"]        = get_content("shell",        matched_cw, cw_num, color_raw)
<<<<<<< HEAD
        result.at[idx, "Care Code"]    = get_care("care_code", matched_cw, cw_num, color_raw)
        result.at[idx, "Care Supplier"] = resolve_supplier(care_code_mat, "care_label")

        result.at[idx, "RFID w/o MSRP"]          = rfid_no_msrp_code or "N/A"
        result.at[idx, "RFID w/o MSRP Supplier"] = rfid_no_msrp_sup  or "N/A"
        result.at[idx, "RFID Stickers"]           = rfid_sticker_code or "N/A"
        result.at[idx, "RFID Stickers Supplier"]  = rfid_sticker_sup  or "N/A"

=======
        result.at[idx, "Care Code"]    = get_care("care_code",       matched_cw, cw_num, color_raw)

        # ── FIX: Care Supplier — use the resolved care_code_mat (which now
        # correctly uses the explicit ID from the settings string) ─────────────
        result.at[idx, "Care Supplier"] = resolve_supplier(care_code_mat, "care_label")

        result.at[idx, "RFID w/o MSRP"]          = rfid_no_msrp_code
        result.at[idx, "RFID w/o MSRP Supplier"] = rfid_no_msrp_sup
        result.at[idx, "RFID Stickers"]           = rfid_sticker_code or "N/A"
        result.at[idx, "RFID Stickers Supplier"]  = rfid_sticker_sup  or "N/A"

        # ── FIX: UPC — use the directly-extracted upc_code ───────────────────
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        result.at[idx, "UPC Bag Sticker (Polybag)"] = upc_code or extract_id_only(upc_cw) or "N/A"
        result.at[idx, "UPC Supplier"]              = resolve_supplier(upc_code) if upc_code else "N/A"

        for field, key in [("TP STATUS", "tp_status"), ("TP DATE", "tp_date"),
                           ("PRODUCT STATUS", "product_status"), ("REMARKS", "remarks")]:
            if not str(result.at[idx, field]).strip():
                result.at[idx, field] = label_settings.get(key, "")

<<<<<<< HEAD
        # ── Validation Status ─────────────────────────────────────────────────
        main_label_val  = str(result.at[idx, "Main Label"]).strip()
        main_color_val  = str(result.at[idx, "Main Label Color"]).strip()
=======
        main_label_val = str(result.at[idx, "Main Label"]).strip()
        main_color_val = str(result.at[idx, "Main Label Color"]).strip()
>>>>>>> 499ea02ee42257d2a594346030ab6584ca25d938
        label_has_value = main_label_val not in ("N/A", "", "nan")
        color_missing   = main_color_val in ("N/A", "", "nan")

        core_cols = [
            "Main Label", "Main Label Supplier", "Care Label", "Care Supplier",
            "Content Code", "Care Code", "Hangtag", "Hangtag Supplier",
        ]
        not_found = sum(1 for c in core_cols if str(result.at[idx, c]) in ("N/A", "", "nan"))

        if not_found == len(core_cols):
            result.at[idx, "Validation Status"] = "❌ Error: No BOM data matched"
        elif _suppress:
            care_code_val = str(result.at[idx, "Care Code"]).strip()
            if care_code_val in ("N/A", "", "nan"):
                result.at[idx, "Validation Status"] = "⚠️ Partial"
            else:
                result.at[idx, "Validation Status"] = "✅ Validated"
        elif label_has_value and color_missing:
            if not use_main_fallback and not use_main_fallback2:
                fallback_note = " — enable Fallback 1 or Fallback 2 (alt component) in Settings"
            elif not use_main_fallback2:
                fallback_note = " — enable Fallback 2 (second alt component) in Settings"
            else:
                fallback_note = " — all fallbacks active but color not found"
            result.at[idx, "Validation Status"] = f"⚠️ Partial: Main Label Color missing{fallback_note}"
        elif not_found > 0:
            result.at[idx, "Validation Status"] = "⚠️ Partial"
        else:
            result.at[idx, "Validation Status"] = "✅ Validated"

    return result