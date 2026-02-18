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
    if "color bom" in txt:              return "color_bom"
    if "colorless bom" in txt:         return "colorless_bom"
    if "color specification" in txt:   return "color_specification"
    if "costing" in txt:
        if "summary" in txt and "material" not in txt:
            return "costing_summary"
        return "costing_detail"
    if "care report" in txt:           return "care_report"
    if "content report" in txt:        return "content_report"
    if "measurement" in txt:           return "measurements"
    if "sales sample" in txt:          return "sales_sample"
    if "hangtag" in txt:               return "hangtag_report"
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
    for row in table[:3]:
        if row is None:
            continue
        row_strs = [str(c).replace("\n", " ").strip().lower() for c in row if c is not None]
        if "material" in row_strs and "supplier" in row_strs:
            return True
        if "component" in row_strs and "material" in row_strs:
            return True
    return False


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
                    for ri, row in enumerate(tbl[:3]):
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
                    num_cols = len(costing_detail_header)
                    for row in tbl:
                        if row is None:
                            continue
                        cleaned = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
                        non_empty = sum(1 for c in cleaned if c)
                        if non_empty < 3:
                            continue
                        first_cell = cleaned[0] if cleaned else ""
                        if "costing bom" in first_cell.lower() or "line slot" in first_cell.lower():
                            continue
                        cleaned = (cleaned + [""] * num_cols)[:num_cols]
                        costing_detail_rows.append(cleaned)
                else:
                    tables_by_section.setdefault(section, []).append(tbl)

        # Build costing_detail
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

        for section, tables in tables_by_section.items():
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


def _fix_split_text(s: str) -> str:
    """
    Fix OCR/PDF text extraction artifacts where words get split character-by-character.
    Examples:
      'Y K K'      → 'YKK'
      'bel cro'    → 'belcro'   (only merges 1-2 char tokens)
      'Avery Den  nison' → 'Avery Dennison'
    """
    if not s:
        return s

    # Fix ALL-CAPS letter sequences like "Y K K" → "YKK"
    s = re.sub(r'\b([A-Z]) ([A-Z])\b', r'\1\2', s)
    s = re.sub(r'\b([A-Z]{2,}) ([A-Z])\b', r'\1\2', s)

    # Fix split lowercase tokens of 1-3 chars: "bel cro" → "belcro"
    s = re.sub(r'\b([a-z]{1,3}) ([a-z]{1,3})\b', lambda m: m.group(1) + m.group(2), s)

    # Fix split in middle of words: "Den  nison" → "Dennison"
    s = re.sub(r'([a-zA-Z]{2,})\s{1,2}([a-z]{2,})', lambda m: m.group(1) + m.group(2), s)

    return s.strip()


def _build_supplier_lookup(costing_detail_df: pd.DataFrame) -> Dict[str, str]:
    """
    Build {material_code → supplier_name} from costing detail.

    Scans ALL columns in every row for 3-6 digit codes.
    If the dedicated material column has codes, use only those (most precise).
    Keeps the longest/most informative supplier name on conflicts.
    """
    if costing_detail_df is None or costing_detail_df.empty:
        return {}

    lookup: Dict[str, str] = {}
    df = costing_detail_df.copy()
    norm_cols = [str(c).lower().strip() for c in df.columns]
    original_cols = list(df.columns)

    # Locate supplier column
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

    # Locate material column (preferred source of codes)
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

    for _, row in df.iterrows():
        supplier_raw = str(row.get(supplier_col, "")).strip()
        if not supplier_raw or supplier_raw.lower() in ("nan", "none", ""):
            continue

        supplier = _fix_split_text(supplier_raw)

        # If material column has a code, use only that — most accurate
        found_codes: set = set()
        if material_col:
            mat_cell = str(row.get(material_col, "")).strip()
            mat_codes = re.findall(r'\b(\d{3,6})\b', mat_cell)
            if mat_codes:
                found_codes = set(mat_codes)

        # Fallback: scan every cell in the row
        if not found_codes:
            for col in original_cols:
                if col == supplier_col:
                    continue
                cell = str(row.get(col, "")).strip()
                codes = re.findall(r'\b(\d{3,6})\b', cell)
                found_codes.update(codes)

        for code in found_codes:
            if code not in lookup:
                lookup[code] = supplier
            elif len(supplier) > len(lookup[code]):
                # Prefer the more descriptive supplier name
                lookup[code] = supplier

    return lookup