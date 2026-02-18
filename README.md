# Columbia BOM Automation

A powerful Streamlit-based application for extracting, validating, and enriching Bill of Materials (BOM) data from Columbia apparel BOMs. Automates the process of matching trim and label specifications across PDF BOMs and comparison spreadsheets.

## 🎯 Overview

This tool streamlines the BOM management workflow for apparel production by:

- **Extracting** structured data from Columbia BOM PDFs (Color BOM, Costing, Care & Content sections)
- **Parsing** supplier, colorway, and pricing information
- **Validating** trim and label specifications against existing inventory
- **Auto-filling** enriched data fields (labels, care codes, suppliers, hanging tags, etc.)
- **Exporting** results in Excel or CSV format for downstream systems

## ✨ Key Features

### PDF Extraction
- Upload Columbia BOM PDFs and automatically parse multiple sections
- Extract Color BOM tables with style codes and colorway information
- Parse costing data with FOB (Freight on Board) pricing
- Extract care codes and content information
- View, search, and preview parsed sections
- Export individual sections or entire BOM in Excel/CSV

### BOM Comparison & Validation
- Upload comparison Excel or CSV files to match against extracted BOM data
- Flexible column mapping (Buyer Style Number, Color/Option)
- Automatic validation and data enrichment:
  - Trim/label supplier lookup from Color BOM
  - Hangtag and RFID specifications
  - Care label and content code assignment
  - FOB pricing extraction
  - Comprehensive validation status reporting
- Color validation with support for multiple color reference formats (code, name, full name)
- Detailed results with validation status indicators:
  - ✅ **Validated**: All required data matched
  - ⚠️ **Partial**: Some data missing but non-critical
  - ❌ **Error**: Critical data missing or mismatched

### Export & Reporting
- Export validated BOMs to Excel (with formatting) or CSV
- Color-coded validation summary with counts
- Comprehensive metadata tracking (Style, Season, Design, Production LO)

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Clone or download this repository:**
   ```bash
   cd Trim-Automation
   ```

2. **Install dependencies:**
   ```bash
   cd bom_automation
   pip install -r requirements.txt
   ```

   Or manually install core packages:
   ```bash
   pip install streamlit pandas openpyxl pdfplumber xlsxwriter
   ```

3. **Run the application:**
   ```bash
   streamlit run app.py
   ```

   The app will open in your browser at `http://localhost:8501`

### Using a Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## 📖 Usage Guide

### Step 1: PDF Extraction

1. Go to the **📄 PDF Extraction** tab
2. Upload your Columbia BOM PDF
3. The system will automatically parse:
   - Color BOM (trim, label, hangtag specifications)
   - Costing data (FOB pricing)
   - Care & Content information
4. Review extracted sections using the section selector
5. Use the search filter to find specific rows
6. Export sections as needed (CSV for single sections, Excel for all)

### Step 2: BOM Comparison & Validation

1. Go to the **🔍 BOM Comparison & Validation** tab
2. Upload your comparison Excel or CSV file containing:
   - Buyer Style Number (e.g., CL2880)
   - Color/Option information (accepts codes like "010" or names like "Black")
3. Map the columns in your file:
   - Select the column containing Buyer Style Numbers
   - Select the column containing Color/Option information
4. Review the comparison data (first 50 rows shown)
5. Click **▶ Run Validation & Auto-Fill** to process
6. Review the validation summary and detailed results
7. Export the enriched BOM in your preferred format

### Color Reference Format Support

The system recognizes colorways in multiple formats:
- **Code only**: "010"
- **Code + Name**: "010-Black" or "010 Black"
- **Full name**: "Black"
- **Alternative names**: "Camel Brown", "Dark Stone", "Everblue", "Lavender Pearl"

## 📁 Project Structure

