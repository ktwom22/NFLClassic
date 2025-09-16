from flask import Flask, render_template_string, request
import pandas as pd
import requests
from io import StringIO
from itertools import combinations

app = Flask(__name__)

GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=931005748&single=true&output=csv"
SALARY_CAP = 50000
LINEUP_ORDER = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]

# ------------------ HTML Templates ------------------
PLAYER_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Player Pool</title>
<style>
body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #f5f6fa; color: #2c3e50; }
h1 { color: #2c3e50; margin-bottom: 10px; }
.card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
table { border-collapse: collapse; width: 100%; margin-top: 10px; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
th { background-color: #34495e; color: white; }
tr:nth-child(even) { background-color: #f9f9f9; }
tr:hover { background-color: #ecf0f1; }
form { margin-top: 15px; }
input[type=checkbox], input[type=radio], input[type=number] { transform: scale(1.1); margin: 2px; }
button { padding: 10px 16px; background-color: #27ae60; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; }
button:hover { background-color: #2ecc71; }
label { font-weight: 500; margin-right: 10px; }
</style>
</head>
<body>
<div class="card">
<h1>NFL Classic DK Player Pool</h1>
<p>Total Players: {{ players|length }}</p>

<form method="get" action="/lineups">
<label>Number of Lineups:</label>
<input type="number" name="count" value="1" min="1" max="10">
<br><br>

<table>
<thead>
<tr>
<th>Name</th>
<th>Team</th>
<th>POS</th>
<th>Salary</th>
<th>Projected Points</th>
<th>Lock</th>
<th>Exclude</th>
</tr>
</thead>
<tbody>
{% for p in players %}
<tr>
<td>{{ p.Name }}</td>
<td>{{ p.Team }}</td>
<td>{{ p.POS }}</td>
<td>${{ "{:,.0f}".format(p.Salary) }}</td>
<td>{{ "%.2f"|format(p.Proj) }}</td>
<td><input type="checkbox" name="lock_flex" value="{{ p.Name }}"></td>
<td><input type="checkbox" name="exclude" value="{{ p.Name }}"></td>
</tr>
{% endfor %}
</tbody>
</table>
<br>
<button type="submit">⚡ Generate Lineups</button>
</form>
</div>
</body>
</html>
"""

LINEUP_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Generated Lineups</title>
<style>
body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #f5f6fa; color: #2c3e50; }
h1 { color: #2c3e50; margin-bottom: 20px; }
.card { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 3px 8px rgba(0,0,0,0.1); margin-bottom: 25px; transition: transform 0.1s ease-in-out; }
.card:hover { transform: translateY(-2px); }
table { border-collapse: collapse; width: 100%; margin-top: 10px; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
th { background-color: #34495e; color: white; }
.role-CPT { color: #e74c3c; font-weight: bold; }
.role-FLEX { color: #2980b9; }
button { padding: 10px 16px; background-color: #3498db; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; }
button:hover { background-color: #2980b9; }
</style>
</head>
<body>
<h1>Generated Classic Lineups</h1>

{% if error %}
<p style="color:red;">{{ error }}</p>
{% endif %}

{% for lu in lineups %}
<div class="card">
<h2>Lineup {{ loop.index }}</h2>
<p><strong>Salary:</strong> ${{ "{:,.0f}".format(lu.Salary) }} | 
<strong>Projected:</strong> {{ "%.2f"|format(lu.Projected) }}</p>
<table>
<tr><th>Role</th><th>Name</th><th>Team</th><th>Salary</th><th>Proj</th></tr>
{% for p in lu.players %}
<tr>
<td class="role-{{ p.Role }}">{{ p.Role }}</td>
<td>{{ p.Name }}</td>
<td>{{ p.Team }}</td>
<td>${{ "{:,.0f}".format(p.Salary) }}</td>
<td>{{ "%.2f"|format(p.Proj) }}</td>
</tr>
{% endfor %}
</table>
</div>
{% endfor %}

<form action="/" method="get">
    <button type="submit">⬅ Back to Player Pool</button>
</form>

</body>
</html>
"""


# ------------------ Data Cleaning ------------------
def clean_data(df):
    df.columns = df.columns.str.strip().str.upper()
    rename_map = {
        next(c for c in df.columns if "PLAYER" in c): "Name",
        next(c for c in df.columns if "SALARY" in c): "Salary",
        next(c for c in df.columns if "FINAL POINTS" in c): "Proj",
        next(c for c in df.columns if c in ["TEAM", "TEam"]): "Team",
        "POS": "POS"
    }
    df = df.rename(columns=rename_map)
    df["Salary"] = df["Salary"].astype(str).str.replace(r'[\$,]', '', regex=True)
    df = df[df["Salary"].str.replace('.', '', 1).str.isnumeric()]
    df["Salary"] = df["Salary"].astype(float)
    df["Proj"] = pd.to_numeric(df["Proj"], errors='coerce')
    df["Name"] = df["Name"].astype(str).str.strip()
    df["Team"] = df["Team"].astype(str).str.upper().str.strip()
    df["POS"] = df["POS"].astype(str).str.upper().str.strip()
    df = df.dropna(subset=["Name", "Salary", "Proj", "POS"]).drop_duplicates(subset=["Name"]).reset_index(drop=True)
    return df[["Name", "Team", "POS", "Salary", "Proj"]]


# ------------------ Generate Classic NFL Lineups ------------------
def generate_classic_lineups(df, lock_players=[], exclude=[], num_lineups=5):
    df = df.copy()
    if exclude:
        df = df[~df["Name"].isin(exclude)]

    lineups = []
    qb_pool = df[df["POS"] == "QB"]
    rb_pool = df[df["POS"] == "RB"]
    wr_pool = df[df["POS"] == "WR"]
    te_pool = df[df["POS"] == "TE"]
    dst_pool = df[df["POS"] == "DST"]

    for qb in qb_pool.itertuples():
        for rbs in combinations(rb_pool.itertuples(), 2):
            for wrs in combinations(wr_pool.itertuples(), 3):
                for te in te_pool.itertuples():
                    for dst in dst_pool.itertuples():
                        flex_pool = df[(df["POS"].isin(["RB", "WR", "TE"])) & (
                            ~df["Name"].isin([p.Name for p in [qb, *rbs, *wrs, te, dst]]))]
                        for flex in flex_pool.itertuples():
                            complete_lineup = [qb, *rbs, *wrs, te, dst, flex]
                            total_salary = sum(p.Salary for p in complete_lineup)
                            if total_salary <= SALARY_CAP:
                                total_proj = sum(p.Proj for p in complete_lineup)
                                lineup_dict = {
                                    "players": [
                                        {"Name": p.Name, "Role": "FLEX" if p == flex else p.POS, "Salary": p.Salary,
                                         "Proj": p.Proj, "Team": p.Team} for p in complete_lineup],
                                    "Salary": total_salary,
                                    "Projected": total_proj
                                }
                                lineups.append(lineup_dict)
                            if len(lineups) >= num_lineups:
                                break
                        if len(lineups) >= num_lineups:
                            break
                    if len(lineups) >= num_lineups:
                        break
                if len(lineups) >= num_lineups:
                    break
            if len(lineups) >= num_lineups:
                break
        if len(lineups) >= num_lineups:
            break

    return sorted(lineups, key=lambda x: x["Projected"], reverse=True)[:num_lineups]


# ------------------ Routes ------------------
@app.route('/')
def player_pool():
    try:
        r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        df = clean_data(df)
        return render_template_string(PLAYER_HTML_TEMPLATE, players=df.to_dict(orient="records"))
    except Exception as e:
        return f"<p>Error loading player pool: {e}</p>"


@app.route('/lineups')
def lineups():
    try:
        r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        df = clean_data(df)

        lock_players = request.args.getlist('lock_flex')
        exclude = request.args.getlist('exclude')
        count = int(request.args.get('count', 1))
        count = max(1, min(count, 10))

        lineups = generate_classic_lineups(df, lock_players=lock_players, exclude=exclude, num_lineups=count)
        if not lineups:
            return render_template_string(LINEUP_HTML_TEMPLATE, lineups=[],
                                          error="Could not generate lineups with current selections.")

        return render_template_string(LINEUP_HTML_TEMPLATE, lineups=lineups, error=None)

    except Exception as e:
        return f"<p>Error generating lineups: {e}</p>"


import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
