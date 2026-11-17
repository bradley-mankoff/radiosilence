import json
import os
import re
import struct
import time
import unittest
import urllib.error
from datetime import date, datetime
from html.parser import HTMLParser

# Expected times below are Dallas local time.
os.environ["TZ"] = "America/Chicago"
time.tzset()

from app import CACHE_SECONDS, Cached, HTML_TYPE, JSON_TYPE, respond
from judging import ESPN, judge, start_time
from presets import Settings

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


def summary(home, away, plays, state="in", home_score="0", away_score="0"):
    """An ESPN summary. plays is a list of (period, clock, home win probability) in ESPN's list order."""
    return {
        "header": {"competitions": [{
            "status": {"type": {"state": state}},
            "competitors": [side("home", home, home_score), side("away", away, away_score)],
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
    live_late = event("e3", "2026-10-23T22:40Z", "in", (DEN, "77"), (LAL, "96"))
    tonight = event("e4", "2026-10-24T00:30Z", "pre", (DAL, "0"), (HOU, "0"))
    later = event("e5", "2026-10-25T00:00Z", "pre", (SA, "0"), (OKC, "0"))
    return {
        TEAM_LIST: ESPN_TEAM_LIST,
        SCOREBOARD: {"events": [finished, live_early, live_late, tonight]},
        f"{ESPN}/summary?event=e1": summary(NY, BOS, [(2, "5:00", 0.99), (4, "0:00", 0.995)],
                                              state="post", home_score="117", away_score="104"),
        f"{ESPN}/summary?event=e2": summary(MIA, IND, [(2, "7:12", 0.6234)]),
        f"{ESPN}/summary?event=e3": summary(DEN, LAL, [(3, "8:00", 0.01), (4, "3:00", 0.02)],
                                              home_score="77", away_score="96"),
        f"{ESPN}/teams/dal/schedule": {"events": [tonight]},
        f"{ESPN}/teams/sa/schedule": {"events": [later]},
        f"{ESPN}/scoreboard?dates=20261024": {"events": []},
    }


def row_for(team, responses, day=GAME_DAY, fan=None):
    return {row["team"]: row for row in judge([team], day, espn(responses), fan)}[team]


OPPONENT = ("MIA", "Miami Heat")
NO_BLOWOUT_LOSSES = Settings(picked=["blow"])
WINS_FOR_MY_TEAM = Settings(picked=["wins"])


def one_game_row(team, plays, team_at_home=False, fan=None, state="in",
                 team_score="0", opponent_score="0"):
    """Judge `team` in one started game against Miami, with ESPN's plays in the given list order."""
    home, away = (team, OPPONENT) if team_at_home else (OPPONENT, team)
    home_score, away_score = (team_score, opponent_score) if team_at_home else (opponent_score, team_score)
    responses = {
        SCOREBOARD: {"events": [event("solo", "2026-10-23T23:10Z", state, (home, "0"), (away, "0"))]},
        f"{ESPN}/summary?event=solo": summary(home, away, plays, state=state,
                                              home_score=home_score, away_score=away_score),
    }
    return row_for(team[0], responses, fan=fan)


class JudgingTest(unittest.TestCase):
    def test_one_row_per_team_for_the_night(self):
        rows = {row["team"]: row for row in judge(
            ["BOS", "NY", "IND", "MIA", "LAL", "DEN", "DAL", "SA"], GAME_DAY, espn(night()),
            NO_BLOWOUT_LOSSES)}
        self.assertEqual(rows, {
            "BOS": {"team": "BOS", "verdict": "Stay away", "detail": "This one looks out of reach.", "next_game": None},
            "NY": {"team": "NY", "verdict": "Watch", "detail": "Still a game.", "next_game": None},
            "IND": {"team": "IND", "verdict": "Too early to call",
                    "detail": "Check back later.", "next_game": None},
            "MIA": {"team": "MIA", "verdict": "Too early to call",
                    "detail": "Check back later.", "next_game": None},
            "LAL": {"team": "LAL", "verdict": "Watch", "detail": "Still a game.", "next_game": None},
            "DEN": {"team": "DEN", "verdict": "Stay away", "detail": "This one looks out of reach.", "next_game": None},
            "DAL": {"team": "DAL", "verdict": None, "detail": None,
                    "next_game": {"day": "Today", "time": "7:30 PM", "opponent": "Houston Rockets", "home": True}},
            "SA": {"team": "SA", "verdict": None, "detail": None,
                    "next_game": {"day": "Sat, Oct 24", "time": "7:00 PM", "opponent": "Oklahoma City Thunder",
                                  "home": True}},
        })

    def test_a_finished_game_keeps_its_verdict_on_the_game_day(self):
        row = row_for("BOS", night(), fan=NO_BLOWOUT_LOSSES)
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
            f"{ESPN}/summary?event=e7": summary(NY, BOS, [(3, "8:00", 0.01)]),
        }
        self.assertEqual(row_for("NYK", responses, fan=NO_BLOWOUT_LOSSES),
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

    def test_a_blowout_before_judge_from_is_too_early_to_call(self):
        row = one_game_row(BOS, [(2, "6:01", 0.99)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Too early to call")

    def test_a_blowout_from_judge_from_on_is_stay_away(self):
        row = one_game_row(BOS, [(2, "6:00", 0.99)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_a_team_at_home_is_judged_against_the_away_side(self):
        row = one_game_row(BOS, [(3, "8:00", 0.01)], team_at_home=True, fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_exactly_the_upper_line_is_not_over_it(self):
        row = one_game_row(BOS, [(3, "8:00", 0.98)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Watch")

    def test_no_blowout_losses_holds_its_band(self):
        row = one_game_row(BOS, [(2, "5:00", 0.99), (3, "4:00", 0.96)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_no_blowout_losses_returns_to_watch_below_the_lower_line(self):
        row = one_game_row(BOS, [(2, "5:00", 0.99), (3, "4:00", 0.94)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Watch")

    def test_exactly_the_lower_line_does_not_release(self):
        row = one_game_row(BOS, [(2, "5:00", 0.99), (3, "4:00", 0.95)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_no_blowout_losses_is_frozen_after_freeze_at(self):
        row = one_game_row(BOS, [(4, "5:05", 0.99), (4, "3:00", 0.01)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_a_last_second_close_loss_reads_watch_under_no_blowout_losses(self):
        row = one_game_row(BOS, [(4, "5:05", 0.97), (4, "0:00", 1.0)], fan=NO_BLOWOUT_LOSSES,
                           state="post", team_score="100", opponent_score="101")
        self.assertEqual(row["verdict"], "Watch")

    def test_a_comeback_goes_back_from_stay_away_to_watch(self):
        row = one_game_row(BOS, [(2, "5:00", 0.99), (3, "4:00", 0.99), (3, "2:00", 0.60)],
                           fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Watch")

    def test_a_late_stat_correction_at_the_end_of_the_list_is_read_in_game_time(self):
        row = one_game_row(IND, [(4, "6:00", 0.30), (2, "5:30", 0.99)], fan=NO_BLOWOUT_LOSSES)
        self.assertEqual(row["verdict"], "Watch")

    def test_wins_for_my_team_is_too_early_before_the_final(self):
        row = one_game_row(BOS, [(3, "8:00", 0.99)], fan=WINS_FOR_MY_TEAM,
                           team_score="110", opponent_score="100")
        self.assertEqual(row["verdict"], "Too early to call")

    def test_wins_for_my_team_watches_a_win_after_the_final(self):
        row = one_game_row(BOS, [(4, "0:00", 1.0)], fan=WINS_FOR_MY_TEAM, state="post",
                           team_score="110", opponent_score="100")
        self.assertEqual(row["verdict"], "Watch")

    def test_wins_for_my_team_stays_away_from_a_loss_after_the_final(self):
        row = one_game_row(BOS, [(4, "0:00", 0.0)], fan=WINS_FOR_MY_TEAM, state="post",
                           team_score="100", opponent_score="110")
        self.assertEqual(row["verdict"], "Stay away")

    def assert_both_presets(self, plays, join, expected, state="in", team_score="0", opponent_score="0"):
        """The BOS row with both Presets picked, for the answers `plays` and the score give, joined `join`."""
        row = one_game_row(BOS, plays, fan=Settings(picked=["wins", "blow"], join=join),
                           state=state, team_score=team_score, opponent_score=opponent_score)
        self.assertEqual(row["verdict"], expected)

    def test_both_presets_not_yet_is_too_early_to_call_either_way(self):
        self.assert_both_presets([(2, "7:00", 0.5)], "OR", "Too early to call")
        self.assert_both_presets([(2, "7:00", 0.5)], "AND", "Too early to call")

    def test_a_fitting_preset_beside_wins_for_my_team_not_yet_is_watch_with_or_too_early_with_and(self):
        self.assert_both_presets([(3, "8:00", 0.6)], "OR", "Watch")
        self.assert_both_presets([(3, "8:00", 0.6)], "AND", "Too early to call")

    def test_a_not_fitting_preset_beside_wins_not_yet_is_too_early_with_or_stay_away_with_and(self):
        self.assert_both_presets([(3, "8:00", 0.99)], "OR", "Too early to call")
        self.assert_both_presets([(3, "8:00", 0.99)], "AND", "Stay away")

    def test_both_presets_fitting_is_watch_either_way(self):
        self.assert_both_presets([(3, "8:00", 0.6)], "OR", "Watch", state="post",
                                 team_score="110", opponent_score="100")
        self.assert_both_presets([(3, "8:00", 0.6)], "AND", "Watch", state="post",
                                 team_score="110", opponent_score="100")

    def test_one_fitting_preset_beside_a_not_fitting_one_is_watch_with_or_stay_away_with_and(self):
        self.assert_both_presets([(2, "5:00", 0.99)], "OR", "Watch", state="post",
                                 team_score="110", opponent_score="100")
        self.assert_both_presets([(2, "5:00", 0.99)], "AND", "Stay away", state="post",
                                 team_score="110", opponent_score="100")

    def test_swapping_which_preset_fits_keeps_the_same_verdicts(self):
        self.assert_both_presets([(3, "8:00", 0.6)], "OR", "Watch", state="post",
                                 team_score="100", opponent_score="110")
        self.assert_both_presets([(3, "8:00", 0.6)], "AND", "Stay away", state="post",
                                 team_score="100", opponent_score="110")

    def test_both_presets_not_fitting_is_stay_away_either_way(self):
        self.assert_both_presets([(2, "5:00", 0.99)], "OR", "Stay away", state="post",
                                 team_score="100", opponent_score="110")
        self.assert_both_presets([(2, "5:00", 0.99)], "AND", "Stay away", state="post",
                                 team_score="100", opponent_score="110")

    def test_a_game_with_no_win_probability_yet_is_too_early_to_call(self):
        responses = {
            SCOREBOARD: {"events": [event("solo", "2026-10-23T23:10Z", "in", (MIA, "0"), (IND, "0"))]},
            f"{ESPN}/summary?event=solo": summary(MIA, IND, []),
        }
        self.assertEqual(row_for("IND", responses, fan=NO_BLOWOUT_LOSSES)["verdict"],
                         "Too early to call")


class RowsResponseTest(unittest.TestCase):
    def rows_body(self, teams, now=NOW, get=None):
        status, content_type, body = respond(f"/rows?teams={','.join(teams)}&presets=blow",
                                             now, get or espn(night()))
        self.assertEqual(status, 200)
        return body

    def test_no_row_contains_a_score_clock_quarter_percentage_or_tip_off_of_a_started_game(self):
        body = self.rows_body(["BOS", "NY", "IND", "MIA", "LAL", "DEN", "DAL", "SA"])
        for spoiler in ["117", "104", "88", "91", "96", "77", "%", "0.99", "0.6234", "0.01", "0.9688",
                        "98", "95", "0:00", "7:12", "3:00", "8:00", "3rd", "4th", "12:00 PM", "6:10 PM",
                        "5:40 PM", "overtime"]:
            self.assertNotIn(spoiler, body.decode(), spoiler)

    def test_a_finished_game_row_has_the_same_shape_as_a_live_one(self):
        rows = {row["team"]: row for row in json.loads(self.rows_body(["BOS", "IND"]))["rows"]}
        self.assertEqual(set(rows["BOS"]), set(rows["IND"]))
        self.assertEqual(set(rows["BOS"]), {"team", "verdict", "detail", "next_game"})

    def test_names_espn_does_not_know_do_not_blank_the_other_rows(self):
        status, content_type, body = respond("/rows?teams=BOS,XYZ,NEW%20YORK&presets=blow", NOW, espn(night()))
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

    def test_a_watch_answer_does_not_say_which_preset_fitted(self):
        # Watch here comes from No blowout losses fitting while Wins for my team is not yet.
        live = {
            SCOREBOARD: {"events": [event("live", "2026-10-23T23:10Z", "in", (MIA, "0"), (BOS, "0"))]},
            f"{ESPN}/summary?event=live": summary(MIA, BOS, [(3, "8:00", 0.6)]),
        }
        # Watch here comes from Wins for my team fitting after a final that was once a blowout.
        final = {
            SCOREBOARD: {"events": [event("done", "2026-10-23T23:10Z", "post", (MIA, "100"), (BOS, "110"))]},
            f"{ESPN}/summary?event=done": summary(MIA, BOS, [(2, "5:00", 0.99)], state="post",
                                                  home_score="100", away_score="110"),
        }
        asked = "/rows?teams=BOS&presets=wins,blow&join=OR"
        self.assertEqual(respond(asked, NOW, espn(live))[2], respond(asked, NOW, espn(final))[2])

    def test_a_request_that_names_no_preset_gets_a_row_that_says_so(self):
        status, content_type, body = respond("/rows?teams=BOS", NOW, espn(night()))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["rows"][0],
                         {"team": "BOS", "verdict": None,
                          "detail": "Pick a Preset to judge this game.", "next_game": None})

    def test_an_unreachable_espn_is_an_error_not_a_verdict(self):
        def offline(url):
            raise urllib.error.URLError("offline")
        status, content_type, body = respond("/rows?teams=BOS", NOW, offline)
        self.assertEqual(status, 503)
        self.assertNotIn("rows", json.loads(body))
        self.assertIn("error", json.loads(body))


class PresetsResponseTest(unittest.TestCase):
    def test_the_presets_answer_lists_each_preset_with_its_sliders_and_defaults(self):
        status, content_type, body = respond("/presets", NOW, espn(night()))
        self.assertEqual(status, 200)
        self.assertEqual(content_type, JSON_TYPE)
        answer = json.loads(body)
        self.assertEqual([preset["name"] for preset in answer["presets"]],
                         ["Wins for my team", "No blowout losses"])
        self.assertEqual(answer["presets"][0], {"key": "wins", "name": "Wins for my team", "sliders": []})
        self.assertEqual(answer["presets"][1]["sliders"], [
            {"parameter": "blow_upper", "name": "Stay away above",
             "min": 90, "max": 99, "default": 98, "unit": "%"},
            {"parameter": "blow_lower", "name": "Back to Watch below",
             "min": 85, "max": 98, "default": 95, "unit": "%"},
        ])
        self.assertEqual([slider["parameter"] for slider in answer["shared"]], ["judge_from", "freeze_at"])
        self.assertEqual([slider["default"] for slider in answer["shared"]], [1080, 2580])


class PresetSettingsTest(unittest.TestCase):
    def blow_row(self, plays, query=""):
        """The BOS row for one started game against Miami, judged from the query's Preset settings."""
        responses = {
            SCOREBOARD: {"events": [event("solo", "2026-10-23T23:10Z", "in", (MIA, "0"), (BOS, "0"))]},
            f"{ESPN}/summary?event=solo": summary(MIA, BOS, plays),
        }
        status, content_type, body = respond(f"/rows?teams=BOS&presets=blow{query}", NOW, espn(responses))
        self.assertEqual(status, 200)
        return json.loads(body)["rows"][0]

    def test_missing_slider_values_use_the_defaults(self):
        self.assertEqual(self.blow_row([(2, "6:00", 0.99)])["verdict"], "Stay away")

    def test_an_out_of_range_slider_value_falls_back_to_its_default(self):
        # 150 is outside the upper line's 90-99 range, so the default 98 decides and 99% stays Stay away.
        self.assertEqual(self.blow_row([(2, "6:00", 0.99)], "&blow_upper=150")["verdict"], "Stay away")
        # 10 is outside the lower line's 85-98 range, so the default 95 releases the hold at 94%.
        self.assertEqual(self.blow_row([(2, "5:00", 0.99), (3, "4:00", 0.94)],
                                       "&blow_lower=10")["verdict"], "Watch")

    def test_an_in_range_slider_value_moves_the_verdict(self):
        # 98.5% is over the shipped 98% line, and under a line the fan moved to 99%.
        self.assertEqual(self.blow_row([(3, "8:00", 0.985)])["verdict"], "Stay away")
        self.assertEqual(self.blow_row([(3, "8:00", 0.985)], "&blow_upper=99")["verdict"], "Watch")

    def test_the_served_default_is_the_default_the_verdict_uses(self):
        answer = json.loads(respond("/presets", NOW, espn(night()))[2])
        upper = next(slider for slider in answer["presets"][1]["sliders"]
                     if slider["parameter"] == "blow_upper")["default"]
        self.assertEqual(self.blow_row([(3, "8:00", upper / 100)])["verdict"], "Watch")
        self.assertEqual(self.blow_row([(3, "8:00", (upper + 1) / 100)])["verdict"], "Stay away")


class Tags(HTMLParser):
    """Every start tag in a page, with its attributes, in the order it appears."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []

    def handle_starttag(self, tag, attrs):
        self.found.append((tag, dict(attrs)))


class Words(HTMLParser):
    """The text a browser would show for a piece of markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def tags(markup):
    parser = Tags()
    parser.feed(markup)
    return parser.found


def words(markup):
    parser = Words()
    parser.feed(markup)
    return " ".join("".join(parser.parts).split())


def cards(page):
    """The cards on a list page, by team, each as its own markup."""
    return dict(re.findall(r'<article class="card" data-team="([^"]+)">(.*?)</article>', page, re.S))


def summary_text(card):
    return words(re.search(r"<summary>(.*?)</summary>", card, re.S).group(1))


def checked_teams(page):
    return sorted(attrs["value"] for tag, attrs in tags(page)
                  if tag == "input" and attrs.get("name") == "teams" and "checked" in attrs)


class PageTest(unittest.TestCase):
    def page(self, path="/", get=None):
        status, content_type, body = respond(path, NOW, get or espn(night()))
        self.assertEqual(status, 200)
        self.assertEqual(content_type, HTML_TYPE)
        return body.decode()

    def test_the_first_visit_opens_team_setup(self):
        page = self.page("/")
        self.assertIn(("form", {"id": "setup", "method": "get", "action": "/"}), tags(page))
        self.assertEqual(cards(page), {})

    def test_setup_offers_all_thirty_teams_by_abbreviation(self):
        values = [attrs["value"] for tag, attrs in tags(self.page("/"))
                  if tag == "input" and attrs.get("name") == "teams"]
        self.assertEqual(sorted(values), sorted(NBA_TEAMS))

    def test_the_page_saves_picked_teams_on_the_phone(self):
        self.assertRegex(self.page("/"), r'localStorage\.setItem\("radiosilence\.teams", picked\)')

    def test_the_page_sends_a_fan_with_saved_teams_to_their_cards(self):
        page = self.page("/")
        self.assertRegex(page, r'localStorage\.getItem\("radiosilence\.teams"\)')
        self.assertIn('location.replace("/?teams=" + encodeURIComponent(saved))', page)

    def test_picking_teams_shows_one_card_per_team(self):
        page = self.page("/?teams=LAL&teams=BOS&teams=IND")
        self.assertEqual(sorted(cards(page)), ["BOS", "IND", "LAL"])

    def test_the_list_header_shows_only_the_app_name_and_the_gear(self):
        page = self.page("/?teams=LAL")
        header = re.search(r"<header>(.*?)</header>", page, re.S).group(1)
        self.assertEqual(words(header), "RadioSilence ⚙︎")
        self.assertEqual(next(attrs for tag, attrs in tags(header) if tag == "a")["href"],
                         "/?setup=1&teams=LAL")

    def test_the_comma_joined_teams_the_script_saves_show_one_card_each(self):
        # The script saves the picks joined with commas, so a reload arrives as one `teams` value.
        self.assertEqual(sorted(cards(self.page("/?teams=LAL,BOS"))), ["BOS", "LAL"])

    def test_the_gear_reopens_setup_with_the_fans_teams_ticked(self):
        page = self.page("/?teams=LAL&teams=BOS")
        gear = next(attrs for tag, attrs in tags(page) if attrs.get("class") == "gear")
        setup = self.page(gear["href"])
        self.assertEqual(checked_teams(setup), ["BOS", "LAL"])

    def assert_dot(self, team, verdict, dot_class, colour):
        """The card's dot: its class and the Verdict it labels, no Verdict word, and the colour it paints."""
        page = self.page(f"/?teams={team}&presets=blow")
        card = cards(page)[team]
        dot = next(attrs for tag, attrs in tags(card) if "dot" in (attrs.get("class") or ""))
        self.assertEqual(dot["class"], f"dot {dot_class}")
        self.assertEqual(dot["aria-label"], verdict)
        self.assertNotIn(verdict, summary_text(card))
        self.assertIn(f"--{dot_class}:{colour};", page)  # the palette holds the colour...
        self.assertIn(f".dot.{dot_class} {{ background:var(--{dot_class}); }}", page)  # ...and paints with it

    def test_a_watch_card_has_a_green_dot_and_no_verdict_word(self):
        self.assert_dot("LAL", "Watch", "watch", "#2e9e5b")

    def test_a_stay_away_card_has_a_red_dot_and_no_verdict_word(self):
        self.assert_dot("BOS", "Stay away", "stay", "#c0392b")

    def test_a_too_early_card_has_a_yellow_dot_and_no_verdict_word(self):
        self.assert_dot("IND", "Too early to call", "early", "#e3b341")

    def test_a_team_with_no_started_game_shows_its_next_game_preview(self):
        card = cards(self.page("/?teams=DAL"))["DAL"]
        self.assertIn("Today, 7:30 PM vs Houston Rockets", summary_text(card))

    def test_tapping_a_card_outside_its_buttons_opens_the_rule_applied_to_it(self):
        card = cards(self.page("/?teams=BOS&presets=blow"))["BOS"]
        self.assertIn("<details>", card)
        self.assertNotIn("<details open", card)
        self.assertIn("The Presets you pick decide this dot.", words(card))
        self.assertNotIn("<button", re.search(r"<summary>(.*?)</summary>", card, re.S).group(1))

    def test_the_highlights_button_says_no_highlights_yet_and_is_disabled(self):
        card = cards(self.page("/?teams=BOS"))["BOS"]
        attributes, label = re.search(r'<button class="highlights"([^>]*)>(.*?)</button>',
                                       card, re.S).groups()
        self.assertIn("disabled", attributes)
        self.assertEqual(words(label), "No highlights yet")

    def test_the_list_refreshes_after_a_minute(self):
        self.assertIn(("meta", {"http-equiv": "refresh", "content": "60"}),
                      tags(self.page("/?teams=DAL")))

    def test_the_page_says_plainly_when_espn_cannot_be_reached(self):
        def offline(url):
            raise urllib.error.URLError("offline")
        page = self.page("/?teams=BOS", get=offline)
        self.assertIn("Couldn't reach ESPN (URLError).", words(page))
        self.assertEqual(sorted(cards(page)), ["BOS"])

    def test_the_page_is_addable_to_the_home_screen_as_radiosilence(self):
        page = self.page("/")
        found = tags(page)
        self.assertIn(("link", {"rel": "manifest", "href": "/manifest.webmanifest"}), found)
        self.assertIn(("meta", {"name": "apple-mobile-web-app-capable", "content": "yes"}), found)
        self.assertIn(("meta", {"name": "apple-mobile-web-app-title", "content": "RadioSilence"}), found)
        self.assertIn(("link", {"rel": "apple-touch-icon", "href": "/icon-180.png"}), found)
        self.assertEqual(re.search(r"<title>(.*?)</title>", page, re.S).group(1), "RadioSilence")

    def test_the_manifest_names_the_app_radiosilence(self):
        status, content_type, body = respond("/manifest.webmanifest", NOW, espn(night()))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["name"], "RadioSilence")

    def test_the_manifest_icon_is_a_served_png(self):
        manifest = json.loads(respond("/manifest.webmanifest", NOW, espn(night()))[2])
        self.assertTrue(manifest["icons"])
        for icon in manifest["icons"]:
            status, content_type, body = respond(icon["src"], NOW, espn(night()))
            self.assertEqual(status, 200)
            self.assertEqual(content_type, "image/png")
            self.assertTrue(body.startswith(b"\x89PNG\r\n\x1a\n"))
            width, height = struct.unpack(">II", body[16:24])
            self.assertEqual(f"{width}x{height}", icon["sizes"])

    def test_a_live_game_puts_no_score_clock_quarter_or_percentage_in_the_page_or_its_script(self):
        page = self.page("/?teams=BOS&teams=IND&teams=LAL&teams=DAL&teams=SA&presets=blow")
        # The rules panel's words are the same for every game, not a Reading from this one.
        self.assertIn("The Presets you pick decide this dot.", page)
        for spoiler in ["117", "104", "88", "91", "96", "77", "7:12", "8:00", "3:00", "0:00",
                        "3rd", "4th", "0.99", "0.6234", "0.01", "98%", "95%",
                        "12:00 PM", "6:10 PM", "5:40 PM", "overtime", "final"]:
            self.assertNotIn(spoiler, page, spoiler)


SEASON_CACHE = "/tmp/bgw-season-2026"


@unittest.skipUnless(os.path.exists(f"{SEASON_CACHE}/schedule.json"),
                     f"no cached 2025-26 season in {SEASON_CACHE}")
class SeasonReplayTest(unittest.TestCase):
    def test_no_blowout_losses_reads_stay_away_in_25_of_the_82_games(self):
        with open(f"{SEASON_CACHE}/schedule.json") as saved:
            schedule = json.load(saved)
        completed = [event for event in schedule["events"]
                     if event["competitions"][0]["status"]["type"]["state"] == "post"]
        stay_away, played = 0, 0
        for event in completed:
            with open(f"{SEASON_CACHE}/{event['id']}.json") as saved:
                game = json.load(saved)
            if not game.get("plays"):
                continue
            played += 1
            day = start_time(event).date()
            responses = {
                TEAM_LIST: ESPN_TEAM_LIST,
                f"{ESPN}/scoreboard?dates={day:%Y%m%d}": {"events": [event]},
                f"{ESPN}/summary?event={event['id']}": game,
            }
            row = judge(["DAL"], day, responses.__getitem__, NO_BLOWOUT_LOSSES)[0]
            if row["verdict"] == "Stay away":
                stay_away += 1
        self.assertEqual(played, 82)
        self.assertEqual(stay_away, 25)


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
