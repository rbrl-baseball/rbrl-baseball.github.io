#!/usr/bin/env python3
"""Fetch game results from GameChanger and compute RBRL standings."""

import json
import urllib.request
import yaml
from pathlib import Path

ORG_ID = "fCGlFdY1Z4hj"
ORG_EVENTS_URL = f"https://api.team-manager.gc.com/public/organizations/{ORG_ID}/events"

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


def fetch_org_events():
    """Fetch all scheduled events for the league organization.

    This is the league-managed schedule shown at
    https://web.gc.com/organizations/{ORG_ID}/schedule and is the
    definitive source of game results.
    """
    req = urllib.request.Request(ORG_EVENTS_URL)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def collect_completed_games(team_map):
    """Pick completed games from the org schedule with both league teams."""
    games = []
    for event in fetch_org_events():
        if event.get("game_status") != "completed":
            continue

        home = event.get("home_team") or {}
        away = event.get("away_team") or {}
        home_id = home.get("id")
        away_id = away.get("id")
        if home_id not in team_map or away_id not in team_map:
            continue

        home_score = home.get("score")
        away_score = away.get("score")
        if home_score is None or away_score is None:
            continue

        games.append({
            "date": event.get("start_ts", ""),
            "home": team_map[home_id]["name"],
            "away": team_map[away_id]["name"],
            "home_score": home_score,
            "away_score": away_score,
        })

    return games


def compute_standings(completed_games, team_map):
    """Process completed games into standings and game results."""
    records = {}
    for info in team_map.values():
        records[info["name"]] = {
            "name": info["name"],
            "division": info["division"],
            "w": 0, "l": 0, "t": 0, "points": 0,
        }

    game_results = []

    for g in completed_games:
        home_name = g["home"]
        away_name = g["away"]
        home_score = g["home_score"]
        away_score = g["away_score"]

        if home_name not in records or away_name not in records:
            continue

        game_results.append({
            "date": g["date"],
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
    completed = collect_completed_games(team_map)
    standings = compute_standings(completed, team_map)

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
