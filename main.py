from flask import Flask, render_template_string, request
import pandas as pd
import requests
from io import StringIO
import os

app = Flask(__name__)

CSV_URLS = {
    "all": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=931005748&single=true&output=csv",
    "early": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=1028993857&single=true&output=csv",
    "late": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=1256404350&single=true&output=csv"
}

SALARY_CAP = 50000

# ------------------ HTML Templates ------------------
PLAYER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Player Pool</title>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.4/css/jquery.dataTables.min.css">
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
<style>
body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #f5f6fa; color: #2c3e50; }
h1 { color: #2c3e50; margin-bottom: 10px; }
.card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
form { margin-top: 15px; }
button { padding: 10px 16px; background-color: #27ae60; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; }
button:hover { background-color: #2ecc71; }
input[type=number] { width: 60px; }
</style>
</head>
<body>
<div class="card">
<h1>NFL Classic DK Player Pool</h1>
<p>Slate: <strong>{{ slate_choice|capitalize }}</strong> | Total Players: {{ players|length }}</p>

<form method="get" action="/">
<label>Slate:</label>
<input type="radio" name="slate" value="all" {% if slate_choice=="all" %}checked{% endif %} onchange="this.form.submit()"> All Games
<input type="radio" name="slate" value="early" {% if slate_choice=="early" %}checked{% endif %} onchange="this.form.submit()"> Early (1 PM)
<input type="radio" name="slate" value="late" {% if slate_choice=="late" %}checked{% endif %} onchange="this.form.submit()"> Late (4 PM+)
</form>

<form method="get" action="/lineups" onsubmit="showLoading()">
<input type="hidden" name="slate" value="{{ slate_choice }}">
<label>Number of Lineups:</label>
<input type="number" name="count" value="1" min="1" max="50">
<br><br>

<table id="playerTable" class="display">
<thead>
<tr>
<th>Name</th>
<th>Team</th>
<th>POS</th>
<th>Salary</th>
<th>Proj</th>
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
<td>{{ "%.0f"|format(p.Salary) }}</td>
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
<div id="loading" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:#fff; opacity:0.9; z-index:9999; text-align:center; padding-top:200px; font-size:24px;">
⚡ Building your winning lineups...
</div>
<script>
function showLoading(){ document.getElementById('loading').style.display='block'; }
$(document).ready(function() { $('#playerTable').DataTable(); });
</script>
</body>
</html>
"""

LINEUP_HTML = """<!DOCTYPE html>
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
<h1>Generated Classic Lineups ({{ slate_choice|capitalize }} Slate)</h1>

{% if error %}<p style="color:red;">{{ error }}</p>{% endif %}

{% for lu in lineups %}
<div class="card">
<h2>Lineup {{ loop.index }}</h2>
<p><strong>Salary:</strong> ${{ "%.0f"|format(lu.Salary) }} | <strong>Projected:</strong> {{ "%.2f"|format(lu.Projected) }}</p>
<table>
<tr><th>Role</th><th>Name</th><th>Team</th><th>Salary</th><th>Proj</th></tr>
{% for p in lu.players %}
<tr>
<td class="role-{{ p.Role }}">{{ p.Role }}</td>
<td>{{ p.Name }}</td>
<td>{{ p.Team }}</td>
<td>${{ "%.0f"|format(p.Salary) }}</td>
<td>{{ "%.2f"|format(p.Proj) }}</td>
</tr>
{% endfor %}
</table>
</div>
{% endfor %}

<form action="/" method="get">
<input type="hidden" name="slate" value="{{ slate_choice }}">
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
        next(c for c in df.columns if "FINAL POINTS" in c or "PROJECTION" in c): "Proj",
        next(c for c in df.columns if c in ["TEAM", "TEAMABBREV", "TEam"]): "Team",
        "POS": "POS"
    }
    df = df.rename(columns=rename_map)
    df["Salary"] = df["Salary"].astype(str).str.replace(r'[\$,]', '', regex=True)
    df = df[df["Salary"].str.replace('.', '', 1).str.isnumeric()]
    df["Salary"] = df["Salary"].astype(float)
    df["Proj"] = pd.to_numeric(df["Proj"], errors="coerce")
    df = df.dropna(subset=["Name", "Salary", "Proj", "POS"]).drop_duplicates(subset=["Name"]).reset_index(drop=True)
    return df[["Name", "Team", "POS", "Salary", "Proj"]]

# ------------------ Fast Greedy Lineup Generation ------------------
def generate_lineups(df, lock_players, exclude, num_lineups=5):
    if exclude:
        df = df[~df["Name"].isin(exclude)]
    df_sorted = df.sort_values("Proj", ascending=False)
    lineups = []

    for _ in range(num_lineups):
        lineup = []
        salary_used = 0
        roles_needed = {"QB":1, "RB":2, "WR":3, "TE":1, "FLEX":1, "DST":1}

        # Add locked players first
        for lock in lock_players:
            p = df[df["Name"]==lock].iloc[0]
            role = "FLEX" if roles_needed.get(p.POS,0)==0 else p.POS
            lineup.append({"Name":p.Name,"Role":role,"Salary":p.Salary,"Proj":p.Proj,"Team":p.Team})
            salary_used += p.Salary
            if p.POS in roles_needed:
                roles_needed[p.POS] = max(roles_needed[p.POS]-1,0)
            elif role=="FLEX":
                roles_needed["FLEX"] = max(roles_needed["FLEX"]-1,0)

        # Fill remaining positions
        for pos, count in roles_needed.items():
            if count>0:
                candidates = df_sorted[df_sorted["POS"].isin([pos,"RB","WR","TE"]) if pos=="FLEX" else df_sorted["POS"]==pos]
                for _, p in candidates.iterrows():
                    if any(lp["Name"]==p.Name for lp in lineup):
                        continue
                    lineup.append({"Name":p.Name,"Role":pos if pos!="FLEX" else "FLEX","Salary":p.Salary,"Proj":p.Proj,"Team":p.Team})
                    salary_used += p.Salary
                    count -= 1
                    if count==0: break

        total_proj = sum(p["Proj"] for p in lineup)
        total_salary = sum(p["Salary"] for p in lineup)
        lineups.append({"players":lineup,"Projected":total_proj,"Salary":total_salary})

    return lineups

# ------------------ Routes ------------------
@app.route("/")
def player_pool():
    try:
        slate_choice = request.args.get("slate","all")
        url = CSV_URLS.get(slate_choice,CSV_URLS["all"])
        df = clean_data(pd.read_csv(StringIO(requests.get(url).text)))
        return render_template_string(PLAYER_HTML, players=df.to_dict(orient="records"), slate_choice=slate_choice)
    except Exception as e:
        return f"<p>Error loading player pool: {e}</p>"

@app.route("/lineups")
def lineups():
    try:
        slate_choice = request.args.get("slate","all")
        url = CSV_URLS.get(slate_choice,CSV_URLS["all"])
        df = clean_data(pd.read_csv(StringIO(requests.get(url).text)))
        lock_players = request.args.getlist("lock_flex")
        exclude = request.args.getlist("exclude")
        count = max(1,min(int(request.args.get("count",1)),50))
        lineups = generate_lineups(df, lock_players, exclude, num_lineups=count)
        return render_template_string(LINEUP_HTML,lineups=lineups,error=None,slate_choice=slate_choice)
    except Exception as e:
        return f"<p>Error generating lineups: {e}</p>"

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
