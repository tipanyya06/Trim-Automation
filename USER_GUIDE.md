# Columbia BOM Automation - User Guide

## What is BOM Automation?

**BOM** stands for **Bill of Materials** — a detailed list of all the components (parts, labels, colors, materials) that go into making a Columbia product.

This system **automatically extracts** BOM information from PDF documents and **matches** them against your Excel specifications to ensure everything is correct before production.

---

## How the System Works

### **The Big Picture**

```
PDF files with BOM data
    ↓
System reads & extracts information
    ↓
System matches extracted data to your Excel file
    ↓
System checks if everything is correct
    ↓
You review & export the results
```

---

## Step-by-Step User Instructions

### **Tab 1: PDF Extraction** 📄

This is where you upload the PDF files containing BOM data.

#### What to do:
1. **Click "Click to add PDF files"** button
2. **Select one or more PDF files** from your computer
3. **Wait for the system** to read and extract the information (usually 5-30 seconds depending on file size)
4. **Review the extracted data** in the preview

#### What the system does:
- ✅ Reads the PDF and finds the style number (e.g., "CA2024")
- ✅ Extracts the season, design name, and production details
- ✅ Identifies all components (labels, shells, insulation, packaging, etc.)
- ✅ Detects color information and measurements
- ✅ Looks for detail sketch pages (shows thread colors for embroidery)

#### What you'll see:
- **Style Number**: E.g., "CA2024" — This unique identifier is used to match the PDF to your Excel file
- **Season**: E.g., "S1" (Spring 1) or "F1" (Fall 1)
- **Design**: Product name
- **LO**: Line slot number
- **Sections**: Number of different data tables found in the PDF
- **Colorways**: How many color variations of this product
- **📄 Sketch**: Shows ✓ if detail sketch (thread colors) found, ✗ if missing

---

### **Tab 2: BOM Comparison** 🔍

This is where the system **matches PDFs to your Excel file** and checks if everything is correct.

#### What to do:
1. **Click "Upload Excel file"** button
2. **Select your master Excel file** containing product specifications
3. **Wait for automatic matching** (system finds matching rows by style number)
4. **Review validation results** for each BOM:
   - **✓ PASS** (Green) = Everything matches perfectly
   - **⚠ WARNING** (Yellow) = Minor issues found (extra components, missing colors)
   - **✗ ERROR** (Red) = Critical problems (mismatched colors, missing required items)

#### How the System Matches BOMs

**The system matches your PDFs to Excel rows using the Style Number:**

1. **Extracts Style Number from PDF**
   - Example: PDF shows style "CA2024"

2. **Searches Excel for matching Style**
   - Looks in the Excel file for "CA2024"
   - Finds the row with this style

3. **Compares PDF data to Excel row**
   - PDF says: "Color = Black"
   - Excel says: "Color = Black"
   - ✅ MATCH!

#### How Color Matching Works

The system validates colors in multiple ways:

**1. Color BOM (Colorway Matching)**
- Each product has different color variations called "colorways" (e.g., 256-Black, 257-Navy, 258-Red)
- System checks that the PDF colorway colors match Excel specifications
- Example: If colorway 256 is supposed to be Black, the system confirms it is Black in the PDF

**2. Color Specification Sheet**
- For components that are colored (labels, thread, etc.)
- System verifies the actual colors listed in the PDF match what's specified in Excel

**3. Detail Sketch (Thread Colors)**
- For embroidered items with specific thread colors
- System checks the detail sketch page in the PDF
- Example: If embroidery uses Black/White/Red threads, it confirms that's what's listed

#### What Information Gets Validated

The system checks:
- ✓ **Component materials** (fabric codes, thread codes)
- ✓ **Component suppliers** (which company provides the label, tag, etc.)
- ✓ **Colors** for each colorway
- ✓ **Care labels** (washing instructions)
- ✓ **Content codes** (fabric content percentages)
- ✓ **Hangtags** (price/branding tags)
- ✓ **RFID components** (if applicable)
- ✓ **Packaging** (boxes, bags, stickers)

---

### **Tab 3: Results & Export** 📊

Review all validated BOMs in one place and download the results.

#### What to do:
1. **View the results table** showing all BOMs in a summary
2. **Filter by status** if needed (to see only Passed, Warnings, or Errors)
3. **Download as Excel** — Click "Export to Excel" to get a detailed spreadsheet
4. **Download as CSV** — Click "Export to CSV" for a simpler format

#### What you can see:
- **Style**: Product style number
- **Status**: Pass ✓ / Warning ⚠ / Error ✗
- **Color**: Main color of the product
- **Sections**: How many data tables (color bom, costing, etc.) were found
- **Colorways**: How many colors this product comes in
- **Detail Sketch**: Whether embroidery thread colors were found

#### Using the Export Files

**Excel Export:**
- Most detailed format
- Contains all component information
- Includes validation notes and errors
- Can be shared with designers, buyers, and suppliers

**CSV Export:**
- Simple text format
- Works in any spreadsheet program
- Easier to share via email
- Good for quick reviews

---

### **Tab 4: QA Comparison** 🧪

Quality Assurance checks to ensure consistency across batches.

#### What to do:
1. **Select previous batch data** (from previous exports)
2. **Compare current BOMs** to previous batches
3. **Identify inconsistencies** (e.g., "This supplier was used before, but not now")
4. **Review change log** to see what changed between batches

#### What it checks:
- ✓ Same suppliers used consistently
- ✓ Same color codes for same colorways
- ✓ No missing components from previous versions
- ✓ Material codes haven't changed unexpectedly

---

## Understanding the Status Indicators

### **PASS ✓ (Green)**
Everything matches perfectly between PDF and Excel. The BOM is ready for production.

