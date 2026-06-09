#!/usr/bin/env python3
"""Fetch playoff game results from GameChanger and update the bracket."""

import json
import urllib.request
import yaml
from pathlib import Path

ORG_ID = "fCGlFdY1Z4hj"
ORG_EVENTS_URL = f"https://api.team-manager.gc.com/public/organizations/{ORG_ID}/events"

ROOT = Path(__file__).resolve().parent.parent
TEAMS_FILE = ROOT / "data" / "teams.yaml"
PLAYOFFS_FILE = ROOT / "data" / "playoffs.yaml"

# How winners advance through the bracket.  Each entry maps
# (league, round) → (league, next_round, slot) where slot is "home" or "away".
ADVANCEMENT = {
    ("american_league", "play_in"): ("american_league", "semifinal_lower", "away"),
    ("american_league", "semifinal_upper"): ("american_league", "championship", "away"),
    ("american_league", "semifinal_lower"): ("american_league", "championship", "home"),
    ("national_league", "play_in"): ("national_league", "semifinal_lower", "away"),
    ("national_league", "semifinal_upper"): ("national_league", "championship", "away"),
    ("national_league", "semifinal_lower"): ("national_league", "championship", "home"),
}

# TBD placeholder team IDs used by GameChanger for unset matchups.
TBD_TEAM_IDS = {"5HyBYHOuyvuF", "kx8O4T4mv4Jl"}

ROUNDS = ["play_in", "semifinal_upper", "semifinal_lower", "championship"]


def load_teams():
    """Return gc_team_id → {name, seed} map from teams.yaml + standings."""
    with open(TEAMS_FILE) as f:
        data = yaml.safe_load(f)

    team_map = {}
    for t in data["american_league"]:
        team_map[t["gc_team_id"]] = {"name": t["name"]}
    for t in data["national_league"]:
        team_map[t["gc_team_id"]] = {"name": t["name"]}
    return team_map


def load_playoffs():
    with open(PLAYOFFS_FILE) as f:
        return yaml.safe_load(f)


