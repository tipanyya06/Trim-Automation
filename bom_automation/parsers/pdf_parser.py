import re
import io
from typing import Dict, Any
import pandas as pd
import pdfplumber

from parsers.detail_sketch import parse_detail_sketch_pages, get_sketch_color

def _clean_table(rows):
    cleaned = []
    for r in rows or []:
        if r is None:
            continue
        cleaned.append([(str(c).replace("\n", " ").strip()) if c is not None else "" for c in r])
    return cleaned


def _rows_to_df(rows: list) -> pd.DataFrame:
    rows = _clean_table(rows)
    if not rows:
        return pd.DataFrame()
    best_header_idx, best_count = 0, 0
    for i, row in enumerate(rows[:5]):
        count = sum(1 for c in row if c)
        if count > best_count:
            best_count = count
            best_header_idx = i
    header_row = rows[best_header_idx]
    num_cols = len(header_row)
    header, seen = [], {}
    for i, c in enumerate(header_row):
        name = c if c else f"col_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
            if not c:
                name = f"col_{i}"
            else:
                name = f"{c}_{seen[c]}"
        else:
            seen[name] = 0
        header.append(name)
    data = []
    for row in rows[best_header_idx + 1:]:
        if len(row) < num_cols:
            row = row + [""] * (num_cols - len(row))
        elif len(row) > num_cols:
            row = row[:num_cols]
        data.append(row)
    df = pd.DataFrame(data, columns=header)
    return df[~(df.eq("").all(axis=1))]


def _detect_section(page_text: str) -> str:
    txt = page_text.lower()
    first_lines = "\n".join(page_text.lower().splitlines()[:5])
    first_lines_nsp = re.sub(r'\s+', '', first_lines)

    if "color bom" in txt:
        return "color_bom"
    if "colorless bom" in txt:
        return "colorless_bom"
    if "color specification" in txt:
        return "color_specification"

    _costing_keywords = [
        "costing detail", "costing bom", "cost detail", "cost bom",
        "costing summary", "costingdetail", "costingbom",
    ]
    _is_costing = (
        any(kw in first_lines for kw in _costing_keywords)
        or "costing" in first_lines_nsp
    )
    if _is_costing:
        _is_summary = "summary" in first_lines and "material" not in txt and "supplier" not in txt
        return "costing_summary" if _is_summary else "costing_detail"

    if "care report" in txt:
        return "care_report"
    if "content report" in txt:
        return "content_report"
    if "measurement" in txt:
        return "measurements"
    if "sales sample" in txt:
        return "sales_sample"
    if "hangtag" in txt:
        return "hangtag_report"

    return "unknown"


def _extract_metadata(first_page_text: str) -> Dict[str, Any]:
    meta = {}
    text = first_page_text

    m = re.search(r'\b([A-Z]{2}\d{4})\b', text)
    if m:
        meta["style"] = m.group(1)

    m = re.search(r'Season[:\s]+([A-Z]\d+)', text)
    if m:
        meta["season"] = m.group(1)

    m = re.search(r'Design[:\s]+([A-Z0-9]{5,})', text)
    if m:
        meta["design"] = m.group(1)

    m = re.search(r'Production LO[:\s]+([A-Za-z]+)', text)
    if m:
        meta["production_lo"] = m.group(1)

    smu_type = ""
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if re.search(r'\bSMU\s+Type\b', line, re.IGNORECASE):
            after = re.split(r'SMU\s+Type', line, flags=re.IGNORECASE, maxsplit=1)[-1].strip()
            after = after.lstrip(':').strip()
            if after and after.lower() not in ('', 'nan', 'none'):
                smu_type = after
                break

            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not re.search(
                    r'(Line Slot|Season|Designer|Fit Engineer|Merchandise)',
                    next_line, re.IGNORECASE
                ):
                    m_fit = re.search(
                        r'\b(?:Accessories|Footwear|Apparel)\b\s+(.+)$',
                        next_line, re.IGNORECASE
                    )
                    if m_fit:
                        smu_type = m_fit.group(1).strip()
                    else:
                        tokens = next_line.split()
                        if tokens:
                            smu_type = tokens[-1].strip()
                    break

    if not smu_type:
        smu_value_pattern = re.compile(
            r'\b(Color\s+Add|Size\s+Add|Color[/ ]Size\s+Add|SMU)\b',
            re.IGNORECASE,
        )
        in_header_zone = False
        for line in lines:
            if re.search(r'\bFit\b.*\bSMU', line, re.IGNORECASE):
                in_header_zone = True
                continue
            if in_header_zone:
                m2 = smu_value_pattern.search(line)
                if m2:
                    smu_type = m2.group(0).strip()
                    break
                if line.strip():
                    break

    if not smu_type:
        data_row_pattern = re.compile(
            r'\b(?:Accessories|Footwear|Apparel)\b\s+(.+)$',
            re.IGNORECASE,
        )
        for line in lines:
            m3 = data_row_pattern.search(line)
            if m3:
                smu_type = m3.group(1).strip()
                break

    meta["smu_type"] = smu_type.strip() if smu_type else "N/A"

    meta.setdefault("style", "")
    meta.setdefault("season", "")
    meta.setdefault("design", "")
    meta.setdefault("production_lo", "")
    return meta


