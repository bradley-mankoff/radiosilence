import json
import os
import time
import unittest
import urllib.error
from datetime import date, datetime

# Expected times below are Dallas local time.
os.environ["TZ"] = "America/Chicago"
time.tzset()

from app import CACHE_SECONDS, Cached, respond
from judging import ESPN, judge

GAME_DAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 23, 19, 0).astimezone()  # 7:00 PM Dallas time on the Game day
SCOREBOARD = f"{ESPN}/scoreboard?dates=20261023"
TEAM_LIST = f"{ESPN}/teams"

NBA_TEAMS = ["ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS",
             "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NO", "NY",
             "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SA", "TOR", "UTAH", "WSH"]


def team_list(abbreviations):
    """ESPN's teams endpoint: every NBA team, with the abbreviation ESPN uses for it."""
    return {"sports": [{"leagues": [{"teams": [
        {"team": {"abbreviation": abbreviation, "displayName": abbreviation}}
        for abbreviation in abbreviations]}]}]}


ESPN_TEAM_LIST = team_list(NBA_TEAMS)

BOS = ("BOS", "Boston Celtics")
NY = ("NY", "New York Knicks")
IND = ("IND", "Indiana Pacers")
MIA = ("MIA", "Miami Heat")
LAL = ("LAL", "Los Angeles Lakers")
DEN = ("DEN", "Denver Nuggets")
DAL = ("DAL", "Dallas Mavericks")
HOU = ("HOU", "Houston Rockets")
SA = ("SA", "San Antonio Spurs")
OKC = ("OKC", "Oklahoma City Thunder")


def side(home_or_away, team, score="0"):
    """One competitor in an ESPN event; team is an (abbreviation, display name) pair."""
    abbreviation, name = team
    return {"homeAway": home_or_away, "score": score,
            "team": {"abbreviation": abbreviation, "displayName": name}}


def event(event_id, start, state, home, away):
    """An ESPN scoreboard or schedule event. home and away are (team, score) pairs."""
    return {"id": event_id, "date": start, "competitions": [{
        "status": {"type": {"state": state}},
        "competitors": [side("home", home[0], home[1]), side("away", away[0], away[1])],
    }]}


def schedule(team, events):
    """An ESPN team schedule: its header names the team ESPN knows, and its events use that abbreviation."""
    abbreviation, name = team
    return {"team": {"abbreviation": abbreviation, "displayName": name}, "events": events}


def summary(home, away, plays, state="in"):
    """An ESPN summary. plays is a list of (period, clock, home win probability) in ESPN's list order."""
    return {
        "header": {"competitions": [{
            "status": {"type": {"state": state}},
            "competitors": [side("home", home), side("away", away)],
        }]},
        "plays": [{"id": str(i), "period": {"number": p}, "clock": {"displayValue": c}}
                  for i, (p, c, _) in enumerate(plays)],
        "winprobability": [{"playId": str(i), "homeWinPercentage": w}
                           for i, (_, _, w) in enumerate(plays)],
    }


def espn(responses):
    """Saved ESPN JSON by URL, with ESPN's team list unless the test saves its own. A URL that was not saved
    raises, so a test fails if judge asks for more than it needs."""
    responses = {TEAM_LIST: ESPN_TEAM_LIST, **responses}

    def get(url):
        return responses[url]
    return get


class Counting:
    """Saved ESPN JSON that also records every URL it was asked for."""
    def __init__(self, responses):
        self.responses, self.asked = responses, []

    def __call__(self, url):
        self.asked.append(url)
        return self.responses[url]

    def count(self, url):
        return self.asked.count(url)


