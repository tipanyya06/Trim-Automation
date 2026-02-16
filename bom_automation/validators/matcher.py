from typing import Optional, List

KNOWN_COLORWAYS = {
    "010": {"name": "Black",          "full": "010-Black"},
    "224": {"name": "Camel Brown",    "full": "224-Camel Brown"},
    "278": {"name": "Dark Stone",     "full": "278-Dark Stone"},
    "429": {"name": "Everblue",       "full": "429-Everblue"},
    "551": {"name": "Lavender Pearl", "full": "551-Lavender Pearl"},
}

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


def normalize_colorway(color_option_value: str, available_colorways: Optional[List[str]] = None) -> Optional[str]:
    """
    Map any colorway input format to the full canonical name e.g. '010-Black'.
    Falls back to KNOWN_COLORWAYS if available_colorways not provided.
    """
    if not color_option_value:
        return None

    if available_colorways is None:
        available_colorways = [v["full"] for v in KNOWN_COLORWAYS.values()]

    val = str(color_option_value).strip()

    # 1. Exact match
    if val in available_colorways:
        return val

    val_lower = val.lower()

    # 2. Case-insensitive exact match
    for cw in available_colorways:
        if cw.lower() == val_lower:
            return cw

    # 3. Starts with known number prefix (e.g. "010", "010-Black")
    for cw in available_colorways:
        prefix = cw.split("-")[0]
        if val_lower.startswith(prefix):
            return cw

    # 4. Substring match on color name part (after the dash)
    for cw in available_colorways:
        color_name = cw.split("-", 1)[1].lower() if "-" in cw else cw.lower()
        if val_lower in color_name or color_name in val_lower:
            return cw

    # 5. Partial word match (fuzzy fallback)
    val_words = set(val_lower.split())
    for cw in available_colorways:
        cw_words = set(cw.lower().replace("-", " ").split())
        if val_words & cw_words:
            return cw

    return None


def normalize_component(component_name: str) -> str:
    """
    Map incoming component name variations to canonical Color BOM component names.
    Returns the canonical name, or the original if no match found.
    """
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