def _is_costing_detail_table(table: list) -> bool:
    for row in table[:5]:
        if row is None:
            continue
        row_strs = [str(c).replace("\n", " ").strip().lower() for c in row if c is not None]
        row_joined = " ".join(row_strs)
        if "material" in row_strs and "supplier" in row_strs:
            return True
        if "component" in row_strs and "material" in row_strs:
            return True
        if "material" in row_joined and "supplier" in row_joined:
            return True
    return False


def _fix_split_text(s: str) -> str:
    if not s:
        return s
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'(?<![a-zA-Z])([A-Z]) ([A-Z])(?![a-zA-Z])', r'\1\2', s)
    s = re.sub(r'([a-zA-Z]{4,})  ?([a-z]{2,5})(?=\s|$)',
               lambda m: m.group(1) + m.group(2) if len(m.group(2)) <= 4 else m.group(0), s)
    return s.strip()


def _extract_codes_from_cell(cell_str: str) -> set:
    codes = set()
    s = str(cell_str).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return codes
    for m in re.finditer(r'(?<!\d)(\d{3,7})(?!\d)', s):
        raw = m.group(1)
        codes.add(raw)
        stripped = raw.lstrip("0")
        if stripped:
            codes.add(stripped)
    digits_only = re.sub(r'[^\d]', '', s)
    if 3 <= len(digits_only) <= 7:
        codes.add(digits_only)
        codes.add(digits_only.lstrip("0"))
    return codes


def _build_supplier_lookup(costing_detail_df: pd.DataFrame) -> Dict[str, str]:
    if costing_detail_df is None or costing_detail_df.empty:
        return {}

    lookup: Dict[str, str] = {}
    df = costing_detail_df.copy()
    norm_cols = [str(c).lower().strip() for c in df.columns]
    original_cols = list(df.columns)

    supplier_idx = None
    for i, c in enumerate(norm_cols):
        if c == "supplier":
            supplier_idx = i
            break
    if supplier_idx is None:
        for i, c in enumerate(norm_cols):
            if "supplier" in c or "vendor" in c:
                supplier_idx = i
                break
    if supplier_idx is None:
        return {}

    supplier_col = original_cols[supplier_idx]

    material_col = None
    for i, c in enumerate(norm_cols):
        if c == "material":
            material_col = original_cols[i]
            break
    if material_col is None:
        for i, c in enumerate(norm_cols):
            if "material" in c:
                material_col = original_cols[i]
                break

    def _register(code: str, supplier: str):
        for key in {code, code.lstrip("0")}:
            if not key:
                continue
            if key not in lookup:
                lookup[key] = supplier
            elif len(supplier) > len(lookup[key]):
                lookup[key] = supplier

    for _, row in df.iterrows():
        supplier_raw = str(row.get(supplier_col, "")).strip()
        if not supplier_raw or supplier_raw.lower() in ("nan", "none", ""):
            continue

        supplier = _fix_split_text(supplier_raw)

        found_codes: set = set()
        if material_col:
            mat_cell = str(row.get(material_col, "")).strip()
            found_codes = _extract_codes_from_cell(mat_cell)
        if not found_codes:
            for col in original_cols:
                if col == supplier_col:
                    continue
                found_codes.update(_extract_codes_from_cell(str(row.get(col, ""))))

        for code in found_codes:
            _register(code, supplier)

    return lookup


# ── Content Report Parser ─────────────────────────────────────────────────────

