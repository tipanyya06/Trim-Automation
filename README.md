# Columbia BOM Automation

Uploads Columbia BOM PDFs + a comparison spreadsheet, then auto-fills trim, label, care code, and supplier columns for every row. Export the result to Excel or CSV.

---

## How it works — 3 steps

1. **Upload BOM PDF(s)** — Go to the *PDF Extraction* tab. Drop one or more Columbia BOM PDFs. They parse in parallel.
2. **Upload your comparison file** — Go to *BOM Comparison*. Drop your Excel or CSV. Map the Style Number and Color/Option columns.
3. **Run & export** — Click **▶ Run Validation & Auto-Fill**. Rows are filled automatically. Download the result.

---

## What gets filled in automatically

| Column group | Source section in BOM |
|---|---|
| Main Label, Additional Main Label, Care Label (code + color + supplier) | Color BOM |
| Content Code, TP FC (fiber description), Care Code | Care Report / Content Report |
| Hangtag, Hangtag RFID, RFID Sticker, UPC Sticker — codes + suppliers | Color BOM |
| FOB price per colorway | Costing Detail |

---

## Validation status after running

- ✅ **Validated** — All required fields found and filled. Ready to use.
- ⚠️ **Partial** — Some optional fields are missing. Review before exporting.
- ❌ **Mismatch** — Colorway or style not found in the BOM. Check naming.
- ❌ **Error: No BOM** — No PDF was uploaded for this style. Upload the matching PDF first.

---

## Installation

```bash
cd Trim-Automation/bom_automation
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. If `streamlit` isn't recognized, use `python -m streamlit run app.py`.

---

## File structure

```
bom_automation/
├── app.py                   ← main UI: tabs, upload, validation, export
├── requirements.txt
│
├── parsers/
│   ├── pdf_parser.py        ← reads PDF, detects and routes sections
│   ├── color_bom.py         ← extracts labels, hangtags, suppliers per colorway
│   ├── costing.py           ← extracts FOB pricing
│   └── care_content.py      ← extracts care codes and fiber content
│
├── validators/
│   ├── filler.py            ← orchestrates all column-filling logic
│   └── matcher.py           ← normalizes colorway strings for matching
│
└── exporters/
    ├── excel_exporter.py    ← formatted Excel output
    └── csv_exporter.py      ← plain CSV output
```

---

## Color/Option format support

The matcher accepts any of these formats for the same colorway:

- Code only: `010`
- Code + name: `010-Black` or `010 Black`
- Name only: `Black`

Built-in colorways: 010 Black, 224 Camel Brown, 278 Dark Stone, 429 Everblue, 551 Lavender Pearl.
To add more, edit `KNOWN_COLORWAYS` in `parsers/pdf_parser.py`.

---

## Troubleshooting

**PDF fails to parse**
Make sure it's a real Columbia BOM with formatted tables — scanned/image PDFs won't work.

**Rows show ❌ Error: No BOM**
The style number in your Excel has no matching PDF uploaded. Go to PDF Extraction and upload the correct BOM.

**Old BOM data still showing after removing a file**
Click **🗑 Clear All Data** in the sidebar to fully reset the session, then re-upload only what you need.

**`streamlit: command not found`**
Run `python -m streamlit run app.py`, or activate your virtual environment first.

**Column mapping dropdown is empty**
Your file may be missing a header row or is malformed. Make sure the first row has column names.

---

## Tips

- Upload all style PDFs at once — they're parsed in parallel, so it's fast.
- Use numeric color codes (010, 278…) for the most reliable matching.
- Use the **🔬 Diagnose** expander in the Comparison tab to test a specific Color/Option value and see exactly what the tool finds.
- Validated results are not saved between sessions — export before closing the tab.
- Check ⚠️ Partial rows: usually a secondary label or RFID component wasn't found in the BOM.