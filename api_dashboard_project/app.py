
from flask import Flask, render_template, request, jsonify
import pandas as pd
import sqlite3
import os
from datetime import datetime
app = Flask(__name__)
CSV_FILE = "api_logs_5000.csv"
DB_FILE = "api_logs.db"


if os.path.exists(CSV_FILE) and not os.path.exists(DB_FILE):
    try:
        df = pd.read_csv(CSV_FILE)
        # normalize column names 
        df.columns = [c.strip() for c in df.columns]
        conn = sqlite3.connect(DB_FILE)
        df.to_sql("api_logs", conn, if_exists="replace", index=False)
        conn.commit()
        conn.close()
        print(f"Created {DB_FILE} from {CSV_FILE}")
    except Exception as e:
        print("Failed to create DB from CSV:", e)

def get_connection():
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"{DB_FILE} not found. Provide {CSV_FILE} or create DB.")
    return sqlite3.connect(DB_FILE)

@app.route('/')
def index():
    return render_template("index.html")


@app.route('/api/summary')
def get_summary():
    """Return total requests, error rate, avg response time (with optional filters)."""
    region = request.args.get("region")
    status = request.args.get("status")
    method = request.args.get("method")
    client = request.args.get("client")

    query = "SELECT COUNT(*) as total, SUM(CASE WHEN CAST(StatusCode AS INTEGER) >= 400 THEN 1 ELSE 0 END)*1.0 / COUNT(*) as error_rate, AVG(CAST(ResponseTimeMS AS REAL)) as avg_resp FROM api_logs WHERE 1=1"
    filters = []

    if region:
        query += " AND Region = ?"
        filters.append(region)
    if status:
        query += " AND StatusCode = ?"
        filters.append(status)
    if method:
        query += " AND Method = ?"
        filters.append(method)
    if client:
        query += " AND ClientType = ?"
        filters.append(client)

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, filters)
        row = cur.fetchone()
        conn.close()
    except Exception as e:
        print("get_summary error:", e)
        return jsonify({"total":0, "error_rate":0, "avg_response_time":0})

    if row:
        total = int(row[0] or 0)
        error_rate = float(row[1] or 0)
        avg_response = float(row[2] or 0)
    else:
        total = 0
        error_rate = 0
        avg_response = 0

    return jsonify({
        "total": total,
        "error_rate": round(error_rate * 100, 2) if error_rate else 0,
        "avg_response_time": round(avg_response, 2) if avg_response else 0
    })


@app.route('/api/<metric>')
def get_metric_data(metric):
    """
    Generic metric endpoint.
    Metrics supported:
      - endpoint        -> returns {"labels": [...], "counts": [...]}
          When query param 'endpoint' is provided, returns time-series counts for that endpoint (group by Timestamp)
      - status
      - response_time   -> returns timestamp vs avg response
      - region
      - methods
      - clients
    Optional global filters: region, status, method, client
    """
    
    region = request.args.get("region")
    status = request.args.get("status")
    method = request.args.get("method")
    client = request.args.get("client")
    endpoint_param = request.args.get("endpoint")  # used for drilldown on endpoint

    filters = []
    where = "WHERE 1=1"

    if region:
        where += " AND Region = ?"
        filters.append(region)
    if status:
        where += " AND StatusCode = ?"
        filters.append(status)
    if method:
        where += " AND Method = ?"
        filters.append(method)
    if client:
        where += " AND ClientType = ?"
        filters.append(client)

    conn = get_connection()
    cur = conn.cursor()

    try:
        if metric == "endpoint":
            if endpoint_param:
                # Drilldown: return counts grouped by Timestamp for this endpoint (time-series)
                q = f"SELECT Timestamp, COUNT(*) FROM api_logs {where} AND Endpoint = ? GROUP BY Timestamp ORDER BY Timestamp ASC"
                params = filters + [endpoint_param]
                cur.execute(q, params)
                rows = cur.fetchall()
                labels = [r[0] for r in rows]
                counts = [r[1] for r in rows]
                return jsonify({"labels": labels, "counts": counts})
            else:
                cur.execute(f"SELECT Endpoint, COUNT(*) FROM api_logs {where} GROUP BY Endpoint ORDER BY COUNT(*) DESC", filters)
        elif metric == "status":
            cur.execute(f"SELECT StatusCode, COUNT(*) FROM api_logs {where} GROUP BY StatusCode ORDER BY COUNT(*) DESC", filters)
        elif metric == "response_time":
            try:
                cur.execute(f"SELECT Timestamp, AVG(CAST(ResponseTimeMS AS REAL)) FROM api_logs {where} GROUP BY Timestamp ORDER BY Timestamp ASC")
            except Exception:
                cur.execute(f"SELECT rowid as Timestamp, AVG(CAST(ResponseTimeMS AS REAL)) FROM api_logs {where} GROUP BY rowid ORDER BY rowid ASC")
        elif metric == "region":
            cur.execute(f"SELECT Region, COUNT(*) FROM api_logs {where} GROUP BY Region ORDER BY COUNT(*) DESC", filters)
        elif metric == "methods":
            cur.execute(f"SELECT Method, COUNT(*) FROM api_logs {where} GROUP BY Method ORDER BY COUNT(*) DESC", filters)
        elif metric == "clients":
            cur.execute(f"SELECT ClientType, COUNT(*) FROM api_logs {where} GROUP BY ClientType ORDER BY COUNT(*) DESC", filters)
        else:
            conn.close()
            return jsonify({"labels": [], "counts": []})
    except Exception as e:
        print("get_metric_data error:", e)
        conn.close()
        return jsonify({"labels": [], "counts": []})

    rows = cur.fetchall()
    conn.close()

    labels = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    return jsonify({"labels": labels, "counts": counts})