def night():
    """Saved ESPN responses for Friday, Oct 23, 2026, and the Saturday after it."""
    finished = event("e1", "2026-10-23T17:00Z", "post", (NY, "117"), (BOS, "104"))
    live_early = event("e2", "2026-10-23T23:10Z", "in", (MIA, "88"), (IND, "91"))
    live_late = event("e3", "2026-10-23T22:40Z", "in", (DEN, "96"), (LAL, "77"))
    tonight = event("e4", "2026-10-24T00:30Z", "pre", (DAL, "0"), (HOU, "0"))
    later = event("e5", "2026-10-25T00:00Z", "pre", (SA, "0"), (OKC, "0"))
    return {
        TEAM_LIST: ESPN_TEAM_LIST,
        SCOREBOARD: {"events": [finished, live_early, live_late, tonight]},
        f"{ESPN}/summary?event=e1": summary(NY, BOS, [(4, "0:00", 0.9931)], state="post"),
        f"{ESPN}/summary?event=e2": summary(MIA, IND, [(2, "7:12", 0.6234)]),
        f"{ESPN}/summary?event=e3": summary(DEN, LAL, [(3, "8:00", 0.2010), (4, "3:00", 0.0312)]),
        f"{ESPN}/teams/dal/schedule": {"events": [tonight]},
        f"{ESPN}/teams/sa/schedule": {"events": [later]},
        f"{ESPN}/scoreboard?dates=20261024": {"events": []},
    }


def row_for(team, responses, day=GAME_DAY):
    return {row["team"]: row for row in judge([team], day, espn(responses))}[team]


OPPONENT = ("MIA", "Miami Heat")


def one_game_row(team, plays, team_at_home=False):
    """Judge `team` in one started game against Miami, with ESPN's plays in the given list order."""
    home, away = (team, OPPONENT) if team_at_home else (OPPONENT, team)
    responses = {
        SCOREBOARD: {"events": [event("solo", "2026-10-23T23:10Z", "in", (home, "0"), (away, "0"))]},
        f"{ESPN}/summary?event=solo": summary(home, away, plays),
    }
    return row_for(team[0], responses)