```
bom_automation/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── parsers/
│   ├── pdf_parser.py              # PDF extraction and parsing logic
│   ├── color_bom.py               # Color BOM data extraction
│   ├── costing.py                 # Costing/FOB data extraction
│   └── care_content.py            # Care codes and content extraction
├── validators/
│   ├── filler.py                  # Main validation and enrichment logic
│   ├── matcher.py                 # Color and specification matching
│   └── matcher.py                 # Colorway normalization
└── exporters/
    ├── excel_exporter.py          # Excel export with formatting
    └── csv_exporter.py            # CSV export functionality
```

### Core Modules

- **app.py**: Streamlit frontend with tabs for extraction and validation workflows
- **pdf_parser.py**: Extracts tables from PDFs using pdfplumber
- **color_bom.py**: Parses color-specific BOM data (trims, labels, suppliers)
- **costing.py**: Extracts supplier and pricing information
- **care_content.py**: Extracts care codes and content classifications
- **filler.py**: Orchestrates validation and automatically fills enriched data columns
- **matcher.py**: Handles colorway matching and normalization logic

## 📦 Dependencies

- **streamlit** - Web application framework
- **pandas** - Data manipulation and analysis
- **pdfplumber** - PDF text and table extraction
- **openpyxl** - Excel file reading/writing
- **xlsxwriter** - Excel formatting support

See `requirements.txt` for specific versions.

## 🎨 Features

### Advanced Validation
- **Colorway Matching**: Normalizes and matches colors across different reference formats
- **Supplier Lookup**: Automatically retrieves supplier information from Color BOM
- **FOB Pricing**: Extracts and validates FOB costs for each colorway
- **Care Code Resolution**: Matches to known care code database
- **Hangtag & RFID**: Identifies and assigns specialty labels and tracking

### UI/UX
- Dark theme with professional design
- Real-time search and filtering
- Progress indicators and status badges
- Detailed validation summaries with visual indicators
- Pre-configured known colorways for Columbia products

## 📝 Known Colorways

The system includes built-in support for Columbia colorways:
- **010** - Black
- **224** - Camel Brown
- **278** - Dark Stone
- **429** - Everblue
- **551** - Lavender Pearl

Additional colorways can be added to the `KNOWN_COLORWAYS` dictionary in [parsers/pdf_parser.py](bom_automation/parsers/pdf_parser.py).

## 🔧 Troubleshooting

### "Failed to parse PDF"
- Ensure PDF is a valid Columbia BOM format
- Check that the PDF contains the expected tables/sections
- Try a different PDF to verify the tool works

### Import errors when running
- Verify all dependencies are installed: `pip install -r requirements.txt`
- If using a virtual environment, ensure it's activated
- Try reinstalling: `pip install --upgrade -r requirements.txt`

### Streamlit not recognized
- Use: `python -m streamlit run app.py` instead of `streamlit run app.py`
- Or add streamlit to your PATH

### Column mapping shows no options
- Ensure your comparison file has a header row
- Check that the file is valid Excel (.xlsx/.xls) or CSV format

## 📊 Validation Status Indicators

| Status | Meaning | Action |
|--------|---------|--------|
| ✅ **Validated** | All required fields matched and filled | Ready for production |
| ⚠️ **Partial** | Some optional fields missing | Review and manually verify |
| ❌ **Mismatch** | Color or style not found in BOM | Verify data accuracy |
| ❌ **Error** | Critical field missing | Cannot proceed |

## 💡 Tips & Best Practices

1. **Before uploading BOMs**: Ensure your comparison file follows Columbia naming conventions
2. **Color codes**: Use the standard colorway codes (010, 224, etc.) for best matching
3. **PDF quality**: Ensure BOM PDFs are clean and tables are well-formatted
4. **Regular exports**: Always export and archive validated BOMs
5. **Error review**: Check validation errors before exporting to catch data issues early

## 📄 License

[Add your license information here]

## 🤝 Support

For issues, questions, or feature requests, please contact the development team.

---

**Last Updated**: February 2026  
**Status**: Active Development