@app.route('/api/regions')
def get_regions():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT Region FROM api_logs")
        rows = cur.fetchall()
        regions = [r[0] for r in rows if r[0] is not None]
    except Exception as e:
        print("get_regions error:", e)
        regions = []
    conn.close()
    return jsonify(regions)


@app.route('/api/statuscodes')
def get_statuscodes():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT StatusCode FROM api_logs")
        rows = cur.fetchall()
        statuses = [r[0] for r in rows if r[0] is not None]
    except Exception as e:
        print("get_statuscodes error:", e)
        statuses = []
    conn.close()
    return jsonify(statuses)


@app.route('/api/methods/list')
def get_methods():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT Method FROM api_logs")
        rows = cur.fetchall()
        methods = [r[0] for r in rows if r[0] is not None]
    except Exception as e:
        print("get_methods error:", e)
        methods = []
    conn.close()
    return jsonify(methods)


@app.route('/api/clients/list')
def get_clients():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT ClientType FROM api_logs")
        rows = cur.fetchall()
        clients = [r[0] for r in rows if r[0] is not None]
    except Exception as e:
        print("get_clients error:", e)
        clients = []
    conn.close()
    return jsonify(clients)


@app.route('/api/heatmap')
def api_heatmap():
    """
    Returns counts aggregated by Region x Hour-of-day for a recent window.
    Query params:
      hours (int) - lookback window in hours (default 24)
      top (int)   - top N regions by total count (default 20)
    Response:
    {
      regions: [...],
      hours: [0..23],
      matrix: [ [counts for hour 0..23], ... ],
      totals: [...]
    }
    """
    try:
        hours = int(request.args.get('hours', 24))
        top = int(request.args.get('top', 20))
    except Exception:
        return jsonify({"error": "invalid params"}), 400

    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT Timestamp, Region FROM api_logs ORDER BY Timestamp DESC LIMIT 500000", conn, parse_dates=['Timestamp'])
    except Exception:
        df = pd.read_sql_query("SELECT Timestamp, Region FROM api_logs ORDER BY rowid DESC LIMIT 500000", conn)
    conn.close()

    if df.empty:
        return jsonify({"regions": [], "hours": list(range(24)), "matrix": [], "totals": []})

    # normalize and parse timestamp
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    most_recent = df['Timestamp'].max()
    if pd.isna(most_recent):
        # if timestamps invalid, fallback to last N rows and set hour zero
        df['hour'] = 0
    else:
        start = most_recent - pd.Timedelta(hours=hours)
        df = df[df['Timestamp'] >= start]
        df['hour'] = df['Timestamp'].dt.hour

    # normalize region names
    df['Region'] = df['Region'].fillna('Unknown').astype(str)

    # aggregate counts
    agg = df.groupby(['Region', 'hour']).size().reset_index(name='count')

    totals = agg.groupby('Region')['count'].sum().reset_index().sort_values('count', ascending=False)
    top_regions = list(totals.head(top)['Region'])

    hours_range = list(range(24))

    matrix = []
    totals_out = []
    for reg in top_regions:
        row_counts = []
        row_total = 0
        for h in hours_range:
            v = agg[(agg['Region'] == reg) & (agg['hour'] == h)]['count']
            cnt = int(v.values[0]) if not v.empty else 0
            row_counts.append(cnt)
            row_total += cnt
        matrix.append(row_counts)
        totals_out.append(row_total)

    return jsonify({
        "regions": top_regions,
        "hours": hours_range,
        "matrix": matrix,
        "totals": totals_out
    })


