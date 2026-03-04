import re
from typing import Dict
import pandas as pd


# ── Fabric section labels used to split composition text ──────────────────────
# BUG 3 FIX: Added 'Fleece Lining' so that "Lining: 100% Polyester  Fleece Lining: 100%..."
# is split correctly into two separate sections instead of "Lining" swallowing the rest.
# Order does NOT matter here because sorted(key=len, reverse=True) is applied below.
_FABRIC_SECTIONS = [
    "Exclusive of Trimming", "Fleece Lining", "Faux Fur", "Insulation", "Lining",
    "Fill", "Face", "Body", "Trim", "Outer", "Inner", "Shell",
]

# Output order for the multi-line TP FC string
_LABEL_ORDER = [
    "Shell", "Faux Fur", "Lining", "Fleece Lining",
    "Insulation", "Fill", "Face", "Body", "Trim", "Outer", "Inner",
]

# ── Known fiber names for normalisation (Bug 6) ───────────────────────────────
_FIBER_NAMES = [
    "Acrylic", "Polyester", "Nylon", "Wool", "Cotton", "Elastane",
    "Modacrylic", "Spandex", "Viscose", "Rayon", "Linen", "Silk",
    "Cashmere", "Alpaca", "Recycled", "Other Fibers",
]
_FIBER_RE = re.compile(
    r'\b(' + '|'.join(re.escape(f) for f in _FIBER_NAMES) + r')\b',
    re.IGNORECASE,
)


def _normalize_fiber_text(text: str) -> str:
    """
    BUG 6 FIX - two issues transcribed directly from PDF text:
      1. Lowercase fiber names  e.g. "nylon"  ->  "Nylon"
      2. Stray space before comma  e.g. " ,"  ->  ","
    """
    if not text:
        return text
    text = re.sub(r'\s+,', ',', text)
    text = _FIBER_RE.sub(lambda m: m.group(0).title(), text)
    return text.strip()


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

    # BUG 3 FIX + BUG 6 FIX:
    # Previously: out["shell"] = sections.get("Shell", "")
    # That discarded Lining, Fleece Lining, Faux Fur etc from the TP FC output.
    # Now: build a newline-joined string of ALL composition layers in order,
    # with fiber names normalised (Bug 6 - lowercase nylon, stray space-comma).
    # Single-layer BOMs produce the same result as before.
    layer_parts = []
    for label in _LABEL_ORDER:
        if label in sections and sections[label].strip():
            val = _normalize_fiber_text(sections[label].strip())
            layer_parts.append(f"{label}: {val}")
    out["shell"] = "\n".join(layer_parts) if layer_parts else sections.get("Shell", "")

    return out


def _build_shell_from_content_full(content_full: str) -> str:
    """
    Build a multi-layer shell string from a 'Content Full' cell that may contain
    embedded composition label strings like:
      'Shell: 100% Acrylic Exclusive of Trimming  Lining: 100% Polyester'
    or from a plain composition string like:
      '100% Acrylic Exclusive of Trimming'

    This mirrors the logic in _parse_content_header but accepts an already-extracted
    full_content string (i.e. the text AFTER the "CONTENT CODE: XXX" prefix).
    """
    if not content_full:
        return ""

    # Check whether any fabric section labels appear embedded in the string
    # (they are injected by _parse_content_report_tables as "Label: value" tokens)
    pat = '|'.join(re.escape(s) for s in sorted(_FABRIC_SECTIONS, key=len, reverse=True))
    parts = re.split(r'\b(' + pat + r'):', content_full)

    if len(parts) > 1:
        # Multi-section: reassemble in canonical label order
        sections = {}
        i = 1
        while i + 1 < len(parts):
            sections[parts[i].strip()] = parts[i + 1].strip().rstrip(",").strip()
            i += 2
        layer_parts = []
        for label in _LABEL_ORDER:
            if label in sections and sections[label].strip():
                val = _normalize_fiber_text(sections[label].strip())
                layer_parts.append(f"{label}: {val}")
        return "\n".join(layer_parts) if layer_parts else content_full.strip()
    else:
        # No section labels found — treat whole string as shell composition
        return _normalize_fiber_text(content_full.strip())


