# Columbia BOM Automation

Automated Bill of Materials extraction, comparison, validation, and QA for Columbia production workflows.

## What This System Does

The app helps teams move from raw BOM PDFs to validated output files in one Streamlit workflow.

1. Extracts BOM tables and metadata from PDF files.
2. Matches extracted styles/colors with your Excel or CSV comparison file.
3. Runs validation in either quick mode or full purchasing mode.
4. Exports clean output for business use.
5. Supports QA file-to-file comparison for release checks.

## Main Workflow

1. Open PDF Extraction tab and upload one or more BOM PDFs.
2. Open BOM Comparison tab and upload the comparison Excel or CSV file.
3. Choose a validation mode:
   - Quick Trim (Planning): faster, extraction-led check.
   - Trim (Purchasing): full run with per-style settings.
4. Review output in Results and download Excel/CSV.
5. Optionally run QA Comparison to compare actual vs expected files.

## Install And Run (Local)

```bash
pip install -r requirements.txt
streamlit run bom_automation/app.py --server.address 127.0.0.1 --server.port 8501
```

Open: http://localhost:8501

## Run Modes (Local And Deployed)

- Local dev (localhost only):

```bash
streamlit run bom_automation/app.py --server.address 127.0.0.1 --server.port 8501
```

- Deployed/default behavior (no forced localhost binding):

```bash
streamlit run bom_automation/app.py
```

The shared `.streamlit/config.toml` intentionally does not hardcode `server.address`, so deployment settings are not impacted.

## Dev Dependency Note

Most developers only need Python + `requirements.txt`.
For some PDF extraction paths, Java (for `tabula-py`) and Ghostscript (for `camelot-py`) may also be required.
See full setup in [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

## Documentation

- User guide: [USER_GUIDE.md](USER_GUIDE.md)
- Developer system documentation: [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)

## Important Notes

- Style matching is driven by style identifiers in PDF metadata and comparison file columns.
- Uploaded data is session-based in Streamlit; refresh/close can clear active state.
- For large batches, process in smaller groups for better responsiveness.

## Live Demo

https://trim-automation-vkcso8plmgews4ujpjrk7z.streamlit.app/

Last updated: March 25, 2026