class JudgingTest(unittest.TestCase):
    def test_one_row_per_team_for_the_night(self):
        rows = {row["team"]: row for row in judge(
            ["BOS", "NY", "IND", "MIA", "LAL", "DEN", "DAL", "SA"], GAME_DAY, espn(night()))}
        self.assertEqual(rows, {
            "BOS": {"team": "BOS", "verdict": "Stay away", "detail": "This one looks out of reach.", "next_game": None},
            "NY": {"team": "NY", "verdict": "Watch", "detail": "Still a game.", "next_game": None},
            "IND": {"team": "IND", "verdict": "Too early to call",
                    "detail": "Check back after the middle of the 2nd quarter.", "next_game": None},
            "MIA": {"team": "MIA", "verdict": "Too early to call",
                    "detail": "Check back after the middle of the 2nd quarter.", "next_game": None},
            "LAL": {"team": "LAL", "verdict": "Watch", "detail": "Still a game.", "next_game": None},
            "DEN": {"team": "DEN", "verdict": "Stay away", "detail": "This one looks out of reach.", "next_game": None},
            "DAL": {"team": "DAL", "verdict": None, "detail": None,
                    "next_game": {"day": "Today", "time": "7:30 PM", "opponent": "Houston Rockets", "home": True}},
            "SA": {"team": "SA", "verdict": None, "detail": None,
                    "next_game": {"day": "Sat, Oct 24", "time": "7:00 PM", "opponent": "Oklahoma City Thunder",
                                  "home": True}},
        })

    def test_a_finished_game_keeps_its_verdict_on_the_game_day(self):
        row = row_for("BOS", night())
        self.assertEqual(row["verdict"], "Stay away")

    def test_a_finished_game_gives_way_to_the_next_game_after_midnight(self):
        responses = night()
        responses[f"{ESPN}/teams/bos/schedule"] = {"events": [
            event("e1", "2026-10-23T17:00Z", "post", (NY, "117"), (BOS, "104")),
            event("e6", "2026-10-27T23:00Z", "pre", (OKC, "0"), (BOS, "0")),
        ]}
        row = row_for("BOS", responses, day=date(2026, 10, 24))
        self.assertEqual(row["next_game"], {"day": "Tue, Oct 27", "time": "6:00 PM", "opponent": "Oklahoma City Thunder",
                                            "home": False})

    def test_a_team_named_by_a_short_name_espn_does_not_use_gets_its_verdict(self):
        live = event("e7", "2026-10-23T23:10Z", "in", (NY, "0"), (BOS, "0"))
        responses = {
            SCOREBOARD: {"events": [live]},
            f"{ESPN}/summary?event=e7": summary(NY, BOS, [(3, "8:00", 0.02)]),
        }
        self.assertEqual(row_for("NYK", responses),
                         {"team": "NYK", "verdict": "Stay away", "detail": "This one looks out of reach.",
                          "next_game": None})

    def test_a_team_named_by_a_short_name_espn_does_not_use_gets_its_next_game(self):
        game = event("e8", "2026-10-25T00:00Z", "pre", (NY, "0"), (BOS, "0"))
        responses = {SCOREBOARD: {"events": []}, f"{ESPN}/teams/ny/schedule": schedule(NY, [game])}
        self.assertEqual(row_for("NYK", responses)["next_game"],
                         {"day": "Sat, Oct 24", "time": "7:00 PM", "opponent": "Boston Celtics", "home": True})

    def test_a_team_espn_does_not_know_gets_a_row_that_says_so(self):
        rows = judge(["XYZ"], GAME_DAY, espn({SCOREBOARD: {"events": []}}))
        self.assertEqual(rows, [{"team": "XYZ", "verdict": None,
                                 "detail": "ESPN doesn't list an NBA team called XYZ.", "next_game": None}])

    def test_a_team_with_no_game_left_says_so(self):
        responses = {SCOREBOARD: {"events": []}, f"{ESPN}/teams/por/schedule": {"events": []}}
        row = row_for("POR", responses)
        self.assertEqual(row, {"team": "POR", "verdict": None, "detail": "No more games scheduled.",
                               "next_game": None})

    def test_a_blowout_before_the_judging_window_is_too_early_to_call(self):
        row = one_game_row(BOS, [(2, "6:01", 0.97)])
        self.assertEqual(row["verdict"], "Too early to call")

    def test_a_blowout_at_six_minutes_left_in_the_second_is_stay_away(self):
        row = one_game_row(BOS, [(2, "6:00", 0.96)])
        self.assertEqual(row["verdict"], "Stay away")

    def test_a_team_at_home_is_judged_against_the_away_side(self):
        row = one_game_row(BOS, [(3, "8:00", 0.04)], team_at_home=True)
        self.assertEqual(row["verdict"], "Stay away")

    def test_exactly_ninety_five_percent_is_still_watchable(self):
        row = one_game_row(BOS, [(3, "8:00", 0.95)])
        self.assertEqual(row["verdict"], "Watch")

    def test_a_comeback_goes_back_from_stay_away_to_watch(self):
        row = one_game_row(BOS, [(2, "5:00", 0.98), (3, "4:00", 0.99), (4, "3:00", 0.60)])
        self.assertEqual(row["verdict"], "Watch")

    def test_a_late_stat_correction_at_the_end_of_the_list_is_not_the_latest_reading(self):
        row = one_game_row(IND, [(4, "3:00", 0.30), (2, "5:30", 0.99)])
        self.assertEqual(row["verdict"], "Watch")

    def test_a_game_with_no_win_probability_yet_is_too_early_to_call(self):
        responses = {
            SCOREBOARD: {"events": [event("solo", "2026-10-23T23:10Z", "in", (MIA, "0"), (IND, "0"))]},
            f"{ESPN}/summary?event=solo": summary(MIA, IND, []),
        }
        self.assertEqual(row_for("IND", responses)["verdict"], "Too early to call")