def extract_content_codes(content_report_df: pd.DataFrame) -> Dict[str, dict]:
    """
    Build a colorway-number → {content_code, shell, full_content, sections} mapping
    from the content_report DataFrame.

    The DataFrame may arrive in two formats:

    FORMAT A — RAW (pre-parsed):
        Cells and/or column headers contain strings like
        "CONTENT CODE: BWO  80% Acrylic Exclusive of Trimming"
        and data rows contain 3-digit colorway numbers.
        This was the only format handled by the original code.

    FORMAT B — PARSED (output of bom_parser._parse_content_report_tables):
        Clean columnar data with columns:
          "Color Way Number", "Color Way Name", "Content Code", "Content Full"
        Each row is one (colorway ↔ content_code) pair, already correctly
        assigned by the multi-section-aware parser.

    BUG FIX (TP FC / Content Code wrong per colorway):
        The original code only handled Format A.  After bom_parser was updated to
        call _parse_content_report_tables (which emits Format B), extract_content_codes
        received Format B but couldn't read it.  It returned an empty dict, so
        get_content() in filler.py always fell back to __default__ (the first
        section) and every colorway got the same wrong content code.

        Fix: detect Format B by the presence of a "Content Code" column and build
        the result dict directly from its rows, preserving the per-colorway mapping
        that _parse_content_report_tables correctly computed.
    """
    if content_report_df is None or content_report_df.empty:
        return {}

    df = content_report_df.copy()
    cols_lower = {str(c).strip().lower(): c for c in df.columns}

    # ── FORMAT B DETECTION ────────────────────────────────────────────────────
    # If the DataFrame has explicit "Content Code" and "Color Way Number" columns
    # (i.e. it came from _parse_content_report_tables), read it directly.
    _cc_col  = cols_lower.get("content code")
    _cw_col  = (cols_lower.get("color way number")
                or cols_lower.get("colorway number"))
    _cf_col  = cols_lower.get("content full")

    if _cc_col is not None and _cw_col is not None:
        result: Dict[str, dict] = {}
        for _, row in df.iterrows():
            cw_num = str(row.get(_cw_col, "")).strip()
            if not re.match(r'^\d{3}$', cw_num):
                continue

            content_code = str(row.get(_cc_col, "")).strip()
            if not content_code or content_code.lower() in ("nan", "none", ""):
                continue

            content_full = str(row.get(_cf_col, "")).strip() if _cf_col else ""

            # Derive the shell / TP FC string from Content Full.
            # Content Full may be:
            #   (a) "CONTENT CODE: BWO  Shell: 100% Acrylic Exclusive of Trimming"
            #   (b) "Shell: 100% Acrylic Exclusive of Trimming  Lining: 100% Polyester"
            #   (c) "100% Acrylic Exclusive of Trimming"
            # Strip any leading "CONTENT CODE: XXX" prefix first.
            cleaned_full = re.sub(
                r'^CONTENT\s+CODE[:\s]+\w+\s*', '', content_full, flags=re.IGNORECASE
            ).strip()
            shell = _build_shell_from_content_full(cleaned_full)

            # If shell is still empty, fall back to trying to parse sections from
            # the full content_full string (handles case (a) above).
            if not shell and content_full:
                parsed = _parse_content_header(f"CONTENT CODE: {content_code} {content_full}")
                shell = parsed.get("shell", "")

            result[cw_num] = {
                "content_code": content_code,
                "shell":        shell,
                "full_content": content_full,
                "sections":     {},
            }

        # Set __default__ only when every colorway maps to the same single code
        # (single-section BOM), so filler.py's fallback chain still works for
        # styles where the colorway number isn't explicitly listed.
        unique_codes = {v["content_code"] for v in result.values()}
        if len(unique_codes) == 1 and result:
            only = next(iter(result.values()))
            result["__default__"] = only

        return result

    # ── FORMAT A — original raw-cell scanning logic ───────────────────────────
    num_col = cols_lower.get('color way number') or cols_lower.get('colorway number') or None

    result: Dict[str, dict] = {}
    current_parsed = None

    # Check column headers first
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


def extract_care_codes(care_report_df: pd.DataFrame, content_report_df: pd.DataFrame = None) -> Dict[str, dict]:
    # If care_report is missing/empty, fall back to content_report
    if care_report_df is None or care_report_df.empty:
        if content_report_df is not None and not content_report_df.empty:
            care_report_df = content_report_df
        else:
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