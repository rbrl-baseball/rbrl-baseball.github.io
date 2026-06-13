#!/usr/bin/env python3

import copy
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("update-playoffs.py")
spec = importlib.util.spec_from_file_location("update_playoffs", MODULE_PATH)
update_playoffs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_playoffs)


TEAM_MAP = {
    "FOMGvZmC0gch": {"name": "Royals"},
    "66tiLz0VM3zM": {"name": "Mariners"},
    "H31Y5RGs1o5n": {"name": "Pirates"},
    "OFdLcufZgA9n": {"name": "Padres"},
}


BRACKET = {
    "american_league": {
        "play_in": {"winner": "Athletics", "home": {"name": "Astros", "seed": 4}, "away": {"name": "Athletics", "seed": 5}},
        "semifinal_upper": {"winner": "Mariners", "home": {"name": "Mariners", "seed": 2}, "away": {"name": "Angels", "seed": 3}},
        "semifinal_lower": {"winner": "Royals", "home": {"name": "Royals", "seed": 1}, "away": {"name": "Athletics", "seed": 5}},
        "championship": {"home": {"name": "Royals", "seed": 1}, "away": {"name": "Mariners", "seed": 2}},
    },
    "national_league": {
        "play_in": {"winner": "Padres", "home": {"name": "Padres", "seed": 4}, "away": {"name": "Cubs", "seed": 5}},
        "semifinal_upper": {"winner": "Pirates", "home": {"name": "Phillies", "seed": 2}, "away": {"name": "Pirates", "seed": 3}},
        "semifinal_lower": {"winner": "Padres", "home": {"name": "Marlins", "seed": 1}, "away": {"name": "Padres", "seed": 4}},
        "championship": {"home": {"name": "Padres", "seed": 4}, "away": {"name": "Pirates", "seed": 3}},
    },
    "world_series": {"al_champion": "TBD", "nl_champion": "TBD"},
}


STANDINGS = {
    "american_league": [
        {
            "name": "Royals",
            "points": 20,
            "division_points": 14,
            "runs_allowed": 45,
            "division_runs_allowed": 20,
        },
    ],
    "national_league": [
        {
            "name": "Padres",
            "points": 10,
            "division_points": 6,
            "runs_allowed": 70,
            "division_runs_allowed": 48,
        },
    ],
    "games": [],
}


class UpdatePlayoffsTest(unittest.TestCase):
    def test_advancement_reseeds_championship_home_team(self):
        bracket = copy.deepcopy(BRACKET)

        changed = update_playoffs.advance_winners(bracket)

        self.assertTrue(changed)
        championship = bracket["national_league"]["championship"]
        self.assertEqual("Pirates", championship["home"]["name"])
        self.assertEqual(3, championship["home"]["seed"])
        self.assertEqual("Padres", championship["away"]["name"])
        self.assertEqual(4, championship["away"]["seed"])

    def test_seed_enforcement_keeps_scores_with_teams(self):
        bracket = copy.deepcopy(BRACKET)
        bracket["american_league"]["semifinal_upper"] = {
            "status": "final",
            "home": {"name": "Angels", "seed": 3},
            "away": {"name": "Mariners", "seed": 2},
            "home_score": 5,
            "away_score": 8,
            "winner": "Mariners",
        }

        changed = update_playoffs.enforce_seeded_home_teams(bracket)

        semifinal = bracket["american_league"]["semifinal_upper"]
        self.assertTrue(changed)
        self.assertEqual("Mariners", semifinal["home"]["name"])
        self.assertEqual(8, semifinal["home_score"])
        self.assertEqual("Angels", semifinal["away"]["name"])
        self.assertEqual(5, semifinal["away_score"])

    def test_event_lookup_corrects_swapped_event_id_by_participants(self):
        game = {
            "label": "AL Championship",
            "date": "2026-06-12",
            "gc_event_id": "nl-event",
            "home": {"name": "Royals", "seed": 1},
            "away": {"name": "Mariners", "seed": 2},
        }
        events = {
            "nl-event": {
                "id": "nl-event",
                "start_ts": "2026-06-12T21:45:00.000Z",
                "home_team": {"id": "H31Y5RGs1o5n"},
                "away_team": {"id": "OFdLcufZgA9n"},
            },
            "al-event": {
                "id": "al-event",
                "start_ts": "2026-06-12T21:45:00.000Z",
                "home_team": {"id": "FOMGvZmC0gch"},
                "away_team": {"id": "66tiLz0VM3zM"},
            },
        }

        event, changed = update_playoffs.get_event_for_game(game, events, TEAM_MAP)

        self.assertTrue(changed)
        self.assertEqual("al-event", event["id"])
        self.assertEqual("al-event", game["gc_event_id"])

    def test_completed_scores_are_mapped_by_bracket_team_names(self):
        game = {
            "status": "scheduled",
            "home": {"name": "Pirates", "seed": 3},
            "away": {"name": "Padres", "seed": 4},
        }
        event = {
            "game_status": "completed",
            "home_team": {"id": "OFdLcufZgA9n", "score": 8},
            "away_team": {"id": "H31Y5RGs1o5n", "score": 5},
        }

        changed = update_playoffs.update_game(game, event, TEAM_MAP)

        self.assertTrue(changed)
        self.assertEqual("final", game["status"])
        self.assertEqual(5, game["home_score"])
        self.assertEqual(8, game["away_score"])
        self.assertEqual("Padres", game["winner"])

    def test_world_series_home_teams_alternate_from_home_field_advantage(self):
        bracket = copy.deepcopy(BRACKET)
        bracket["world_series"] = {
            "al_champion": "Royals",
            "nl_champion": "Padres",
            "games": [{}, {}, {"if_necessary": True}],
        }

        changed = update_playoffs.assign_world_series_home_teams(bracket, STANDINGS)

        games = bracket["world_series"]["games"]
        self.assertTrue(changed)
        self.assertEqual("Royals", games[0]["home"]["name"])
        self.assertEqual("Padres", games[0]["away"]["name"])
        self.assertEqual("Padres", games[1]["home"]["name"])
        self.assertEqual("Royals", games[1]["away"]["name"])
        self.assertEqual("Royals", games[2]["home"]["name"])
        self.assertEqual("Padres", games[2]["away"]["name"])

    def test_world_series_home_team_switch_preserves_scores(self):
        bracket = copy.deepcopy(BRACKET)
        bracket["world_series"] = {
            "al_champion": "Royals",
            "nl_champion": "Padres",
            "games": [
                {
                    "status": "final",
                    "home": {"name": "Padres"},
                    "away": {"name": "Royals"},
                    "home_score": 2,
                    "away_score": 7,
                    "winner": "Royals",
                },
            ],
        }

        changed = update_playoffs.assign_world_series_home_teams(bracket, STANDINGS)

        game = bracket["world_series"]["games"][0]
        self.assertTrue(changed)
        self.assertEqual("Royals", game["home"]["name"])
        self.assertEqual(7, game["home_score"])
        self.assertEqual("Padres", game["away"]["name"])
        self.assertEqual(2, game["away_score"])


if __name__ == "__main__":
    unittest.main()
