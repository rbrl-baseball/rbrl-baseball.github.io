#!/usr/bin/env python3
"""Fetch playoff game results from GameChanger and update the bracket."""

import json
import urllib.request
import yaml
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ORG_ID = "fCGlFdY1Z4hj"
ORG_EVENTS_URL = f"https://api.team-manager.gc.com/public/organizations/{ORG_ID}/events"

ROOT = Path(__file__).resolve().parent.parent
TEAMS_FILE = ROOT / "data" / "teams.yaml"
PLAYOFFS_FILE = ROOT / "data" / "playoffs.yaml"
STANDINGS_FILE = ROOT / "data" / "standings.json"
EASTERN = ZoneInfo("America/New_York")

# TBD placeholder team IDs used by GameChanger for unset matchups.
TBD_TEAM_IDS = {"5HyBYHOuyvuF", "kx8O4T4mv4Jl"}

ROUNDS = ["play_in", "semifinal_upper", "semifinal_lower", "championship"]


def load_teams():
    """Return gc_team_id → canonical team info map from teams.yaml."""
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


def load_standings():
    with open(STANDINGS_FILE) as f:
        return json.load(f)


def save_playoffs(data):
    with open(PLAYOFFS_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def fetch_events():
    """Fetch all org events and return a gc_event_id → event dict."""
    req = urllib.request.Request(ORG_EVENTS_URL)
    with urllib.request.urlopen(req, timeout=30) as resp:
        events = json.loads(resp.read())
    return {e["id"]: e for e in events}


def event_datetime(event):
    """Return the event start time in Eastern time, or None."""
    start_ts = event.get("start_ts", "")
    if not start_ts:
        return None
    return datetime.fromisoformat(start_ts.replace("Z", "+00:00")).astimezone(EASTERN)


def resolve_team(gc_team_id, team_map):
    """Map a GC team ID to canonical name, or None if TBD/unknown."""
    if gc_team_id in TBD_TEAM_IDS:
        return None
    info = team_map.get(gc_team_id)
    return info["name"] if info else None


def event_team_names(event, team_map):
    """Return canonical team names participating in a GC event."""
    names = set()
    for side in ("home", "away"):
        name = resolve_team((event.get(f"{side}_team") or {}).get("id"), team_map)
        if name:
            names.add(name)
    return names


def game_team_names(game):
    """Return canonical team names already assigned to a bracket game."""
    names = set()
    for side in ("home", "away"):
        name = (game.get(side) or {}).get("name")
        if name and name != "TBD":
            names.add(name)
    return names


def event_matches_game(game, event, team_map):
    """Return True when a GC event has the same assigned participants as a game."""
    expected = game_team_names(game)
    if len(expected) < 2:
        return True
    return event_team_names(event, team_map) == expected


def find_matching_event(game, events, team_map):
    """Find the org event that matches this bracket game's assigned teams."""
    expected = game_team_names(game)
    if len(expected) < 2:
        return None

    candidates = [
        event for event in events.values()
        if event_team_names(event, team_map) == expected
    ]
    if not candidates:
        return None

    game_date = game.get("date")
    dated_candidates = [
        event for event in candidates
        if event_datetime(event) and event_datetime(event).strftime("%Y-%m-%d") == game_date
    ]
    candidates = dated_candidates or candidates
    return candidates[0] if len(candidates) == 1 else None


def get_event_for_game(game, events, team_map):
    """Return a matching GC event for a game, correcting gc_event_id when needed."""
    event_id = game.get("gc_event_id")
    event = events.get(event_id) if event_id else None
    if event and event_matches_game(game, event, team_map):
        return event, False

    matching_event = find_matching_event(game, events, team_map)
    if matching_event:
        if game.get("gc_event_id") != matching_event.get("id"):
            game["gc_event_id"] = matching_event["id"]
            return matching_event, True
        return matching_event, False

    if event:
        label = game.get("label", event_id)
        expected = ", ".join(sorted(game_team_names(game))) or "TBD"
        actual = ", ".join(sorted(event_team_names(event, team_map))) or "TBD"
        print(f"Skipping {label}: GC event teams ({actual}) do not match bracket teams ({expected})")
    return None, False


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


def event_scores_by_team(event, team_map):
    """Return canonical team name → score for a GC event."""
    scores = {}
    for side in ("home", "away"):
        gc_team = event.get(f"{side}_team", {})
        name = resolve_team(gc_team.get("id"), team_map)
        score = gc_team.get("score")
        if name and score is not None:
            scores[name] = score
    return scores


def standings_records(standings):
    """Return team name → regular-season standings row."""
    records = {}
    for league in ("american_league", "national_league"):
        for team in standings.get(league, []):
            records[team["name"]] = team
    return records


def head_to_head_points(team_name, opponent_name, games):
    """Return standings points earned by team_name against opponent_name."""
    points = 0
    for game in games:
        home = game["home"]
        away = game["away"]
        if team_name == home and opponent_name == away:
            team_score = game["home_score"]
            opponent_score = game["away_score"]
        elif team_name == away and opponent_name == home:
            team_score = game["away_score"]
            opponent_score = game["home_score"]
        else:
            continue

        if team_score > opponent_score:
            points += 2
        elif team_score == opponent_score:
            points += 1
    return points


def head_to_head_runs_allowed(team_name, opponent_name, games):
    """Return runs allowed by team_name against opponent_name."""
    runs_allowed = 0
    for game in games:
        home = game["home"]
        away = game["away"]
        if team_name == home and opponent_name == away:
            runs_allowed += game["away_score"]
        elif team_name == away and opponent_name == home:
            runs_allowed += game["home_score"]
    return runs_allowed


def world_series_home_field_team(standings, al_champion, nl_champion):
    """Return the champion with home-field advantage for World Series Games 1 and 3."""
    records = standings_records(standings)
    games = standings.get("games", [])
    al_record = records[al_champion]
    nl_record = records[nl_champion]

    comparisons = [
        (al_record["points"], nl_record["points"], True),
        (
            head_to_head_points(al_champion, nl_champion, games),
            head_to_head_points(nl_champion, al_champion, games),
            True,
        ),
        (al_record["division_points"], nl_record["division_points"], True),
        (
            head_to_head_runs_allowed(al_champion, nl_champion, games),
            head_to_head_runs_allowed(nl_champion, al_champion, games),
            False,
        ),
        (al_record["division_runs_allowed"], nl_record["division_runs_allowed"], False),
        (al_record["runs_allowed"], nl_record["runs_allowed"], False),
    ]

    for al_value, nl_value, prefer_max in comparisons:
        if al_value == nl_value:
            continue
        if prefer_max:
            return al_champion if al_value > nl_value else nl_champion
        return al_champion if al_value < nl_value else nl_champion

    return min(al_champion, nl_champion)


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


def set_slot(game, side, team_name, seed=None):
    """Set a bracket slot and return True if it changed."""
    slot = game.get(side) or {}
    changed = False

    if slot.get("name") != team_name:
        slot["name"] = team_name
        changed = True
    if seed is not None and slot.get("seed") != seed:
        slot["seed"] = seed
        changed = True
    if "note" in slot:
        del slot["note"]
        changed = True

    game[side] = slot
    return changed


def set_matchup_by_seed(bracket, league, round_key, teams):
    """Assign two teams to a matchup, with the better seed as home."""
    if len(teams) != 2:
        return False

    first, second = teams
    first_seed = find_seed(bracket, league, first)
    second_seed = find_seed(bracket, league, second)

    if first_seed is not None and second_seed is not None and second_seed < first_seed:
        home, home_seed = second, second_seed
        away, away_seed = first, first_seed
    else:
        home, home_seed = first, first_seed
        away, away_seed = second, second_seed

    game = bracket.get(league, {}).get(round_key, {})
    existing_scores = {}
    existing_home = (game.get("home") or {}).get("name")
    existing_away = (game.get("away") or {}).get("name")
    if existing_home and "home_score" in game:
        existing_scores[existing_home] = game["home_score"]
    if existing_away and "away_score" in game:
        existing_scores[existing_away] = game["away_score"]

    changed = set_slot(game, "home", home, home_seed)
    changed = set_slot(game, "away", away, away_seed) or changed
    if home in existing_scores and game.get("home_score") != existing_scores[home]:
        game["home_score"] = existing_scores[home]
        changed = True
    if away in existing_scores and game.get("away_score") != existing_scores[away]:
        game["away_score"] = existing_scores[away]
        changed = True

    return changed


def enforce_seeded_home_teams(bracket):
    """Ensure league playoff games use the higher seed as home."""
    changed = False

    for league in ("american_league", "national_league"):
        for round_key in ROUNDS:
            game = bracket.get(league, {}).get(round_key, {})
            home = game.get("home") or {}
            away = game.get("away") or {}
            home_seed = home.get("seed")
            away_seed = away.get("seed")

            if home_seed is None or away_seed is None or home_seed <= away_seed:
                continue

            game["home"], game["away"] = away, home
            if "home_score" in game or "away_score" in game:
                game["home_score"], game["away_score"] = (
                    game.get("away_score"),
                    game.get("home_score"),
                )
            changed = True

    return changed


def set_game_teams(game, home, away):
    """Set game home/away teams, preserving scores with the matching teams."""
    existing_scores = {}
    existing_home = (game.get("home") or {}).get("name")
    existing_away = (game.get("away") or {}).get("name")
    if existing_home and "home_score" in game:
        existing_scores[existing_home] = game["home_score"]
    if existing_away and "away_score" in game:
        existing_scores[existing_away] = game["away_score"]

    changed = set_slot(game, "home", home)
    changed = set_slot(game, "away", away) or changed
    if home in existing_scores and game.get("home_score") != existing_scores[home]:
        game["home_score"] = existing_scores[home]
        changed = True
    if away in existing_scores and game.get("away_score") != existing_scores[away]:
        game["away_score"] = existing_scores[away]
        changed = True

    return changed


def assign_world_series_home_teams(bracket, standings):
    """Alternate World Series home teams, with home-field advantage in Games 1 and 3."""
    ws = bracket.get("world_series", {})
    al_champion = ws.get("al_champion")
    nl_champion = ws.get("nl_champion")
    if not al_champion or not nl_champion or "TBD" in (al_champion, nl_champion):
        return False

    advantage = world_series_home_field_team(standings, al_champion, nl_champion)
    other = nl_champion if advantage == al_champion else al_champion
    changed = False

    for index, game in enumerate(ws.get("games", [])):
        if index % 2 == 0:
            home, away = advantage, other
        else:
            home, away = other, advantage
        changed = set_game_teams(game, home, away) or changed

    return changed


def update_game(game, event, team_map):
    """Update a single bracket game from a GC event. Returns True if changed."""
    changed = False

    # Sync date and time from GC schedule.
    et = event_datetime(event)
    if et:
        gc_date = et.strftime("%Y-%m-%d")
        gc_time = et.strftime("%-I:%M %p")
        if game.get("date") != gc_date:
            game["date"] = gc_date
            changed = True
        if game.get("time") != gc_time:
            game["time"] = gc_time
            changed = True

    # Update team names if GC has resolved TBD placeholders.
    for side in ("home", "away"):
        gc_side = event.get(f"{side}_team", {})
        gc_id = gc_side.get("id")
        if gc_id and gc_id not in TBD_TEAM_IDS:
            canonical = resolve_team(gc_id, team_map)
            slot = game.get(side) or {}
            if canonical and slot.get("name") in ("TBD", None):
                slot["name"] = canonical
                if "note" in slot:
                    del slot["note"]
                game[side] = slot
                changed = True

    if event.get("game_status") == "completed":
        scores = event_scores_by_team(event, team_map)
        home_name = (game.get("home") or {}).get("name")
        away_name = (game.get("away") or {}).get("name")
        if home_name in scores and away_name in scores:
            home_score = scores[home_name]
            away_score = scores[away_name]
            winner = determine_winner(event, team_map)
            if game.get("status") != "final":
                game["status"] = "final"
                changed = True
            if game.get("home_score") != home_score:
                game["home_score"] = home_score
                changed = True
            if game.get("away_score") != away_score:
                game["away_score"] = away_score
                changed = True
            if winner and game.get("winner") != winner:
                game["winner"] = winner
                changed = True
        else:
            home = event.get("home_team", {})
            away = event.get("away_team", {})
            home_score = home.get("score")
            away_score = away.get("score")
            if home_score is None or away_score is None:
                return changed
            game["status"] = "final"
            game["home_score"] = home_score
            game["away_score"] = away_score
            winner = determine_winner(event, team_map)
            if winner:
                game["winner"] = winner
            changed = True

    return changed


def advance_winners(bracket):
    """Propagate winners to the next bracket round, reseeding before the World Series."""
    changed = False

    for league in ("american_league", "national_league"):
        play_in_winner = bracket.get(league, {}).get("play_in", {}).get("winner")
        semifinal_lower = bracket.get(league, {}).get("semifinal_lower", {})
        bye_team = (semifinal_lower.get("home") or {}).get("name")
        if play_in_winner and bye_team and bye_team != "TBD":
            changed = set_matchup_by_seed(
                bracket,
                league,
                "semifinal_lower",
                [bye_team, play_in_winner],
            ) or changed

        semifinal_winners = [
            bracket.get(league, {}).get(round_key, {}).get("winner")
            for round_key in ("semifinal_upper", "semifinal_lower")
        ]
        if all(semifinal_winners):
            changed = set_matchup_by_seed(
                bracket,
                league,
                "championship",
                semifinal_winners,
            ) or changed

    # Championship winners → World Series
    for league, ws_key in [("american_league", "al_champion"), ("national_league", "nl_champion")]:
        champ_game = bracket.get(league, {}).get("championship", {})
        winner = champ_game.get("winner")
        if winner and bracket.get("world_series", {}).get(ws_key) != winner:
            bracket["world_series"][ws_key] = winner
            changed = True

    changed = enforce_seeded_home_teams(bracket) or changed
    return changed


def update_games(games, events, team_map):
    """Update bracket games from matching GC events."""
    changed = False

    for game in games:
        event, event_changed = get_event_for_game(game, events, team_map)
        changed = event_changed or changed
        if not event:
            continue
        changed = update_game(game, event, team_map) or changed

    return changed


def update_world_series(bracket, events, team_map):
    """Update World Series game results."""
    ws = bracket.get("world_series", {})
    return update_games(ws.get("games", []), events, team_map)


def main():
    team_map = load_teams()
    bracket = load_playoffs()
    standings = load_standings()
    events = fetch_events()
    changed = False

    if advance_winners(bracket):
        changed = True

    for league in ("american_league", "national_league"):
        league_data = bracket.get(league, {})
        for round_key in ROUNDS:
            game = league_data.get(round_key, {})
            if update_games([game], events, team_map):
                changed = True
            if advance_winners(bracket):
                changed = True

    if advance_winners(bracket):
        changed = True

    if assign_world_series_home_teams(bracket, standings):
        changed = True

    if update_world_series(bracket, events, team_map):
        changed = True

    if assign_world_series_home_teams(bracket, standings):
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
