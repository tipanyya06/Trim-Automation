import re
from typing import Dict
import pandas as pd

KNOWN_CARE_CODE = "3000"

_FABRIC_SECTIONS = [
    "Exclusive of Trimming",
    "Faux Fur",
    "Insulation",
    "Lining",
    "Fill",
    "Face",
    "Body",
    "Trim",
    "Outer",
    "Inner",
    "Shell",
]


def _parse_content_header(header: str) -> dict:
    """
    Parse a CONTENT CODE header like:
      'CONTENT CODE: SRH Shell: 55% Recycled Polyester ...'
    Returns: {content_code, shell, sections, full_content}
    """
    out = {"content_code": "", "shell": "", "sections": {}, "full_content": ""}

    m = re.search(r'CONTENT CODE:\s*(\w+)', header, re.IGNORECASE)
    if m:
        out["content_code"] = m.group(1).strip()

    full_m = re.search(r'CONTENT CODE:\s*\w+\s+(.*)', header, re.IGNORECASE)
    out["full_content"] = full_m.group(1).strip() if full_m else ""

    section_pat = '|'.join(re.escape(s) for s in sorted(_FABRIC_SECTIONS, key=len, reverse=True))
    parts = re.split(f'\\b({section_pat}):', out["full_content"])
    sections = {}
    i = 1
    while i + 1 < len(parts):
        sections[parts[i].strip()] = parts[i + 1].strip().rstrip(",")
        i += 2
    out["sections"] = sections
    out["shell"] = sections.get("Shell", "")
    return out


def _parse_care_header(header: str) -> str:
    """Parse 'Care Code: 3000' → '3000'"""
    m = re.search(r'Care Code:\s*(\S+)', header, re.IGNORECASE)
    return m.group(1).strip() if m else KNOWN_CARE_CODE


def extract_content_codes(content_report_df: pd.DataFrame) -> Dict[str, dict]:
    """
    Parse content_report to build {colorway_number: {content_code, shell, ...}}.

    The PDF produces multiple CONTENT CODE blocks, each in a column header like:
      'CONTENT CODE: SRH Shell: 55% Recycled Polyester ...'
    followed by rows containing 'Color Way Number' and 'Color Way Name'.

    Strategy — scan ALL column names and ALL cell values for CONTENT CODE patterns,
    then associate each code with the colorway numbers that follow it.
    """
    if content_report_df is None or content_report_df.empty:
        return {}

    df = content_report_df.copy()
    result: Dict[str, dict] = {}

    # Collect all (content_code_header, colorway_numbers[]) groups by scanning rows
    # A group starts when we see a cell containing "CONTENT CODE:" and ends at the next one
    current_entry = None

    # First check column headers for CONTENT CODE (first block is in the col name)
    for col in df.columns:
        col_str = str(col).strip()
        if "CONTENT CODE" in col_str.upper() and len(col_str) > 15:
            parsed = _parse_content_header(col_str)
            if parsed["content_code"] and current_entry is None:
                current_entry = parsed
            break

    for _, row in df.iterrows():
        # Check every cell in the row for a CONTENT CODE pattern
        found_code = None
        for cell in row:
            cell_str = str(cell).strip()
            if "CONTENT CODE" in cell_str.upper() and len(cell_str) > 15:
                parsed = _parse_content_header(cell_str)
                if parsed["content_code"]:
                    found_code = parsed
                    break

        if found_code:
            current_entry = found_code
            continue

        if current_entry is None:
            continue

        # Look for Color Way Number values in this row
        # They appear in rows where "Color Way Number" is a column name
        # but since column names are dynamic, just look for 3-digit numeric cells
        # combined with rows that have a colorway name
        colorway_num = None
        for cell in row:
            cell_str = str(cell).strip()
            if re.match(r'^\d{3}$', cell_str):
                colorway_num = cell_str
                break

        if colorway_num:
            result[colorway_num] = {
                "content_code": current_entry["content_code"],
                "shell": current_entry["shell"],
                "full_content": current_entry["full_content"],
                "sections": current_entry["sections"],
            }

    return result


def extract_care_codes(care_report_df: pd.DataFrame) -> Dict[str, dict]:
    """
    Extract care code from care_report.
    The PDF stores the care code in the column header: 'Care Code: 3000'
    English instructions are in the first data row.
    """
    fallback_instructions = (
        "Hand Wash Cold, Do Not Bleach, Dry Flat, "
        "Do Not Wring or Twist, Reshape, Do Not Iron, Drycleanable"
    )

    if care_report_df is None or care_report_df.empty:
        return {}

    df = care_report_df.copy()

    care_code = KNOWN_CARE_CODE
    english_instructions = ""

    for col in df.columns:
        col_str = str(col)
        if "Care Code" in col_str:
            care_code = _parse_care_header(col_str)
            instr_col = df.columns[1] if len(df.columns) > 1 else None
            for _, row in df.iterrows():
                lang = str(row.get(col, "")).strip().lower()
                if lang == "english" and instr_col:
                    english_instructions = str(row.get(instr_col, "")).strip()
                    break
            break

    if not english_instructions:
        english_instructions = fallback_instructions

    entry = {"care_code": care_code, "english_instructions": english_instructions}

    result: Dict[str, dict] = {}
    cols_lower = {str(c).lower(): c for c in df.columns}
    num_col = cols_lower.get("color way number") or cols_lower.get("colorway number")
    name_col = cols_lower.get("color way name") or cols_lower.get("colorway name")

    if num_col or name_col:
        for _, row in df.iterrows():
            key = str(row.get(num_col) or row.get(name_col) or "").strip()
            if key and re.match(r'^\d{3}$', key):
                result[key] = entry

    return result
