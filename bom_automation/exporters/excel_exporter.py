import io
import pandas as pd

NEW_COLUMNS = [
    "Main Label", "Main Label Color", "Main Label Supplier",
    "Additional Main Label", "Additional Main Label Color",
    "Care Label", "Care Label Color", "Care Label Supplier",
    "Content Code", "TP FC", "Care Code",
    "Hangtag", "Hangtag Supplier",
    "Hangtag (RFID)", "Hangtag (RFID) Supplier",
    "RFID Sticker", "RFID Sticker Supplier",
    "UPC Sticker (Polybag)", "UPC Sticker Supplier",
    "Validation Status",
]


def export_to_excel(result_df: pd.DataFrame, original_df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        result_df.to_excel(writer, index=False, sheet_name="Validated BOM")
        if original_df is not None and not original_df.empty:
            original_df.to_excel(writer, index=False, sheet_name="Original")

        wb  = writer.book
        ws  = writer.sheets["Validated BOM"]
        cols = list(result_df.columns)

        # Formats
        fmt_header     = wb.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1, "text_wrap": True})
        fmt_new_header = wb.add_format({"bold": True, "bg_color": "#BDD7EE", "border": 1, "text_wrap": True})
        fmt_new_cell   = wb.add_format({"bg_color": "#DEEAF1", "border": 1})
        fmt_validated  = wb.add_format({"bg_color": "#C6EFCE", "font_color": "#276221", "border": 1})
        fmt_partial    = wb.add_format({"bg_color": "#FFEB9C", "font_color": "#9C5700", "border": 1})
        fmt_error      = wb.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006", "border": 1})
        fmt_default    = wb.add_format({"border": 1})

        # Header row
        for col_idx, col_name in enumerate(cols):
            fmt = fmt_new_header if col_name in NEW_COLUMNS else fmt_header
            ws.write(0, col_idx, col_name, fmt)

        # Data rows
        for row_idx, (_, row) in enumerate(result_df.iterrows()):
            excel_row = row_idx + 1
            status = str(row.get("Validation Status", ""))

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
                elif col_name in NEW_COLUMNS:
                    fmt = fmt_new_cell
                else:
                    fmt = fmt_default

                ws.write(excel_row, col_idx, val, fmt)

        # Auto-fit column widths
        for col_idx, col_name in enumerate(cols):
            max_len = max(
                len(str(col_name)),
                result_df[col_name].astype(str).map(len).max() if not result_df.empty else 0
            )
            ws.set_column(col_idx, col_idx, min(max_len + 2, 50))

        # Freeze top row
        ws.freeze_panes(1, 0)

    return buffer.getvalue()