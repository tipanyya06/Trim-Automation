import io
from typing import Dict, Any
import pandas as pd
import pdfplumber

KNOWN_COLORWAYS = {
    "010": {"name": "Black",          "full": "010-Black",          "sap": "2092641010"},
    "224": {"name": "Camel Brown",    "full": "224-Camel Brown",    "sap": "2092641224"},
    "278": {"name": "Dark Stone",     "full": "278-Dark Stone",     "sap": "2092641278"},
    "429": {"name": "Everblue",       "full": "429-Everblue",       "sap": "2092641429"},
    "551": {"name": "Lavender Pearl", "full": "551-Lavender Pearl", "sap": "2092641551"},
}


def _fix_broken_words(text: str) -> str:
    """Fix words broken across lines by PDF extraction (e.g. 'Internatio nal' → 'International')."""
    import re
    # Join lines within a cell, collapsing internal newlines
    text = text.replace("\n", " ")
    # Fix words split by newline: "Internatio nal" - these appear as two fragments
    # This is tricky to fix perfectly, so we just collapse extra spaces
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


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

    # Find the row with the most non-empty cells to use as header
    best_header_idx = 0
    best_count = 0
    for i, row in enumerate(rows[:5]):  # only check first 5 rows
        count = sum(1 for c in row if c)
        if count > best_count:
            best_count = count
            best_header_idx = i

    header_row = rows[best_header_idx]
    num_cols = len(header_row)

    # Build unique header names
    header = []
    seen = {}
    for i, c in enumerate(header_row):
        name = c if c else f"col_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        header.append(name)

    # Normalize all data rows to same column count
    data = []
    for row in rows[best_header_idx + 1:]:
        if len(row) < num_cols:
            row = row + [""] * (num_cols - len(row))
        elif len(row) > num_cols:
            row = row[:num_cols]
        data.append(row)

    df = pd.DataFrame(data, columns=header)
    df = df[~(df.eq("").all(axis=1))]
    return df


def _detect_section(page_text: str) -> str:
    txt = page_text.lower()
    if "color bom" in txt:
        return "color_bom"
    if "colorless bom" in txt:
        return "colorless_bom"
    if "color specification" in txt:
        return "color_specification"
    # For costing, prefer detail if we see material/supplier columns
    if "costing" in txt:
        # If it mentions "summary" but NOT component/material/supplier detail, it's a summary
        if "summary" in txt and "material" not in txt:
            return "costing_summary"
        # Otherwise assume it's detail (has Component, Material, Supplier columns)
        return "costing_detail"
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
    lines = first_page_text.splitlines()
    for line in lines:
        line = line.strip()
        for key, label in [
            ("style", "Style"),
            ("season", "Season"),
            ("design", "Design"),
            ("production_lo", "Production LO"),
        ]:
            if line.lower().startswith(label.lower()) and ":" in line:
                meta[key] = line.split(":", 1)[1].strip()
    meta.setdefault("style", "CL2880")
    meta.setdefault("season", "F25")
    meta.setdefault("design", "F4WA209264")
    meta.setdefault("production_lo", "Vietnam")
    return meta


