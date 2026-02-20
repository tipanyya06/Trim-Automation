import re
import io
from typing import Dict, Any
import pandas as pd
import pdfplumber


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
    """
    Dedicated parser for the Content Report table structure.

    PDF layout (pdfplumber extracts it as one merged table):
        Row A:  [CONTENT CODE: HUG Shell:...]  [Color Way Number]  [Color Way Name]
        Row B:  [FRENCH | translation]          [023]               [City Grey]
        Row C:  [GERMAN | translation]          [810]               [Hot Coral...]
        Row D:  []                              [433]               [Mountain Blue...]
        ...

    Output — one row per colorway:
        Color Way Number | Color Way Name | Content Code | Content Full
        023              | City Grey      | HUG          | CONTENT CODE: HUG Shell:...
        810              | Hot Coral...   | HUG          | ...
    """
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

    # ── Step 1: Identify colorway number + name column indices ──────────────────
    cw_num_col_idx = None
    cw_name_col_idx = None

    # First pass: look for explicit header text "Color Way Number" / "Color Way Name"
    for row in all_rows[:10]:
        for i, cell in enumerate(row):
            cl = cell.lower()
            if "color way number" in cl or "colorway number" in cl:
                cw_num_col_idx = i
            if "color way name" in cl or "colorway name" in cl:
                cw_name_col_idx = i

    # Fallback: rightmost columns — find the one that most often holds 3-digit numbers
    if cw_num_col_idx is None and all_rows:
        num_cols = max(len(r) for r in all_rows)
        for candidate in range(num_cols - 1, -1, -1):
            hits = sum(
                1 for r in all_rows
                if len(r) > candidate and re.match(r'^\d{3}$', r[candidate].strip())
            )
            if hits >= 2:          # need at least 2 rows with a 3-digit value
                cw_num_col_idx = candidate
                # Name column is immediately to the right (if it exists)
                if candidate + 1 < num_cols:
                    cw_name_col_idx = candidate + 1
                break

    # ── Step 2: Collect all (cw_num, cw_name) pairs and the content code ────────
    current_content_code = ""
    current_content_full = ""

    # colorway dict: {cw_num: cw_name}  — preserves first-seen order
    colorway_map: dict = {}

    # Skip rows that are page-level noise (not actual table data)
    _skip_patterns = [
        r'content report line slot',
        r'color way number',
        r'color way name',
        r'colorway number',
        r'colorway name',
    ]

    for row in all_rows:
        row_text = " ".join(row).lower()

        # Skip page header / label rows
        if any(re.search(p, row_text) for p in _skip_patterns):
            # But still grab the colorway data that may sit in the same row
            pass  # fall through to colorway extraction below

        # Detect CONTENT CODE in any cell
        for cell in row:
            if "CONTENT CODE" in cell.upper():
                m = re.search(r'CONTENT CODE[:\s]+(\w+)', cell, re.IGNORECASE)
                if m:
                    current_content_code = m.group(1).strip()
                    current_content_full = cell.strip()
                break

        # Extract colorway number + name from their dedicated columns
        cw_num = ""
        cw_name = ""
        if cw_num_col_idx is not None and len(row) > cw_num_col_idx:
            cw_num = row[cw_num_col_idx].strip()
        if cw_name_col_idx is not None and len(row) > cw_name_col_idx:
            cw_name = row[cw_name_col_idx].strip()

        # Only store rows where cw_num is a real 3-digit colorway number
        if re.match(r'^\d{3}$', cw_num) and cw_num not in colorway_map:
            colorway_map[cw_num] = cw_name

    if not colorway_map or not current_content_code:
        return pd.DataFrame()

    # ── Step 3: Build clean output — one row per colorway ───────────────────────
    output_rows = [
        {
            "Color Way Number": cw_num,
            "Color Way Name":   cw_name,
            "Content Code":     current_content_code,
            "Content Full":     current_content_full,
        }
        for cw_num, cw_name in colorway_map.items()
    ]

    return pd.DataFrame(output_rows)


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
                    # Content report pages go into a dedicated bucket for special parsing
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

            # ── Special handling: content_report ───────────────────────────────
            if section == "content_report":
                result["content_report"] = _parse_content_report_tables(tables)
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
    return result