@app.route('/api/anomalies')
def api_anomalies():
    """
    Returns anomalies per endpoint for response time and error-rate.
    Query params:
      minutes (int)         - recent window in minutes (default 60)
      lookback_hours (int)  - baseline window length in hours (default 6)
      z (float)             - z-score threshold (default 2.5)
      min_recent_count (int)- minimum recent samples to consider (default 3)
      limit (int)           - max anomalies to return (default 20)
    """
    try:
        minutes = int(request.args.get('minutes', 60))
        lookback_hours = int(request.args.get('lookback_hours', 6))
        z_threshold = float(request.args.get('z', 2.5))
        min_recent_count = int(request.args.get('min_recent_count', 3))
        limit = int(request.args.get('limit', 20))
    except Exception:
        return jsonify({"error":"invalid params"}), 400

    conn = get_connection()
    try:
        df = pd.read_sql_query(
            "SELECT Timestamp, Endpoint, ResponseTimeMS, StatusCode, Region FROM api_logs ORDER BY Timestamp DESC LIMIT 200000",
            conn, parse_dates=['Timestamp']
        )
    except Exception:
        df = pd.read_sql_query(
            "SELECT Timestamp, Endpoint, ResponseTimeMS, StatusCode, Region FROM api_logs ORDER BY rowid DESC LIMIT 200000",
            conn
        )
    conn.close()

    if df.empty:
        return jsonify({"anomalies": []})

    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df[df['Endpoint'].notna()]

    most_recent = df['Timestamp'].max()
    if pd.isna(most_recent):
        return jsonify({"anomalies": []})

    recent_start = most_recent - pd.Timedelta(minutes=minutes)
    baseline_start = most_recent - pd.Timedelta(hours=lookback_hours)

    recent_df = df[df['Timestamp'] >= recent_start].copy()
    baseline_df = df[(df['Timestamp'] >= baseline_start) & (df['Timestamp'] < recent_start)].copy()

    if baseline_df.empty:
        baseline_df = df[df['Timestamp'] < recent_start].copy()

    
    base_stats = baseline_df.groupby('Endpoint')['ResponseTimeMS'].agg(['mean','std','count']).rename(columns={'mean':'base_mean','std':'base_std','count':'base_count'}).reset_index()
    recent_stats = recent_df.groupby('Endpoint')['ResponseTimeMS'].agg(['mean','count']).rename(columns={'mean':'recent_mean','count':'recent_count'}).reset_index()

    merged = recent_stats.merge(base_stats, on='Endpoint', how='left')
    merged['base_mean'] = merged['base_mean'].fillna(merged['recent_mean'])
    merged['base_std'] = merged['base_std'].fillna(merged['base_mean'] * 0.5).replace(0, merged['base_mean'] * 0.5)

    merged['z_score_resp'] = (merged['recent_mean'] - merged['base_mean']) / merged['base_std']

    resp_anoms = merged[(merged['recent_count'] >= min_recent_count) & (merged['z_score_resp'].abs() >= z_threshold)].copy()
    resp_anoms['type'] = 'response_time'

    
    def is_error_val(x):
        try:
            return 1 if int(x) >= 400 else 0
        except Exception:
            return 0
    df['is_error'] = df['StatusCode'].apply(is_error_val)
    recent_err = recent_df.groupby('Endpoint')['is_error'].agg(['mean','count']).rename(columns={'mean':'recent_err_rate','count':'recent_count'}).reset_index()
    base_err = baseline_df.groupby('Endpoint')['is_error'].agg(['mean','count']).rename(columns={'mean':'base_err_rate','count':'base_count'}).reset_index()

    merged_err = recent_err.merge(base_err, on='Endpoint', how='left')
    merged_err['base_err_rate'] = merged_err['base_err_rate'].fillna(0.0)
    merged_err['recent_count'] = merged_err['recent_count'].replace(0, 1)  
    merged_err['std_binom'] = (merged_err['base_err_rate'] * (1 - merged_err['base_err_rate']) / merged_err['recent_count']).replace(0, 1e-6).apply(lambda x: max(x, 1e-6))**0.5
    merged_err['z_score_err'] = (merged_err['recent_err_rate'] - merged_err['base_err_rate']) / merged_err['std_binom']

    err_anoms = merged_err[(merged_err['recent_count'] >= min_recent_count) & (merged_err['z_score_err'] >= z_threshold)].copy()
    err_anoms['type'] = 'error_rate'

    anomalies = []

    def add_resp_rows(df_rows):
        for _, r in df_rows.sort_values('z_score_resp', ascending=False).iterrows():
            anomalies.append({
                "endpoint": r['Endpoint'],
                "type": "response_time",
                "recent_mean": float(round(r['recent_mean'],2)) if pd.notna(r['recent_mean']) else None,
                "baseline_mean": float(round(r['base_mean'],2)) if pd.notna(r['base_mean']) else None,
                "std": float(round(r['base_std'],2)) if pd.notna(r['base_std']) else None,
                "z_score": float(round(r['z_score_resp'],3)),
                "recent_count": int(r['recent_count'])
            })

    def add_err_rows(df_rows):
        for _, r in df_rows.sort_values('z_score_err', ascending=False).iterrows():
            anomalies.append({
                "endpoint": r['Endpoint'],
                "type": "error_rate",
                "recent_err_rate": float(round(r['recent_err_rate']*100,3)),
                "baseline_err_rate": float(round(r['base_err_rate']*100,3)),
                "z_score": float(round(r['z_score_err'],3)),
                "recent_count": int(r['recent_count'])
            })

    add_resp_rows(resp_anoms)
    add_err_rows(err_anoms)

    seen = set()
    deduped = []
    for a in anomalies:
        if a['endpoint'] in seen: continue
        seen.add(a['endpoint'])
        deduped.append(a)
        if len(deduped) >= limit:
            break

    return jsonify({"anomalies": deduped})



if __name__ == "__main__":
    app.run(debug=True)
