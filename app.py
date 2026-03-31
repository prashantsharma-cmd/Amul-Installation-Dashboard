from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import numpy as np
import os
import io
import time

app = Flask(__name__)

SHEET_ID  = "12gl_Ci2m_SQIBxlm-Z-KxniSKatgHqqq"
SHEET_GID = "753760495"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

HIDDEN_COLUMNS = [
    "Request Date", "DCS Samati", "Samati Date",
    "Belt Demand in Samati", "Date of Installation",
    "Latitude", "Longitude"
]

# Simple in-memory cache — avoids hitting Google on every request
_cache = {"df": None, "ts": 0}
CACHE_TTL = 300  # 5 minutes

def load_data():
    now = time.time()
    if _cache["df"] is None or (now - _cache["ts"]) > CACHE_TTL:
        df = pd.read_csv(SHEET_URL, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna("")
        _cache["df"] = df
        _cache["ts"] = now
    return _cache["df"].copy()

def apply_filters(df, args):
    search               = args.get("search", "").strip().lower()
    lot                  = args.get("lot", "")
    installation_status  = args.get("installation_status", "")
    farm_status          = args.get("farm_status", "")
    installed_from       = args.get("installed_from", "")
    installed_to         = args.get("installed_to", "")
    cancelled_before     = args.get("cancelled_before", "")

    
    if installed_from or installed_to or cancelled_before:
        # "Installed Date" is stored as M/D/YYYY; convert to datetime for proper comparison
        df["_installed_dt"] = pd.to_datetime(df["Installed Date"], errors="coerce")

        if installed_from:
            from_dt = pd.to_datetime(installed_from, errors="coerce")
            df = df[df["_installed_dt"] >= from_dt]
        if installed_to:
            to_dt = pd.to_datetime(installed_to, errors="coerce")
            df = df[df["_installed_dt"] <= to_dt]

        # Show farms installed BEFORE the selected cancellation date
        if cancelled_before:
            cb_dt = pd.to_datetime(cancelled_before, errors="coerce")
            df = df[df["_installed_dt"].notna() & (df["_installed_dt"] < cb_dt)]

        df = df.drop(columns=["_installed_dt"])
        
    if lot:
        df = df[df["Lot"] == lot]
    if installation_status:
        df = df[df["Installation Status"] == installation_status]
    if farm_status:
        df = df[df["FARM STATUS"] == farm_status]

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
    total_devices     = s["total_devices"]
    installed_devices = s["installed_devices"]
    removed_devices   = s["removed_devices"]
    installed_farms   = s["installed_farms"]

    visible_columns = [c for c in df.columns if c not in HIDDEN_COLUMNS]

    return render_template(
        "index.html",
        lots=lots,
        installation_statuses=installation_statuses,
        farm_statuses=farm_statuses,
        total_devices=total_devices,
        installed_devices=installed_devices,
        removed_devices=removed_devices,
        installed_farms=installed_farms,
        columns=visible_columns,
    )

def compute_stats(df):
    df_num = df.copy()

    # Convert numeric columns safely
    df_num["Belt Demand in Samati - Revised"] = pd.to_numeric(
        df_num["Belt Demand in Samati - Revised"], errors="coerce"
    ).fillna(0)

    df_num["Cancelled Devices"] = pd.to_numeric(
        df_num["Cancelled Devices"], errors="coerce"
    ).fillna(0)

    # --- Core metrics ---
    total_devices = df_num["Belt Demand in Samati - Revised"].sum()

    installed_devices = df_num.loc[
        df_num["Installation Status"] == "INSTALLED",
        "Belt Demand in Samati - Revised"
    ].sum()

    removed_devices = df_num.loc[
        df_num["FARM STATUS"] == "REMOVED",
        "Cancelled Devices"
    ].sum()

    cancelled_devices = df_num.loc[
        df_num["Installation Status"] == "ORDER CANCELLED",
        "Belt Demand in Samati - Revised"
    ].sum()

    duplicate_devices = df_num.loc[
        df_num["Installation Status"] == "DUPLICATE",
        "Belt Demand in Samati - Revised"
    ].sum()
    # --- Pending logic (your formula) ---
    pending_devices = df_num.loc[
        df_num["Installation Status"] == "PENDING",
        "Belt Demand in Samati - Revised"
    ].sum()

    # Prevent negative values (data safety)
    #pending_devices = max(0, pending_devices)

    return {
        "total_devices": int(total_devices),
        "installed_devices": int(installed_devices),
        "removed_devices": int(removed_devices),
        "cancelled_devices": int(cancelled_devices),
        "duplicate_devices": int(duplicate_devices),
        "pending_devices": int(pending_devices),
        "installed_farms": int((df["FARM STATUS"].isin(["ACTIVE", "INSTALLED"])).sum()),
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
