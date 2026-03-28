from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import os
import io

app = Flask(__name__)

CSV_PATH = os.path.join(os.path.dirname(__file__), "master_list.csv")

HIDDEN_COLUMNS = [
    "Request Date", "DCS Samati", "Samati Date",
    "Belt Demand in Samati", "Date of Installation",
    "Latitude", "Longitude"
]

def load_data():
    df = pd.read_csv(CSV_PATH, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df.fillna("")
    return df

def apply_filters(df, args):
    search               = args.get("search", "").strip().lower()
    lot                  = args.get("lot", "")
    installation_status  = args.get("installation_status", "")
    farm_status          = args.get("farm_status", "")
    installed_from       = args.get("installed_from", "")
    installed_to         = args.get("installed_to", "")
    cancelled_before     = args.get("cancelled_before", "")

    if lot:
        df = df[df["Lot"] == lot]
    if installation_status:
        df = df[df["Installation Status"] == installation_status]
    if farm_status:
        df = df[df["FARM STATUS"] == farm_status]

    if installed_from:
        df = df[df["Installed Date"] >= installed_from]
    if installed_to:
        df = df[df["Installed Date"] <= installed_to]

    # Show farms installed BEFORE the selected cancellation date
    if cancelled_before:
        df = df[(df["Installed Date"] != "") & (df["Installed Date"] < cancelled_before)]

    if search:
        mask = df.apply(lambda row: row.astype(str).str.lower().str.contains(search, na=False).any(), axis=1)
        df = df[mask]

    return df

@app.route("/")
def index():
    df = load_data()
    lots                  = sorted(df["Lot"].unique().tolist())
    installation_statuses = sorted(df["Installation Status"].unique().tolist())
    farm_statuses         = sorted(df["FARM STATUS"].unique().tolist())

    s = compute_stats(df)
    total_records     = s["total_records"]
    installed_devices = s["installed_devices"]
    removed_devices   = s["removed_devices"]
    installed_farms   = s["installed_farms"]

    visible_columns = [c for c in df.columns if c not in HIDDEN_COLUMNS]

    return render_template(
        "index.html",
        lots=lots,
        installation_statuses=installation_statuses,
        farm_statuses=farm_statuses,
        total_records=total_records,
        installed_devices=installed_devices,
        removed_devices=removed_devices,
        installed_farms=installed_farms,
        columns=visible_columns,
    )

def compute_stats(df):
    df_num = df.copy()
    df_num["Belt Demand in Samati - Revised"] = pd.to_numeric(df_num["Belt Demand in Samati - Revised"], errors="coerce").fillna(0)
    df_num["Cancelled Devices"] = pd.to_numeric(df_num["Cancelled Devices"], errors="coerce").fillna(0)
    return {
        "total_records":     len(df),
        "installed_devices": int(df_num.loc[df_num["Installation Status"] == "INSTALLED", "Belt Demand in Samati - Revised"].sum()),
        "removed_devices":   int(df_num.loc[df_num["FARM STATUS"] == "REMOVED", "Cancelled Devices"].sum()),
        "installed_farms":   int((df["FARM STATUS"].isin(["ACTIVE", "INSTALLED"])).sum()),
    }

@app.route("/api/data")
def api_data():
    df       = load_data()
    df       = apply_filters(df, request.args)
    sort_col = request.args.get("sort", "")
    sort_dir = request.args.get("dir", "asc")
    page     = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    if sort_col and sort_col in df.columns:
        df = df.sort_values(by=sort_col, ascending=(sort_dir == "asc"))

    stats          = compute_stats(df)
    total_filtered = len(df)
    start          = (page - 1) * per_page
    df_page        = df.iloc[start: start + per_page]

    visible = [c for c in df_page.columns if c not in HIDDEN_COLUMNS]
    df_page = df_page[visible]

    return jsonify({
        "total":    total_filtered,
        "page":     page,
        "per_page": per_page,
        "rows":     df_page.to_dict(orient="records"),
        "stats":    stats,
    })

@app.route("/api/download")
def api_download():
    df       = load_data()
    df       = apply_filters(df, request.args)
    sort_col = request.args.get("sort", "")
    sort_dir = request.args.get("dir", "asc")
    if sort_col and sort_col in df.columns:
        df = df.sort_values(by=sort_col, ascending=(sort_dir == "asc"))

    visible = [c for c in df.columns if c not in HIDDEN_COLUMNS]
    df = df[visible]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Master")
        ws = writer.sheets["Master"]
        for col_cells in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col_cells), default=10)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 40)

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="master_list_filtered.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    app.run(debug=True)
