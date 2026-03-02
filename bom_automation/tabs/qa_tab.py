"""tabs/qa_tab.py — QA File Comparison tab."""
import io as _bio
import json
import re
from collections import defaultdict
from html import escape

import pandas as pd
import streamlit as st

from .utils import (
    render_section_header, render_divider, render_info_banner, render_warn_banner,
    render_pagination,
)

# ── Column classification ──────────────────────────────────────────────────────
_SKIP_COL_HINTS = [
    "po #", "po#", "po number", "plant", "dest country", "destination country",
    "ult. destination", "ult destination", "ultimate destination",
    "material style", "vendor code", "size", "vas",
    "ordered qty", "ordered quantity", "orig ex fac", "original ex fac",
]

_INFO_COL_HINTS = [
    "tp status", "tp date", "product status", "remarks",
]

def _col_classify(col_name):
    """Return 'skip', 'info', or 'compare' for a column."""
    cn = str(col_name).lower().strip()
    for h in _SKIP_COL_HINTS:
        if h in cn or cn in h:
            return "skip"
    for h in _INFO_COL_HINTS:
        if h in cn or cn in h:
            return "info"
    return "compare"


def _qa_read_file(uploaded_file):
    """Read uploaded Excel or CSV, auto-detect header row."""
    name = uploaded_file.name.lower()
    is_excel = name.endswith((".xlsx", ".xls"))
    raw = pd.read_excel(uploaded_file, header=None, sheet_name=0) if is_excel else pd.read_csv(uploaded_file, header=None)
    n_cols = raw.shape[1]
    header_row = 0
    for i in range(min(10, len(raw))):
        non_empty = raw.iloc[i].notna().sum()
        if non_empty >= max(1, n_cols * 0.4):
            header_row = i
            break
    df = raw.iloc[header_row + 1:].copy()
    raw_headers = raw.iloc[header_row].tolist()
    seen = {}
    headers = []
    for h in raw_headers:
        h_str = str(h).strip() if pd.notna(h) else "Unnamed"
        if h_str in seen:
            seen[h_str] += 1
            headers.append(f"{h_str}.{seen[h_str]}")
        else:
            seen[h_str] = 0
            headers.append(h_str)
    df.columns = headers
    df = df[~df.isnull().all(axis=1)].reset_index(drop=True)
    return df


def _fix_ocr_spaces(s: str) -> str:
    """
    Collapse OCR-introduced mid-word spaces so comparison is not tripped up
    by artifacts like "packagin g" vs "packaging" or "nex tgen" vs "nextgen".

    Strategy: if a whitespace-separated token has no vowel and is ≤3 chars,
    it was likely split off the preceding token — merge them.
    Single-character tokens always merge.
    Run until stable.
    """
    prev = None
    while prev != s:
        prev = s
        s = re.sub(
            r'([a-z]{2,})\s+([a-z]{1,3})(?=\s|$)',
            lambda m: (
                m.group(1) + m.group(2)
                if (not re.search(r'[aeiou]', m.group(2)) or len(m.group(2)) == 1)
                else m.group(0)
            ),
            s,
        )
    return s


def _qa_normalize_val(v):
    """
    Normalize a cell value for comparison.

    Rules:
    - True empty / pandas null  → ""   (genuinely missing — skipped in accuracy)
    - "N/A", "n/a" strings      → "n/a"  (kept as a REAL comparable value,
                                          so N/A vs something else counts as a diff)
    - Trailing .0 stripped (Excel float artefact)
    - Leading zeros are NOT stripped — care codes, UPC, RFID sticker values
      like "077027" must remain intact
    - Lowercased + whitespace-collapsed
    - Newlines collapsed to space before processing
    - OCR mid-word spaces collapsed ("packagin g" → "packaging")
    - Spaces before/after abbreviation periods removed ("Co. Ltd" → "Co.Ltd")
    - All content-section prefixes stripped: "Shell:", "Lining:", "Body:", etc.
      from ANY position in the string (handles multi-section TP FC values)
    - Common content-code prefixes stripped
    """
    if v is None:
        return ""
    s = str(v).strip()
    # Only truly blank / pandas null → empty string
    if s.lower() in ("nan", "none", "nat", ""):
        return ""
    # Strip trailing .0 from Excel integers stored as float
    s = re.sub(r"\.0$", "", s)
    s = s.lower()
    # Collapse multiple whitespace including newlines to a single space
    s = re.sub(r"\s+", " ", s).strip()
    # Fix OCR mid-word spaces (e.g. "packagin g global" → "packaging global")
    s = _fix_ocr_spaces(s)
    # Normalize punctuation: remove spaces around abbreviation periods
    # "Co. Ltd" → "Co.Ltd", "Co. Ltd." → "Co.Ltd."
    s = re.sub(r"\.\s+([a-z]{1,5})(?=[\s.,)]|$)", r".\1", s)
    # Strip ALL content-section prefixes wherever they appear (handles multi-section TP FC):
    # "Shell: 100% Acrylic Lining: 100% Polyester..." → "100% Acrylic 100% Polyester..."
    s = re.sub(
        r"(?:^|(?<=\s))(shell|body|lining|fill|fabric|material|fleece lining)\s*:\s*",
        " ", s
    ).strip()
    # Final whitespace cleanup
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _qa_values_match(a_norm: str, e_norm: str) -> bool:
    """
    Match check: exact equality after normalization only.

    Substring / partial matching has been intentionally removed because it
    caused false positives across unrelated columns (e.g. a short care-code
    value being found inside a gloves-column value, or vice-versa).

    The normalization in _qa_normalize_val already handles the real sources
    of legitimate near-misses:
      - OCR mid-word spaces
      - Section prefixes (Shell:/Lining:/Body:)
      - Trailing .0 Excel artefacts
      - Abbreviation-period spacing
    After that, values should match exactly or genuinely differ.
    """
    return a_norm == e_norm