def _is_costing_detail_table(table: list) -> bool:
    """Check if a table has Component/Material/Supplier columns (the real BOM detail)."""
    if not table:
        return False
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
        if len(pdf.pages) == 0:
            raise ValueError("PDF has no pages")

        first_text = pdf.pages[0].extract_text() or ""
        result["metadata"] = _extract_metadata(first_text)

        # We collect costing detail separately with special handling
        costing_detail_rows: list = []
        costing_detail_header: list = None  # known column headers once discovered
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

                # Special handling: detect real costing detail tables by their columns
                if section == "costing_detail" and _is_costing_detail_table(tbl):
                    # Find the header row (has "Material" and "Supplier")
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
                        # Pad/trim
                        if len(cleaned) < num_cols:
                            cleaned += [""] * (num_cols - len(cleaned))
                        elif len(cleaned) > num_cols:
                            cleaned = cleaned[:num_cols]
                        costing_detail_rows.append(cleaned)

                elif section == "costing_detail":
                    # This is a costing page but with continuation data rows (no header)
                    # If we already know the header, use it; otherwise skip
                    if costing_detail_header is not None:
                        num_cols = len(costing_detail_header)
                        for row in tbl:
                            if row is None:
                                continue
                            cleaned = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
                            # Skip rows that look like the big metadata header block (very few non-empty cells)
                            non_empty = sum(1 for c in cleaned if c)
                            if non_empty < 3:
                                continue
                            # Skip the metadata header rows that start with "Costing BOM"
                            first_cell = cleaned[0] if cleaned else ""
                            if "costing bom" in first_cell.lower() or "line slot" in first_cell.lower():
                                continue
                            # Pad/trim
                            if len(cleaned) < num_cols:
                                cleaned += [""] * (num_cols - len(cleaned))
                            elif len(cleaned) > num_cols:
                                cleaned = cleaned[:num_cols]
                            costing_detail_rows.append(cleaned)
                else:
                    tables_by_section.setdefault(section, [])
                    tables_by_section[section].append(tbl)

        # Build costing_detail DataFrame from collected rows
        if costing_detail_header and costing_detail_rows:
            # Build unique header
            header = []
            seen = {}
            for c in costing_detail_header:
                name = c if c else f"col_{len(header)}"
                if name in seen:
                    seen[name] += 1
                    name = f"{name}_{seen[name]}"
                else:
                    seen[name] = 0
                header.append(name)
            df = pd.DataFrame(costing_detail_rows, columns=header)
            df = df[~(df.eq("").all(axis=1))]
            result["costing_detail"] = df
        else:
            result["costing_detail"] = pd.DataFrame()

        for section, tables in tables_by_section.items():
            all_rows = []
            expected_cols = None

            for t in tables:
                for row in t:
                    if row is None:
                        continue
                    cleaned = [(str(c).replace("\n", " ").strip() if c is not None else "") for c in row]
                    if expected_cols is None:
                        expected_cols = len(cleaned)
                    # Pad or trim to expected width
                    if len(cleaned) < expected_cols:
                        cleaned += [""] * (expected_cols - len(cleaned))
                    elif len(cleaned) > expected_cols:
                        cleaned = cleaned[:expected_cols]
                    all_rows.append(cleaned)

            df = _rows_to_df(all_rows)
            result[section] = df

    for key in [
        "color_bom", "colorless_bom", "color_specification",
        "costing_summary", "costing_detail", "care_report",
        "content_report", "measurements", "sales_sample", "hangtag_report",
    ]:
        result.setdefault(key, pd.DataFrame())

    # Build supplier lookup from costing_detail if available
    supplier_lookup = _build_supplier_lookup(result.get("costing_detail", pd.DataFrame()))
    result["supplier_lookup"] = supplier_lookup

    return result


def _build_supplier_lookup(costing_detail_df: pd.DataFrame) -> Dict[str, str]:
    """
    Extract supplier information from costing_detail DataFrame.
    Returns {material_code: supplier_name} mapping.
    """
    if costing_detail_df is None or costing_detail_df.empty:
        return {}
    
    lookup = {}
    df = costing_detail_df.copy()
    
    # Normalize column names
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    # Find material and supplier columns
    material_col = None
    supplier_col = None
    
    for col in df.columns:
        if col == "material":
            material_col = col
        if col == "supplier":
            supplier_col = col
    
    # If not found by exact name, try contains match
    if not material_col:
        for col in df.columns:
            if "material" in col:
                material_col = col
                break
    
    if not supplier_col:
        for col in df.columns:
            if "supplier" in col or "vendor" in col:
                supplier_col = col
                break
    
    # Build lookup table
    if material_col and supplier_col and material_col in df.columns and supplier_col in df.columns:
        import re

        def _clean_supplier(s: str) -> str:
            """Fix words broken by PDF line extraction e.g. 'Internatio nal' → 'International'."""
            prev = None
            while prev != s:
                prev = s
                s = re.sub(r'([a-z]) ([a-z])', lambda m: m.group(1) + m.group(2), s)
            return s

        for _, row in df.iterrows():
            mat = str(row.get(material_col, '')).strip()
            supp = _clean_supplier(str(row.get(supplier_col, '')).strip())
            
            # Extract material code if cell contains descriptive text
            match = re.search(r'\b(\d{3,6})\b', mat)
            if match:
                mat_code = match.group(1)
                # Only skip truly empty/NaN values — all real supplier names are valid
                if supp and supp.lower() not in ("", "nan", "none"):
                    lookup[mat_code] = supp

            # Fallback: if material col is empty, try extracting code from description col
            if not match:
                desc_cols = [c for c in df.columns if "description" in c]
                for dc in desc_cols:
                    desc_val = str(row.get(dc, '')).strip()
                    m2 = re.search(r'\b(\d{3,6})\b', desc_val)
                    if m2:
                        mat_code = m2.group(1)
                        if supp and supp.lower() not in ("", "nan", "none"):
                            lookup[mat_code] = supp
                        break
    
    return lookup