### **WARNING ⚠ (Yellow)**
Minor issues found, but not critical:
- Extra components in PDF that weren't in Excel
- Missing optional information (e.g., no supplier listed)
- Color names are slightly different but refer to the same color
- Some embroidery details differ from standard

**Action:** Review the differences. Usually safe to proceed, but confirm with designer.

### **ERROR ✗ (Red)**
Critical problems found. Do NOT proceed to production:
- Color mismatch (PDF says Black, Excel says Navy)
- Missing required components (care label missing)
- Supplier change from approved vendor
- Material code incorrect
- Colorway specification doesn't match

**Action:** Contact designer or supplier to fix the PDF or Excel before proceeding.

---

## Common Questions

### **Q: How do I know if my PDF will work?**
A: The system works best with official Columbia BOM PDFs. As long as the PDF contains:
- Style numbers clearly labeled
- Color/colorway information
- Component specifications
- Supplier details

Then it will work! ✅

### **Q: What if the system can't find the matching Excel row?**
A: This usually means:
- The style number in the PDF doesn't exactly match the Excel file
- The PDF style might have extra spaces or different formatting
- Double-check that the style number is typed exactly the same in both files

### **Q: What does "Detail Sketch" mean when it shows ✗?**
A: It means the PDF doesn't have a detail sketch page with embroidery thread colors. This is only needed if the product has embroidered designs. If it's a printed or plain product, you can ignore this.

### **Q: Can I upload multiple PDFs at once?**
A: **Yes!** The system can process multiple PDFs in one upload. It will:
- Extract all PDFs in parallel (faster processing)
- Match each to the Excel file automatically
- Show you all results together

### **Q: What happens to my data?**
A: Your data stays in your current session only. When you:
- Close the browser → all data is cleared
- Refresh the page → you start fresh
- Sign out → data is deleted

For safety, **always export and download your results** before closing or refreshing.

### **Q: Can I fix errors and re-upload?**
A: **Yes!** If you find errors:
1. Fix the PDF or Excel file
2. Come back to the app
3. Upload the corrected files
4. The system will reprocess and update the results

---

## Best Practices

### **For Accurate Results:**

1. **Use official Columbia BOM PDFs**
   - Extracted from the official design database
   - Not hand-created or modified PDFs

2. **Keep Excel format consistent**
   - Use the approved template
   - Don't add extra columns or rearrange columns
   - Save as .xlsx (Excel format)

3. **Match style numbers exactly**
   - Ensure PDFs and Excel use the same style number format
   - No extra spaces, uppercase/lowercase should match

4. **Upload in batches**
   - For large numbers of BOMs (50+), split into smaller batches
   - Process 10-20 at a time for faster results

5. **Review errors immediately**
   - Don't ignore ✗ Error status
   - Contact designer/supplier same day
   - Fix and reprocess before production

6. **Export before closing**
   - Always download your results
   - Keep a backup copy
   - Share with relevant teams immediately

---

## Workflow Examples

### **Example 1: New Product Launch**

```
Monday-Wednesday: Upload 15 new product PDFs
↓
System extracts all BOMs
↓
Compare against new Excel template
↓
All 15 show PASS status ✓
↓
Export to Excel
↓
Share with production team Wednesday EOD
↓
Production can start Thursday
```

### **Example 2: Finding Color Issues**

```
Upload BOM PDF for style "CA2024-Red"
↓
System shows WARNING ⚠
Reason: "Colorway colors don't match specification"
↓
Investigation: Colorway 256 in PDF shows "Navy" but Excel says "Black"
↓
Contact designer: "Did we approve Navy for 256?"
↓
Designer confirms: "Yes, we changed it to Navy last week"
↓
Update Excel to "Navy"
↓
Re-upload PDF
↓
Now shows PASS ✓
↓
Production approved!
```

### **Example 3: Supplier Verification**

```
Upload BOM PDF for embroidered beanie
↓
System shows PASS ✓ for colors and materials
↓
Check Tab 4 (QA): Compare to last season's version
↓
Notice: Different supplier for hangtag (was PT BSN, now Avery Dennison)
↓
Is this intentional? Check with sourcing team
↓
Confirmed supplier change is approved
↓
Proceed to production with new supplier
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **"Oh no!" error when uploading PDF** | The PDF file might be corrupted. Try downloading it again from the official source and re-upload. |
| **PDF uploaded but no data appears** | The PDF might not be a BOM document. Ensure it's an official Columbia BOM PDF. |
| **Style not found in Excel** | Check that the style number in the PDF exactly matches the Excel file (same spelling, spacing, case). |
| **Colors showing as mismatch but they look the same** | Color names might be spelled differently. Contact design team to confirm if they're the same color. |
| **Export file is empty** | Make sure you completed validation in Tab 2 before trying to export. |
| **Can't find my old results** | Results only stay in your current session. Always download and save your exports! |

---

## Support & Contact

If you encounter issues not listed above:

1. **Check the browser console** (Press F12 → Console tab)
2. **Note any error messages** you see
3. **Take a screenshot** of the error
4. **Contact your system administrator** with the error details

---

## System Summary

| Feature | What It Does |
|---------|-------------|
| **PDF Extraction** | Reads BOM PDFs and pulls out all component info |
| **Auto-Matching** | Finds the correct Excel row using style number |
| **Color Validation** | Compares colors between PDF and Excel specifications |
| **Component Verification** | Checks all parts, suppliers, and materials |
| **Status Reporting** | Shows PASS/WARNING/ERROR for each BOM |
| **Export Options** | Download results as Excel or CSV for sharing |
| **QA Tracking** | Compare current BOMs to previous versions |

---

**Last Updated:** March 10, 2026

**Version:** 1.0

**System:** Columbia BOM Automation

---