def save_playoffs(data):
    with open(PLAYOFFS_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def fetch_events():
    """Fetch all org events and return a gc_event_id → event dict."""
    req = urllib.request.Request(ORG_EVENTS_URL)
    with urllib.request.urlopen(req, timeout=30) as resp:
        events = json.loads(resp.read())
    return {e["id"]: e for e in events}


def resolve_team(gc_team_id, team_map):
    """Map a GC team ID to canonical name, or None if TBD/unknown."""
    if gc_team_id in TBD_TEAM_IDS:
        return None
    info = team_map.get(gc_team_id)
    return info["name"] if info else None


def determine_winner(event, team_map):
    """Return the canonical name of the winning team, or None."""
    home = event.get("home_team", {})
    away = event.get("away_team", {})
    home_score = home.get("score")
    away_score = away.get("score")
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return resolve_team(home.get("id"), team_map)
    elif away_score > home_score:
        return resolve_team(away.get("id"), team_map)
    return None  # tie — shouldn't happen in playoffs


def find_seed(bracket, league, team_name):
    """Look up a team's seed from earlier bracket rounds."""
    league_data = bracket.get(league, {})
    for round_key in ROUNDS:
        game = league_data.get(round_key, {})
        for side in ("home", "away"):
            slot = game.get(side, {})
            if slot.get("name") == team_name and "seed" in slot:
                return slot["seed"]
    return None


def update_game(game, event, team_map):
    """Update a single bracket game from a GC event. Returns True if changed."""
    changed = False

    # Sync date and time from GC schedule.
    start_ts = event.get("start_ts", "")
    if start_ts:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        et = dt.astimezone(ZoneInfo("America/New_York"))
        gc_date = et.strftime("%Y-%m-%d")
        gc_time = et.strftime("%-I:%M %p")
        if game.get("date") != gc_date:
            game["date"] = gc_date
            changed = True
        if game.get("time") != gc_time:
            game["time"] = gc_time
            changed = True

    if event.get("game_status") == "completed" and game.get("status") != "final":
        home = event.get("home_team", {})
        away = event.get("away_team", {})
        home_score = home.get("score")
        away_score = away.get("score")
        if home_score is not None and away_score is not None:
            game["status"] = "final"
            game["home_score"] = home_score
            game["away_score"] = away_score
            winner = determine_winner(event, team_map)
            if winner:
                game["winner"] = winner
            changed = True

    # Update team names if GC has resolved TBD placeholders.
    for side in ("home", "away"):
        gc_side = event.get(f"{side}_team", {})
        gc_id = gc_side.get("id")
        if gc_id and gc_id not in TBD_TEAM_IDS:
            canonical = resolve_team(gc_id, team_map)
            if canonical and game.get(side, {}).get("name") in ("TBD", None):
                game[side]["name"] = canonical
                if "note" in game[side]:
                    del game[side]["note"]
                changed = True

    return changed


def advance_winners(bracket, team_map):
    """Propagate winners to the next bracket round."""
    changed = False

    for (league, round_key), (next_league, next_round, slot) in ADVANCEMENT.items():
        game = bracket.get(league, {}).get(round_key, {})
        winner = game.get("winner")
        if not winner:
            continue

        next_game = bracket.get(next_league, {}).get(next_round, {})
        next_slot = next_game.get(slot, {})
        if next_slot.get("name") != winner:
            next_slot["name"] = winner
            seed = find_seed(bracket, league, winner)
            if seed is not None:
                next_slot["seed"] = seed
            if "note" in next_slot:
                del next_slot["note"]
            next_game[slot] = next_slot
            changed = True

    # Championship winners → World Series
    for league, ws_key in [("american_league", "al_champion"), ("national_league", "nl_champion")]:
        champ_game = bracket.get(league, {}).get("championship", {})
        winner = champ_game.get("winner")
        if winner and bracket.get("world_series", {}).get(ws_key) != winner:
            bracket["world_series"][ws_key] = winner
            changed = True

    return changed


def update_world_series(bracket, events, team_map):
    """Update World Series game results."""
    ws = bracket.get("world_series", {})
    games = ws.get("games", [])
    changed = False

    for game in games:
        event_id = game.get("gc_event_id")
        if not event_id or event_id not in events:
            continue
        if update_game(game, events[event_id], team_map):
            changed = True

    return changed


def main():
    team_map = load_teams()
    bracket = load_playoffs()
    events = fetch_events()
    changed = False

    for league in ("american_league", "national_league"):
        league_data = bracket.get(league, {})
        for round_key in ROUNDS:
            game = league_data.get(round_key, {})
            event_id = game.get("gc_event_id")
            if not event_id or event_id not in events:
                continue
            if update_game(game, events[event_id], team_map):
                changed = True

    if advance_winners(bracket, team_map):
        changed = True

    if update_world_series(bracket, events, team_map):
        changed = True

    if changed:
        save_playoffs(bracket)
        print("Playoff bracket updated")
    else:
        print("No changes to playoff bracket")

    # Print current bracket state
    for league in ("american_league", "national_league"):
        label = "AL" if league == "american_league" else "NL"
        print(f"\n{label} Bracket:")
        for round_key in ROUNDS:
            game = bracket.get(league, {}).get(round_key, {})
            home = game.get("home", {}).get("name", "?")
            away = game.get("away", {}).get("name", "?")
            status = game.get("status", "?")
            line = f"  {game.get('label', round_key)}: {away} @ {home}"
            if status == "final":
                line += f"  {game.get('away_score')}-{game.get('home_score')} (Final)"
            else:
                line += f"  [{status}]"
            print(line)

    ws = bracket.get("world_series", {})
    print(f"\nWorld Series: {ws.get('al_champion', '?')} (AL) vs {ws.get('nl_champion', '?')} (NL)")


if __name__ == "__main__":
    main()
