from flask import Flask, render_template, request
import pandas as pd
import pulp

app = Flask(__name__)

GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQEcvQUS_HIbxKp4SbD5HUMJvhLr7tP6yXNVHMul6Ad2PrIQZF9VKgqAmESJBp4CkjfcDxvClpBqK6M/pub?gid=931005748&single=true&output=csv"
SALARY_CAP = 50000

# Required positions
POSITIONS = ['QB', 'RB', 'WR', 'TE', 'DST']
LINEUP_ORDER = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'DST']

def load_data():
    try:
        df = pd.read_csv(GOOGLE_SHEET_URL)
        df.columns = df.columns.str.upper()
        df['SALARY'] = df['SALARY'].replace('[\$,]', '', regex=True).astype(float)
        df['PROJECTED_POINTS'] = pd.to_numeric(df['FINAL POINTS'], errors='coerce')
        df['POS'] = df['POS'].str.upper().str.strip()
        df['TEAM'] = df['TEAM'].str.upper().str.strip()
        df = df.dropna(subset=['PLAYER', 'SALARY', 'POS', 'PROJECTED_POINTS', 'TEAM'])
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return pd.DataFrame()

def generate_lineups(df, locks=[], excludes=[], num_lineups=1):
    lineups = []
    for _ in range(num_lineups):
        # MILP problem
        prob = pulp.LpProblem("DFS_Lineup", pulp.LpMaximize)
        player_vars = {i: pulp.LpVariable(f"player_{i}", cat='Binary') for i in df.index}

        # Objective: maximize projected points
        prob += pulp.lpSum(df.loc[i, 'PROJECTED_POINTS'] * player_vars[i] for i in df.index)

        # Salary cap
        prob += pulp.lpSum(df.loc[i, 'SALARY'] * player_vars[i] for i in df.index) <= SALARY_CAP

        # Position constraints
        for pos in POSITIONS:
            if pos != 'DST':
                count = LINEUP_ORDER.count(pos)
                prob += pulp.lpSum(player_vars[i] for i in df.index if df.loc[i, 'POS'] == pos) == count
            else:
                prob += pulp.lpSum(player_vars[i] for i in df.index if df.loc[i, 'POS'] == pos) == 1

        # Locks / Excludes
        for i in df.index:
            if df.loc[i, 'PLAYER'] in locks:
                prob += player_vars[i] == 1
            if df.loc[i, 'PLAYER'] in excludes:
                prob += player_vars[i] == 0

        # FLEX constraint: must be RB, WR, or TE
        flex_candidates = [i for i in df.index if df.loc[i, 'POS'] in ['RB','WR','TE']]
        prob += pulp.lpSum(player_vars[i] for i in flex_candidates) >= 1

        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        # Build lineup
        lineup = df.loc[[i for i in df.index if player_vars[i].varValue==1]].copy()

        # Assign FLEX position
        assigned_positions = []
        final_lineup = []
        for pos in LINEUP_ORDER:
            candidates = lineup[~lineup['PLAYER'].isin(assigned_positions)]
            if pos == 'FLEX':
                flex_row = candidates[candidates['POS'].isin(['RB','WR','TE'])].iloc[0]
                final_lineup.append(flex_row)
                assigned_positions.append(flex_row['PLAYER'])
            else:
                row = candidates[candidates['POS']==pos].iloc[0]
                final_lineup.append(row)
                assigned_positions.append(row['PLAYER'])

        lineups.append(final_lineup)

        # Remove selected players for uniqueness
        df = df[~df.index.isin([row.name for row in final_lineup])]

    return lineups

@app.route("/", methods=["GET", "POST"])
def index():
    df = load_data()
    locks = request.form.getlist('lock') if request.method == 'POST' else []
    excludes = request.form.getlist('exclude') if request.method == 'POST' else []
    num_lineups = int(request.form.get('num_lineups', 1))
    lineups = []

    try:
        if request.method == 'POST':
            lineups = generate_lineups(df, locks, excludes, num_lineups)
    except Exception as e:
        print(f"Error generating lineups: {e}")

    return render_template(
        "index.html",
        players=df.to_dict(orient='records'),
        lineups=lineups,
        locks=locks,
        excludes=excludes,
        num_lineups=num_lineups
    )

if __name__ == "__main__":
    app.run(debug=True)