def _auto_detect(cols, hint_groups):
    for hint in hint_groups:
        for c in cols:
            if hint in str(c).lower():
                return c
    return None


@st.cache_data(show_spinner=False, max_entries=10)
def _qa_compare(actual_bytes, expected_bytes, actual_name, expected_name,
                actual_key_cols, expected_key_cols, col_map_json):
    """Core comparison engine."""
    col_map = json.loads(col_map_json)

    def _read(b, n):
        f = _bio.BytesIO(b)
        f.name = n
        return _qa_read_file(f)

    df_a = _read(actual_bytes, actual_name)
    df_e = _read(expected_bytes, expected_name)

    def _make_key(df, key_cols):
        return df[key_cols].apply(
            lambda r: "|".join(_qa_normalize_val(v) for v in r), axis=1
        )

    df_a = df_a.copy()
    df_e = df_e.copy()
    df_a["__key__"] = _make_key(df_a, actual_key_cols)
    df_e["__key__"] = _make_key(df_e, expected_key_cols)

    exp_by_key = {}
    for _, row in df_e.iterrows():
        k = row["__key__"]
        if k not in exp_by_key:
            exp_by_key[k] = row

    results = []
    for row_num, (_, a_row) in enumerate(df_a.iterrows()):
        key = a_row["__key__"]
        e_row = exp_by_key.get(key)
        row_result = {
            "__key__": key,
            "__matched__": e_row is not None,
            "__row_num__": row_num + 2,
        }
        row_result["__style__"] = _qa_normalize_val(a_row.get(actual_key_cols[0], ""))
        row_result["__display_key__"] = " | ".join(
            str(a_row.get(c, "")) for c in actual_key_cols
        )
        col_diffs = {}
        for entry in col_map:
            a_col, e_col, kind = entry[0], entry[1], entry[2]
            a_val = _qa_normalize_val(a_row.get(a_col, ""))
            e_val = _qa_normalize_val(e_row.get(e_col, "")) if e_row is not None else ""

            matched = _qa_values_match(a_val, e_val)

            col_diffs[a_col] = {
                "actual": a_val,
                "expected": e_val,
                "match": matched,
                # both_empty = ONLY when both sides are truly blank (not n/a)
                # N/A vs N/A  → match=True,  both_empty=False  (shown as match)
                # N/A vs something → match=False, both_empty=False (shown as diff)
                # ""  vs ""   → match=True,  both_empty=True   (skipped in accuracy)
                "both_empty": (a_val == "" and e_val == ""),
                "kind": kind,
            }
        row_result["cols"] = col_diffs

        compare_cols = {c: v for c, v in col_diffs.items() if v["kind"] == "compare"}
        row_result["n_diff"]       = sum(1 for v in compare_cols.values() if not v["match"] and not v["both_empty"])
        row_result["n_match"]      = sum(1 for v in compare_cols.values() if v["match"] and not v["both_empty"])
        row_result["n_both_empty"] = sum(1 for v in compare_cols.values() if v["both_empty"])
        results.append(row_result)

    actual_keys = set(df_a["__key__"])
    missing_in_actual = [k for k in exp_by_key if k not in actual_keys]

    return results, missing_in_actual, list(df_a.columns), list(df_e.columns)


_QA_STATE_KEYS = [
    "__qa_sig", "__qa_actual_cols", "__qa_expected_cols",
    "__qa_results", "__qa_run_sig", "__qa_col_map_init", "__qa_missing",
    "qa_page", "qa_style_page",
]


