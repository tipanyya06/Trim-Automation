from typing import Optional, List, Dict
import re
import pandas as pd

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

# Common filler words to ignore when matching colorway names
_STOP_WORDS = {
    "col", "color", "colour", "the", "and", "with", "of", "a", "an",
    "black", "white", "grey", "gray",  # kept separately - these ARE color words
}
_NOISE_WORDS = {"col", "color", "colour", "the", "and", "with", "of", "a", "an"}


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
    """Extract leading numeric portion: 'COL-464 COLLEGIATE NAVY' -> '464', '009-Black' -> '009'."""
    value = value.strip()
    m = re.match(r'^[A-Za-z]+-(\d+)', value)
    if m:
        return m.group(1)
    m = re.match(r'^(\d+)', value)
    if m:
        return m.group(1)
    return ""


def _color_words(value: str) -> List[str]:
    """
    Extract meaningful color words from a colorway string.
    'COL-013 BLACK, BLACK' -> ['black']
    '009-Black' -> ['black']
    'COL-053 Graphite, Tradewinds C Sea' -> ['graphite', 'tradewinds', 'sea']
    """
    v = value.strip().lower()
    # Remove leading prefix like "col-013" or "013-"
    v = re.sub(r'^[a-z]+-\d+\s*', '', v)
    v = re.sub(r'^\d+-\s*', '', v)
    # Split on spaces, commas, slashes, hyphens
    tokens = re.split(r'[\s,/\-]+', v)
    # Filter noise and short tokens
    return [t for t in tokens if len(t) >= 3 and t not in _NOISE_WORDS]


def normalize_colorway(
    color_option_value: str,
    available_colorways: Optional[List[str]] = None
) -> Optional[str]:
    """
    Map any colorway input (from Excel) to a BOM canonical colorway key.

    The Excel may use a completely different numbering system (e.g. COL-013)
    from the BOM (e.g. 009-Black). We resolve by:
    1. Exact match
    2. Case-insensitive exact
    3. Numeric prefix match (same number system)
    4. Color-word overlap score (primary fallback when numbers differ)
    5. Substring of color name
    6. Any shared word
    """
    if not color_option_value or not available_colorways:
        return None

    val = str(color_option_value).strip()
    val_lower = val.lower()

    # Guard: reject clearly invalid inputs
    if val_lower in ("n/a", "nan", "none", "null", ""):
        return None
    if len(val.strip()) < 2:
        return None

    # 1. Exact
    if val in available_colorways:
        return val

    # 2. Case-insensitive exact
    for cw in available_colorways:
        if cw.lower() == val_lower:
            return cw

    # 3. Numeric prefix match (only works if same numbering system)
    input_num = _extract_numeric_prefix(val)
    if input_num:
        for cw in available_colorways:
            bom_num = _extract_numeric_prefix(cw)
            if bom_num and input_num == bom_num:
                return cw

    # 4. Color-word overlap scoring — most important when number systems differ
    input_words = set(_color_words(val))
    if input_words:
        scored = []
        for cw in available_colorways:
            cw_words = set(_color_words(cw))
            if not cw_words:
                continue
            overlap = input_words & cw_words
            # Score: number of overlapping words, normalized by BOM colorway word count
            # to avoid matching a very generic word against a very specific colorway
            score = len(overlap) / max(len(cw_words), 1)
            if overlap:
                scored.append((score, len(overlap), cw))
        if scored:
            scored.sort(reverse=True)
            best_score, best_count, best_cw = scored[0]
            # Require at least 1 overlapping word AND score > 0
            if best_count >= 1 and best_score > 0:
                return best_cw

    # 5. Substring match on color name part
    for cw in available_colorways:
        color_name = cw.split("-", 1)[1].lower() if "-" in cw else cw.lower()
        if val_lower in color_name or color_name in val_lower:
            return cw

    # 6. Any shared raw word (broad fallback)
    val_raw_words = set(w for w in re.split(r'[\s,/\-]+', val_lower) if len(w) >= 3)
    for cw in available_colorways:
        cw_raw = set(w for w in re.split(r'[\s,/\-]+', cw.lower()) if len(w) >= 3)
        if val_raw_words & cw_raw:
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