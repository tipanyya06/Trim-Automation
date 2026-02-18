import re
from typing import Dict
import pandas as pd


_FABRIC_SECTIONS = [
    "Exclusive of Trimming", "Faux Fur", "Insulation", "Lining",
    "Fill", "Face", "Body", "Trim", "Outer", "Inner", "Shell",
]


def _parse_content_header(header: str) -> dict:
    out = {"content_code": "", "shell": "", "full_content": "", "sections": {}}
    m = re.search(r'CONTENT CODE:\s*(\w+)', header, re.IGNORECASE)
    if m:
        out["content_code"] = m.group(1).strip()
    full_m = re.search(r'CONTENT CODE:\s*\w+\s+(.*)', header, re.IGNORECASE)
    out["full_content"] = full_m.group(1).strip() if full_m else ""
    pat = '|'.join(re.escape(s) for s in sorted(_FABRIC_SECTIONS, key=len, reverse=True))
    parts = re.split(r'\b(' + pat + r'):', out["full_content"])
    sections = {}
    i = 1
    while i + 1 < len(parts):
        sections[parts[i].strip()] = parts[i + 1].strip().rstrip(",")
        i += 2
    out["sections"] = sections
    out["shell"] = sections.get("Shell", "")
    return out


def extract_content_codes(content_report_df: pd.DataFrame) -> Dict[str, dict]:
    if content_report_df is None or content_report_df.empty:
        return {}
    df = content_report_df.copy()
    cols = {str(c).lower(): c for c in df.columns}
    num_col = cols.get('color way number') or cols.get('colorway number') or None
    result = {}
    current_parsed = None
    for col in df.columns:
        col_str = str(col).strip()
        if "CONTENT CODE" in col_str.upper() and len(col_str) > 15:
            p = _parse_content_header(col_str)
            if p["content_code"]:
                current_parsed = p
            break
    for _, row in df.iterrows():
        for cell in row:
            cell_str = str(cell).strip()
            if "CONTENT CODE" in cell_str.upper() and len(cell_str) > 15:
                p = _parse_content_header(cell_str)
                if p["content_code"]:
                    current_parsed = p
                break
        if current_parsed is None:
            continue
        colorway_key = None
        if num_col:
            v = str(row.get(num_col, "")).strip()
            if re.match(r"^\d{3}$", v):
                colorway_key = v
        if not colorway_key:
            for cell in row:
                if re.match(r"^\d{3}$", str(cell).strip()):
                    colorway_key = str(cell).strip()
                    break
        if colorway_key:
            result[colorway_key] = {
                "content_code": current_parsed["content_code"],
                "shell":        current_parsed["shell"],
                "full_content": current_parsed["full_content"],
                "sections":     current_parsed["sections"],
            }
    return result


def extract_care_codes(care_report_df: pd.DataFrame) -> Dict[str, dict]:
    if care_report_df is None or care_report_df.empty:
        return {}
    df = care_report_df.copy()
    cols = {str(c).lower(): c for c in df.columns}
    num_col  = cols.get('color way number') or cols.get('colorway number') or None
    name_col = cols.get('color way name')   or cols.get('colorway name')   or None
    code_col = cols.get('care code')        or cols.get('code')            or None
    eng_col = None
    for c in df.columns:
        if 'english' in c.lower() and 'instruction' in c.lower():
            eng_col = c
            break
    if not eng_col:
        for c in df.columns:
            if 'instruction' in c.lower():
                eng_col = c
                break
    header_care_code = ""
    header_english = ""
    for col in df.columns:
        col_str = str(col)
        if "Care Code" in col_str:
            m = re.search(r'Care Code[:\s]+(\S+)', col_str, re.IGNORECASE)
            if m:
                header_care_code = m.group(1).strip()
            instr_col = df.columns[1] if len(df.columns) > 1 else None
            for _, row in df.iterrows():
                lang = str(row.iloc[0]).strip().lower()
                if lang == "english" and instr_col:
                    header_english = str(row.get(instr_col, "")).strip()
                    break
            break
    result = {}
    for _, row in df.iterrows():
        key = str(row.get(num_col) or row.get(name_col) or "").strip()
        if not key or not re.match(r"^\d{3}$", key):
            continue
        result[key] = {
            "care_code":            str(row.get(code_col, "")).strip() if code_col else header_care_code,
            "english_instructions": str(row.get(eng_col,  "")).strip() if eng_col  else header_english,
        }
        if not result[key]["care_code"]:
            result[key]["care_code"] = header_care_code
        if not result[key]["english_instructions"]:
            result[key]["english_instructions"] = header_english
    if not result and header_care_code:
        for _, row in df.iterrows():
            for cell in row:
                if re.match(r"^\d{3}$", str(cell).strip()):
                    result[str(cell).strip()] = {
                        "care_code": header_care_code,
                        "english_instructions": header_english,
                    }
    return result