def _parse_content_report_tables(tables: list) -> pd.DataFrame:
    all_rows = []
    for tbl in tables:
        for row in tbl:
            if row is None:
                continue
            cleaned = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
            if any(cleaned):
                all_rows.append(cleaned)

    if not all_rows:
        return pd.DataFrame()

    cw_num_col_idx = None
    cw_name_col_idx = None

    for row in all_rows[:10]:
        for i, cell in enumerate(row):
            cl = cell.lower()
            if "color way number" in cl or "colorway number" in cl:
                cw_num_col_idx = i
            if "color way name" in cl or "colorway name" in cl:
                cw_name_col_idx = i

    if cw_num_col_idx is None and all_rows:
        num_cols = max(len(r) for r in all_rows)
        for candidate in range(num_cols - 1, -1, -1):
            hits = sum(
                1 for r in all_rows
                if len(r) > candidate and re.match(r'^\d{3}$', r[candidate].strip())
            )
            if hits >= 2:
                cw_num_col_idx = candidate
                if candidate + 1 < num_cols:
                    cw_name_col_idx = candidate + 1
                break

    _COMPOSITION_LABELS = [
        ("fleece lining", "Fleece Lining"),
        ("faux fur",      "Faux Fur"),
        ("insulation",    "Insulation"),
        ("lining",        "Lining"),
        ("shell",         "Shell"),
    ]

    _skip_patterns = [
        r'content report line slot',
        r'color way number',
        r'color way name',
        r'colorway number',
        r'colorway name',
    ]

    sections: list = []
    current_content_code: str = ""
    current_content_full: str = ""
    colorway_map: dict = {}
    _composition_parts: list = []

    def _flush_section():
        if current_content_code and colorway_map:
            _compo_suffix = (
                "  " + "  ".join(_composition_parts) if _composition_parts else ""
            )
            enriched = current_content_full + _compo_suffix
            sections.append((current_content_code, enriched, dict(colorway_map)))

    for row in all_rows:
        row_text = " ".join(row).lower()

        if any(re.search(p, row_text) for p in _skip_patterns):
            pass

        for cell in row:
            if "CONTENT CODE" in cell.upper():
                m = re.search(r'CONTENT CODE[:\s]+(\w+)', cell, re.IGNORECASE)
                if m:
                    _flush_section()
                    current_content_code = m.group(1).strip()
                    current_content_full = cell.strip()
                    colorway_map = {}
                    _composition_parts = []
                break

        if row and len(row) >= 2:
            first_cell = row[0].strip().rstrip(":").lower()
            second_cell = row[1].strip() if len(row) > 1 else ""
            if second_cell and second_cell.lower() not in ("", "none", "nan"):
                for match_key, canonical_label in _COMPOSITION_LABELS:
                    if first_cell == match_key or first_cell.startswith(match_key):
                        label_str = f"{canonical_label}: {second_cell}"
                        already = any(
                            p.startswith(f"{canonical_label}:") for p in _composition_parts
                        )
                        if not already:
                            _composition_parts.append(label_str)
                        break

        cw_num = ""
        cw_name = ""
        if cw_num_col_idx is not None and len(row) > cw_num_col_idx:
            cw_num = row[cw_num_col_idx].strip()
        if cw_name_col_idx is not None and len(row) > cw_name_col_idx:
            cw_name = row[cw_name_col_idx].strip()

        if re.match(r'^\d{3}$', cw_num) and cw_num not in colorway_map:
            colorway_map[cw_num] = cw_name

    _flush_section()

    if not sections:
        return pd.DataFrame()

    output_rows = []
    for (content_code, enriched_full, cw_map) in sections:
        for cw_num, cw_name in cw_map.items():
            output_rows.append({
                "Color Way Number": cw_num,
                "Color Way Name":   cw_name,
                "Content Code":     content_code,
                "Content Full":     enriched_full,
            })

    return pd.DataFrame(output_rows)


# ── Color BOM horizontal merge ────────────────────────────────────────────────

