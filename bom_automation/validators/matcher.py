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

_NOISE_WORDS = {"col", "color", "colour", "the", "and", "with", "of", "a", "an"}


def get_product_type(material_name: str) -> str:
    """Change 6: Determine product type from Material Name. Returns 'glove', 'beanie', or 'standard'."""
    if not material_name:
        return "standard"
    ml = str(material_name).lower()
    if "glove" in ml or "gloves" in ml or "mitt" in ml:
        return "glove"
    if "beanie" in ml or "knit hat" in ml or "toque" in ml:
        return "beanie"
    return "standard"


def auto_detect_columns(df: pd.DataFrame) -> Optional[Dict]:
    """
    Change 5: Auto-detect style, color, and material name columns.
    Supports new template (JDE Style / Color) and old template (Buyer Style Number / Color/Option).
    Also detects Material Name for product type inference.
    """
    cols_lower = {c.lower().strip(): c for c in df.columns}

    # Style: new template (JDE Style) first, then old fallback
    style_col = None
    for pattern in ["jde style", "jde"]:
        for lc, oc in cols_lower.items():
            if lc == pattern or lc.startswith(pattern):
                style_col = oc
                break
        if style_col:
            break
    if not style_col:
        for pattern in ["buyer style", "style number", "style", "item", "sku", "product code", "article"]:
            for lc, oc in cols_lower.items():
                if pattern in lc:
                    style_col = oc
                    break
            if style_col:
                break

    # Color: new template (exact "color"/"colour") first, then old fallback
    color_col = None
    for lc, oc in cols_lower.items():
        if lc in ("color", "colour"):
            color_col = oc
            break
    if not color_col:
        for pattern in ["color/option", "colour/option", "option", "colorway", "variant", "shade", "color", "colour"]:
            for lc, oc in cols_lower.items():
                if pattern in lc and "description" not in lc:
                    color_col = oc
                    break
            if color_col:
                break

    # Material Name column (for glove/beanie detection, Change 6)
    material_col = None
    for pattern in ["material name", "material", "description", "product name", "style name"]:
        for lc, oc in cols_lower.items():
            if pattern in lc:
                material_col = oc
                break
        if material_col:
            break

    confidence = 0.9 if (style_col and color_col) else (0.5 if (style_col or color_col) else 0.0)

    return {
        "style_col":    style_col,
        "color_col":    color_col,
        "material_col": material_col,
        "confidence":   confidence,
    }


def _extract_numeric_prefix(value: str) -> str:
    value = value.strip()
    m = re.match(r'^[A-Za-z]+-(\d+)', value)
    if m:
        return m.group(1)
    m = re.match(r'^(\d+)', value)
    if m:
        return m.group(1)
    return ""


def _color_words(value: str) -> List[str]:
    v = value.strip().lower()
    v = re.sub(r'^[a-z]+-\d+\s*', '', v)
    v = re.sub(r'^\d+-\s*', '', v)
    tokens = re.split(r'[\s,/\-]+', v)
    return [t for t in tokens if len(t) >= 3 and t not in _NOISE_WORDS]


def normalize_colorway(
    color_option_value: str,
    available_colorways: Optional[List[str]] = None
) -> Optional[str]:
    if not color_option_value or not available_colorways:
        return None

    val = str(color_option_value).strip()
    val_lower = val.lower()

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
    # 3. Numeric prefix match
    input_num = _extract_numeric_prefix(val)
    if input_num:
        for cw in available_colorways:
            bom_num = _extract_numeric_prefix(cw)
            if bom_num and input_num == bom_num:
                return cw
    # 4. Color-word overlap scoring
    input_words = set(_color_words(val))
    if input_words:
        scored = []
        for cw in available_colorways:
            cw_words = set(_color_words(cw))
            if not cw_words:
                continue
            overlap = input_words & cw_words
            score = len(overlap) / max(len(cw_words), 1)
            if overlap:
                scored.append((score, len(overlap), cw))
        if scored:
            scored.sort(reverse=True)
            best_score, best_count, best_cw = scored[0]
            if best_count >= 1 and best_score > 0:
                return best_cw
    # 5. Substring match
    for cw in available_colorways:
        color_name = cw.split("-", 1)[1].lower() if "-" in cw else cw.lower()
        if val_lower in color_name or color_name in val_lower:
            return cw
    # 6. Any shared raw word
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