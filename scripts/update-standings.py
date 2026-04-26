#!/usr/bin/env python3
"""Fetch game results from GameChanger and compute RBRL standings."""

import json
import urllib.request
import yaml
from pathlib import Path

TEAM_GAMES_URL = "https://api.team-manager.gc.com/public/teams/{team_id}/games"

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


def fetch_team_games(team_id):
    """Fetch the games list for a single team."""
    url = TEAM_GAMES_URL.format(team_id=team_id)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def resolve_opponent_name(gc_name, team_map):
    """Map a GC opponent name to a canonical team name, or None if unknown.

    GC names may include league prefixes/suffixes (e.g. "RBRL Padres",
    "Mariners - RBRL"), so we match the canonical name as a case-insensitive
    substring.
    """
    if not gc_name:
        return None
    lowered = gc_name.lower()
    for info in team_map.values():
        if info["name"].lower() in lowered:
            return info["name"]
    return None


def collect_completed_games(team_map):
    """Iterate every team's games endpoint and dedupe completed games.

    The same physical game has a different id in each team's endpoint, so
    we dedupe by (start_ts, frozenset of team names) instead of by id.
    """
    games = {}
    for gc_id, info in team_map.items():
        this_name = info["name"]
        try:
            data = fetch_team_games(gc_id)
        except Exception as e:  # noqa: BLE001
            print(f"Warning: failed to fetch games for {this_name} ({gc_id}): {e}")
            continue

        for g in data:
            if g.get("game_status") != "completed":
                continue
            score = g.get("score") or {}
            team_score = score.get("team")
            opp_score = score.get("opponent_team")
            if team_score is None or opp_score is None:
                continue

            opp_gc_name = (g.get("opponent_team") or {}).get("name", "")
            opp_name = resolve_opponent_name(opp_gc_name, team_map)
            if not opp_name:
                # Non-league opponent; skip for standings purposes.
                continue

            start_ts = g.get("start_ts", "")
            key = (start_ts, frozenset({this_name, opp_name}))
            if key in games:
                continue

            if g.get("home_away") == "home":
                home_name, away_name = this_name, opp_name
                home_score, away_score = team_score, opp_score
            else:
                home_name, away_name = opp_name, this_name
                home_score, away_score = opp_score, team_score

            games[key] = {
                "date": start_ts,
                "home": home_name,
                "away": away_name,
                "home_score": home_score,
                "away_score": away_score,
            }

    return list(games.values())


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
