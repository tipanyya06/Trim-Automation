from typing import Optional, List, Dict
import re
import pandas as pd

# No hardcoded colorways - all resolved dynamically from BOM PDF
COMPONENT_ALIASES = {
    "Label 1":              ["main label", "label1", "label 1", "care label"],
    "Label Logo 1":         ["logo label", "label logo", "logo 1", "additional main label"],
    "Shell 1":              ["shell", "main shell", "shell1", "shell 1"],
    "Shell 2":              ["faux fur", "fur shell", "shell 2", "shell2"],
    "Insulation 1":         ["insulation", "fill", "pompom", "pom pom"],
    "Hangtag Package Part": ["hangtag", "hang tag", "ht"],
    "Packaging 1":          ["swing hook", "dh-blm", "packaging 1"],
    "Packaging 2":          ["polybag", "poly bag", "packaging 2"],
    "Packaging 3":          ["upc sticker", "upc bag sticker", "packaging 3"],
    "Packaging 4":          ["outer carton", "carton", "packaging 4"],
}


def auto_detect_columns(df: pd.DataFrame) -> Optional[Dict[str, str]]:
    cols_lower = {c.lower(): c for c in df.columns}
    style_col = None
    for pattern in ["style", "buyer style", "item", "sku", "product code", "article"]:
        for lower_col, original_col in cols_lower.items():
            if pattern in lower_col:
                style_col = original_col
                break
        if style_col:
            break
    color_col = None
    for pattern in ["color", "option", "colorway", "variant", "shade"]:
        for lower_col, original_col in cols_lower.items():
            if pattern in lower_col and "description" not in lower_col:
                color_col = original_col
                break
        if color_col:
            break
    if style_col and color_col:
        return {"style_col": style_col, "color_col": color_col, "confidence": 0.9}
    elif style_col or color_col:
        return {"style_col": style_col, "color_col": color_col, "confidence": 0.5}
    return None


def _extract_numeric_prefix(value: str) -> str:
    """Extract leading numeric portion from colorway strings like 'COL-464', '464-Black', '464 Black'."""
    value = value.strip()
    # Handle "COL-464 COLLEGIATE NAVY" → "464"
    m = re.match(r'^[A-Za-z]+-(\d+)', value)
    if m:
        return m.group(1)
    # Handle "464-Black" or "464 Black" → "464"
    m = re.match(r'^(\d+)', value)
    if m:
        return m.group(1)
    return ""


def _extract_color_words(value: str) -> List[str]:
    """Extract significant color words, stripping prefixes like 'COL-464'."""
    value = value.strip().lower()
    # Remove leading prefix like "col-464" or "464-"
    value = re.sub(r'^[a-z]+-\d+\s*', '', value)
    value = re.sub(r'^\d+-\s*', '', value)
    # Return remaining words
    return [w for w in re.split(r'[\s\-_/]+', value) if len(w) > 1]


def normalize_colorway(color_option_value: str, available_colorways: Optional[List[str]] = None) -> Optional[str]:
    """Map any colorway input to the full canonical name from BOM.
    
    Handles formats like:
    - 'COL-464 COLLEGIATE NAVY'  → matches '464-Collegiate Navy'
    - '464-Black'                → matches '464-Black'
    - 'CRUSHED BLUE'             → matches by color name
    - '010'                      → matches '010-Black'
    """
    if not color_option_value or not available_colorways:
        return None
    val = str(color_option_value).strip()
    val_lower = val.lower()

    # 1. Exact match
    if val in available_colorways:
        return val

    # 2. Case-insensitive exact
    for cw in available_colorways:
        if cw.lower() == val_lower:
            return cw

    # 3. Extract numeric prefix from input and match against BOM numeric prefixes
    input_num = _extract_numeric_prefix(val)
    if input_num:
        for cw in available_colorways:
            bom_num = _extract_numeric_prefix(cw)
            if bom_num and input_num == bom_num:
                return cw

    # 4. Input starts with BOM prefix (e.g. "010" matches "010-Black")
    for cw in available_colorways:
        prefix = cw.split("-")[0].strip()
        if val_lower.startswith(prefix.lower()):
            return cw

    # 5. Color word overlap — extract significant words and compare
    input_words = set(_extract_color_words(val))
    if input_words:
        best_match = None
        best_score = 0
        for cw in available_colorways:
            cw_words = set(_extract_color_words(cw))
            overlap = len(input_words & cw_words)
            if overlap > best_score:
                best_score = overlap
                best_match = cw
        if best_score >= 1 and best_match:
            return best_match

    # 6. Substring match on the full color name part after prefix
    for cw in available_colorways:
        color_name = cw.split("-", 1)[1].lower() if "-" in cw else cw.lower()
        if val_lower in color_name or color_name in val_lower:
            return cw

    # 7. Partial word match (fallback)
    val_words = set(val_lower.split())
    for cw in available_colorways:
        cw_words = set(cw.lower().replace("-", " ").split())
        if val_words & cw_words:
            return cw

    return None


def normalize_component(component_name: str) -> str:
    if not component_name:
        return component_name
    needle = component_name.strip().lower()
    for canonical, aliases in COMPONENT_ALIASES.items():
        if needle == canonical.lower():
            return canonical
        for alias in aliases:
            if needle == alias or alias in needle or needle in alias:
                return canonical
    return component_name


def extract_material_code(text: str) -> str:
    if not text:
        return ""
    matches = re.findall(r'\b(\d{3,6})\b', str(text))
    return matches[0] if matches else ""


def extract_id_only(value: str) -> str:
    if not value or value == "N/A":
        return value
    text = str(value).strip()
    if not text:
        return "N/A"
    first_token = text.split()[0] if text.split() else text
    return first_token.rstrip('.,;:-()')