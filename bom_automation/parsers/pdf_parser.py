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
    if "costing bom" in txt and ("summary" in txt or "total fob" in txt):
        return "costing_summary"
    if "costing bom" in txt or "costing detail" in txt:
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


def parse_bom_pdf(pdf_file_obj) -> Dict[str, Any]:
    result: Dict[str, Any] = {"metadata": {}}

    with pdfplumber.open(pdf_file_obj) as pdf:
        if len(pdf.pages) == 0:
            raise ValueError("PDF has no pages")

        first_text = pdf.pages[0].extract_text() or ""
        result["metadata"] = _extract_metadata(first_text)

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
                tables_by_section.setdefault(section, [])
                tables_by_section[section].append(tbl)

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

    return result