def _merge_color_bom_tables(tables: list) -> pd.DataFrame:
    """
    Color BOM may span multiple PDF pages/tables with the same component rows
    but different colorway columns. Merge them horizontally by matching the
    Component column.

    BUG FIX (positional fallback):
    When a PDF page has NO component names at all (all blank — the entire page
    is continuation data), forward-filling the Component column produces NaN
    throughout because there is no prior non-null value to propagate from.
    The resulting cw_map is empty (or contains only a 'nan' key), so
    base[comp_col].apply(lambda v: cw_map.get(v, None)) returns None for every
    component and the entire page's colorway data is silently lost.

    Fix: after building the name-based cw_map, if it is empty, fall back to
    POSITIONAL matching — align extra_df rows to base rows by index position.
    This is correct because the PDF always lists components in the same order
    on every page; the continuation page just omits the names.
    """
    dfs = [_rows_to_df(_clean_table(t)) for t in tables if t]
    dfs = [df for df in dfs if not df.empty]
    if not dfs:
        return pd.DataFrame()
    if len(dfs) == 1:
        return dfs[0]

    base = dfs[0].copy()
    comp_col = base.columns[0]  # "Component"

    _META_COLS = {"component", "details", "placement", "usage", "width", "marker width",
                  "sap material code", "smu accounts"}

    # Step 1: rename any col_N columns in base by matching data against named
    # columns from subsequent pages (fixes the unnamed colorway column bug)
    for extra_df in dfs[1:]:
        named_cw_cols = [c for c in extra_df.columns if re.match(r'^\d{3}-', str(c))]
        for named_col in named_cw_cols:
            for base_col in list(base.columns):
                if not str(base_col).startswith("col_"):
                    continue
                base_vals = set(base[base_col].dropna().astype(str)) - {"", "None", "nan"}
                extra_vals = set(extra_df[named_col].dropna().astype(str)) - {"", "None", "nan"}
                if base_vals & extra_vals:
                    base = base.rename(columns={base_col: named_col})
                    break

    # Step 2: merge new colorway columns from each extra page
    for extra_df in dfs[1:]:
        if extra_df.empty:
            continue
        extra_comp_col = extra_df.columns[0]

        new_cw_cols = [
            c for c in extra_df.columns[1:]
            if str(c).lower() not in _META_COLS
            and not str(c).startswith("col_")
            and re.match(r'^\d{3}-', str(c))
        ]
        if not new_cw_cols:
            new_cw_cols = [
                c for c in extra_df.columns[1:]
                if str(c).lower() not in _META_COLS
            ]

        for cw_col in new_cw_cols:
            # Forward-fill blank component names in extra_df.
            # Page 2+ continuation rows have an empty Component column but
            # belong to the preceding non-blank row.
            _extra_filled = extra_df.copy()
            _extra_filled[extra_comp_col] = (
                _extra_filled[extra_comp_col]
                .replace("", pd.NA).replace("None", pd.NA).replace("nan", pd.NA)
                .ffill()
            )

            # Build name-based map: component_name -> colorway_cell_value
            cw_map = {}
            for _, row in _extra_filled.iterrows():
                comp_val = str(row.get(extra_comp_col, "")).strip()
                cell_val = str(row.get(cw_col, "")).strip()
                if (comp_val and comp_val.lower() not in ("nan", "none", "")
                        and cell_val and cell_val.lower() not in ("none", "nan", "")):
                    cw_map[comp_val] = cell_val

            # ── POSITIONAL FALLBACK ───────────────────────────────────────────
            # When ALL Component cells on this extra page are blank, ffill
            # leaves them as NaN (nothing to propagate from), so cw_map is
            # empty.  In that case the rows are in the same ORDER as base rows,
            # so we can match by position: extra row i -> base row i.
            if not cw_map:
                base_comps = list(base[comp_col].astype(str).str.strip())
                extra_vals_list = list(_extra_filled[cw_col].astype(str).str.strip())
                for i, comp_name in enumerate(base_comps):
                    if i < len(extra_vals_list):
                        val = extra_vals_list[i]
                        if val and val.lower() not in ("none", "nan", ""):
                            cw_map[comp_name] = val
            # ── END POSITIONAL FALLBACK ───────────────────────────────────────

            if cw_col in base.columns:
                # Column already exists — fill in any missing (None) values
                mask = base[cw_col].isna() | base[cw_col].isin(["", "None", "nan"])
                base.loc[mask, cw_col] = base.loc[mask, comp_col].apply(
                    lambda v: cw_map.get(str(v).strip(), None)
                )
                continue

            # New column — add it
            base[cw_col] = base[comp_col].apply(
                lambda v: cw_map.get(str(v).strip(), None)
            )

    return base


# ── Main Parser ───────────────────────────────────────────────────────────────

