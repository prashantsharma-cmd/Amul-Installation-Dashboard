# Master List Flask App

A searchable, filterable web table for the 12-Lots Master List spreadsheet.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the app**
   ```bash
   python app.py
   ```

3. **Open in browser**
   ```
   http://127.0.0.1:5000
   ```

## Features

- 🔍 **Global search** across all fields (debounced)
- 🗂️ **Filter by** Lot, Installation Status, Farm Status
- ↕️ **Sort** by any column (click column header)
- 📄 **Pagination** with 20 / 50 / 100 rows per page
- 🏷️ **Color-coded badges** for Installation Status and Farm Status
- 📊 **Stats bar** showing total and filtered record counts

## Updating the data

Replace `master_list.csv` with a new export from the spreadsheet and restart the app.
To re-export: open the Google Sheet → File → Download → CSV, then rename to `master_list.csv`.
