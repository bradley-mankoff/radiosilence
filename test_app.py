import unittest
from datetime import date

from app import seconds_left, todays_game_id, verdict


def summary(state, mavs_side, plays):
    """Build a minimal ESPN summary; `plays` is a list of (period, clock, home_win_percentage)."""
    other_side = "away" if mavs_side == "home" else "home"
    return {
        "header": {"competitions": [{
            "status": {"type": {"state": state}},
            "competitors": [
                {"homeAway": mavs_side, "team": {"abbreviation": "DAL"}},
                {"homeAway": other_side, "team": {"abbreviation": "IND"}},
            ],
        }]},
        "plays": [{"id": str(i), "period": {"number": p}, "clock": {"displayValue": c}}
                  for i, (p, c, _) in enumerate(plays)],
        "winprobability": [{"playId": str(i), "homeWinPercentage": w}
                           for i, (_, _, w) in enumerate(plays)],
    }


class VerdictTest(unittest.TestCase):
    def test_not_started(self):
        self.assertEqual(verdict(summary("pre", "away", []))[0], "Not started")

    def test_blowout_before_the_cutoff_is_too_early(self):
        game = summary("in", "away", [(2, "6:01", 0.97)])
        self.assertEqual(verdict(game)[0], "Too early to call")

    def test_blowout_at_the_cutoff_is_stay_away(self):
        game = summary("in", "away", [(2, "6:00", 0.91)])
        self.assertEqual(verdict(game)[0], "Stay away")

    def test_mavs_at_home_use_the_away_side(self):
        game = summary("in", "home", [(3, "8:00", 0.05)])
        self.assertEqual(verdict(game)[0], "Stay away")

    def test_exactly_ninety_percent_is_still_watchable(self):
        game = summary("in", "away", [(3, "8:00", 0.90)])
        self.assertEqual(verdict(game)[0], "Watch")

    def test_comeback_uses_the_latest_reading(self):
        game = summary("in", "away", [(2, "5:00", 0.95), (4, "3:00", 0.60)])
        self.assertEqual(verdict(game)[0], "Watch")

    def test_seconds_left_under_a_minute(self):
        self.assertEqual(seconds_left("45.2"), 45.2)
        self.assertEqual(seconds_left("6:00"), 360)

    def test_todays_game_uses_local_date(self):
        schedule = {"events": [{"id": "1", "date": "2026-10-22T00:30Z"},
                               {"id": "2", "date": "2026-10-23T23:00Z"}]}
        self.assertEqual(todays_game_id(schedule, date(2026, 10, 23)), "2")
        self.assertIsNone(todays_game_id(schedule, date(2026, 10, 24)))


if __name__ == "__main__":
    unittest.main()
