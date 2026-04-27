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
    # Map team name -> division for quick lookup during accumulation.
    division_of = {info["name"]: info["division"] for info in team_map.values()}

    records = {}
    for info in team_map.values():
        records[info["name"]] = {
            "name": info["name"],
            "division": info["division"],
            "w": 0, "l": 0, "t": 0, "points": 0,
            "division_points": 0,
            "runs_scored": 0,
            "runs_allowed": 0,
            "division_runs_allowed": 0,
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

        same_division = division_of[home_name] == division_of[away_name]

        # Runs scored / allowed (overall and division-scoped)
        records[home_name]["runs_scored"] += home_score
        records[home_name]["runs_allowed"] += away_score
        records[away_name]["runs_scored"] += away_score
        records[away_name]["runs_allowed"] += home_score
        if same_division:
            records[home_name]["division_runs_allowed"] += away_score
            records[away_name]["division_runs_allowed"] += home_score

        if home_score > away_score:
            records[home_name]["w"] += 1
            records[away_name]["l"] += 1
            if same_division:
                records[home_name]["division_points"] += 2
        elif away_score > home_score:
            records[away_name]["w"] += 1
            records[home_name]["l"] += 1
            if same_division:
                records[away_name]["division_points"] += 2
        else:
            records[home_name]["t"] += 1
            records[away_name]["t"] += 1
            if same_division:
                records[home_name]["division_points"] += 1
                records[away_name]["division_points"] += 1

    for r in records.values():
        r["points"] = r["w"] * 2 + r["t"]

    al = order_division(
        [r for r in records.values() if r["division"] == "american_league"],
        game_results,
    )
    nl = order_division(
        [r for r in records.values() if r["division"] == "national_league"],
        game_results,
    )

    return {
        "american_league": al,
        "national_league": nl,
        "games": sorted(game_results, key=lambda g: g["date"]),
    }


def order_division(teams, games):
    """Sort a division's teams: by points first, then league tiebreakers."""
    # Group by points (primary). Within each group, run the recursive
    # tiebreaker. Higher points come first.
    by_points = {}
    for t in teams:
        by_points.setdefault(t["points"], []).append(t)

    ordered = []
    for pts in sorted(by_points.keys(), reverse=True):
        ordered.extend(resolve_ties(by_points[pts], games))
    return ordered


def head_to_head_points(team_name, opponents, games):
    """Points (2W + 1T) for `team_name` against any team in `opponents`."""
    pts = 0
    for g in games:
        home, away = g["home"], g["away"]
        if team_name == home and away in opponents:
            opp_score, my_score = g["away_score"], g["home_score"]
        elif team_name == away and home in opponents:
            opp_score, my_score = g["home_score"], g["away_score"]
        else:
            continue
        if my_score > opp_score:
            pts += 2
        elif my_score == opp_score:
            pts += 1
    return pts


def head_to_head_runs_allowed(team_name, opponents, games):
    """Runs allowed by `team_name` in games against any team in `opponents`."""
    ra = 0
    for g in games:
        home, away = g["home"], g["away"]
        if team_name == home and away in opponents:
            ra += g["away_score"]
        elif team_name == away and home in opponents:
            ra += g["home_score"]
    return ra


def resolve_ties(group, games):
    """Order teams tied on points using the league's tiebreakers.

    Rules (in order):
      a. Head-to-head points (most)
      b. Division points (most)
      c. Head-to-head runs allowed (fewest)
      d. Division runs allowed (fewest)
      e. Overall runs allowed (fewest)
      Fallback: alphabetical by team name.

    At each step, the team(s) tied for first on the metric stay
    together; the rest are "eliminated" below them. Both sub-groups
    then recurse from step (a). If a step does not separate anyone,
    fall through to the next step.
    """
    if len(group) <= 1:
        return list(group)

    others = {t["name"] for t in group}

    # (metric_fn, prefer_max?) — prefer_max=True for points, False for RA.
    steps = [
        (lambda t: head_to_head_points(t["name"], others - {t["name"]}, games), True),
        (lambda t: t["division_points"], True),
        (lambda t: head_to_head_runs_allowed(t["name"], others - {t["name"]}, games), False),
        (lambda t: t["division_runs_allowed"], False),
        (lambda t: t["runs_allowed"], False),
    ]

    for metric_fn, prefer_max in steps:
        scored = [(metric_fn(t), t) for t in group]
        best = max(s for s, _ in scored) if prefer_max else min(s for s, _ in scored)
        winners = [t for s, t in scored if s == best]
        eliminated = [t for s, t in scored if s != best]
        if eliminated:
            return resolve_ties(winners, games) + resolve_ties(eliminated, games)

    # Fully unresolved — fall back to alphabetical for stability.
    return sorted(group, key=lambda t: t["name"])


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
