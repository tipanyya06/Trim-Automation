"""
parsers/detail_sketch.py
========================
Parse Detail Sketch pages from a Columbia BOM PDF.

Handles two formats:
  - Format 1 (C/O):  "NNN Name C/O  A - COLOR"  (e.g. component 125802)
  - Format 2 (non-C/O): Two side-by-side colorway columns; A/B rows are
    garbled by pdfplumber because both columns' text overlaps in the same
    x-coordinate space.  This module uses coordinate-based word extraction
    + fuzzy un-garbling to recover the correct thread color names.

Public API
----------
  parse_detail_sketch_pages(pdf_path) -> dict
      Returns {comp_code: {cw_num: "Color1, Color2, ..."}}

  get_sketch_color(sketch_data, comp_code, matched_cw) -> str | None
      Look up a colorway's colors from the parsed sketch_data dict.
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import get_close_matches
from typing import Dict, Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore


# ---------------------------------------------------------------------------
# Known Columbia color vocabulary – used for fuzzy un-garbling
# ---------------------------------------------------------------------------
_COLUMBIA_COLOR_VOCAB: list[str] = [
    "BLACK", "WHITE", "DARK STONE", "CITY GREY", "COLUMBIA GREY",
    "SEA SALT", "DELTA", "CAMEL BROWN", "BEACH", "SEDONA SAGE",
    "SAFARI", "NIAGARA", "TEA LIGHT", "GRILL", "GREY GREEN",
    "COLLEGIATE NAVY", "PHOENIX BLUE", "FATHOM BLUE", "SHARK",
    "RED OXIDE", "FLINT GREY", "TEAK BROWN", "MINERAL PINK",
    "ANTIQUE MAUVE", "NOCTURNAL", "DARK NOCTURNAL", "SUPER SONIC",
    "TOBACCO", "RAINY DAY", "IRON", "CHALK", "COLUMBIA BLUE",
    "BRIGHT MARIGOLD", "VAPOR", "GUMDROP", "PEACH BLOSSOM",
    "TRADEWINDS", "ATMOSPHERE", "SILVER RIDGE", "FOSSIL", "DARK FOSSIL",
    "GRAPHITE", "CHARCOAL", "NOCTURNAL MARLED", "RED OXIDE MARLED",
]

# Words that indicate noise / boilerplate lines to skip entirely
_SKIP_WORDS: frozenset[str] = frozenset({
    "100%", "SIZE", "PLACEMENT", "Single", "stitch", "attachment",
    "matches", "ground", "color", "Centered", "Horizontal",
    "Vertical", "CF", "&", "This", "confidential", "Dec", "Page", "on",
    "of", "at",
})

_SKIP_SUBSTRINGS: tuple[str, ...] = (
    "confidential", "proprietary", "Columbia.", "Columbia's",
    "intellectual property", "trademarks", "Sportswear",
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_noise_word(text: str) -> bool:
    return (
        text in _SKIP_WORDS
        or any(s in text for s in _SKIP_SUBSTRINGS)
        or bool(re.match(r'^Dec\s', text))
        or bool(re.match(r'^Page\s', text))
    )


def _clean_garbled_color(phrase: str, known_colors: list[str]) -> str:
    """
    Strip letter-indicator prefixes and lowercase-x noise, then fuzzy-match
    to the nearest known Columbia color name.

    The garbling pattern on Format-2 pages looks like:
      "A A- B - LxAxxCK"  →  "BLACK"
      "SEAD O- NxxAx SAGE"  →  "SEDONA SAGE"
      "COLLBE -G xIxAxTE NAVY"  →  "COLLEGIATE NAVY"
    """
    if not phrase:
        return ""

    # Remove leading letter-indicator patterns
    phrase = re.sub(r"^[A-E]\s+[A-E]-?\s+[A-E]?\s*-?\s*", "", phrase.strip())
    phrase = re.sub(r"^[A-E]\s*-\s*", "", phrase.strip())
    phrase = re.sub(r"^[A-Z]\s*-\s*", "", phrase.strip())  # single-letter noise prefix

    # Remove all lowercase 'x' characters (PDF rendering noise)
    cleaned = re.sub(r"x", "", phrase)

    # Normalise internal dashes/spaces
    cleaned = re.sub(r"\s*-\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned or len(cleaned) < 2:
        return ""

    candidates = get_close_matches(cleaned.upper(), known_colors, n=1, cutoff=0.4)
    return candidates[0] if candidates else cleaned.upper()


def _collect_vocab_from_words(words: list) -> list[str]:
    """
    Extend the known-color vocabulary with uppercase tokens found on the page
    (C/D/E rows are clean and add real color words).
    """
    extra: list[str] = []
    for w in words:
        t = w["text"]
        if re.match(r"^[A-Z][A-Z]{2,}$", t) and t not in {"C/O", "SMU", "LO", "FIT", "PDF"}:
            extra.append(t)
    return _COLUMBIA_COLOR_VOCAB + extra


# ---------------------------------------------------------------------------
# Format 1: C/O style (e.g. page with component 125802)
# ---------------------------------------------------------------------------

def _parse_co_format(text: str, comp_code: str) -> dict:
    """
    Parse a Detail Sketch page where colorways are labelled with 'C/O'.

    Example line:
      "016 Black C/O A - DARK STONE   026 City Grey C/O A - SEA SALT"
    Subsequent lines:
      "B - CITY GREY   B - DARK STONE"
      "C - BLACK       C - COLUMBIA GREY"
    """
    result: dict[str, str] = {}

    m = re.search(r"\b" + re.escape(comp_code) + r"\s*:[^\n]*\n", text)
    if not m:
        return result
    content = text[m.end():]

    current_cws: list[str] = []
    cw_colors: dict[str, list[str]] = defaultdict(list)

    skip_phrases = (
        "100% SIZE", "Single stitch", "matches ground",
        "Centered Horizontal", "& Vertical", "This is confidential",
        "Dec ", "Page ",
    )

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(sp in line for sp in skip_phrases):
            continue

        # Colorway header: "NNN Name C/O ..."
        cw_matches = list(re.finditer(r"(\d{3})\s+[\w][^0-9]+?C/O", line))
        if cw_matches:
            current_cws = [h.group(1) for h in cw_matches]
            # Extract A colors embedded in the header line
            a_colors = re.findall(
                r"C/O\s+A\s*-\s*([A-Z][A-Z ]+?)(?=\s+\d{3}|\s*$)", line
            )
            for i, ac in enumerate(a_colors):
                if i < len(current_cws):
                    cw_colors[current_cws[i]].append(ac.strip())
            continue

        if current_cws:
            # Letter-color rows: "B - CITY GREY   B - DARK STONE"
            color_pairs = list(
                re.finditer(
                    r"([A-E])\s*-\s*([A-Z][A-Z ]+?)(?=\s+[A-E]\s*-\s*|\s*$)", line
                )
            )
            for i, cp in enumerate(color_pairs):
                if i < len(current_cws):
                    cw_colors[current_cws[i]].append(cp.group(2).strip())

    for cw, colors in cw_colors.items():
        if colors:
            result[cw] = ", ".join(c.title() for c in colors)

    return result


# ---------------------------------------------------------------------------
# Format 2: Non-C/O multi-column (e.g. pages with 135956, 135957)
# ---------------------------------------------------------------------------

def _parse_multicolumn_format(page, comp_code: str) -> dict:
    """
    Parse a Detail Sketch page where colorways are arranged in two side-by-side
    columns and there is no 'C/O' marker.

    pdfplumber's text-level extraction garbles the A/B rows because the two
    columns share overlapping x-coordinates.  This function uses word-level
    extraction with coordinate-based column splitting and fuzzy un-garbling.

    Column structure (observed in CU0214 F26 BOM):
      Left-column CW headers:  x ≈ 28
      Right-column CW headers: x ≈ 298
      Left-column color rows:  x ≈ 207–265
      Right-column color rows: x ≈ 477–557
      Column split for HEADERS: x < 180  vs  x ≥ 180
      Column split for COLORS:  x < 380  vs  x ≥ 380
    """
    result: dict[str, str] = {}

    words = page.extract_words(x_tolerance=5, y_tolerance=3)

    # Locate the component-code header line
    comp_y: Optional[float] = None
    for w in words:
        if w["text"].startswith(comp_code):
            comp_y = w["top"]
            break
    if comp_y is None:
        return result

    # Filter to content words
    content_words = [
        w for w in words
        if w["top"] > comp_y + 5
        and w["top"] < 860
        and not _is_noise_word(w["text"])
        and not re.match(r"^\d{4,}$", w["text"])  # skip long numeric codes
    ]

    known_colors = _collect_vocab_from_words(content_words)

    # Group words into rows using a tight y-tolerance (2 pt) so that the
    # colorway-header row (top≈199) and the A-color row (top≈202) are kept
    # separate even though pdfplumber groups them at the same word-level top.
    Y_TOL = 2
    rows: dict[float, list] = defaultdict(list)
    for w in content_words:
        y_key = round(w["top"] / Y_TOL) * Y_TOL
        rows[y_key].append(w)

    COLOR_COL_SPLIT = 380  # separates left-col colors from right-col colors

    left_cw: Optional[str] = None
    right_cw: Optional[str] = None
    cw_colors: dict[str, list[str]] = defaultdict(list)

    for y in sorted(rows.keys()):
        row_words = sorted(rows[y], key=lambda w: w["x0"])

        # ── Detect colorway header rows ───────────────────────────────────────
        # Header rows contain 3-digit colorway numbers.
        cw_numbers = [
            (w["x0"], w["text"])
            for w in row_words
            if re.match(r"^\d{3}$", w["text"])
        ]
        if cw_numbers:
            cw_numbers.sort()
            left_cw = cw_numbers[0][1]
            right_cw = cw_numbers[1][1] if len(cw_numbers) >= 2 else None

            # Check for an A color embedded in the header line
            # (happens when the A-color row has the same top as the header)
            left_header_words = [w for w in row_words if w["x0"] < COLOR_COL_SPLIT]
            left_header_text = " ".join(w["text"] for w in left_header_words)
            # After the 3-digit CW number and CW name there may be "A A- X - COLOR"
            embedded = re.search(
                r"\d{3}\s+[A-Za-z][A-Za-z ,\./\-]+?\s+([A-E]\s+.+)", left_header_text
            )
            if embedded:
                color = _clean_garbled_color(embedded.group(1), known_colors)
                if color and len(color) >= 3:
                    cw_colors[left_cw].append(color.title())
            continue

        if not left_cw:
            continue

        # ── Parse color row ───────────────────────────────────────────────────
        left_words = [w for w in row_words if w["x0"] < COLOR_COL_SPLIT]
        right_words = [
            w for w in row_words
            if COLOR_COL_SPLIT <= w["x0"] < 700
        ]
        left_text = " ".join(w["text"] for w in left_words).strip()
        right_text = " ".join(w["text"] for w in right_words).strip()

        def _extract_color(text: str) -> Optional[str]:
            if not text:
                return None
            # Skip mixed-case fragments (CW name overflow like "Day" from "Rainy Day")
            if re.match(r"^[A-Z][a-z]", text) and not re.match(r"^[A-E]\s", text):
                return None
            # Clean format: "X - COLOR NAME"
            clean = re.match(r"^[A-E]\s*-\s*([A-Z][A-Z ]+)$", text)
            if clean:
                return clean.group(1).strip().title()
            # Garbled format: recover via fuzzy matching
            if re.match(r"^[A-E]\s", text) or re.search(r"[a-z]", text):
                color = _clean_garbled_color(text, known_colors)
                if color and len(color) >= 3:
                    return color.title()
            return None

        left_color = _extract_color(left_text)
        if left_color and left_cw:
            cw_colors[left_cw].append(left_color)

        if right_cw:
            right_color = _extract_color(right_text)
            if right_color:
                cw_colors[right_cw].append(right_color)

    for cw, colors in cw_colors.items():
        if colors:
            result[cw] = ", ".join(c for c in colors)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_detail_sketch_pages(pdf_path: str) -> Dict[str, Dict[str, str]]:
    """
    Open *pdf_path* and parse every Detail Sketch page.

    Returns
    -------
    dict
        ``{comp_code: {cw_num: "Color1, Color2, ..."}}``

        *comp_code* is a 5–7 digit material code string (e.g. ``"135957"``).
        *cw_num* is a 3-digit string (e.g. ``"256"``).
        Colors are title-cased and comma-separated.
    """
    if pdfplumber is None:
        raise ImportError("pdfplumber is required: pip install pdfplumber")

    sketch_data: Dict[str, Dict[str, str]] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Detail Sketch" not in text:
                continue

            # Find the component material code.
            # There are always two "NNNNNN:" entries on a Detail Sketch page:
            #   - The style code (e.g. "191132: WHIRLIBIRD CUFFED BEANIE")
            #   - The component code (e.g. "135957: 39.6mm Columbia Multi…")
            # We want the LAST one whose description looks like a material.
            comp_code: Optional[str] = None
            for m in re.finditer(r"\b(\d{5,7})\s*:\s*([^\n]{5,})", text):
                code = m.group(1)
                desc = m.group(2)
                # Skip style-level entries (contain product name keywords)
                if any(kw in desc for kw in ("Beanie", "BEANIE", "HEADWEAR", "CUFFED")):
                    continue
                comp_code = code

            if not comp_code:
                continue

            # Choose parser based on whether C/O notation is present
            is_co_format = bool(re.search(r"\bC/O\b", text))

            if is_co_format:
                page_result = _parse_co_format(text, comp_code)
            else:
                page_result = _parse_multicolumn_format(page, comp_code)

            if page_result:
                sketch_data[comp_code] = page_result

    return sketch_data


def get_sketch_color(
    sketch_data: Dict[str, Dict[str, str]],
    comp_code: str,
    matched_cw: str,
) -> Optional[str]:
    """
    Look up the Detail Sketch thread colors for *comp_code* + *matched_cw*.

    Parameters
    ----------
    sketch_data : dict
        Output of :func:`parse_detail_sketch_pages`.
    comp_code : str
        Material/component code (e.g. ``"135957"``).
    matched_cw : str
        Colorway string as it appears in the BOM row.  May have a numeric
        prefix (e.g. ``"256-Tobacco"`` or just ``"256"``).

    Returns
    -------
    str or None
        Comma-separated, title-cased color string, or ``None`` if not found.
    """
    if not sketch_data or not comp_code:
        return None

    comp_data = sketch_data.get(str(comp_code))
    if not comp_data:
        # Try zero-stripped variant
        comp_data = sketch_data.get(str(comp_code).lstrip("0"))
    if not comp_data:
        return None

    # Extract the 3-digit numeric prefix from matched_cw
    cw_num_m = re.match(r"^(\d{3})", str(matched_cw).strip())
    if not cw_num_m:
        return None
    cw_num = cw_num_m.group(1)

    return comp_data.get(cw_num)