class RowsResponseTest(unittest.TestCase):
    def rows_body(self, teams, now=NOW, get=None):
        status, content_type, body = respond(f"/rows?teams={','.join(teams)}", now, get or espn(night()))
        self.assertEqual(status, 200)
        return body

    def test_no_row_contains_a_score_clock_quarter_percentage_or_tip_off_of_a_started_game(self):
        body = self.rows_body(["BOS", "NY", "IND", "MIA", "LAL", "DEN", "DAL", "SA"])
        for spoiler in ["117", "104", "88", "91", "96", "77", "%", "0.9931", "0.6234", "0.0312", "0.9688",
                        "0:00", "7:12", "3:00", "8:00", "3rd", "4th", "12:00 PM", "6:10 PM", "5:40 PM", "overtime"]:
            self.assertNotIn(spoiler, body.decode(), spoiler)

    def test_a_finished_game_row_has_the_same_shape_as_a_live_one(self):
        rows = {row["team"]: row for row in json.loads(self.rows_body(["BOS", "IND"]))["rows"]}
        self.assertEqual(set(rows["BOS"]), set(rows["IND"]))
        self.assertEqual(set(rows["BOS"]), {"team", "verdict", "detail", "next_game"})

    def test_the_root_page_still_shows_the_mavericks_next_game(self):
        status, content_type, body = respond("/", NOW, espn(night()))
        self.assertEqual(status, 200)
        self.assertIn("Next game", body.decode())
        self.assertIn("Today, 7:30 PM vs Houston Rockets", body.decode())

    def test_names_espn_does_not_know_do_not_blank_the_other_rows(self):
        status, content_type, body = respond("/rows?teams=BOS,XYZ,NEW%20YORK", NOW, espn(night()))
        self.assertEqual(status, 200)
        rows = {row["team"]: row for row in json.loads(body)["rows"]}
        self.assertEqual(rows["BOS"]["verdict"], "Stay away")
        self.assertEqual(rows["XYZ"], {"team": "XYZ", "verdict": None,
                                        "detail": "ESPN doesn't list an NBA team called XYZ.", "next_game": None})
        self.assertEqual(rows["NEW YORK"]["detail"], "ESPN doesn't list an NBA team called NEW YORK.")

    def test_a_name_espn_cannot_list_gets_its_own_row(self):
        status, content_type, body = respond("/rows?teams=_", NOW, espn(night()))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["rows"],
                         [{"team": "_", "verdict": None,
                           "detail": "ESPN doesn't list an NBA team called _.", "next_game": None}])

    def test_a_name_espn_does_not_list_costs_only_the_team_list_fetch(self):
        fake = Counting(night())
        respond("/rows?teams=_", NOW, fake)
        self.assertEqual(fake.asked, [TEAM_LIST])

    def test_an_unreachable_espn_is_an_error_not_a_verdict(self):
        def offline(url):
            raise urllib.error.URLError("offline")
        status, content_type, body = respond("/rows?teams=BOS", NOW, offline)
        self.assertEqual(status, 503)
        self.assertNotIn("rows", json.loads(body))
        self.assertIn("error", json.loads(body))


class CachingTest(unittest.TestCase):
    def test_requests_for_the_same_game_within_one_cycle_cost_one_espn_fetch(self):
        fake = Counting(night())
        cache = Cached(fake, clock=lambda: 0)
        respond("/rows?teams=BOS,DEN", NOW, cache)
        respond("/rows?teams=BOS,DEN", NOW, cache)
        self.assertEqual(fake.count(f"{ESPN}/summary?event=e1"), 1)
        self.assertEqual(fake.count(f"{ESPN}/summary?event=e3"), 1)

    def test_the_team_list_is_fetched_once_a_day(self):
        fake = Counting(night())
        now = [0]
        cache = Cached(fake, clock=lambda: now[0])
        respond("/rows?teams=BOS", NOW, cache)
        now[0] = 12 * 60 * 60
        respond("/rows?teams=BOS", NOW, cache)
        self.assertEqual(fake.count(TEAM_LIST), 1)
        now[0] = 24 * 60 * 60
        respond("/rows?teams=BOS", NOW, cache)
        self.assertEqual(fake.count(TEAM_LIST), 2)

    def test_after_the_cycle_ends_the_game_is_fetched_again(self):
        fake = Counting(night())
        now = [0]
        cache = Cached(fake, clock=lambda: now[0])
        respond("/rows?teams=BOS", NOW, cache)
        now[0] = CACHE_SECONDS
        respond("/rows?teams=BOS", NOW, cache)
        self.assertEqual(fake.count(f"{ESPN}/summary?event=e1"), 2)


if __name__ == "__main__":
    unittest.main()
