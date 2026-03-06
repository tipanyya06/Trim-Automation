"""tabs/pdf_tab.py — PDF Extraction tab."""
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from parsers.pdf_parser import parse_bom_pdf as _parse_bom_pdf_raw
from .utils import (
    render_section_header, render_divider, render_info_banner,
    render_pagination, render_view_toggle,
    _status_style, _status_accent_color, _style_color_hint,
    _style_validation_status, _resolve_style_key,
    show_conflict_dialog, show_bom_inspector,
)


@st.cache_data(show_spinner=False, max_entries=50)
def _parse_bom_pdf_cached(raw_bytes: bytes):
    import io
    return _parse_bom_pdf_raw(io.BytesIO(raw_bytes))


def render_pdf_tab():
    render_section_header("PDF Extraction", "Click any card to view all section data & key IDs", compact=True)
    uploader_key  = f"pdf_uploader_{st.session_state.get('pdf_uploader_key', 0)}"
    uploaded_pdfs = st.file_uploader(
        "Click to add PDF files", type=["pdf"], accept_multiple_files=True,
        key=uploader_key, label_visibility="collapsed",
        help="Upload one or more PDFs. Each PDF is matched to Excel rows by style number.",
    )
    if not uploaded_pdfs:
        render_info_banner("Upload one or more Columbia BOM PDFs to start extraction.")
        st.session_state.pop("pending_conflicts", None)
        return

    bom_dict        = st.session_state.get("bom_dict", {})
    pdf_bytes_store = st.session_state.get("pdf_bytes_store", {})
    pdf_hashes      = st.session_state.get("pdf_hashes", {})

    pdf_data_list = []
    for f in uploaded_pdfs:
        raw = f.read()
        fhash = hashlib.md5(raw).hexdigest()
        pdf_data_list.append((f.name, raw, fhash))
    current_fnames = {fname for fname, _, _ in pdf_data_list}

    # Remove stale BOMs from removed files
    stale_hashes = {pdf_hashes.pop(fn) for fn in list(pdf_hashes) if fn not in current_fnames}
    for style in list(bom_dict):
        raw = pdf_bytes_store.get(style)
        if raw and hashlib.md5(raw).hexdigest() in stale_hashes:
            bom_dict.pop(style, None)
            pdf_bytes_store.pop(style, None)

    to_parse = [(fn, rb, fh) for fn, rb, fh in pdf_data_list if pdf_hashes.get(fn) != fh]
    pending_conflicts = st.session_state.get("pending_conflicts", None)

    if to_parse and not pending_conflicts:
        seen_fhashes   = set()
        unique, dups   = [], []
        for idx, (fn, rb, fh) in enumerate(pdf_data_list):
            if fh in seen_fhashes:
                dups.append((fn, rb, fh, idx))
            else:
                if pdf_hashes.get(fn) != fh:
                    unique.append((fn, rb, fh, idx))
                seen_fhashes.add(fh)

        pre_parsed = {}
        if unique:
            total = len(unique)
            bar   = st.progress(0, text=f"Parsing {total} PDF(s)...")
            txt   = st.empty()
            done, parsed_styles = 0, []
            with ThreadPoolExecutor(max_workers=min(8, total)) as ex:
                def _pp(args):
                    fn, rb, fh, idx = args
                    bd    = _parse_bom_pdf_cached(rb)
                    style = bd.get("metadata", {}).get("style") or fn
                    return (fn, idx), style, bd, rb, fh
                for fut in as_completed({ex.submit(_pp, a): a[0] for a in unique}):
                    key, style, bd, rb, fh = fut.result()
                    pre_parsed[key] = (style, bd, rb, fh)
                    parsed_styles.append(style)
                    done += 1
                    bar.progress(done / total, text=f"Parsed {done} / {total}")
                    txt.markdown(
                        f"<div style='font-size:0.78rem;color:#9ca3af;'>✓ {', '.join(parsed_styles[-3:])}"
                        f"{'...' if len(parsed_styles) > 3 else ''}</div>",
                        unsafe_allow_html=True,
                    )
            bar.progress(1.0, text=f"✅ Done — {len(parsed_styles)} BOM(s) parsed")
            txt.empty()

        style_seen, conflicts, non_conflicts = {}, {}, {}
        for key, (style, bd, rb, fh) in pre_parsed.items():
            ek = _resolve_style_key(style, bom_dict)
            if ek is not None:
                conflicts[f"{style}__{key[1]}"] = dict(style=style, fname=key[0], bom_data=bd, raw_bytes=rb, fhash=fh, existing_key=ek, conflict_reason="already_loaded")
            elif style in style_seen:
                conflicts[f"{style}__{key[1]}"] = dict(style=style, fname=key[0], bom_data=bd, raw_bytes=rb, fhash=fh, existing_key=style, conflict_reason="duplicate_in_batch")
            else:
                style_seen[style] = key
                non_conflicts[style] = dict(fname=key[0], bom_data=bd, raw_bytes=rb, fhash=fh)

        all_info = {**non_conflicts, **{c["style"]: c for c in conflicts.values()}}
        for fn, rb, fh, idx in dups:
            ms = next((s for s, info in all_info.items() if hashlib.md5(info["raw_bytes"]).hexdigest() == fh), None)
            if ms is None:
                continue
            ek = _resolve_style_key(ms, bom_dict) or ms
            conflicts[f"{ms}__{idx}"] = dict(
                style=ms, fname=fn, fhash=fh, existing_key=ek, conflict_reason="duplicate_file",
                bom_data=bom_dict.get(ek, non_conflicts.get(ms, {}).get("bom_data", {})),
                raw_bytes=rb,
            )

        for style, info in non_conflicts.items():
            bom_dict[style]           = info["bom_data"]
            pdf_bytes_store[style]    = info["raw_bytes"]
            pdf_hashes[info["fname"]] = info["fhash"]

        st.session_state.update(bom_dict=bom_dict, pdf_bytes_store=pdf_bytes_store, pdf_hashes=pdf_hashes)
        st.session_state["pending_conflicts"] = conflicts if conflicts else {}
        st.rerun()

    pending_conflicts = st.session_state.get("pending_conflicts", {})
    if pending_conflicts:
        ck   = next(iter(pending_conflicts))
        info = pending_conflicts[ck]
        show_conflict_dialog(ck, info, bom_dict, pdf_bytes_store, pdf_hashes)
        return

    if not bom_dict:
        render_info_banner("Upload one or more Columbia BOM PDFs. Each PDF's style is auto-detected and used to match rows in your Excel.")
        return

    st.markdown(
        f'<div class="cx-banner" style="border-color:#9ad8b7;background:#ecf9f2;color:#167f52;">'
        f'All {len(uploaded_pdfs)} PDF(s) loaded. {len(bom_dict)} BOM(s) in session.</div>',
        unsafe_allow_html=True,
    )
    render_divider()
    st.markdown('<div class="cx-meta">Loaded BOMs</div>', unsafe_allow_html=True)

    all_styles = list(bom_dict.keys())
    summary_rows = []
    for style in all_styles:
        bom  = bom_dict[style]
        meta = bom.get("metadata", {})
        sects = [k for k, v in bom.items() if k not in ("metadata", "supplier_lookup") and isinstance(v, pd.DataFrame) and not v.empty]
        cb    = bom.get("color_bom", pd.DataFrame())
        summary_rows.append({
            "Style": style, "Season": meta.get("season", "\u2014"),
            "Design": meta.get("design", "\u2014"), "LO": meta.get("production_lo", "\u2014"),
            "Color": _style_color_hint(bom),
            "Sections": len(sects),
            "Colorways": len(cb.columns) if not cb.empty else 0,
            "Status": _style_validation_status(style),
        })

    if "pdf_inspect_style" not in st.session_state and all_styles:
        st.session_state["pdf_inspect_style"] = all_styles[0]

    count_val = sum(1 for r in summary_rows if r["Status"] == "Validated")
    count_err = sum(1 for r in summary_rows if r["Status"] == "Error")
    st.markdown(
        f'<div class="cx-stats" style="grid-template-columns:repeat(3,minmax(0,1fr));">'
        f'<div class="cx-stat-card"><div class="cx-stat-number" style="color:#3569de;">{len(summary_rows)}</div><div class="cx-stat-label">BOMS</div></div>'
        f'<div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--green);">{count_val}</div><div class="cx-stat-label">VALIDATED</div></div>'
        f'<div class="cx-stat-card"><div class="cx-stat-number" style="color:var(--red);">{count_err}</div><div class="cx-stat-label">ERRORS</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    view_mode    = render_view_toggle("loaded_boms_view", default="Grid", label="Loaded BOM View")
    per_page     = 15 if view_mode == "Tile" else 10
    total_pages  = max(1, -(-len(summary_rows) // per_page))
    page_key     = "loaded_boms_page"
    page         = max(0, min(st.session_state.get(page_key, 0), total_pages - 1))
    st.session_state[page_key] = page
    page_rows    = summary_rows[page * per_page: (page + 1) * per_page]
    col_count    = 1 if view_mode == "List" else (3 if view_mode == "Tile" else 2)
    deck_cols    = st.columns(col_count)

    for idx, row in enumerate(page_rows):
        style      = row["Style"]
        global_idx = page * per_page + idx + 1
        status     = row.get("Status", _style_validation_status(style))
        bg, border, fg, label = _status_style(status)
        accent     = _status_accent_color(label)

        with deck_cols[idx % col_count]:
            if view_mode == "List":
                st.markdown(
                    f'<div class="cx-list-row" style="border-left:4px solid {accent};border-radius:10px;'
                    f'padding:12px 16px;margin-bottom:6px;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,0.07);'
                    f'display:flex;align-items:center;gap:14px;">'
                    f'<span style="font-size:0.7rem;font-weight:800;color:#9aabbd;min-width:22px;text-align:right;">{global_idx}</span>'
                    f'<div style="flex:1;min-width:0;">'
                    f'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">'
                    f'<span style="font-size:0.95rem;font-weight:800;color:#1a2b45;">{style}</span>'
                    f'<span style="font-size:0.68rem;font-weight:700;padding:2px 9px;border-radius:999px;'
                    f'background:{bg};border:1px solid {border};color:{fg};">{label}</span></div>'
                    f'<div style="font-size:0.75rem;color:#5a6a82;margin-top:2px;margin-bottom:5px;">{row.get("Design","—")}</div>'
                    f'<div style="display:flex;flex-wrap:wrap;gap:4px;">'
                    f'<span class="cx-chip">Color: {row.get("Color","N/A")}</span>'
                    f'<span class="cx-chip">Season: {row["Season"]}</span>'
                    f'<span class="cx-chip">LO: {row["LO"]}</span>'
                    f'<span class="cx-chip">⊞ {row["Sections"]} Sections</span>'
                    f'<span class="cx-chip">◇ {row["Colorways"]} Colorways</span>'
                    f'</div></div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="cx-style-card" style="border-left:4px solid {accent};border-radius:10px;'
                    f'padding:14px 16px 10px;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,0.08);margin-bottom:8px;">'
                    f'<div class="cx-style-top"><div>'
                    f'<div class="cx-style-id cx-style-id-row">'
                    f'<span style="font-size:0.7rem;color:#9aabbd;font-weight:600;margin-right:4px;">#{global_idx}</span>'
                    f'<span>{style}</span></div>'
                    f'<div class="cx-style-name" style="margin-top:2px;font-size:0.8rem;color:#5a6a82;">{row.get("Design","BOM Style")}</div>'
                    f'</div><div class="cx-status" style="background:{bg};border-color:{border};color:{fg};">{label}</div></div>'
                    f'<div class="cx-chip-row" style="margin-top:8px;">'
                    f'<span class="cx-chip">Color: {row.get("Color","N/A")}</span>'
                    f'<span class="cx-chip">Season: {row["Season"]}</span>'
                    f'<span class="cx-chip">LO: {row["LO"]}</span>'
                    f'</div>'
                    f'<div class="cx-style-footer" style="margin-top:8px;border-top:1px solid #f0f4f8;padding-top:8px;">'
                    f'<div class="cx-footer-meta">'
                    f'<span><span class="cx-count-num">⊞ {row["Sections"]}</span> <span class="cx-count-label">Sections</span></span>'
                    f'<span><span class="cx-count-num">◇ {row["Colorways"]}</span> <span class="cx-count-label">Colorways</span></span>'
                    f'</div><div class="cx-footer-hint">Click to inspect</div></div></div>',
                    unsafe_allow_html=True,
                )
            pfx = "card_hit_list" if view_mode == "List" else "card_hit_grid"
            with st.container(key=f"{pfx}_{idx}"):
                if st.button(" ", key=f"inspect_card_{style}", use_container_width=True):
                    st.session_state["pdf_inspect_style"]    = style
                    st.session_state["inspect_popup_style"]  = style
                    st.rerun()

    render_pagination(page_key, page, total_pages, key_suffix="bom_pg", show_page_text=True)

    popup = st.session_state.get("inspect_popup_style")
    if popup and popup in bom_dict:
        show_bom_inspector(popup, bom_dict[popup])