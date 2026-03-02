"""
parsers/detail_sketch.py

Parses Columbia BOM "Detail Sketch" pages to extract patch thread color assignments.

Each Detail Sketch page documents one component (patch material) and lists the
A / B [/ C] thread colors for each colorway that uses that patch.

Returns a nested dict:
    { comp_code: { cw_prefix: "A_color, B_color [, C_color]" } }

Example:
    {
      "117027": {
          "010": "Columbia Grey, Black",
          "432": "Dark Nocturnal, White",
          "464": "Columbia Grey, Collegiate Navy",
      },
      "125802": {"262": "Dark Stone, Canoe, Black"},
      "135956": {
          "309": "Grill, Tea Light",
          "442": "Phoenix Blue, Rainy Day",
          "568": "Paisley Purple, Purple Tint",
          "618": "Mineral Pink, Sea Salt",
          "657": "Nico, Powder Pink",
      },
    }

Two page formats handled:
  Format 1 — "NNN name C/O A - COLOR" (inline C/O marker, e.g. 117027 pages)
  Format 2 — "NNN name" header rows then "A - X A - Y" / "B - X B - Y" color rows
              (no C/O marker, e.g. 135956 pages)
"""

from __future__ import annotations
import re
from typing import Dict

# ── noise patterns stripped before parsing ──────────────────────────────────
_NOISE = [
    r'\d+%\s*SIZE\s*PLACEMENT',
    r'Single\s+stitch\s+attachment',
    r'matches\s+ground\s+color',
    r'Patch\s+is\s+Centered',
    r'Horizontal\s+[&\w]+\s+Vertical',
    r'\bon\s+CF\b',
    r'Dec\s+\d+.*',
    r'Page\s+\d+\s+of\s+\d+',
    r'This\s+is\s+confidential.*',
    r'100%\s+SIZE',
    r'You\s+agree.*',
    r'Columbia\s+has.*',
]


def _strip_noise(text: str) -> str:
    for p in _NOISE:
        text = re.sub(p, ' ', text, flags=re.IGNORECASE | re.DOTALL)
    # Remove component header line "NNNNNN: description"
    text = re.sub(r'^\s*\d{4,7}\s*:.*\n', '', text)
    return text


def _parse_format1(lines: list[str]) -> dict[str, str]:
    """Format 1: lines contain 'NNN name C/O A - COLOR' entries."""
    combined = ' '.join(lines)

    entries = re.findall(
        r'(\d{3})\s+[A-Za-z][^C]*?C/O\s+A\s*-\s*([A-Z][A-Z\s]+?)'
        r'(?=\s+\d{3}[^:0-9]|\s+B\s*-|\s*$)',
        combined
    )
    bs = re.findall(
        r'B\s*-\s*([A-Z][A-Z\s]+?)(?=\s+B\s*-|\s+C\s*-|\s+\d{3}|\s*$)',
        combined
    )
    cs = re.findall(
        r'C\s*-\s*([A-Z][A-Z\s]+?)(?=\s+C\s*-|\s+\d{3}|\s*$)',
        combined
    )

    result = {}
    for i, (cw_num, a_color) in enumerate(entries):
        colors = [a_color.strip()]
        if i < len(bs):
            colors.append(bs[i].strip())
        if i < len(cs):
            colors.append(cs[i].strip())
        result[cw_num] = ', '.join(c.title() for c in colors if c)
    return result