def render_qa_tab():
    render_section_header("QA Comparison", "Upload any two Excel/CSV files — actual vs expected — to diff them row by row", compact=True)

    qa_gen_a = st.session_state.get("__qa_gen_actual", 0)
    qa_gen_e = st.session_state.get("__qa_gen_expected", 0)

    up_col1, up_col2 = st.columns(2, gap="large")
    with up_col1:
        st.markdown("<div class='cx-meta'>Actual / Your Output</div>", unsafe_allow_html=True)
        actual_file = st.file_uploader("Upload Actual", type=["xlsx","xls","csv"],
                                       key=f"qa_actual_{qa_gen_a}", label_visibility="collapsed")
    with up_col2:
        st.markdown("<div class='cx-meta'>Expected / Reference</div>", unsafe_allow_html=True)
        expected_file = st.file_uploader("Upload Expected", type=["xlsx","xls","csv"],
                                         key=f"qa_expected_{qa_gen_e}", label_visibility="collapsed")

    has_any = actual_file or expected_file or st.session_state.get("__qa_sig")
    if has_any:
        if st.button("✕ Clear all", key="qa_clear_btn", type="tertiary"):
            for k in _QA_STATE_KEYS:
                st.session_state.pop(k, None)
            st.session_state["__qa_gen_actual"]   = qa_gen_a + 1
            st.session_state["__qa_gen_expected"] = qa_gen_e + 1
            st.rerun()

    if not actual_file or not expected_file:
        render_info_banner("Upload both files above to start comparison. Any Excel or CSV works — columns are auto-detected.")
        return

    actual_bytes   = actual_file.getvalue()
    expected_bytes = expected_file.getvalue()
    qa_sig = f"{actual_file.name}:{len(actual_bytes)}:{expected_file.name}:{len(expected_bytes)}"
    if st.session_state.get("__qa_sig") != qa_sig:
        for k in ["__qa_actual_cols","__qa_expected_cols","__qa_sig",
                  "__qa_results","__qa_run_sig","__qa_col_map_init"]:
            st.session_state.pop(k, None)
        st.session_state["__qa_sig"] = qa_sig

    if "__qa_actual_cols" not in st.session_state:
        f = _bio.BytesIO(actual_bytes); f.name = actual_file.name
        df_a_preview = _qa_read_file(f)
        f = _bio.BytesIO(expected_bytes); f.name = expected_file.name
        df_e_preview = _qa_read_file(f)
        st.session_state["__qa_actual_cols"]   = list(df_a_preview.columns)
        st.session_state["__qa_expected_cols"] = list(df_e_preview.columns)

    a_cols = st.session_state["__qa_actual_cols"]
    e_cols = st.session_state["__qa_expected_cols"]

    render_divider()
    cfg_card = st.container(border=True, key="qa_cfg_card")
    with cfg_card:
        st.markdown("<div class='cx-meta' style='margin-bottom:4px;'>Column Mapping</div>", unsafe_allow_html=True)

        def _idx(lst, val):
            try: return lst.index(val) if val else 0
            except: return 0

        def_style_a = (
            _auto_detect(a_cols, ["jde style", "jde"]) or
            _auto_detect(a_cols, ["buyer style", "style number", "style"]) or
            a_cols[0]
        )
        def_color_a = (
            _auto_detect(a_cols, ["color/option", "color option"]) or
            _auto_detect(a_cols, ["color"]) or
            (a_cols[1] if len(a_cols) > 1 else a_cols[0])
        )
        def_mat_a = (
            _auto_detect(a_cols, ["material name", "material"]) or
            _auto_detect(a_cols, ["description", "desc"]) or
            (a_cols[2] if len(a_cols) > 2 else a_cols[0])
        )

        def_style_e = (
            _auto_detect(e_cols, ["jde style", "jde"]) or
            _auto_detect(e_cols, ["buyer style", "style number", "style"]) or
            e_cols[0]
        )
        def_color_e = (
            _auto_detect(e_cols, ["color/option", "color option"]) or
            _auto_detect(e_cols, ["color"]) or
            (e_cols[1] if len(e_cols) > 1 else e_cols[0])
        )

        auto_info = (
            f"Auto-selected columns: Style = <b>{def_style_a or 'N/A'}</b>, "
            f"Color = <b>{def_color_a or 'N/A'}</b>, "
            f"Material = <b>{def_mat_a or 'N/A'}</b>"
        )
        st.markdown(f"<div style='font-size:0.75rem;color:#64748b;margin-bottom:12px;'>{auto_info}</div>", unsafe_allow_html=True)

        m1, m2, m3 = st.columns(3, gap="medium")

        with m1:
            st.markdown(
                "<div style='font-size:0.72rem;font-weight:600;color:#4a6286;margin-bottom:4px;'>"
                "JDE Style / Style Number column</div>",
                unsafe_allow_html=True,
            )
            sel_style_a = st.selectbox("", options=a_cols, index=_idx(a_cols, def_style_a),
                                       key="qa_style_col", label_visibility="collapsed")

        with m2:
            st.markdown(
                "<div style='font-size:0.72rem;font-weight:600;color:#4a6286;margin-bottom:4px;'>"
                "Color column</div>",
                unsafe_allow_html=True,
            )
            sel_color_a = st.selectbox("", options=a_cols, index=_idx(a_cols, def_color_a),
                                       key="qa_color_col", label_visibility="collapsed")

        with m3:
            st.markdown(
                "<div style='font-size:0.72rem;font-weight:600;color:#4a6286;margin-bottom:4px;'>"
                "Material Name column (Glove/Beanie detection)</div>",
                unsafe_allow_html=True,
            )
            sel_mat_a = st.selectbox("", options=a_cols, index=_idx(a_cols, def_mat_a),
                                     key="qa_mat_col", label_visibility="collapsed")

    key_actual   = [sel_style_a, sel_color_a]
    key_expected = [
        def_style_e or e_cols[0],
        def_color_e or (e_cols[1] if len(e_cols) > 1 else e_cols[0]),
    ]

    import re as _re
    def _norm_col(c):
        return _re.sub(r'[^a-z0-9]', '', str(c).lower())

    if "__qa_col_map_init" not in st.session_state:
        e_norm = {_norm_col(c): c for c in e_cols}
        mapping = []
        used_e = set()
        for ac in a_cols:
            kind = _col_classify(ac)
            if kind == "skip":
                continue
            an = _norm_col(ac)
            matched_ec = None
            if an in e_norm and e_norm[an] not in used_e:
                matched_ec = e_norm[an]
                used_e.add(matched_ec)
            else:
                for en, ec in e_norm.items():
                    if ec in used_e: continue
                    if an in en or en in an:
                        matched_ec = ec
                        used_e.add(ec)
                        break
            if matched_ec:
                mapping.append([ac, matched_ec, kind])
        st.session_state["__qa_col_map_init"] = mapping

    col_map = st.session_state["__qa_col_map_init"]
    compare_col_names = [e[0] for e in col_map if e[2] == "compare"]
    info_col_names    = [e[0] for e in col_map if e[2] == "info"]

    render_divider()
    if not col_map:
        render_warn_banner("No matching columns found between files.")
        return

    col_map_json = json.dumps(col_map)
    run_sig = f"{qa_sig}:{','.join(key_actual)}:{','.join(key_expected)}:{col_map_json}"

    if st.session_state.get("__qa_run_sig") != run_sig:
        with st.spinner("Running comparison..."):
            results, missing_keys, _, _ = _qa_compare(
                actual_bytes, expected_bytes,
                actual_file.name, expected_file.name,
                key_actual, key_expected,
                col_map_json,
            )
        st.session_state["__qa_results"]  = results
        st.session_state["__qa_missing"]  = missing_keys
        st.session_state["__qa_run_sig"]  = run_sig

    results      = st.session_state.get("__qa_results", [])
    missing_keys = st.session_state.get("__qa_missing", [])

    if not results:
        render_warn_banner("No rows to compare. Check your key columns.")
        return

    total_rows   = len(results)
    rows_perfect = sum(1 for r in results if r["n_diff"] == 0 and r["__matched__"])
    rows_diff    = sum(1 for r in results if r["n_diff"] > 0 and r["__matched__"])
    rows_nomatch = sum(1 for r in results if not r["__matched__"])
    total_cells  = sum(r["n_match"] + r["n_diff"] for r in results)
    match_cells  = sum(r["n_match"] for r in results)
    match_pct    = round(match_cells / total_cells * 100, 1) if total_cells else 0

    st.markdown(
        f"""
        <div class="cx-stats" style="grid-template-columns:repeat(5,minmax(0,1fr));">
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:#334e75;">{total_rows}</div><div class="cx-stat-label">Total Rows</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--green);">{rows_perfect}</div><div class="cx-stat-label">Perfect Match</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--amber);">{rows_diff}</div><div class="cx-stat-label">Has Differences</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--red);">{rows_nomatch}</div><div class="cx-stat-label">No Match Found</div></div>
          <div class="cx-stat-card"><div class="cx-stat-number" style="color:#4f89f7;">{match_pct}%</div><div class="cx-stat-label">Cell Accuracy</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ok_w   = round(rows_perfect / total_rows * 100, 1)
    diff_w = round(rows_diff / total_rows * 100, 1)
    err_w  = max(0.0, round(100 - ok_w - diff_w, 1))
    st.markdown(
        f"""
        <div class="cx-progress-card">
          <div class="cx-progress-head"><span>Row Match Rate</span><span class="pct">{ok_w}% Perfect</span></div>
          <div class="cx-progress-track">
            <div class="cx-progress-seg ok"      style="width:{ok_w}%;"></div>
            <div class="cx-progress-seg partial"  style="width:{diff_w}%;"></div>
            <div class="cx-progress-seg err"      style="width:{err_w}%;"></div>
          </div>
          <div class="cx-progress-legend">
            <span><span class="cx-progress-dot" style="background:#10b981;"></span>Perfect</span>
            <span><span class="cx-progress-dot" style="background:#f0b429;"></span>Has Diffs</span>
            <span><span class="cx-progress-dot" style="background:#ef4444;"></span>No Match</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_divider()
    st.markdown("<div class='cx-meta'>Column Accuracy</div>", unsafe_allow_html=True)

    def _build_col_stats(col_names, kind_filter):
        stats = {}
        for r in results:
            if not r["__matched__"]: continue
            for col, info in r["cols"].items():
                if info["kind"] != kind_filter: continue
                if col not in col_names: continue
                if col not in stats:
                    stats[col] = {"match": 0, "diff": 0, "both_empty": 0}
                if info["both_empty"]:  stats[col]["both_empty"] += 1
                elif info["match"]:     stats[col]["match"] += 1
                else:                   stats[col]["diff"] += 1
        rows_out = []
        for col, s in stats.items():
            total_c = s["match"] + s["diff"]
            acc = round(s["match"] / total_c * 100, 1) if total_c else 100.0
            rows_out.append({"col": col, "match": s["match"], "diff": s["diff"],
                             "empty": s["both_empty"], "acc": acc})
        return sorted(rows_out, key=lambda x: x["acc"])

    def _render_chip_grid(col_rows_list, muted=False):
        per_row = 3
        for ri in range(0, len(col_rows_list), per_row):
            chunk = col_rows_list[ri:ri + per_row]
            c_cells = st.columns(len(chunk))
            for ci, cr in enumerate(chunk):
                acc = cr["acc"]
                if muted:
                    bar_col, bg, fg = "#94a3b8", "#f8fafc", "#64748b"
                elif acc >= 95:
                    bar_col, bg, fg = "#10b981", "#f0fdf4", "#065f46"
                elif acc >= 75:
                    bar_col, bg, fg = "#f0b429", "#fffbeb", "#854d0e"
                else:
                    bar_col, bg, fg = "#ef4444", "#fef2f2", "#991b1b"
                with c_cells[ci]:
                    st.markdown(
                        f"""
                        <div style="background:{bg};border:1px solid {bar_col}33;border-radius:10px;
                            padding:10px 14px;margin-bottom:8px;">
                          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="font-size:0.78rem;font-weight:700;color:#1a2b45;
                                word-break:break-word;max-width:70%;">{escape(cr['col'])}</span>
                            <span style="font-size:0.88rem;font-weight:800;color:{fg};">{acc}%</span>
                          </div>
                          <div style="height:5px;background:#e2e8f0;border-radius:99px;overflow:hidden;margin-bottom:7px;">
                            <div style="width:{round(acc)}%;height:100%;background:{bar_col};border-radius:99px;"></div>
                          </div>
                          <div style="display:flex;gap:8px;font-size:0.68rem;color:#64748b;">
                            <span>&#10003; {cr['match']} match</span>
                            <span style="color:#ef4444;">&#10007; {cr['diff']} diff</span>
                            <span style="color:#94a3b8;">&#8709; {cr['empty']} empty</span>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    compare_stats = _build_col_stats(compare_col_names, "compare")
    info_stats    = _build_col_stats(info_col_names, "info")

    if compare_stats:
        st.markdown(
            "<div style='font-size:0.68rem;font-weight:700;color:#4a6286;text-transform:uppercase;"
            "letter-spacing:0.06em;margin-bottom:6px;'>Compared Columns</div>",
            unsafe_allow_html=True,
        )
        _render_chip_grid(compare_stats, muted=False)

    if info_stats:
        st.markdown(
            "<div style='font-size:0.68rem;font-weight:700;color:#94a3b8;text-transform:uppercase;"
            "letter-spacing:0.06em;margin:12px 0 4px;'>Info-Only Columns "
            "<span style=\"font-weight:400;font-size:0.65rem;\">(not counted in accuracy)</span></div>",
            unsafe_allow_html=True,
        )
        _render_chip_grid(info_stats, muted=True)

    render_divider()
    st.markdown("<div class='cx-meta'>Per Style Summary</div>", unsafe_allow_html=True)

    style_groups = defaultdict(list)
    for r in results:
        style_val = str(r.get("__style__", "N/A")).upper().strip()
        style_groups[style_val].append(r)

    style_summary = []
    for sty, rows in style_groups.items():
        matched  = [r for r in rows if r["__matched__"]]
        no_match = [r for r in rows if not r["__matched__"]]
        perfect  = [r for r in matched if r["n_diff"] == 0]
        has_diff = [r for r in matched if r["n_diff"] > 0]

        col_diff_count  = defaultdict(int)
        col_match_count = defaultdict(int)
        for r in matched:
            for c, info in r["cols"].items():
                if info["kind"] != "compare": continue
                if not info["both_empty"]:
                    if info["match"]: col_match_count[c] += 1
                    else:             col_diff_count[c] += 1

        row_errors = []
        for r in has_diff:
            bad_cols = [c for c, info in r["cols"].items()
                        if info["kind"] == "compare" and not info["match"] and not info["both_empty"]]
            ok_cols  = sum(1 for c, info in r["cols"].items()
                           if info["kind"] == "compare" and info["match"] and not info["both_empty"])
            row_errors.append({
                "row_num": r["__row_num__"],
                "key": r["__display_key__"],
                "bad_cols": bad_cols,
                "n_diff": r["n_diff"],
                "n_match": ok_cols,
            })
        for r in no_match:
            row_errors.append({
                "row_num": r["__row_num__"],
                "key": r["__display_key__"],
                "bad_cols": ["no match found"],
                "n_diff": None,
                "n_match": 0,
            })

        style_summary.append({
            "style": sty,
            "total": len(rows),
            "perfect": len(perfect),
            "has_diff": len(has_diff),
            "no_match": len(no_match),
            "row_errors": row_errors,
            "col_diff_count": dict(col_diff_count),
            "col_match_count": dict(col_match_count),
        })

    style_summary.sort(key=lambda x: (-x["has_diff"], -x["no_match"]))

    STYLES_PER_PAGE = 6
    total_style_pages = max(1, -(-len(style_summary) // STYLES_PER_PAGE))
    style_page = max(0, min(st.session_state.get("qa_style_page", 0), total_style_pages - 1))
    st.session_state["qa_style_page"] = style_page

    st.markdown(
        f"<div style='font-size:0.73rem;color:#64748b;margin-bottom:8px;'>"
        f"{len(style_summary)} styles &middot; Page {style_page + 1} of {total_style_pages}</div>",
        unsafe_allow_html=True,
    )

    page_styles = style_summary[style_page * STYLES_PER_PAGE: (style_page + 1) * STYLES_PER_PAGE]

    for ss in page_styles:
        total_s  = ss["total"]
        is_clean = ss["has_diff"] + ss["no_match"] == 0
        accent   = "#10b981" if is_clean else ("#ef4444" if ss["no_match"] > 0 else "#f0b429")

        col_chip_html = ""
        for col in compare_col_names:
            diff_n  = ss["col_diff_count"].get(col, 0)
            match_n = ss["col_match_count"].get(col, 0)
            total_c = diff_n + match_n
            acc = round((match_n / total_c) * 100) if total_c else 100
            chip_bg  = "#d1fae5" if acc >= 95 else ("#fef9c3" if acc >= 75 else "#fee2e2")
            chip_col = "#065f46" if acc >= 95 else ("#854d0e" if acc >= 75 else "#991b1b")
            col_chip_html += (
                f"<span style='font-size:0.65rem;font-weight:700;padding:2px 7px;"
                f"border-radius:999px;background:{chip_bg};color:{chip_col};white-space:nowrap;'>"
                f"{escape(col)} {acc}%</span> "
            )

        row_table_html = ""
        if ss["row_errors"]:
            for re_info in ss["row_errors"][:10]:
                is_unmatched = re_info["n_diff"] is None
                row_bg_c = "#fef2f2" if is_unmatched else "#fffbeb"
                bad_cols_html = " ".join(
                    f"<span style='font-size:0.62rem;background:#fee2e2;color:#991b1b;"
                    f"border-radius:3px;padding:1px 5px;'>{escape(c)}</span>"
                    for c in re_info["bad_cols"]
                )
                match_badge = (
                    f"<span style='font-size:0.62rem;color:#10b981;font-weight:600;'>"
                    f"&#10003; {re_info['n_match']} ok</span>"
                    if not is_unmatched and re_info["n_match"] else ""
                )
                diff_badge = (
                    f"<span style='font-size:0.62rem;color:#ef4444;font-weight:600;margin-left:4px;'>"
                    f"&#10007; {re_info['n_diff']} diff</span>"
                    if re_info["n_diff"] else ""
                )
                row_table_html += f"""
                <tr style="background:{row_bg_c};">
                  <td style="padding:4px 10px;font-size:0.68rem;font-weight:700;color:#475569;
                      white-space:nowrap;border-bottom:1px solid #f1f5f9;">Row {re_info['row_num']}</td>
                  <td style="padding:4px 10px;font-size:0.66rem;color:#334e75;
                      border-bottom:1px solid #f1f5f9;max-width:160px;overflow:hidden;
                      text-overflow:ellipsis;white-space:nowrap;">{escape(re_info['key'])}</td>
                  <td style="padding:4px 10px;border-bottom:1px solid #f1f5f9;">{bad_cols_html}</td>
                  <td style="padding:4px 10px;border-bottom:1px solid #f1f5f9;white-space:nowrap;">
                    {match_badge}{diff_badge}
                  </td>
                </tr>"""

            more = len(ss["row_errors"]) - 10
            if more > 0:
                row_table_html += (
                    f"<tr><td colspan='4' style='padding:5px 10px;font-size:0.65rem;color:#94a3b8;"
                    f"text-align:center;'>... and {more} more rows with issues</td></tr>"
                )

        row_section_html = ""
        if row_table_html:
            row_section_html = f"""
            <div style="margin-top:10px;border-radius:7px;overflow:hidden;border:1px solid #f1e4e4;">
              <table style="border-collapse:collapse;width:100%;background:#fff;">
                <thead>
                  <tr style="background:#f8fafc;">
                    <th style="padding:4px 10px;font-size:0.61rem;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;text-align:left;border-bottom:2px solid #e2e8f0;
                        white-space:nowrap;">Row #</th>
                    <th style="padding:4px 10px;font-size:0.61rem;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;text-align:left;border-bottom:2px solid #e2e8f0;">Key</th>
                    <th style="padding:4px 10px;font-size:0.61rem;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;text-align:left;border-bottom:2px solid #e2e8f0;">Error Columns</th>
                    <th style="padding:4px 10px;font-size:0.61rem;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;text-align:left;border-bottom:2px solid #e2e8f0;">Result</th>
                  </tr>
                </thead>
                <tbody>{row_table_html}</tbody>
              </table>
            </div>"""

        no_err_html = (
            "<div style='font-size:0.7rem;color:#10b981;margin-top:6px;'>All columns match &#10003;</div>"
            if is_clean else ""
        )

        st.markdown(
            f"""
            <div style="border-left:4px solid {accent};border-radius:10px;padding:14px 16px 12px;
                background:#fff;box-shadow:0 1px 6px rgba(0,0,0,0.07);margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="font-size:1rem;font-weight:800;color:#1a2b45;">{escape(ss['style'])}</span>
                <span style="font-size:0.72rem;color:#64748b;font-weight:600;">{total_s} rows total</span>
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
                <span style="font-size:0.72rem;font-weight:700;padding:2px 10px;border-radius:999px;
                    background:#d1fae5;color:#065f46;">&#10003; {ss['perfect']} perfect</span>
                <span style="font-size:0.72rem;font-weight:700;padding:2px 10px;border-radius:999px;
                    background:#fef9c3;color:#854d0e;">&#9888; {ss['has_diff']} with diffs</span>
                <span style="font-size:0.72rem;font-weight:700;padding:2px 10px;border-radius:999px;
                    background:#fee2e2;color:#991b1b;">&#10007; {ss['no_match']} unmatched</span>
              </div>
              <div style="font-size:0.62rem;color:#94a3b8;font-weight:600;text-transform:uppercase;
                  letter-spacing:0.05em;margin-bottom:5px;">Column Accuracy</div>
              <div style="display:flex;gap:5px;flex-wrap:wrap;">{col_chip_html}</div>
              {no_err_html}
              {row_section_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_pagination("qa_style_page", style_page, total_style_pages, key_suffix="qa_style", show_page_text=True)

    render_divider()
    st.markdown("<div class='cx-meta'>Row-Level Diff Inspector</div>", unsafe_allow_html=True)

    all_display_cols = compare_col_names + info_col_names

    fc1, fc2, fc3 = st.columns([2, 2, 2])
    with fc1:
        filter_status = st.selectbox("Show", ["All rows", "Differences only", "Perfect matches", "No match found"],
                                     key="qa_filter_status")
    with fc2:
        all_styles_list = ["All styles"] + sorted(style_groups.keys())
        filter_style = st.selectbox("Style", all_styles_list, key="qa_filter_style")
    with fc3:
        filter_col = st.selectbox("Column filter", ["All columns"] + all_display_cols, key="qa_filter_col")

    filtered = results
    if filter_status == "Differences only":
        filtered = [r for r in filtered if r["n_diff"] > 0]
    elif filter_status == "Perfect matches":
        filtered = [r for r in filtered if r["n_diff"] == 0 and r["__matched__"]]
    elif filter_status == "No match found":
        filtered = [r for r in filtered if not r["__matched__"]]

    if filter_style != "All styles":
        filtered = [r for r in filtered if r["__style__"].upper() == filter_style.upper()]

    show_cols = all_display_cols if filter_col == "All columns" else [filter_col]

    QA_PER_PAGE = 15
    total_qa_pages = max(1, -(-len(filtered) // QA_PER_PAGE))
    qa_page = max(0, min(st.session_state.get("qa_page", 0), total_qa_pages - 1))
    st.session_state["qa_page"] = qa_page

    st.markdown(
        f"<div style='font-size:0.74rem;color:#64748b;margin-bottom:6px;'>"
        f"Showing {len(filtered)} rows &middot; Page {qa_page+1} of {total_qa_pages}</div>",
        unsafe_allow_html=True,
    )

    page_rows = filtered[qa_page * QA_PER_PAGE: (qa_page + 1) * QA_PER_PAGE]

    if not page_rows:
        render_info_banner("No rows match the current filter.")
    else:
        def _th(label, extra=""):
            return (
                f"<th style='padding:6px 10px;text-align:left;font-size:0.65rem;font-weight:700;"
                f"text-transform:uppercase;letter-spacing:0.05em;color:#64748b;white-space:nowrap;"
                f"background:#f8fafc;border-bottom:2px solid #e2e8f0;position:sticky;top:0;z-index:2;{extra}'>"
                f"{label}</th>"
            )

        header_cells = (
            _th("#") + _th("Row") + _th("Row Key") +
            "".join(
                _th(escape(c), "color:#94a3b8;" if c in info_col_names else "")
                for c in show_cols
            )
        )

        body_rows_html = ""
        for pi, r in enumerate(page_rows):
            global_idx = qa_page * QA_PER_PAGE + pi + 1
            row_bg = "#fef2f2" if not r["__matched__"] else ("#fffbeb" if r["n_diff"] > 0 else "#f0fdf4")

            cells = (
                f"<td style='padding:5px 10px;font-size:0.72rem;color:#94a3b8;font-weight:600;"
                f"border-bottom:1px solid #f1f5f9;'>{global_idx}</td>"
                f"<td style='padding:5px 10px;font-size:0.68rem;color:#475569;font-weight:700;"
                f"border-bottom:1px solid #f1f5f9;white-space:nowrap;'>Row {r['__row_num__']}</td>"
                f"<td style='padding:5px 10px;font-size:0.72rem;font-weight:700;color:#1a2b45;"
                f"border-bottom:1px solid #f1f5f9;white-space:nowrap;max-width:200px;"
                f"overflow:hidden;text-overflow:ellipsis;'>{escape(r['__display_key__'])}</td>"
            )

            for col in show_cols:
                info = r["cols"].get(col, {"match": True, "both_empty": True,
                                           "actual": "", "expected": "", "kind": "compare"})
                is_info_col = info.get("kind") == "info"

                if not r["__matched__"]:
                    cell_bg = "#fee2e2"; icon = "X"
                    a_v = escape(info.get("actual","") or "-"); txt_col = "#991b1b"
                elif info["both_empty"]:
                    cell_bg = "transparent"; icon = "-"
                    a_v = "-"; txt_col = "#cbd5e1"
                elif info["match"]:
                    cell_bg = "#f0fdf4" if not is_info_col else "#f8fafc"
                    icon = "OK"; a_v = escape(info.get("actual","") or "-")
                    txt_col = "#065f46" if not is_info_col else "#64748b"
                else:
                    cell_bg = "#fef2f2" if not is_info_col else "#fafafa"
                    icon = "!="; a_v = escape(info.get("actual","") or "-")
                    txt_col = "#991b1b" if not is_info_col else "#94a3b8"

                e_v = escape(info.get("expected","") or "-")

                if not info["match"] and not info["both_empty"] and r["__matched__"]:
                    if is_info_col:
                        cell_content = (
                            f"<div style='font-size:0.66rem;color:#94a3b8;'>"
                            f"A: {a_v}<br>E: {e_v}</div>"
                        )
                    else:
                        cell_content = (
                            f"<div style='font-size:0.66rem;font-weight:700;'>"
                            f"<span style='color:#ef4444;'>A: {a_v}</span><br>"
                            f"<span style='color:#10b981;'>E: {e_v}</span></div>"
                        )
                else:
                    cell_content = (
                        f"<span style='font-size:0.66rem;font-weight:600;color:{txt_col};'>"
                        f"{icon} {a_v}</span>"
                    )

                cells += (
                    f"<td style='padding:4px 8px;background:{cell_bg};"
                    f"border-bottom:1px solid #f1f5f9;border-left:1px solid #f1f5f9;"
                    f"max-width:160px;'>{cell_content}</td>"
                )

            body_rows_html += f"<tr style='background:{row_bg};'>{cells}</tr>"

        st.markdown(
            f"""
            <div style="overflow-x:auto;border-radius:10px;border:1px solid #e2e8f0;
                box-shadow:0 1px 4px rgba(0,0,0,0.06);max-height:520px;overflow-y:auto;">
              <table style="border-collapse:collapse;width:100%;min-width:600px;">
                <thead><tr>{header_cells}</tr></thead>
                <tbody>{body_rows_html}</tbody>
              </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_pagination("qa_page", qa_page, total_qa_pages, key_suffix="qa", show_page_text=True)

    if missing_keys:
        render_divider()
        st.markdown(
            f"<div class='cx-meta' style='color:var(--red);'>&#9888; {len(missing_keys)} rows in Expected not found in Actual</div>",
            unsafe_allow_html=True,
        )
        miss_html = "".join(
            f"<span style='font-size:0.72rem;background:#fee2e2;color:#991b1b;"
            f"border-radius:5px;padding:2px 8px;margin:2px;display:inline-block;'>"
            f"{escape(k)}</span>"
            for k in missing_keys[:50]
        )
        st.markdown(f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>{miss_html}</div>", unsafe_allow_html=True)
        if len(missing_keys) > 50:
            st.markdown(
                f"<div style='font-size:0.72rem;color:#94a3b8;margin-top:4px;'>... and {len(missing_keys)-50} more</div>",
                unsafe_allow_html=True,
            )