def parse_bom_pdf(pdf_file_obj) -> Dict[str, Any]:
    result: Dict[str, Any] = {"metadata": {}}

    with pdfplumber.open(pdf_file_obj) as pdf:
        if not pdf.pages:
            raise ValueError("PDF has no pages")

        first_text = pdf.pages[0].extract_text() or ""
        result["metadata"] = _extract_metadata(first_text)

        costing_detail_rows: list = []
        costing_detail_header = None
        tables_by_section: Dict[str, list] = {}

        for page in pdf.pages:
            text = page.extract_text() or ""
            section = _detect_section(text)
            try:
                page_tables = page.extract_tables() or []
            except Exception:
                page_tables = []
            if not page_tables:
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                if lines:
                    page_tables = [[[line] for line in lines]]

            for tbl in page_tables:
                if not tbl:
                    continue

                if section == "costing_detail" and _is_costing_detail_table(tbl):
                    header_idx = 0
                    for ri, row in enumerate(tbl[:5]):
                        if row is None:
                            continue
                        row_strs = [str(c).replace("\n", " ").strip().lower() for c in row if c is not None]
                        if "material" in row_strs and "supplier" in row_strs:
                            header_idx = ri
                            break
                    cleaned_header = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in tbl[header_idx]]
                    if costing_detail_header is None:
                        costing_detail_header = cleaned_header
                    num_cols = len(costing_detail_header)
                    for row in tbl[header_idx + 1:]:
                        if row is None:
                            continue
                        cleaned = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
                        cleaned = (cleaned + [""] * num_cols)[:num_cols]
                        costing_detail_rows.append(cleaned)

                elif section == "costing_detail" and costing_detail_header:
                    tbl_data = tbl
                    if _is_costing_detail_table(tbl):
                        start_idx = 1
                        for ri, row in enumerate(tbl[:5]):
                            if row is None:
                                continue
                            row_strs = [str(c).replace("\n", " ").strip().lower() for c in row if c is not None]
                            if "material" in row_strs and "supplier" in row_strs:
                                start_idx = ri + 1
                                break
                        tbl_data = tbl[start_idx:]

                    num_cols = len(costing_detail_header)
                    for row in tbl_data:
                        if row is None:
                            continue
                        cleaned = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
                        non_empty = sum(1 for c in cleaned if c)
                        if non_empty < 2:
                            continue
                        first_cell = cleaned[0] if cleaned else ""
                        if "costing bom" in first_cell.lower() or "line slot" in first_cell.lower():
                            continue
                        cleaned = (cleaned + [""] * num_cols)[:num_cols]
                        costing_detail_rows.append(cleaned)

                elif section == "costing_detail":
                    pass

                else:
                    tables_by_section.setdefault(section, []).append(tbl)

        # ── Build costing_detail DataFrame ─────────────────────────────────────
        if costing_detail_header and costing_detail_rows:
            header, seen = [], {}
            for c in costing_detail_header:
                name = c if c else f"col_{len(header)}"
                if name in seen:
                    seen[name] += 1
                    name = f"{name}_{seen[name]}"
                else:
                    seen[name] = 0
                header.append(name)
            df = pd.DataFrame(costing_detail_rows, columns=header)
            result["costing_detail"] = df[~(df.eq("").all(axis=1))]
        else:
            result["costing_detail"] = pd.DataFrame()

        # ── Build all other section DataFrames ──────────────────────────────────
        for section, tables in tables_by_section.items():

            if section == "content_report":
                result["content_report"] = _parse_content_report_tables(tables)
                continue

            if section in ("color_bom", "colorless_bom"):
                result[section] = _merge_color_bom_tables(tables)
                continue

            all_rows, expected_cols = [], None
            for t in tables:
                for row in t:
                    if row is None:
                        continue
                    cleaned = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
                    if expected_cols is None:
                        expected_cols = len(cleaned)
                    cleaned = (cleaned + [""] * expected_cols)[:expected_cols]
                    all_rows.append(cleaned)
            result[section] = _rows_to_df(all_rows)

        for key in ["color_bom", "colorless_bom", "color_specification",
                    "costing_summary", "costing_detail", "care_report",
                    "content_report", "measurements", "sales_sample", "hangtag_report"]:
            result.setdefault(key, pd.DataFrame())

        result["supplier_lookup"] = _build_supplier_lookup(result.get("costing_detail", pd.DataFrame()))
        result["detail_sketch"] = parse_detail_sketch_pages(pdf_file_obj)

        return result

    return result