def _parse_format2(lines: list[str]) -> dict[str, str]:
    """
    Format 2: colorway header row(s) then A/B/C color rows.
    e.g. "309 Tea Light, Sedona Sage  568 Purple Tint, Antique Mauve"
         "A - GRILL  A - PAISLEY PURPLE"
         "B - TEA LIGHT  B - PURPLE TINT"
    """
    result = {}
    cw_queue: list[str] = []
    pending: dict[str, list[str]] = {'A': [], 'B': [], 'C': []}

    def _flush():
        for i, cw_num in enumerate(cw_queue):
            colors = []
            for letter in ('A', 'B', 'C'):
                if i < len(pending[letter]):
                    colors.append(pending[letter][i])
            result[cw_num] = ', '.join(c.title() for c in colors if c)
        cw_queue.clear()
        for v in pending.values():
            v.clear()

    for line in lines:
        # Color letter row: "A - X  A - Y" or "B - X" etc.
        if re.match(r'^[ABC]\s*-\s*[A-Z]', line):
            letter = line[0]
            colors = re.findall(
                r'[A-Z]\s*-\s*([A-Z][A-Z\s,]+?)(?=\s+[A-Z]\s*-|\s*$)',
                line
            )
            if not colors:
                colors = [re.sub(r'^[A-Z]\s*-\s*', '', line).strip()]
            pending[letter].extend(c.strip() for c in colors if c.strip())
            continue

        # Colorway header row: starts with 3-digit number
        if re.match(r'^\d{3}\s+', line):
            # Flush previous block before starting a new one
            if pending['A'] and cw_queue:
                _flush()
            # Extract all NNN entries from this line
            entries = re.findall(r'(\d{3})\s+[A-Za-z][^\d]*?(?=\s+\d{3}\s+|$)', line)
            if not entries:
                m = re.match(r'(\d{3})', line)
                if m:
                    entries = [m.group(1)]
            cw_queue.extend(entries)

    # Flush any remaining
    if pending['A'] and cw_queue:
        _flush()

    return result


def _parse_sketch_page(text: str) -> tuple[str, dict[str, str]]:
    """
    Parse a single Detail Sketch page.
    Returns (comp_code, {cw_prefix: color_string}).
    """
    # Extract component code from the header line:
    # Component lines look like "117027: 38.1mm Columbia EST. 1938 Woven Youth Patch"
    # Style number lines like "201106: YOUTH WHIRLIBIRD CUFFED BEANIE" are excluded
    # because they don't have a decimal/measurement after the colon.
    comp_match = re.search(r'(\d{4,7})\s*:\s*[\d.]+[^\n]*\n', text)
    comp_code = comp_match.group(1) if comp_match else ''

    # Only parse text AFTER the component header line to avoid confusing
    # style/metadata numbers with colorway prefixes.
    if comp_match:
        body = text[comp_match.end():]
    else:
        body = text

    clean = _strip_noise(body)
    lines = [l.strip() for l in clean.split('\n') if l.strip()]

    if any('C/O' in l for l in lines):
        cw_colors = _parse_format1(lines)
    else:
        cw_colors = _parse_format2(lines)

    return comp_code, cw_colors


def parse_detail_sketches(pdf) -> Dict[str, Dict[str, str]]:
    """
    Parse all Detail Sketch pages from an open pdfplumber PDF object.

    Args:
        pdf: open pdfplumber.PDF instance

    Returns:
        { comp_code: { cw_prefix: "A_color, B_color [, C_color]" } }
    """
    result: dict[str, dict[str, str]] = {}

    for page in pdf.pages:
        text = page.extract_text() or ''
        if 'Detail Sketch' not in text:
            continue
        comp_code, cw_colors = _parse_sketch_page(text)
        if comp_code and cw_colors:
            if comp_code not in result:
                result[comp_code] = {}
            result[comp_code].update(cw_colors)

    return result


def get_sketch_color(
    sketch_data: Dict[str, Dict[str, str]],
    comp_code: str,
    matched_cw: str,
) -> str:
    """
    Look up the thread color string for a given component code and colorway.

    Args:
        sketch_data: output of parse_detail_sketches()
        comp_code:   material code e.g. "125802"
        matched_cw:  full colorway string e.g. "262-Canoe, Mountains"

    Returns:
        Color string like "Dark Stone, Canoe, Black" or "" if not found.
    """
    if not sketch_data or not comp_code or not matched_cw:
        return ''

    comp_data = sketch_data.get(str(comp_code).strip())
    if not comp_data:
        return ''

    # Extract 3-digit prefix from matched_cw
    m = re.match(r'^(\d{3})', str(matched_cw).strip())
    if not m:
        return ''
    cw_prefix = m.group(1)

    return comp_data.get(cw_prefix, '')