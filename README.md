# Columbia BOM Automation

Automated Bill of Materials extraction, comparison, validation, and QA for Columbia apparel production.

---

## � Complete User Guide

**For detailed instructions on how to use the system, including:**
- Step-by-step workflow for each tab
- How color and style matching works
- Understanding validation status
- Common questions and troubleshooting

👉 **See [USER_GUIDE.md](USER_GUIDE.md)** ← Start here if you're new!

---

## �🚀 Quick Start

### 1. Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
cd bom_automation
python -m streamlit run app.py
```

App opens at `http://localhost:8501`

---

## 📖 How to Use

### **Tab 1: PDF Extraction** 📄

1. Click **"Add PDF files"** button
2. Select one or more Columbia BOM PDF files
3. System auto-detects style numbers and parses BOM data
4. Review extracted data in the preview panel
5. Cached PDFs can be reused across tabs

### **Tab 2: BOM Comparison** 🔍

1. Upload your **Excel specification file**
2. System auto-matches PDF styles to Excel rows
3. Review validation status for each BOM:
   - ✅ **Pass** — BOM matches specifications
   - ⚠️ **Warning** — Minor discrepancies detected
   - ❌ **Fail** — Critical errors found
4. Resolve conflicts using the conflict dialog if needed
5. Export validated BOMs to Excel/CSV

### **Tab 3: Results & Export** 📊

1. View all validated BOMs in table format
2. Filter by status (Pass/Warning/Fail)
3. Click **"Export to Excel"** or **"Export to CSV"**
4. Download generated report files
5. Review compliance summary

### **Tab 4: QA Comparison** 🧪

1. Load validated BOM data from previous tabs
2. Run quality assurance checks
3. Compare BOMs across batches
4. Generate QA report with findings
5. Export QA documentation

---

## 📋 Standard Workflow

```
1. Upload PDFs (Tab 1)
   ↓
2. Load Excel specifications (Tab 2)
   ↓
3. Validate & review BOMs (Tab 2)
   ↓
4. Export results (Tab 3)
   ↓
5. Run QA checks (Tab 4)
   ↓
6. Download reports
```

---

## 💡 Tips & Keyboard Shortcuts

| Action | How |
|--------|-----|
| Clear cached PDFs | Sidebar → Clear Cache → Refresh (Ctrl+Shift+R) |
| Reload data | Refresh browser (F5 or Ctrl+R) |
| Export all results | Tab 3 → Export button |
| View validation details | Hover over status badge |
| Filter results | Use filter dropdown in results table |

---

## ⚠️ Important Notes

- **PDF Format**: Ensure PDFs follow Columbia BOM standard format
- **Style Matching**: Style numbers in PDF and Excel must match exactly
- **Session Data**: All data is cleared when you close the browser
- **Large Batches**: Process large batches in smaller groups for best performance
- **Cache Size**: System caches up to 50 PDFs per session

---

## 🌐 Live Demo

**Deployed App:** https://trim-automation-vkcso8plmgews4ujpjrk7z.streamlit.app/

---

**Last Updated:** March 10, 2026
