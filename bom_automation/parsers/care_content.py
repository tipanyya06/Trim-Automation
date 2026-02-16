from typing import Dict
import pandas as pd

# Fallbacks from spec
KNOWN_CONTENT_CODES = {
    "010": "R8T",
    "224": "R8T",
    "278": "R8U",
    "429": "R8U",
    "551": "SRH",
}
KNOWN_CARE_CODE = "3000"


def extract_content_codes(content_report_df: pd.DataFrame) -> Dict[str, dict]:
    """Return mapping per colorway number or full name → content details."""
    result: Dict[str, dict] = {}
    if content_report_df is None or content_report_df.empty:
        # build from fallbacks only
        for num, code in KNOWN_CONTENT_CODES.items():
            result[num] = {"content_code": code}
        return result

    df = content_report_df.copy()
    # Try to locate columns
    cols = {c.lower(): c for c in df.columns}
    num_col = cols.get('color way number') or cols.get('colorway number') or None
    name_col = cols.get('color way name') or cols.get('colorway name') or None
    code_col = cols.get('content code') or cols.get('code') or None

    for _, row in df.iterrows():
        key = str(row.get(num_col) or row.get(name_col) or '').strip()
        if not key:
            continue
        result[key] = {
            "content_code": str(row.get(code_col, '')).strip()
        }

    # Ensure fallbacks present at least by number keys
    for num, code in KNOWN_CONTENT_CODES.items():
        result.setdefault(num, {"content_code": code})
    return result


def extract_care_codes(care_report_df: pd.DataFrame) -> Dict[str, dict]:
    """Return mapping per colorway number or name → care code and english instructions."""
    result: Dict[str, dict] = {}
    if care_report_df is None or care_report_df.empty:
        for num in ["010", "224", "278", "429", "551"]:
            result[num] = {
                "care_code": KNOWN_CARE_CODE,
                "english_instructions": "Hand Wash Cold, Do Not Bleach, Dry Flat, Do Not Wring or Twist, Reshape, Do Not Iron, Drycleanable",
            }
        return result

    df = care_report_df.copy()
    cols = {c.lower(): c for c in df.columns}
    num_col = cols.get('color way number') or cols.get('colorway number') or None
    name_col = cols.get('color way name') or cols.get('colorway name') or None
    code_col = cols.get('care code') or cols.get('code') or None

    # find english instructions column heuristically
    eng_col = None
    for c in df.columns:
        if 'english' in c.lower() and 'instruction' in c.lower():
            eng_col = c
            break
    if eng_col is None:
        # fallback to a column named 'Care Instructions' or similar
        for c in df.columns:
            if 'instruction' in c.lower():
                eng_col = c
                break

    for _, row in df.iterrows():
        key = str(row.get(num_col) or row.get(name_col) or '').strip()
        if not key:
            continue
        result[key] = {
            "care_code": str(row.get(code_col, KNOWN_CARE_CODE)).strip() or KNOWN_CARE_CODE,
            "english_instructions": str(row.get(eng_col, '')).strip(),
        }

    # Ensure fallbacks by number keys
    for num in ["010", "224", "278", "429", "551"]:
        result.setdefault(num, {
            "care_code": KNOWN_CARE_CODE,
            "english_instructions": "Hand Wash Cold, Do Not Bleach, Dry Flat, Do Not Wring or Twist, Reshape, Do Not Iron, Drycleanable",
        })
    return result
