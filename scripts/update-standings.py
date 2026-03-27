#!/usr/bin/env python3
"""Fetch game results from GameChanger and compute RBRL standings."""

import json
import urllib.request
import yaml
from pathlib import Path

SCOREBOARD_URL = (
    "https://api.team-manager.gc.com/public/widgets/scoreboard/"
    "65041549-7a93-400a-a9ee-d67d9a3f8c9e"
)

ROOT = Path(__file__).resolve().parent.parent
TEAMS_FILE = ROOT / "data" / "teams.yaml"
STANDINGS_FILE = ROOT / "data" / "standings.json"


def load_teams():
    """Load teams.yaml and build a gc_team_id -> (name, division) map."""
    with open(TEAMS_FILE) as f:
        data = yaml.safe_load(f)

    team_map = {}
    for t in data["american_league"]:
        team_map[t["gc_team_id"]] = {"name": t["name"], "division": "american_league"}
    for t in data["national_league"]:
        team_map[t["gc_team_id"]] = {"name": t["name"], "division": "national_league"}
    return team_map


def fetch_scoreboard():
    """Fetch all events from the GC scoreboard API."""
    req = urllib.request.Request(SCOREBOARD_URL)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["data"]["events"]


def normalize_name(gc_name, team_map, gc_id):
    """Return canonical team name from our data, falling back to GC name."""
    if gc_id in team_map:
        return team_map[gc_id]["name"]
    return gc_name


def compute_standings(events, team_map):
    """Process events into standings and game results."""
    records = {}
    for info in team_map.values():
        records[info["name"]] = {
            "name": info["name"],
            "division": info["division"],
            "w": 0, "l": 0, "t": 0, "points": 0,
        }

    game_results = []

    for event in events:
        home = event.get("home_team", {})
        away = event.get("away_team", {})
        score = event.get("score")

        if not score:
            continue

        home_id = home.get("id", "")
        away_id = away.get("id", "")
        home_name = normalize_name(home.get("name", ""), team_map, home_id)
        away_name = normalize_name(away.get("name", ""), team_map, away_id)
        home_score = score.get("home_team", score.get("team", 0))
        away_score = score.get("opponent_team", score.get("away_team", 0))

        if home_name not in records or away_name not in records:
            continue

        game_results.append({
            "date": event.get("start_ts", ""),
            "home": home_name,
            "away": away_name,
            "home_score": home_score,
            "away_score": away_score,
        })

        if home_score > away_score:
            records[home_name]["w"] += 1
            records[away_name]["l"] += 1
        elif away_score > home_score:
            records[away_name]["w"] += 1
            records[home_name]["l"] += 1
        else:
            records[home_name]["t"] += 1
            records[away_name]["t"] += 1

    for r in records.values():
        r["points"] = r["w"] * 2 + r["t"]

    al = sorted(
        [r for r in records.values() if r["division"] == "american_league"],
        key=lambda x: (-x["points"], -x["w"], x["l"]),
    )
    nl = sorted(
        [r for r in records.values() if r["division"] == "national_league"],
        key=lambda x: (-x["points"], -x["w"], x["l"]),
    )

    return {
        "american_league": al,
        "national_league": nl,
        "games": sorted(game_results, key=lambda g: g["date"]),
    }


def main():
    team_map = load_teams()
    events = fetch_scoreboard()
    standings = compute_standings(events, team_map)

    with open(STANDINGS_FILE, "w") as f:
        json.dump(standings, f, indent=2)

    al = standings["american_league"]
    nl = standings["national_league"]
    total_games = len(standings["games"])

    print(f"Standings updated: {total_games} completed game(s)")
    for label, div in [("AL", al), ("NL", nl)]:
        print(f"\n{label}:")
        for r in div:
            print(f"  {r['name']:12s}  {r['w']}W {r['l']}L {r['t']}T  ({r['points']} pts)")


if __name__ == "__main__":
    main()
