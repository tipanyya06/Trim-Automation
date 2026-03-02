import io
import pandas as pd

# Must stay in sync with NEW_COLUMNS in validators/filler.py
NEW_COLUMNS = [
    "Main Label", "Main Label Color", "Main Label Supplier",
    "Main Label 2- Gloves", "Main Label Color2", "Main Label Supplier2",
    "Hangtag", "Hangtag Supplier",
    "Hangtag 2", "Hangtag Supplier2",
    "Hangtag3", "Hangtag Supplier3",
    "Micropak Sticker -Gloves", "Micropak Sticker Supplier",
    "Size Label Woven - Gloves", "Size Label Supplier",
    "Size Sticker -Gloves", "Size Sticker Supplier -Gloves",
    "Care Label", "Care Label Color",
    "Content Code -Gloves", "TP FC - Gloves", "Care Code-Gloves",
    "Content Code", "TP FC", "Care Code",
    "Care Supplier",
    "RFID w/o MSRP", "RFID w/o MSRP Supplier",
    "RFID Stickers", "RFID Stickers Supplier",
    "UPC Bag Sticker (Polybag)", "UPC Supplier",
    "TP STATUS", "TP DATE", "PRODUCT STATUS", "REMARKS",
    "Validation Status",
]

# Columns that are glove-specific — highlighted differently
_GLOVE_COLUMNS = {
    "Main Label 2- Gloves", "Main Label Color2", "Main Label Supplier2",
    "Micropak Sticker -Gloves", "Micropak Sticker Supplier",
    "Size Label Woven - Gloves", "Size Label Supplier",
    "Size Sticker -Gloves", "Size Sticker Supplier -Gloves",
    "Content Code -Gloves", "TP FC - Gloves", "Care Code-Gloves",
}

# ── Supplier alias normalization ──────────────────────────────────────────────
# "Bao Shen" and "Bao Shen (Apparel)" → "PT BSN"
_SUPPLIER_ALIASES: list[tuple[str, str]] = [
    ("bao shen", "PT BSN"),
]


def _normalize_supplier_alias(value: str) -> str:
    """Replace known supplier aliases in any cell value."""
    if not value or not isinstance(value, str):
        return value
    vl = value.lower()
    for fragment, canonical in _SUPPLIER_ALIASES:
        if fragment in vl:
            return canonical
    return value


def _apply_supplier_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply supplier alias normalization to every cell in the DataFrame.
    Runs once before writing to Excel so both sheets are clean.
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda v: _normalize_supplier_alias(str(v)) if pd.notna(v) else v
            )
    return df


def export_to_excel(result_df: pd.DataFrame, original_df: pd.DataFrame) -> bytes:
    # Apply alias normalization before writing
    result_df   = _apply_supplier_aliases(result_df)
    if original_df is not None and not original_df.empty:
        original_df = _apply_supplier_aliases(original_df)

    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        result_df.to_excel(writer, index=False, sheet_name="Validated BOM")
        if original_df is not None and not original_df.empty:
            original_df.to_excel(writer, index=False, sheet_name="Original")

        wb   = writer.book
        ws   = writer.sheets["Validated BOM"]
        cols = list(result_df.columns)

        # ── Shared base properties ─────────────────────────────────────────
        _base_header = {"bold": True, "border": 1, "text_wrap": True,
                        "align": "center", "valign": "vcenter"}
        _base_cell   = {"border": 1, "align": "center", "valign": "vcenter"}

        # ── Formats ────────────────────────────────────────────────────────
        fmt_header       = wb.add_format({**_base_header, "bg_color": "#D9D9D9"})
        fmt_new_header   = wb.add_format({**_base_header, "bg_color": "#BDD7EE"})
        fmt_glove_header = wb.add_format({**_base_header, "bg_color": "#E2EFDA"})

        fmt_new_cell     = wb.add_format({**_base_cell, "bg_color": "#DEEAF1"})
        fmt_glove_cell   = wb.add_format({**_base_cell, "bg_color": "#EBF5E1"})
        fmt_validated    = wb.add_format({**_base_cell, "bg_color": "#C6EFCE",
                                          "font_color": "#276221"})
        fmt_partial      = wb.add_format({**_base_cell, "bg_color": "#FFEB9C",
                                          "font_color": "#9C5700"})
        fmt_error        = wb.add_format({**_base_cell, "bg_color": "#FFC7CE",
                                          "font_color": "#9C0006"})
        fmt_default      = wb.add_format({**_base_cell})

        # ── Header row ─────────────────────────────────────────────────────
        for col_idx, col_name in enumerate(cols):
            if col_name in _GLOVE_COLUMNS:
                fmt = fmt_glove_header
            elif col_name in NEW_COLUMNS:
                fmt = fmt_new_header
            else:
                fmt = fmt_header
            ws.write(0, col_idx, col_name, fmt)

        # ── Data rows ──────────────────────────────────────────────────────
        for row_idx, (_, row) in enumerate(result_df.iterrows()):
            excel_row = row_idx + 1
            status    = str(row.get("Validation Status", ""))

            for col_idx, col_name in enumerate(cols):
                val = row[col_name]
                val = "" if pd.isna(val) else val

                if col_name == "Validation Status":
                    if "✅" in status:
                        fmt = fmt_validated
                    elif "⚠️" in status:
                        fmt = fmt_partial
                    else:
                        fmt = fmt_error
                elif col_name in _GLOVE_COLUMNS:
                    fmt = fmt_glove_cell
                elif col_name in NEW_COLUMNS:
                    fmt = fmt_new_cell
                else:
                    fmt = fmt_default

                ws.write(excel_row, col_idx, val, fmt)

        # ── Auto-fit column widths ─────────────────────────────────────────
        for col_idx, col_name in enumerate(cols):
            max_len = max(
                len(str(col_name)),
                result_df[col_name].astype(str).map(len).max() if not result_df.empty else 0,
            )
            ws.set_column(col_idx, col_idx, min(max_len + 2, 50))

        # ── Freeze top row ─────────────────────────────────────────────────
        ws.freeze_panes(1, 0)

        # ── Apply centering to Original sheet too if present ───────────────
        if original_df is not None and not original_df.empty and "Original" in writer.sheets:
            ws_orig      = writer.sheets["Original"]
            orig_cols    = list(original_df.columns)
            fmt_orig_hdr = wb.add_format({**_base_header, "bg_color": "#D9D9D9"})
            fmt_orig_cell = wb.add_format({**_base_cell})

            for col_idx, col_name in enumerate(orig_cols):
                ws_orig.write(0, col_idx, col_name, fmt_orig_hdr)

            for row_idx, (_, row) in enumerate(original_df.iterrows()):
                for col_idx, col_name in enumerate(orig_cols):
                    val = row[col_name]
                    val = "" if pd.isna(val) else val
                    ws_orig.write(row_idx + 1, col_idx, val, fmt_orig_cell)

            for col_idx, col_name in enumerate(orig_cols):
                max_len = max(
                    len(str(col_name)),
                    original_df[col_name].astype(str).map(len).max() if not original_df.empty else 0,
                )
                ws_orig.set_column(col_idx, col_idx, min(max_len + 2, 50))

            ws_orig.freeze_panes(1, 0)

    return buffer.getvalue()


def export_to_csv(df: pd.DataFrame) -> bytes:
    # Apply alias normalization to CSV export too
    df = _apply_supplier_aliases(df)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")