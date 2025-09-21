from flask import Flask, render_template_string, request
import pandas as pd
import requests
from io import StringIO
import os

app = Flask(__name__)

# ------------------ DATA SOURCES ------------------
CSV_URLS = {
    "all": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=931005748&single=true&output=csv",
    "early": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=1028993857&single=true&output=csv",
    "late": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=1256404350&single=true&output=csv"
}

SALARY_CAP = 50000
LINEUP_POSITIONS = ["QB","RB","RB","WR","WR","WR","TE","FLEX","DST"]

# ------------------ HTML TEMPLATES ------------------
PLAYER_HTML_TEMPLATE = """
<!DOCTYPE html>
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

<form method="get" action="/lineups">
<input type="hidden" name="slate" value="{{ slate_choice }}">
<label>Number of Lineups:</label>
<input type="number" name="count" value="1" min="1" max="20">
<br><br>
<label>Select Team to Stack:</label>
<select name="team">
<option value="">--Select Team--</option>
{% for team in teams %}
<option value="{{ team }}" {% if selected_team==team %}selected{% endif %}>{{ team }}</option>
{% endfor %}
</select>
<br><br>
<table id="playerTable" class="display">
<thead>
<tr>
<th>Name</th><th>Team</th><th>POS</th><th>Salary</th><th>Proj</th>
</tr>
</thead>
<tbody>
{% for p in players %}
<tr>
<td>{{ p.Name }}</td><td>{{ p.Team }}</td><td>{{ p.POS }}</td><td>{{ "%.0f"|format(p.Salary) }}</td><td>{{ "%.2f"|format(p.Proj) }}</td>
</tr>
{% endfor %}
</tbody>
</table>
<br>
<button type="submit">⚡ Generate Full Lineups</button>
</form>
</div>
<script>
$(document).ready(function() { $('#playerTable').DataTable(); });
</script>
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
.card { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 3px 8px rgba(0,0,0,0.1); margin-bottom: 25px; }
table { border-collapse: collapse; width: 100%; margin-top: 10px; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
th { background-color: #34495e; color: white; }
</style>
</head>
<body>
<h1>Generated Full Lineups ({{ slate_choice|capitalize }} Slate)</h1>
{% if error %}<p style="color:red;">{{ error }}</p>{% endif %}

{% for lu in lineups %}
<div class="card">
<h2>Lineup {{ loop.index }}</h2>
<p><strong>Team Stack:</strong> {{ lu.team }} | <strong>Salary:</strong> ${{ "%.0f"|format(lu.salary) }} | <strong>Projected:</strong> {{ "%.2f"|format(lu.proj) }}</p>
<table>
<tr><th>Role</th><th>Name</th><th>Salary</th><th>Proj</th></tr>
{% for p in lu.players %}
<tr><td>{{ p.Role }}</td><td>{{ p.Name }}</td><td>${{ "%.0f"|format(p.Salary) }}</td><td>{{ "%.2f"|format(p.Proj) }}</td></tr>
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
    df = df.dropna(subset=["Name","Salary","Proj","POS"]).drop_duplicates(subset=["Name"]).reset_index(drop=True)
    return df[["Name","Team","POS","Salary","Proj"]]

# ------------------ Generate Full Lineup Around Stack ------------------
def generate_full_lineups(df, team, num_lineups=5):
    lineups = []

    # Build team stack: 1 QB + top 2 RB/WR/TE from that team
    qb_pool = df[(df["POS"]=="QB") & (df["Team"]==team)].sort_values("Proj", ascending=False)
    skill_pool = df[(df["POS"].isin(["RB","WR","TE"])) & (df["Team"]==team)].sort_values("Proj", ascending=False)

    if qb_pool.empty or len(skill_pool)<2:
        return lineups

    qb = qb_pool.iloc[0]
    top2 = skill_pool.head(2).to_dict(orient="records")
    stack_players = [{"Name":qb.Name,"Role":"QB","Salary":qb.Salary
,"Proj":qb.Proj}]
    for p in top2:
        stack_players.append({"Name":p["Name"],"Role":p["POS"],"Salary":p["Salary"],"Proj":p["Proj"]})

    # Remaining roster positions
    roster_positions = ["RB","WR","WR","TE","FLEX","DST"]  # positions left after stack
    available_players = df[~df["Name"].isin([p["Name"] for p in stack_players])].sort_values("Proj", ascending=False)

    for _ in range(num_lineups):
        lineup = stack_players.copy()
        filled_positions = []

        for pos in roster_positions:
            if pos == "FLEX":
                flex_pool = available_players[available_players["POS"].isin(["RB","WR","TE"])]
                if flex_pool.empty:
                    continue
                player = flex_pool.iloc[0]
            else:
                pool = available_players[available_players["POS"]==pos]
                if pool.empty:
                    continue
                player = pool.iloc[0]

            lineup.append({"Name":player["Name"],"Role":pos,"Salary":player["Salary"],"Proj":player["Proj"]})
            available_players = available_players[available_players["Name"]!=player["Name"]]

        total_salary = sum(p["Salary"] for p in lineup)
        total_proj = sum(p["Proj"] for p in lineup)
        lineups.append({"team":team,"players":lineup,"salary":total_salary,"proj":total_proj})

    return lineups

# ------------------ Routes ------------------
@app.route("/")
def player_pool():
    try:
        slate_choice = request.args.get("slate","all")
        selected_team = request.args.get("team","")
        url = CSV_URLS.get(slate_choice, CSV_URLS["all"])
        df = clean_data(pd.read_csv(StringIO(requests.get(url).text)))
        teams = sorted(df["Team"].unique())
        return render_template_string(
            PLAYER_HTML_TEMPLATE,
            players=df.to_dict(orient="records"),
            slate_choice=slate_choice,
            teams=teams,
            selected_team=selected_team
        )
    except Exception as e:
        return f"<p>Error loading player pool: {e}</p>"

@app.route("/lineups")
def lineups():
    try:
        slate_choice = request.args.get("slate","all")
        selected_team = request.args.get("team","")
        url = CSV_URLS.get(slate_choice, CSV_URLS["all"])
        df = clean_data(pd.read_csv(StringIO(requests.get(url).text)))

        if not selected_team:
            return "<p>Please select a team to stack.</p>"

        count = max(1,min(int(request.args.get("count",1)),20))
        lineups = generate_full_lineups(df, selected_team, num_lineups=count)

        if not lineups:
            return render_template_string(LINEUP_HTML_TEMPLATE,lineups=[],error="No valid full lineups could be generated for this team.",slate_choice=slate_choice)

        return render_template_string(LINEUP_HTML_TEMPLATE,lineups=lineups,error=None,slate_choice=slate_choice)
    except Exception as e:
        return f"<p>Error generating lineups: {e}</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)), debug=True)
