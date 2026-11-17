import collections
import json
import os
import re
import struct
import time
import unittest
import urllib.error
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

# Expected times below are Dallas local time.
os.environ["TZ"] = "America/Chicago"
time.tzset()

import highlights
import players
from app import CACHE_SECONDS, Cached, HTML_TYPE, JSON_TYPE, respond
from catchup import LINE, catch_up
from judging import ESPN, judge, start_time
from players import Checks, DID_NOT_PLAY, TrackedPlayer, player_verdict
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
LAC = ("LAC", "LA Clippers")

# The button a started game shows while no reel has been found, as the rows and the page hold it.
WAITING = {"label": "No highlights yet", "link": None}


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


def unreachable_for(responses, broken_url):
    """Saved ESPN JSON that raises for `broken_url` and answers every other URL, as ESPN refusing one."""
    saved = espn(responses)

    def get(url):
        if url == broken_url:
            raise urllib.error.URLError("offline")
        return saved(url)
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
CLOSE_GAMES = Settings(picked=["close"])
HIGH_SCORING_GAMES = Settings(picked=["high"])


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


def scored_summary(home, away, plays, state="in"):
    """An ESPN summary whose plays each carry the score after them, in ESPN's list order.

    plays is a list of (period, clock, home score, away score); the last one is the game's score so far.
    """
    game = summary(home, away, [], state=state,
                   home_score=str(plays[-1][2]), away_score=str(plays[-1][3]))
    game["plays"] = [{"id": str(i), "period": {"number": period}, "clock": {"displayValue": clock},
                      "homeScore": home_score, "awayScore": away_score}
                     for i, (period, clock, home_score, away_score) in enumerate(plays)]
    return game


def scored_responses(team, plays, state="in"):
    """ESPN's saved answers for `team` at home against Miami, whose plays each carry the score after them."""
    return {
        SCOREBOARD: {"events": [event("solo", "2026-10-23T23:10Z", state, (team, "0"), (OPPONENT, "0"))]},
        f"{ESPN}/summary?event=solo": scored_summary(team, OPPONENT, plays, state),
    }


def scored_game_row(team, plays, state="in", fan=None):
    """Judge `team` at home against Miami from the score after each play: (period, clock, team, Miami)."""
    return row_for(team[0], scored_responses(team, plays, state), fan=fan)


# The catch-up tests use their own two teams and players, so every expected line is a small literal.
DAL_ID, BOS_ID = "6", "2"
CATCHUP_URL = f"{ESPN}/summary?event=catchup"
PERIOD_LABELS = {1: "1st Quarter", 2: "2nd Quarter", 3: "3rd Quarter", 4: "4th Quarter",
                 5: "OT", 6: "2OT", 7: "3OT"}


def line(**stats):
    """A catch-up line with every stat present, zero unless the test names it."""
    return {field: stats.get(field, 0) for field in LINE}


def game_play(play_id, period, clock, team, type_text, text, short, participants=(),
              scoring=False, score=0, shooting=False, attempted=2):
    """One play in ESPN's summary, with the fields the catch-up answer reads."""
    return {"id": play_id,
            "period": {"number": period, "displayValue": PERIOD_LABELS[period]},
            "clock": {"displayValue": clock},
            "team": {"id": team} if team else None,
            "type": {"text": type_text},
            "shortDescription": short,
            "text": text,
            "participants": [{"athlete": {"id": player_id}} for player_id in participants],
            "scoringPlay": scoring, "scoreValue": score,
            "shootingPlay": shooting, "pointsAttempted": attempted}


def roster_player(player_id, name, starter=False):
    """One athlete in ESPN's boxscore. The stat values are absurd on purpose: catch-up reads names and ids only."""
    return {"athlete": {"id": player_id, "displayName": name}, "starter": starter,
            "didNotPlay": False, "stats": ["99", "99"]}


def roster_team(team_id, team, players):
    """One team in ESPN's boxscore, with its roster in ESPN's order. A player is (id, name) when he came
    off the bench, or (id, name, True) when he tipped off."""
    abbreviation, name = team
    return {"team": {"id": team_id, "abbreviation": abbreviation, "displayName": name},
            "statistics": [{"labels": ["MIN", "PTS"],
                            "athletes": [roster_player(*player) for player in players]}]}


def handmade_game(extra_plays=()):
    """A hand-built Dallas-Boston game: a jump ball, a made shot with an assist, a miss, a rebound, a
    foul, a turnover and two free throws, all in the first quarter. `extra_plays` are appended after
    them, as ESPN appends a late correction."""
    plays = [
        game_play("p1", 1, "12:00", DAL_ID, "Jumpball",
                  "Dereck Lively II vs. Jayson Tatum (Luka Doncic gains possession)", "Jump Ball",
                  ("d3", "b1")),
        game_play("p2", 1, "11:40", DAL_ID, "Jump Shot",
                  "Luka Doncic makes 18-foot jump shot (Kyrie Irving assists)", "+2 Points",
                  ("d1", "d2"), scoring=True, score=2, shooting=True),
        game_play("p3", 1, "11:05", BOS_ID, "Jump Shot",
                  "Jayson Tatum misses 25-foot three point jumper", "Missed 3PT",
                  ("b1",), shooting=True, attempted=3),
        game_play("p4", 1, "10:30", DAL_ID, "Offensive Rebound",
                  "Dereck Lively II offensive rebound", "Rebound", ("d3",)),
        game_play("p5", 1, "10:10", BOS_ID, "Driving Layup Shot",
                  "Jayson Tatum makes driving layup", "+2 Points",
                  ("b1",), scoring=True, score=2, shooting=True),
        game_play("p6", 1, "9:45", DAL_ID, "Bad Pass",
                  "Luka Doncic bad pass turnover (Jaylen Brown steals)", "Turnover",
                  ("d1", "b2")),
        game_play("p7", 1, "9:20", DAL_ID, "Shooting Foul",
                  "Dereck Lively II shooting foul", "Foul", ("d3",)),
        game_play("p8", 1, "9:00", BOS_ID, "Free Throw - 1 of 2",
                  "Jayson Tatum makes free throw 1 of 2", "+1 Point",
                  ("b1",), scoring=True, score=1, shooting=True, attempted=1),
        game_play("p9", 1, "9:00", BOS_ID, "Free Throw - 2 of 2",
                  "Jayson Tatum misses free throw 2 of 2", "Missed FT",
                  ("b1",), shooting=True, attempted=1),
        game_play("p10", 1, "0:00", None, "End Period", "End of the 1st Quarter", "End of 1st"),
    ]
    return {
        "header": {"competitions": [{
            "status": {"type": {"state": "in"}},
            "competitors": [
                {"homeAway": "home", "score": "2",
                 "team": {"id": DAL_ID, "abbreviation": "DAL", "displayName": "Dallas Mavericks"}},
                {"homeAway": "away", "score": "3",
                 "team": {"id": BOS_ID, "abbreviation": "BOS", "displayName": "Boston Celtics"}},
            ],
        }]},
        "boxscore": {"players": [
            roster_team(DAL_ID, DAL, [("d1", "Luka Doncic", True), ("d2", "Kyrie Irving", True),
                                      ("d3", "Dereck Lively II", True)]),
            roster_team(BOS_ID, BOS, [("b1", "Jayson Tatum", True), ("b2", "Jaylen Brown", True)]),
        ]},
        "plays": plays + list(extra_plays),
    }


def substitution_game():
    """A hand-built game whose Dallas lineup changes twice: d1 sits down 6:00 into the 1st, and d6 plays
    out the quarter and through the break until d1 comes back 3:00 into the 2nd. Dallas tips off with d1
    to d5, Boston with b1 and b2."""
    game = handmade_game()
    game["boxscore"]["players"][0] = roster_team(DAL_ID, DAL, [
        ("d1", "Luka Doncic", True), ("d2", "Kyrie Irving", True), ("d3", "Dereck Lively II", True),
        ("d4", "P.J. Washington", True), ("d5", "Klay Thompson", True),
        ("d6", "Naji Marshall")])
    game["plays"] = [
        game_play("sub1", 1, "6:00", DAL_ID, "Substitution",
                  "Naji Marshall enters the game for Luka Doncic", "Substitution", ("d6", "d1")),
        game_play("q1-end", 1, "0:00", None, "End Period", "End of the 1st Quarter", "End of 1st"),
        game_play("q2-tip", 2, "12:00", DAL_ID, "Jumpball",
                  "Jump ball to start the 2nd", "Jump Ball", ("d3", "b1")),
        game_play("sub2", 2, "9:00", DAL_ID, "Substitution",
                  "Luka Doncic enters the game for Naji Marshall", "Substitution", ("d1", "d6")),
        game_play("q2-end", 2, "0:00", None, "End Period", "End of the 2nd Quarter", "End of 2nd"),
    ]
    return game


def minutes_by_name(answer):
    """The minutes the catch-up answer gives each player, by name."""
    return {player["name"]: player["minutes"] for player in answer["players"]}


def expected_play(play_id, period, clock, team, text):
    """One play as the catch-up answer sends it."""
    return {"id": play_id, "period": period, "clock": clock, "team": team, "text": text}


def overtime_game():
    """A hand-built game with three overtimes, each play at a distinctive game time."""
    game = handmade_game()
    game["plays"] = [
        game_play("q4", 4, "12:00", DAL_ID, "Jumpball", "Jump ball to start the 4th", "Jump Ball",
                  ("d3", "b1")),
        game_play("reg", 4, "0:00", None, "End Period", "End of the 4th Quarter", "End of 4th"),
        game_play("ot-tip", 5, "5:00", DAL_ID, "Jumpball",
                  "Jump ball to start overtime", "Jump Ball", ("d3", "b1")),
        game_play("ot1", 5, "4:30", DAL_ID, "Driving Layup Shot",
                  "Luka Doncic makes driving layup", "+2 Points", ("d1",),
                  scoring=True, score=2, shooting=True),
        game_play("end1", 5, "0:00", None, "End Period", "End of the 1st OT", "End of 1st OT"),
        game_play("ot2", 6, "1:00", BOS_ID, "Jump Shot",
                  "Jayson Tatum makes 20-foot jumper", "+2 Points", ("b1",),
                  scoring=True, score=2, shooting=True),
        game_play("ot2-late", 6, "0:59", BOS_ID, "Jump Shot",
                  "Jayson Tatum makes 21-foot jumper", "+2 Points", ("b1",),
                  scoring=True, score=2, shooting=True),
        game_play("end2", 6, "0:00", None, "End Period", "End of the 2nd OT", "End of 2nd OT"),
        game_play("ot3", 7, "1:00", DAL_ID, "Jump Shot",
                  "Luka Doncic makes 25-foot three point jumper", "+3 Points", ("d1",),
                  scoring=True, score=3, shooting=True, attempted=3),
        game_play("end3", 7, "0:00", None, "End Period", "End of the 3rd OT", "End of 3rd OT"),
        game_play("over", 7, "0:00", None, "End Game", "End of Game", "End of Game"),
    ]
    return game


def regulation_end_game():
    """A hand-built game that ended in regulation: a 4th-quarter shot, then ESPN's whistle at the end
    of the 4th and its end-of-game marker."""
    game = handmade_game()
    game["plays"] = [
        game_play("q4", 4, "12:00", DAL_ID, "Jumpball", "Jump ball to start the 4th", "Jump Ball",
                  ("d3", "b1")),
        game_play("shot", 4, "0:30", DAL_ID, "Driving Layup Shot",
                  "Luka Doncic makes driving layup", "+2 Points", ("d1",),
                  scoring=True, score=2, shooting=True),
        game_play("reg", 4, "0:00", None, "End Period", "End of the 4th Quarter", "End of 4th"),
        game_play("over", 4, "0:00", None, "End Game", "End of Game", "End of Game"),
    ]
    return game


# The tracked-player tests follow Luka Doncic, Dallas's d1, through a hand-built Dallas-Boston game.
TRACKED_ID, TRACKED_NAME = "d1", "Luka Doncic"
ATHLETE_API = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes"
PLAYER_API = f"{ATHLETE_API}/{TRACKED_ID}"
PLAYER_OVERVIEW = f"{PLAYER_API}/overview"
PLAYER_STATS = f"{PLAYER_API}/stats"
ATHLETE_LABELS = ["GP", "MIN", "FG%", "3P%", "FT%", "REB", "AST", "BLK", "STL", "PF", "TO", "PTS"]


def clock_at(elapsed):
    """The quarter and its clock when `elapsed` minutes of game time have been played."""
    period = int(elapsed // 12) + 1
    left = 12 * period - elapsed
    return period, f"{int(left)}:{round((left - int(left)) * 60):02d}"


def tracked_game(points=0, rebounds=0, assists=0, steals=0, blocks=0, threes=0,
                 minutes=6, state="in", bench=False):
    """A Dallas-Boston game in which Luka Doncic has exactly the named line by `minutes` minutes played.

    He tips off unless `bench`, in which case he enters `minutes` before the end of the 1st quarter. A
    timeout at the moment the game has been followed to stops the replay's minutes there, so a test's
    expected projection is the literal it passes rather than one this helper works out.
    """
    game = handmade_game()
    game["header"]["competitions"][0]["status"]["type"]["state"] = state
    plays = []
    if bench:
        game["boxscore"]["players"][0]["statistics"][0]["athletes"][0]["starter"] = False
        period, clock = clock_at(12 - minutes)
        plays.append(game_play("sub", period, clock, DAL_ID, "Substitution",
                               f"{TRACKED_NAME} enters the game for Kyrie Irving", "Substitution",
                               (TRACKED_ID, "d2")))
        stop = 12
    else:
        stop = minutes
    period, clock = clock_at(stop)
    leftover = points - 3 * threes
    for index in range(threes):
        plays.append(game_play(f"three{index}", period, clock, DAL_ID, "Jump Shot",
                               f"{TRACKED_NAME} makes 25-foot three point jumper", "+3 Points",
                               (TRACKED_ID,), scoring=True, score=3, shooting=True, attempted=3))
    for index in range(leftover // 2):
        plays.append(game_play(f"shot{index}", period, clock, DAL_ID, "Driving Layup Shot",
                               f"{TRACKED_NAME} makes driving layup", "+2 Points",
                               (TRACKED_ID,), scoring=True, score=2, shooting=True))
    if leftover % 2:
        plays.append(game_play("free-throw", period, clock, DAL_ID, "Free Throw - 1 of 1",
                               f"{TRACKED_NAME} makes free throw", "+1 Point",
                               (TRACKED_ID,), scoring=True, score=1, shooting=True, attempted=1))
    for index in range(assists):
        plays.append(game_play(f"assist{index}", period, clock, DAL_ID, "Jump Shot",
                               f"Kyrie Irving makes jump shot ({TRACKED_NAME} assists)", "+2 Points",
                               ("d2", TRACKED_ID), scoring=True, score=2, shooting=True))
    for index in range(rebounds):
        plays.append(game_play(f"rebound{index}", period, clock, DAL_ID, "Defensive Rebound",
                               f"{TRACKED_NAME} defensive rebound", "Rebound", (TRACKED_ID,)))
    for index in range(steals):
        plays.append(game_play(f"steal{index}", period, clock, BOS_ID, "Bad Pass",
                               f"Jayson Tatum bad pass turnover ({TRACKED_NAME} steals)", "Turnover",
                               ("b1", TRACKED_ID)))
    for index in range(blocks):
        plays.append(game_play(f"block{index}", period, clock, BOS_ID, "Jump Shot",
                               f"Jayson Tatum misses jumper ({TRACKED_NAME} blocks shot)",
                               "Missed 2PT", ("b1", TRACKED_ID), shooting=True))
    plays.append(game_play("stop", period, clock, None, "Timeout", "Timeout", "Timeout"))
    game["plays"] = plays
    return game


def did_not_play_game():
    """A final Dallas-Boston game with Naji Marshall on the bench and no play naming him."""
    game = handmade_game()
    game["header"]["competitions"][0]["status"]["type"]["state"] = "post"
    game["boxscore"]["players"][0]["statistics"][0]["athletes"].append(
        roster_player("d6", "Naji Marshall"))
    game["plays"] = [game_play("end", 4, "0:00", None, "End Game", "End of Game", "End of Game")]
    return game


def athlete_overview(games, minutes):
    """ESPN's athlete overview with this season's games and minutes per game."""
    return {"statistics": {"labels": ATHLETE_LABELS, "splits": [{
        "displayName": "Regular Season", "stats": [str(games), str(minutes), *(["0.0"] * 10)]}]}}


def athlete_overview_without_a_season():
    """ESPN's athlete overview for a player with no games this season: no Regular Season split at all."""
    return {"statistics": {}}


def athlete_seasons(*seasons):
    """ESPN's athlete season averages, each season a (year, games, minutes) literal."""
    labels = ["GP", "GS", "MIN", "PTS"]
    return {"categories": [{"name": "averages", "labels": labels, "statistics": [
        {"season": {"year": year}, "stats": [str(games), "0", str(minutes), "0"]}
        for year, games, minutes in seasons]}]}


def player_responses(game, overview, seasons=None):
    """ESPN's saved answers for a Dallas game with one tracked player."""
    responses = {
        SCOREBOARD: {"events": [event("player-game", "2026-10-23T23:10Z", "in", (DAL, "0"), (BOS, "0"))]},
        f"{ESPN}/summary?event=player-game": game,
        PLAYER_OVERVIEW: overview,
    }
    if seasons is not None:
        responses[PLAYER_STATS] = seasons
    return responses


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

    def test_high_scoring_games_is_too_early_before_judge_from(self):
        # 136 combined points 1079 seconds in is a 363-point pace, well over the line, but 6:00 in the 2nd
        # is one second away, so the Preset has not started reading.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:00", 30, 25), (2, "6:01", 70, 66)],
                              fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Too early to call")

    def test_high_scoring_games_reads_at_judge_from(self):
        # The same 363-point pace at exactly 6:00 in the 2nd is at Judge from, where the Preset starts reading.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:00", 30, 25), (2, "6:00", 70, 66)],
                              fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_high_scoring_games_is_too_early_with_no_game_time_played(self):
        # A fan who moved Judge from to tip-off, with only the 0-0 opening play, has no game time to pace.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0)],
                              fan=Settings(picked=["high"], values={"judge_from": 0}))
        self.assertEqual(row["verdict"], "Too early to call")

    def test_high_scoring_games_watches_a_fast_pace(self):
        # 130 combined points with 24:00 played is a 260-point pace, over the 240 line.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "6:00", 30, 25), (2, "12:00", 60, 55),
                                    (3, "12:00", 70, 60)], fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_high_scoring_games_stays_away_from_a_slow_pace(self):
        # 119 combined points with 24:00 played is a 238-point pace, under the 240 line.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "6:00", 30, 25), (2, "12:00", 60, 55),
                                    (3, "12:00", 70, 49)], fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_high_scoring_games_counts_the_line_itself_as_reached(self):
        # 120 combined points with 24:00 played is exactly a 240-point pace.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "6:00", 30, 25), (2, "12:00", 60, 55),
                                    (3, "12:00", 70, 50)], fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_high_scoring_games_reads_the_pace_over_all_the_game_time_played(self):
        # 130 points with 24:00 played is a 260-point pace, but the game ran on scoreless to 30:00, so the
        # 130 points came in a 208-point pace over every minute played.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "6:00", 30, 25), (2, "12:00", 60, 55),
                                    (3, "12:00", 70, 60), (3, "6:00", 70, 60)], fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_high_scoring_games_reads_the_score_from_the_header(self):
        # These plays carry no score of their own, so the header's total is the one the pace is read from:
        # 130 points with 24:00 played is a 260-point pace.
        row = one_game_row(DAL, [(1, "12:00", 0.5), (3, "12:00", 0.5)], fan=HIGH_SCORING_GAMES,
                           team_at_home=True, team_score="70", opponent_score="60")
        self.assertEqual(row["verdict"], "Watch")

    def test_high_scoring_games_judges_a_finished_game_by_its_final_total(self):
        # 250 points over 53 minutes of overtime is a 226-point pace, but the final total reaches 240.
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (4, "0:00", 110, 110), (5, "0:00", 125, 125)],
                              state="post", fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_high_scoring_games_stays_away_from_a_final_total_under_the_line(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (4, "0:00", 105, 100)],
                              state="post", fan=HIGH_SCORING_GAMES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_close_games_stays_away_from_a_blowout_win(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:50", 10, 2), (2, "12:00", 55, 25),
                                    (3, "12:00", 80, 50), (4, "12:00", 100, 70), (4, "6:00", 105, 80),
                                    (4, "4:00", 110, 85), (4, "0:00", 120, 90)],
                              state="post", fan=CLOSE_GAMES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_close_games_watches_a_close_win(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:00", 5, 4), (2, "12:00", 40, 42),
                                    (3, "12:00", 60, 65), (4, "12:00", 80, 80), (4, "5:00", 88, 86),
                                    (4, "2:00", 95, 96), (4, "0:00", 101, 100)],
                              state="post", fan=CLOSE_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_close_games_watches_a_close_loss(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:00", 5, 4), (2, "12:00", 40, 42),
                                    (3, "12:00", 60, 65), (4, "12:00", 80, 80), (4, "5:00", 86, 88),
                                    (4, "2:00", 96, 95), (4, "0:00", 100, 101)],
                              state="post", fan=CLOSE_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_before_the_last_minutes_a_game_without_close_along_the_way_stays_away(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:50", 10, 2), (2, "12:00", 40, 20),
                                    (3, "12:00", 70, 40), (4, "12:00", 80, 70), (4, "6:00", 85, 82)],
                              fan=CLOSE_GAMES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_close_along_the_way_watches_a_tight_game_before_the_last_minutes(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "6:00", 20, 22), (2, "12:00", 40, 44),
                                    (3, "12:00", 60, 65), (4, "12:00", 80, 82), (4, "6:00", 85, 84)],
                              fan=CLOSE_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_inside_the_last_minutes_a_close_ending_watches_after_a_blowout(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:50", 10, 2), (2, "12:00", 50, 20),
                                    (3, "12:00", 80, 50), (4, "12:00", 100, 70), (4, "4:30", 105, 100),
                                    (4, "4:00", 107, 104)],
                              fan=CLOSE_GAMES)
        self.assertEqual(row["verdict"], "Watch")

    def test_inside_the_last_minutes_without_a_close_ending_stays_away(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:50", 10, 2), (2, "12:00", 50, 20),
                                    (3, "12:00", 80, 50), (4, "12:00", 100, 70), (4, "4:30", 112, 100),
                                    (4, "4:00", 114, 104)],
                              fan=CLOSE_GAMES)
        self.assertEqual(row["verdict"], "Stay away")

    def test_an_overtime_game_watches_under_close_games(self):
        row = scored_game_row(DAL, [(1, "12:00", 0, 0), (1, "11:50", 10, 2), (2, "12:00", 50, 20),
                                    (3, "12:00", 80, 50), (4, "0:00", 100, 100), (5, "0:00", 120, 110)],
                              state="post", fan=CLOSE_GAMES)
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
        self.assertEqual(set(rows["BOS"]), {"team", "verdict", "detail", "next_game", "highlights"})
        self.assertEqual(rows["BOS"]["highlights"], WAITING)

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
                          "detail": "Pick a Preset to judge this game.", "next_game": None,
                          "highlights": WAITING})

    def test_an_unreachable_espn_is_an_error_not_a_verdict(self):
        def offline(url):
            raise urllib.error.URLError("offline")
        status, content_type, body = respond("/rows?teams=BOS", NOW, offline)
        self.assertEqual(status, 503)
        self.assertNotIn("rows", json.loads(body))
        self.assertIn("error", json.loads(body))


# The highlights tests use the Epic's own example: the Thunder at the Clippers on November 13, 2026,
# tipping off at 7:00 PM Dallas time, so the 3 hours 30 minutes wait ends at 10:30 PM.
ENDING_TITLE = "Final 5:31 WILD ENDING Thunder at Clippers | November 13, 2026"
REEL_TITLE = "THUNDER at CLIPPERS | FULL GAME HIGHLIGHTS | November 13, 2026"
HIGHLIGHTS_GAME = highlights.game_of(
    event("highlights", "2026-11-14T01:00Z", "post", (LAC, "112"), (OKC, "118")))
WAIT_IS_OVER = datetime(2026, 11, 13, 22, 30).astimezone()
BEFORE_WAIT_IS_OVER = datetime(2026, 11, 13, 22, 29).astimezone()


def playlist_page(*videos):
    """YouTube's uploads playlist page, in the shape YouTube serves it, listing `videos` in page order.
    Each video is (its id, its title, its length badge)."""
    lockups = [{"lockupViewModel": {
        "contentId": video_id,
        "contentImage": {"thumbnailViewModel": {
            "image": {"sources": [{"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}]},
            "overlays": [{"thumbnailBottomOverlayViewModel": {"badges": [
                {"thumbnailBadgeViewModel": {"text": length}}]}}]}},
        "metadata": {"lockupMetadataViewModel": {"title": {"content": title}}},
    }} for video_id, title, length in videos]
    data = {"contents": {"twoColumnBrowseResultsRenderer": {"tabs": [{"tabRenderer": {"content": {
        "sectionListRenderer": {"contents": [{"itemSectionRenderer": {"contents": lockups}}]}}}}]}}}
    return f"<script>var ytInitialData = {json.dumps(data)};</script>"


def oembed_answer(authors):
    """YouTube's oEmbed answers by video id, naming each author; an id it does not hold is a 404."""
    def answer(video_id):
        if video_id not in authors:
            raise ValueError("Not Found")
        return {"author_name": authors[video_id]}
    return answer


def highlight_finder(page, authors):
    """A highlights finder that reads the saved `page` and YouTube's `authors`, and no network."""
    return highlights.Highlights(lambda: page, oembed_answer(authors))


def highlights_answer(page, authors, now=WAIT_IS_OVER):
    """The Thunder at Clippers button at `now`, from a saved page and its videos' oEmbed authors."""
    return highlight_finder(page, authors).button(HIGHLIGHTS_GAME, now)


class HighlightsTest(unittest.TestCase):
    """The highlights seam: a game, the time, a saved playlist page and YouTube's authors to a button."""

    def test_before_the_wait_is_over_the_button_waits_even_though_an_ending_video_is_saved(self):
        page = playlist_page(("ending", ENDING_TITLE, "5:31"))
        self.assertEqual(highlights_answer(page, {"ending": "NBA"}, BEFORE_WAIT_IS_OVER), WAITING)

    def test_before_the_wait_is_over_the_playlist_page_is_not_read(self):
        def page():
            raise AssertionError("the playlist page was read before the wait was over")
        reels = highlights.Highlights(page, oembed_answer({"ending": "NBA"}))
        self.assertEqual(reels.button(HIGHLIGHTS_GAME, BEFORE_WAIT_IS_OVER), WAITING)

    def test_an_ending_video_opens_from_its_start_even_when_a_full_game_reel_is_listed_first(self):
        page = playlist_page(("reel", REEL_TITLE, "15:02"), ("ending", ENDING_TITLE, "5:31"))
        self.assertEqual(highlights_answer(page, {"ending": "NBA", "reel": "NBA"}),
                         {"label": "End Highlights", "link": "https://www.youtube.com/watch?v=ending"})

    def test_only_a_full_game_reel_opens_two_minutes_before_its_end(self):
        page = playlist_page(("reel", REEL_TITLE, "15:02"))
        self.assertEqual(highlights_answer(page, {"reel": "NBA"}),
                         {"label": "End Highlights", "link": "https://www.youtube.com/watch?v=reel&t=782s"})

    def test_a_game_with_no_reel_waits(self):
        page = playlist_page(("other", "SUNS at NUGGETS | FULL GAME HIGHLIGHTS | November 16, 2026", "16:15"))
        self.assertEqual(highlights_answer(page, {"other": "NBA"}), WAITING)

    def test_an_extended_version_is_never_chosen(self):
        page = playlist_page(("extended", "EXTENDED: " + REEL_TITLE, "30:32"))
        self.assertEqual(highlights_answer(page, {"extended": "NBA"}), WAITING)

    def test_a_team_channels_video_is_never_chosen(self):
        page = playlist_page(("team", REEL_TITLE, "3:14"))
        self.assertEqual(highlights_answer(page, {"team": "Dallas Mavericks"}), WAITING)

    def test_a_reel_for_another_date_is_not_chosen(self):
        page = playlist_page(("reel", "THUNDER at CLIPPERS | FULL GAME HIGHLIGHTS | November 12, 2026", "15:02"))
        self.assertEqual(highlights_answer(page, {"reel": "NBA"}), WAITING)

    def test_a_reel_that_names_only_one_team_is_not_chosen(self):
        page = playlist_page(("reel", "THUNDER | FULL GAME HIGHLIGHTS | November 13, 2026", "15:02"))
        self.assertEqual(highlights_answer(page, {"reel": "NBA"}), WAITING)

    def test_the_button_carries_only_its_label_and_link(self):
        page = playlist_page(("reel", REEL_TITLE, "15:02"))
        answer = highlights_answer(page, {"reel": "NBA"})
        self.assertEqual(set(answer), {"label", "link"})
        for spoiler in (REEL_TITLE, "https://i.ytimg.com/vi/reel/hqdefault.jpg", "15:02", "902"):
            self.assertNotIn(spoiler, json.dumps(answer), spoiler)

    def test_an_unreachable_playlist_page_leaves_the_button_waiting(self):
        def offline():
            raise urllib.error.URLError("offline")
        reels = highlights.Highlights(offline, oembed_answer({}))
        self.assertEqual(reels.button(HIGHLIGHTS_GAME, WAIT_IS_OVER), WAITING)

    def test_a_candidate_youtube_will_not_answer_for_is_not_chosen(self):
        page = playlist_page(("reel", REEL_TITLE, "15:02"))

        def offline(video_id):
            raise urllib.error.URLError("offline")
        reels = highlights.Highlights(lambda: page, offline)
        self.assertEqual(reels.button(HIGHLIGHTS_GAME, WAIT_IS_OVER), WAITING)

    def test_a_found_reel_is_kept_for_the_game_when_the_page_changes(self):
        page = [playlist_page(("reel", REEL_TITLE, "15:02"))]
        reels = highlights.Highlights(lambda: page[0], oembed_answer({"reel": "NBA"}))
        found = reels.button(HIGHLIGHTS_GAME, WAIT_IS_OVER)
        page[0] = playlist_page()
        self.assertEqual(reels.button(HIGHLIGHTS_GAME, WAIT_IS_OVER), found)

    def test_a_game_is_looked_up_again_once_its_answer_has_been_kept_too_long(self):
        page = [playlist_page()]  # nothing listed yet, so the first look waits
        now = [0]
        reels = highlights.Highlights(lambda: page[0], oembed_answer({"reel": "NBA"}), lambda: now[0])
        reels.button(HIGHLIGHTS_GAME, WAIT_IS_OVER)
        page[0] = playlist_page(("reel", REEL_TITLE, "15:02"))
        now[0] = highlights.KEPT_SECONDS
        self.assertEqual(reels.button(HIGHLIGHTS_GAME, WAIT_IS_OVER),
                         {"label": "End Highlights", "link": "https://www.youtube.com/watch?v=reel&t=782s"})


class CatchUpAnswerTest(unittest.TestCase):
    def test_mid_quarter_answers_with_the_score_and_lines_from_the_plays_before_it(self):
        answer = catch_up(handmade_game(), "1st", 10, 0)
        self.assertEqual(answer["score"], {"home": 2, "away": 2})
        self.assertEqual(answer["teams"], [
            {"team": "DAL", "name": "Dallas Mavericks", "home": True,
             **line(points=2, field_goals_made=1, field_goals_attempted=1, rebounds=1, assists=1)},
            {"team": "BOS", "name": "Boston Celtics", "home": False,
             **line(points=2, field_goals_made=1, field_goals_attempted=2, threes_attempted=1)},
        ])
        self.assertEqual(answer["players"], [
            {"id": "d1", "name": "Luka Doncic", "team": "DAL", "minutes": 2.0,
             **line(points=2, field_goals_made=1, field_goals_attempted=1)},
            {"id": "d2", "name": "Kyrie Irving", "team": "DAL", "minutes": 2.0, **line(assists=1)},
            {"id": "d3", "name": "Dereck Lively II", "team": "DAL", "minutes": 2.0, **line(rebounds=1)},
            {"id": "b1", "name": "Jayson Tatum", "team": "BOS", "minutes": 2.0,
             **line(points=2, field_goals_made=1, field_goals_attempted=2, threes_attempted=1)},
            {"id": "b2", "name": "Jaylen Brown", "team": "BOS", "minutes": 2.0, **line()},
        ])

    def test_mid_quarter_plays_run_newest_first_in_espn_text(self):
        answer = catch_up(handmade_game(), "1st", 10, 0)
        self.assertEqual(answer["plays"], [
            expected_play("p5", "1st Quarter", "10:10", "BOS", "Jayson Tatum makes driving layup"),
            expected_play("p4", "1st Quarter", "10:30", "DAL", "Dereck Lively II offensive rebound"),
            expected_play("p3", "1st Quarter", "11:05", "BOS",
                          "Jayson Tatum misses 25-foot three point jumper"),
            expected_play("p2", "1st Quarter", "11:40", "DAL",
                          "Luka Doncic makes 18-foot jump shot (Kyrie Irving assists)"),
            expected_play("p1", "1st Quarter", "12:00", "DAL",
                          "Dereck Lively II vs. Jayson Tatum (Luka Doncic gains possession)"),
        ])

    def test_a_quarter_break_answer_holds_the_whole_period(self):
        answer = catch_up(handmade_game(), "1st", 0, 0)
        self.assertEqual(answer["score"], {"home": 2, "away": 3})
        self.assertEqual(answer["teams"], [
            {"team": "DAL", "name": "Dallas Mavericks", "home": True,
             **line(points=2, field_goals_made=1, field_goals_attempted=1, rebounds=1, assists=1,
                    turnovers=1, fouls=1)},
            {"team": "BOS", "name": "Boston Celtics", "home": False,
             **line(points=3, field_goals_made=1, field_goals_attempted=2, threes_attempted=1,
                    free_throws_made=1, free_throws_attempted=2, steals=1)},
        ])
        self.assertEqual(answer["players"], [
            {"id": "d1", "name": "Luka Doncic", "team": "DAL", "minutes": 12.0,
             **line(points=2, field_goals_made=1, field_goals_attempted=1, turnovers=1)},
            {"id": "d2", "name": "Kyrie Irving", "team": "DAL", "minutes": 12.0, **line(assists=1)},
            {"id": "d3", "name": "Dereck Lively II", "team": "DAL", "minutes": 12.0,
             **line(rebounds=1, fouls=1)},
            {"id": "b1", "name": "Jayson Tatum", "team": "BOS", "minutes": 12.0,
             **line(points=3, field_goals_made=1, field_goals_attempted=2, threes_attempted=1,
                    free_throws_made=1, free_throws_attempted=2)},
            {"id": "b2", "name": "Jaylen Brown", "team": "BOS", "minutes": 12.0, **line(steals=1)},
        ])

    def test_a_quarter_break_play_list_runs_from_the_last_play_back_to_tip_off(self):
        answer = catch_up(handmade_game(), "1st", 0, 0)
        self.assertEqual([play["id"] for play in answer["plays"]],
                         ["p8", "p9", "p7", "p6", "p5", "p4", "p3", "p2", "p1"])
        self.assertEqual(answer["plays"][0],
                         expected_play("p8", "1st Quarter", "9:00", "BOS",
                                       "Jayson Tatum makes free throw 1 of 2"))

    def test_an_end_of_regulation_answer_holds_no_play_from_overtime(self):
        # Overtime's opening tip happened at 5:00 of the 1st OT, the same instant of game time as the 4th
        # quarter's 0:00. Sending it would tell a fan at the end of regulation that an overtime followed.
        plays = catch_up(overtime_game(), "4th", 0, 0)["plays"]
        self.assertEqual([play["id"] for play in plays], ["q4"])
        self.assertEqual({play["period"] for play in plays}, {"4th Quarter"})

    def test_a_quarter_break_answer_holds_no_play_from_the_next_quarter(self):
        # The 2nd quarter opens at 12:00, the same instant of game time as the 1st quarter's 0:00, so a
        # fan at the break must not see the next quarter's opening play.
        plays = catch_up(substitution_game(), "1st", 0, 0)["plays"]
        self.assertEqual([play["id"] for play in plays], ["sub1"])
        self.assertEqual({play["period"] for play in plays}, {"1st Quarter"})

    def test_a_play_list_never_carries_espns_end_of_game_markers(self):
        # At the end of regulation, "End of the 4th Quarter" followed by "End of Game" would tell a fan
        # the game was over, and so that no overtime came. The answer leaves both out.
        plays = catch_up(regulation_end_game(), "4th", 0, 0)["plays"]
        self.assertEqual([play["id"] for play in plays], ["shot", "q4"])

    def test_an_overtime_play_list_never_carries_espns_end_of_game_markers(self):
        # The same at the end of overtime: the end of the 4th, each overtime's end and the game's end are
        # all markers, and a fan who only reached the 4th's end must not learn an overtime followed.
        plays = catch_up(overtime_game(), "OT", 14, 0)["plays"]
        self.assertEqual([play["id"] for play in plays],
                         ["ot3", "ot2-late", "ot2", "ot1", "ot-tip", "q4"])

    def test_a_made_heave_counts_as_an_attempt_but_a_missed_one_does_not(self):
        game = handmade_game()
        game["plays"] = [
            game_play("made-heave", 1, "8:00", BOS_ID, "Heave Jump Shot",
                      "Jayson Tatum makes 60-foot heave jump shot", "+3 Points", ("b1",),
                      scoring=True, score=3, shooting=True, attempted=3),
            game_play("missed-heave", 1, "7:00", BOS_ID, "Heave Jump Shot",
                      "Jayson Tatum misses 60-foot heave jump shot", "Missed 3PT", ("b1",),
                      shooting=True, attempted=3),
        ]
        answer = catch_up(game, "1st", 0, 0)
        tatum = next(player for player in answer["players"] if player["id"] == "b1")
        self.assertEqual((tatum["points"], tatum["field_goals_attempted"], tatum["threes_attempted"]),
                         (3, 1, 1))

    def test_a_late_correction_counts_at_its_game_time(self):
        correction = game_play("p11", 1, "9:50", DAL_ID, "Defensive Rebound",
                               "Luka Doncic defensive rebound", "Rebound", ("d1",))
        played = catch_up(handmade_game([correction]), "1st", 9, 47)
        self.assertEqual([play["id"] for play in played["plays"]],
                         ["p11", "p5", "p4", "p3", "p2", "p1"])
        self.assertEqual(next(player for player in played["players"] if player["id"] == "d1")["rebounds"], 1)
        before_it = catch_up(handmade_game([correction]), "1st", 9, 52)
        self.assertEqual([play["id"] for play in before_it["plays"]], ["p5", "p4", "p3", "p2", "p1"])
        self.assertEqual(next(player for player in before_it["players"] if player["id"] == "d1")["rebounds"], 0)
        in_order = catch_up(handmade_game([correction]), "1st", 9, 40)
        self.assertEqual([play["id"] for play in in_order["plays"]],
                         ["p6", "p11", "p5", "p4", "p3", "p2", "p1"])

    def test_nine_minutes_of_overtime_is_four_minutes_into_the_second_overtime(self):
        answer = catch_up(overtime_game(), "OT", 9, 0)
        self.assertEqual([play["id"] for play in answer["plays"]], ["ot2", "ot1", "ot-tip", "q4"])
        self.assertEqual(answer["score"], {"home": 2, "away": 2})

    def test_fourteen_minutes_of_overtime_is_four_minutes_into_the_third_overtime(self):
        answer = catch_up(overtime_game(), "OT", 14, 0)
        self.assertEqual([play["id"] for play in answer["plays"]],
                         ["ot3", "ot2-late", "ot2", "ot1", "ot-tip", "q4"])
        self.assertEqual(answer["score"], {"home": 5, "away": 4})

    def test_an_overtime_moment_in_a_regulation_game_is_the_whole_game(self):
        overtime_moment = catch_up(handmade_game(), "OT", 9, 0)
        end_of_regulation = catch_up(handmade_game(), "4th", 0, 0)
        self.assertEqual(overtime_moment, end_of_regulation)
        self.assertEqual(set(overtime_moment), {"score", "teams", "players", "plays"})
        self.assertEqual(overtime_moment["score"], {"home": 2, "away": 3})
        self.assertEqual(len(overtime_moment["plays"]), 9)

    def test_a_catch_up_answer_at_the_end_of_regulation_sends_no_overtime_play(self):
        # The phone reads the answer, not the screen built from it, so no overtime word may reach it.
        responses = {
            SCOREBOARD: {"events": [event("catchup", "2026-10-23T23:10Z", "in", (DAL, "2"), (BOS, "2"))]},
            CATCHUP_URL: overtime_game(),
        }
        status, content_type, body = respond(
            "/catchup?teams=DAL&period=4th&minutes=0&seconds=0", NOW, espn(responses))
        self.assertEqual(status, 200)
        for overtime in ["OT", "Jump ball to start overtime"]:
            self.assertNotIn(overtime, body.decode(), overtime)

    def test_a_catch_up_request_sends_nothing_after_the_moment(self):
        summary = handmade_game()
        summary["plays"] = [
            game_play("early-1", 1, "11:40", DAL_ID, "Jump Shot",
                      "Luka Doncic makes 18-foot jump shot", "+2 Points", ("d1",),
                      scoring=True, score=2, shooting=True),
            game_play("later-1", 1, "9:45", BOS_ID, "Jump Shot",
                      "LATER TATUM THREE", "+3 Points", ("b1",),
                      scoring=True, score=3, shooting=True, attempted=3),
            game_play("later-2", 1, "9:20", BOS_ID, "Free Throw - 1 of 1",
                      "LATER TATUM FREE THROW", "+1 Point", ("b1",),
                      scoring=True, score=1, shooting=True, attempted=1),
        ]
        summary["header"]["competitions"][0]["competitors"][1]["score"] = "6"
        responses = {
            SCOREBOARD: {"events": [event("catchup", "2026-10-23T23:10Z", "in",
                                          (DAL, "2"), (BOS, "6"))]},
            CATCHUP_URL: summary,
        }
        status, content_type, body = respond(
            "/catchup?teams=DAL&period=1st&minutes=10&seconds=0", NOW, espn(responses))
        self.assertEqual(status, 200)
        self.assertEqual(content_type, JSON_TYPE)
        answer = json.loads(body)
        self.assertEqual(answer["score"], {"home": 2, "away": 0})
        self.assertEqual([play["id"] for play in answer["plays"]], ["early-1"])
        self.assertEqual(next(player for player in answer["players"] if player["id"] == "b1")["points"], 0)
        for spoiler in ["LATER", "9:45", "9:20", '"away": 6', '"points": 3', "99"]:
            self.assertNotIn(spoiler, body.decode(), spoiler)


class CatchUpMinutesTest(unittest.TestCase):
    def test_a_substitution_hands_the_floor_over_at_its_own_play(self):
        minutes = minutes_by_name(catch_up(substitution_game(), "1st", 6, 0))
        self.assertEqual((minutes["Luka Doncic"], minutes["Naji Marshall"]), (6.0, 0.0))

    def test_a_substitute_keeps_counting_through_the_quarter_break(self):
        minutes = minutes_by_name(catch_up(substitution_game(), "2nd", 9, 0))
        self.assertEqual((minutes["Naji Marshall"], minutes["Luka Doncic"]), (9.0, 6.0))

    def test_every_minute_of_the_half_belongs_to_one_dallas_player(self):
        # 24 minutes in the half with five players on the floor each minute, however often they swap.
        answer = catch_up(substitution_game(), "2nd", 0, 0)
        dallas = [player["minutes"] for player in answer["players"] if player["team"] == "DAL"]
        self.assertEqual(sum(dallas), 120.0)

    def test_a_moment_past_the_latest_play_counts_no_minutes_after_it(self):
        game = handmade_game()
        game["plays"] = [
            game_play("p1", 1, "12:00", DAL_ID, "Jumpball",
                      "Dereck Lively II vs. Jayson Tatum (Luka Doncic gains possession)", "Jump Ball",
                      ("d3", "b1")),
            game_play("p2", 1, "5:00", DAL_ID, "Jump Shot",
                      "Luka Doncic makes 18-foot jump shot", "+2 Points", ("d1",),
                      scoring=True, score=2, shooting=True),
        ]
        self.assertEqual(minutes_by_name(catch_up(game, "1st", 0, 0))["Luka Doncic"], 7.0)


class TrackedPlayerTest(unittest.TestCase):
    def test_under_six_minutes_is_too_early_even_with_the_number_already_reached(self):
        # 20 points in 5:30 would be on track and over the target, but 6 minutes have not been played.
        verdict, _ = player_verdict(tracked_game(points=20, minutes=5.5), TRACKED_ID,
                                    Checks(targets={"points": 10}), 36.0)
        self.assertEqual(verdict, "Too early to call")

    def test_a_star_on_track_through_heavy_early_minutes_is_watch(self):
        # 14 points in the 12 minutes of the 1st project to 42 over his usual 36, reaching 35.
        verdict, _ = player_verdict(tracked_game(points=14, minutes=12), TRACKED_ID,
                                    Checks(targets={"points": 35}), 36.0)
        self.assertEqual(verdict, "Watch")

    def test_a_bench_player_on_track_in_a_few_minutes_is_watch(self):
        # 8 points in 6 minutes project to 16 over his usual 12, reaching the 15 asked for.
        verdict, _ = player_verdict(tracked_game(points=8, minutes=6, bench=True), TRACKED_ID,
                                    Checks(targets={"points": 15}), 12.0)
        self.assertEqual(verdict, "Watch")

    def test_a_number_already_reached_counts_even_when_the_projection_does_not(self):
        # 12 points in 20 minutes project to only 6 over his usual 10, but 12 has reached 10.
        verdict, _ = player_verdict(tracked_game(points=12, minutes=20), TRACKED_ID,
                                    Checks(targets={"points": 10}), 10.0)
        self.assertEqual(verdict, "Watch")

    def test_a_projection_that_reaches_the_number_exactly_is_on_track(self):
        # 10 points in 12 minutes project to exactly 20 over his usual 24.
        verdict, _ = player_verdict(tracked_game(points=10, minutes=12), TRACKED_ID,
                                    Checks(targets={"points": 20}), 24.0)
        self.assertEqual(verdict, "Watch")

    def test_a_points_target_counts_points(self):
        # 14 points in 12 minutes project to 42 over his usual 36, reaching 35; no other stat moves.
        verdict, _ = player_verdict(tracked_game(points=14, minutes=12), TRACKED_ID,
                                    Checks(targets={"points": 35}), 36.0)
        self.assertEqual(verdict, "Watch")

    def test_a_rebounds_target_counts_rebounds(self):
        # 6 rebounds in 12 minutes project to exactly 10 over his usual 20; no other stat moves.
        verdict, _ = player_verdict(tracked_game(rebounds=6, minutes=12), TRACKED_ID,
                                    Checks(targets={"rebounds": 10}), 20.0)
        self.assertEqual(verdict, "Watch")

    def test_an_assists_target_counts_assists(self):
        # 4 assists in 12 minutes project to 6.7 over his usual 20, reaching 6; no other stat moves.
        verdict, _ = player_verdict(tracked_game(assists=4, minutes=12), TRACKED_ID,
                                    Checks(targets={"assists": 6}), 20.0)
        self.assertEqual(verdict, "Watch")

    def test_a_threes_made_target_counts_threes_made(self):
        # 2 threes in 12 minutes project to 3.3 over his usual 20, reaching 3; no other stat moves.
        verdict, _ = player_verdict(tracked_game(threes=2, minutes=12), TRACKED_ID,
                                    Checks(targets={"threes_made": 3}), 20.0)
        self.assertEqual(verdict, "Watch")

    def test_a_steals_target_counts_steals(self):
        # 2 steals in 12 minutes project to 3.3 over his usual 20, reaching 3; no other stat moves.
        verdict, _ = player_verdict(tracked_game(steals=2, minutes=12), TRACKED_ID,
                                    Checks(targets={"steals": 3}), 20.0)
        self.assertEqual(verdict, "Watch")

    def test_a_blocks_target_counts_blocks(self):
        # 2 blocks in 12 minutes project to 3.3 over his usual 20, reaching 3; no other stat moves.
        verdict, _ = player_verdict(tracked_game(blocks=2, minutes=12), TRACKED_ID,
                                    Checks(targets={"blocks": 3}), 20.0)
        self.assertEqual(verdict, "Watch")

    def test_a_double_double_is_watch_when_two_stats_are_on_track(self):
        # 10 points and 10 rebounds in 12 minutes project to 16.7 each over his usual 20.
        verdict, _ = player_verdict(tracked_game(points=10, rebounds=10, minutes=12), TRACKED_ID,
                                    Checks(double_double=True), 20.0)
        self.assertEqual(verdict, "Watch")

    def test_a_double_double_stays_away_when_only_one_stat_is_on_track(self):
        # 10 points reached, but 2 rebounds in 12 minutes project to only 3.3.
        verdict, _ = player_verdict(tracked_game(points=10, rebounds=2, minutes=12), TRACKED_ID,
                                    Checks(double_double=True), 20.0)
        self.assertEqual(verdict, "Stay away")

    def test_a_triple_double_is_watch_when_three_stats_are_on_track(self):
        game = tracked_game(points=10, rebounds=10, assists=10, minutes=12)
        verdict, _ = player_verdict(game, TRACKED_ID, Checks(triple_double=True), 20.0)
        self.assertEqual(verdict, "Watch")

    def test_a_triple_double_needs_three_stats(self):
        # 10 points and 10 rebounds, but 2 assists in 12 minutes project to only 3.3.
        game = tracked_game(points=10, rebounds=10, assists=2, minutes=12)
        verdict, _ = player_verdict(game, TRACKED_ID, Checks(triple_double=True), 20.0)
        self.assertEqual(verdict, "Stay away")

    def test_and_needs_every_check_while_or_needs_one(self):
        # Points reach their target while the rebounds' projection stays short of its own.
        game = tracked_game(points=20, rebounds=2, minutes=12)
        targets = {"points": 10, "rebounds": 10}
        self.assertEqual(player_verdict(game, TRACKED_ID, Checks(targets, join="OR"), 20.0)[0],
                                        "Watch")
        self.assertEqual(player_verdict(game, TRACKED_ID, Checks(targets, join="AND"), 20.0)[0],
                                        "Stay away")

    def test_after_the_final_reaching_the_number_is_watch(self):
        # 22 points in 20 minutes project to only 11 over his usual 10, but 22 has reached 20.
        verdict, _ = player_verdict(tracked_game(points=22, minutes=20, state="post"),
                                    TRACKED_ID, Checks(targets={"points": 20}), 10.0)
        self.assertEqual(verdict, "Watch")

    def test_after_the_final_a_projection_does_not_count(self):
        # 18 points in 10 minutes would project to 72 over his usual 40, but only 18 were reached.
        verdict, _ = player_verdict(tracked_game(points=18, minutes=10, state="post"),
                                    TRACKED_ID, Checks(targets={"points": 20}), 40.0)
        self.assertEqual(verdict, "Stay away")

    def test_a_player_who_has_not_entered_yet_is_too_early(self):
        game = tracked_game(points=22, minutes=20)
        game["boxscore"]["players"][0]["statistics"][0]["athletes"].append(
            roster_player("d6", "Naji Marshall"))
        verdict, _ = player_verdict(game, "d6", Checks(targets={"points": 10}), 20.0)
        self.assertEqual(verdict, "Too early to call")

    def test_a_player_who_did_not_play_reads_did_not_play(self):
        verdict, detail = player_verdict(did_not_play_game(), "d6",
                                         Checks(targets={"points": 10}), 20.0)
        self.assertIsNone(verdict)
        self.assertEqual(detail, DID_NOT_PLAY)

    def test_a_player_with_five_games_this_season_uses_this_seasons_minutes(self):
        # 8 points in 10 minutes project to 8 over this season's 10 and 24 over last season's 30.
        responses = player_responses(
            tracked_game(points=8, minutes=10),
            athlete_overview(games=5, minutes=10.0),
            athlete_seasons((2027, 5, 10.0), (2026, 60, 30.0)))
        row = players.judge([TrackedPlayer(TRACKED_ID, "DAL", TRACKED_NAME)], GAME_DAY,
                            espn(responses), Checks(targets={"points": 20}))[0]
        self.assertEqual(row["verdict"], "Stay away")

    def test_a_player_under_five_games_this_season_uses_last_seasons_minutes(self):
        # 8 points in 10 minutes project to 9.6 over this season's 12 minutes and 24 over last season's 30.
        responses = player_responses(
            tracked_game(points=8, minutes=10),
            athlete_overview(games=4, minutes=12.0),
            athlete_seasons((2027, 4, 12.0), (2026, 60, 30.0)))
        row = players.judge([TrackedPlayer(TRACKED_ID, "DAL", TRACKED_NAME)], GAME_DAY,
                            espn(responses), Checks(targets={"points": 20}))[0]
        self.assertEqual(row["verdict"], "Watch")

    def test_a_player_with_no_games_this_season_uses_last_seasons_minutes(self):
        # ESPN lists no season for him this season. 10 points in 10 minutes project to 30 over last
        # season's 30 minutes, reaching 27; the season before last's 25 would not.
        responses = player_responses(
            tracked_game(points=10, minutes=10),
            athlete_overview_without_a_season(),
            athlete_seasons((2025, 60, 25.0), (2026, 60, 30.0)))
        row = players.judge([TrackedPlayer(TRACKED_ID, "DAL", TRACKED_NAME)], GAME_DAY,
                            espn(responses), Checks(targets={"points": 27}))[0]
        self.assertEqual(row["verdict"], "Watch")

    def test_a_stats_answer_without_an_averages_category_uses_this_seasons_minutes(self):
        # 8 points in 10 minutes project to 9.6 over this season's 12 minutes, short of 20.
        responses = player_responses(
            tracked_game(points=8, minutes=10),
            athlete_overview(games=4, minutes=12.0),
            {"categories": [{"name": "totals", "labels": ["GP"], "statistics": []}]})
        row = players.judge([TrackedPlayer(TRACKED_ID, "DAL", TRACKED_NAME)], GAME_DAY,
                            espn(responses), Checks(targets={"points": 20}))[0]
        self.assertEqual(row["verdict"], "Stay away")

    def test_one_players_unreachable_athlete_answer_leaves_the_other_rows_judged(self):
        # Luka's usual minutes cannot be fetched; Jayson Tatum's 0 points in 20 minutes still judge.
        tracked = "d1:DAL:Luka%20Doncic,b1:BOS:Jayson%20Tatum"
        responses = player_responses(tracked_game(points=22, minutes=20),
                                     athlete_overview(games=12, minutes=36.0))
        responses[f"{ATHLETE_API}/b1/overview"] = athlete_overview(games=12, minutes=36.0)
        status, content_type, body = respond(f"/rows?players={tracked}&player_points=20", NOW,
                                            unreachable_for(responses, PLAYER_OVERVIEW))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["rows"], [
            {"team": "DAL", "player": TRACKED_NAME, "verdict": None,
             "detail": "Couldn't reach ESPN.", "next_game": None},
            {"team": "BOS", "player": "Jayson Tatum", "verdict": "Stay away",
             "detail": "This one looks out of reach.", "next_game": None},
        ])

    def test_each_of_several_tracked_players_gets_a_row_judged_by_the_same_checks(self):
        # Luka's 22 points reach the target; Jayson Tatum has no play in this game, so the same target
        # leaves his row short while Luka's reads Watch.
        tracked = [TrackedPlayer(TRACKED_ID, "DAL", TRACKED_NAME),
                   TrackedPlayer("b1", "BOS", "Jayson Tatum")]
        responses = player_responses(tracked_game(points=22, minutes=20),
                                     athlete_overview(games=12, minutes=36.0))
        responses[f"{ATHLETE_API}/b1/overview"] = athlete_overview(games=12, minutes=36.0)
        rows = players.judge(tracked, GAME_DAY, espn(responses), Checks(targets={"points": 20}))
        self.assertEqual([(row["player"], row["verdict"]) for row in rows],
                         [(TRACKED_NAME, "Watch"), ("Jayson Tatum", "Stay away")])

    def test_a_player_row_names_the_player(self):
        row = players.judge([TrackedPlayer(TRACKED_ID, "DAL", TRACKED_NAME)], GAME_DAY,
                            espn(night()), Checks(targets={"points": 20}))[0]
        self.assertEqual(row["player"], TRACKED_NAME)

    def test_a_tracked_players_row_shows_their_teams_next_game(self):
        row = players.judge([TrackedPlayer(TRACKED_ID, "DAL", TRACKED_NAME)], GAME_DAY,
                            espn(night()), Checks(targets={"points": 20}))[0]
        self.assertEqual(row["next_game"], {"day": "Today", "time": "7:30 PM",
                                             "opponent": "Houston Rockets", "home": True})

    def test_a_player_row_sends_no_score_clock_quarter_percentage_or_tip_off(self):
        game = tracked_game(points=22, minutes=20)
        game["header"]["competitions"][0]["competitors"][0]["score"] = "112"
        game["header"]["competitions"][0]["competitors"][1]["score"] = "105"
        game["winprobability"] = [{"playId": "shot0", "homeWinPercentage": 0.9876}]
        responses = player_responses(game, athlete_overview(games=12, minutes=36.0))
        status, _, body = respond("/rows?players=d1:DAL:Luka%20Doncic&player_points=20",
                                  NOW, espn(responses))
        self.assertEqual(status, 200)
        self.assertIn("Luka Doncic", body.decode())
        for spoiler in ["112", "105", "0.9876", "2:00", "1st", "2nd", "22", "%", "overtime"]:
            self.assertNotIn(spoiler, body.decode(), spoiler)


class PresetsResponseTest(unittest.TestCase):
    def test_the_presets_answer_lists_each_preset_with_its_sliders_and_defaults(self):
        status, content_type, body = respond("/presets", NOW, espn(night()))
        self.assertEqual(status, 200)
        self.assertEqual(content_type, JSON_TYPE)
        answer = json.loads(body)
        self.assertEqual([preset["name"] for preset in answer["presets"]],
                         ["Wins for my team", "No blowout losses", "Close games", "High-scoring games"])
        self.assertEqual(answer["presets"][0], {"key": "wins", "name": "Wins for my team", "sliders": []})
        self.assertEqual(answer["presets"][1]["sliders"], [
            {"parameter": "blow_upper", "name": "Stay away above",
             "min": 90, "max": 99, "default": 98, "unit": "%"},
            {"parameter": "blow_lower", "name": "Back to Watch below",
             "min": 85, "max": 98, "default": 95, "unit": "%"},
        ])
        self.assertEqual(answer["presets"][2]["sliders"], [
            {"parameter": "close_points", "name": "Close ending within",
             "min": 1, "max": 20, "default": 5, "unit": "points"},
            {"parameter": "close_minutes", "name": "Close ending in the last",
             "min": 1, "max": 12, "default": 5, "unit": "minutes"},
            {"parameter": "along_points", "name": "Close along the way within",
             "min": 1, "max": 20, "default": 9, "unit": "points"},
            {"parameter": "along_share", "name": "Close along the way for over",
             "min": 1, "max": 99, "default": 66, "unit": "%"},
        ])
        self.assertEqual(answer["presets"][3], {"key": "high", "name": "High-scoring games", "sliders": [
            {"parameter": "high_total", "name": "Reach a total of",
             "min": 150, "max": 350, "default": 240, "unit": "points"},
        ]})
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

    def preset_row(self, preset, plays, query=""):
        """The DAL row for one live home game against Miami, judged from `preset` and the query's settings.

        plays is a list of (period, clock, Dallas score, Miami score).
        """
        status, content_type, body = respond(f"/rows?teams=DAL&presets={preset}{query}", NOW,
                                             espn(scored_responses(DAL, plays)))
        self.assertEqual(status, 200)
        return json.loads(body)["rows"][0]

    def test_a_close_games_slider_moves_the_verdict(self):
        # A 7-point margin at 4:30 left in the 4th is outside the shipped 5 points, inside a fan's 7.
        plays = [(1, "12:00", 0, 0), (1, "11:50", 10, 2), (2, "12:00", 50, 20),
                 (3, "12:00", 80, 50), (4, "12:00", 100, 70), (4, "4:30", 107, 100),
                 (4, "4:00", 109, 102)]
        self.assertEqual(self.preset_row("close", plays)["verdict"], "Stay away")
        self.assertEqual(self.preset_row("close", plays, "&close_points=7")["verdict"], "Watch")

    def test_a_high_scoring_games_slider_moves_the_verdict(self):
        # 130 combined points with 24:00 played is a 260-point pace: over the shipped 240, under a fan's 270.
        plays = [(1, "12:00", 0, 0), (1, "6:00", 30, 25), (2, "12:00", 60, 55), (3, "12:00", 70, 60)]
        self.assertEqual(self.preset_row("high", plays)["verdict"], "Watch")
        self.assertEqual(self.preset_row("high", plays, "&high_total=270")["verdict"], "Stay away")


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


def checked(page, name):
    """The values of the `name` checkboxes a page has ticked, sorted."""
    return sorted(attrs["value"] for tag, attrs in tags(page)
                  if tag == "input" and attrs.get("name") == name and "checked" in attrs)


def presets_offered(page):
    """The Presets a setup page offers as chips, in order, by the key each travels as."""
    return [attrs["value"] for tag, attrs in tags(page)
            if tag == "input" and attrs.get("name") == "presets"]


def joins_offered(page):
    """The AND or OR choices a setup page offers, in order: (its value, whether it is checked)."""
    return [(attrs["value"], "checked" in attrs) for tag, attrs in tags(page)
            if tag == "input" and attrs.get("name") == "join"]


def slider_rows(page):
    """The slider rows a setup page renders, by the query parameter each carries: its markup and its words."""
    return {parameter: (markup, words(markup))
            for parameter, markup in re.findall(r'<div class="slider" data-slider="([^"]+)">(.*?)</div>',
                                               page, re.S)}


def slider_input(markup):
    """The attributes of the one range input a slider row holds."""
    return next(attrs for tag, attrs in tags(markup) if tag == "input")


def slider_labels(markup):
    """The words a slider row can show, by the value it takes, as it serves them."""
    return json.loads(slider_input(markup)["data-labels"])


def done_button(page):
    """The button that finishes setup, as its attributes."""
    return next(attrs for tag, attrs in tags(page) if tag == "button" and attrs.get("id") == "done")


def script(page, marker):
    """The inline script in `page` that holds `marker`, with its whitespace squeezed so a test can read it."""
    body = next(body for body in re.findall(r"<script>(.*?)</script>", page, re.S) if marker in body)
    return " ".join(body.split())


def card_rules(card):
    """The words of a card's rules panel."""
    return words(re.search(r'<div class="rules">(.*?)</div>', card, re.S).group(1))


class PageServing(unittest.TestCase):
    """The page seam: the page respond serves for a path on the test's Game day."""

    def page(self, path="/", get=None, reels=None):
        status, content_type, body = respond(path, NOW, get or espn(night()), reels)
        self.assertEqual(status, 200)
        self.assertEqual(content_type, HTML_TYPE)
        return body.decode()


class PageTest(PageServing):
    def test_the_first_visit_opens_team_setup(self):
        page = self.page("/")
        self.assertIn(("form", {"id": "setup", "method": "get", "action": "/"}), tags(page))
        self.assertEqual(cards(page), {})

    def test_setup_offers_all_thirty_teams_by_abbreviation(self):
        values = [attrs["value"] for tag, attrs in tags(self.page("/"))
                  if tag == "input" and attrs.get("name") == "teams"]
        self.assertEqual(sorted(values), sorted(NBA_TEAMS))

    def test_the_page_saves_picked_teams_on_the_phone(self):
        self.assertRegex(self.page("/"), r'localStorage\.setItem\(TEAMS, picks\)')

    def test_the_page_sends_a_fan_with_saved_teams_and_settings_to_their_cards(self):
        page = self.page("/")
        self.assertRegex(page, r'localStorage\.getItem\(TEAMS\)')
        self.assertIn('location.replace("/?teams=" + encodeURIComponent(savedTeams) + settingsQuery())',
                      page)
        self.assertIn('localStorage.getItem(SETTINGS)', page)

    def test_picking_teams_shows_one_card_per_team(self):
        page = self.page("/?teams=LAL&teams=BOS&teams=IND")
        self.assertEqual(sorted(cards(page)), ["BOS", "IND", "LAL"])

    def test_the_list_header_shows_only_the_app_name_and_the_gear(self):
        page = self.page("/?teams=LAL&presets=blow")
        header = re.search(r"<header>(.*?)</header>", page, re.S).group(1)
        self.assertEqual(words(header), "RadioSilence ⚙︎")
        href = next(attrs for tag, attrs in tags(header) if tag == "a")["href"]
        self.assertTrue(href.startswith("/?setup=1&teams=LAL&"), href)
        self.assertIn("presets=blow", href)

    def test_the_comma_joined_teams_the_script_saves_show_one_card_each(self):
        # The script saves the picks joined with commas, so a reload arrives as one `teams` value.
        self.assertEqual(sorted(cards(self.page("/?teams=LAL,BOS"))), ["BOS", "LAL"])

    def test_the_gear_reopens_setup_with_the_fans_teams_and_settings(self):
        page = self.page("/?teams=LAL&teams=BOS&presets=blow&join=AND&blow_upper=97")
        gear = next(attrs for tag, attrs in tags(page) if attrs.get("class") == "gear")
        setup = self.page(gear["href"])
        self.assertEqual(checked(setup, "teams"), ["BOS", "LAL"])
        self.assertEqual(checked(setup, "presets"), ["blow"])
        self.assertEqual(joins_offered(setup), [("OR", False), ("AND", True)])
        self.assertEqual(slider_input(slider_rows(setup)["blow_upper"][0])["value"], "97")

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
        self.assertIn("No blowout losses", words(card))
        self.assertNotIn("<button", re.search(r"<summary>(.*?)</summary>", card, re.S).group(1))

    def test_the_highlights_button_says_no_highlights_yet_and_is_disabled(self):
        card = cards(self.page("/?teams=BOS"))["BOS"]
        attributes, label = re.search(r'<button class="highlights"([^>]*)>(.*?)</button>',
                                       card, re.S).groups()
        self.assertIn("disabled", attributes)
        self.assertEqual(words(label), "No highlights yet")

    def test_a_card_past_the_wait_links_to_the_nbas_reel_as_end_highlights(self):
        page = playlist_page(("reel", "CELTICS at KNICKS | FULL GAME HIGHLIGHTS | October 23, 2026", "15:02"))
        card = cards(self.page("/?teams=BOS", reels=highlight_finder(page, {"reel": "NBA"})))["BOS"]
        link = next(attrs["href"] for tag, attrs in tags(card) if attrs.get("class") == "highlights")
        self.assertEqual(link, "https://www.youtube.com/watch?v=reel&t=782s")
        self.assertIn("End Highlights", words(card))

    def test_a_card_before_the_wait_is_disabled_even_though_a_reel_is_saved(self):
        # The Pacers at Heat game tips off at 6:10 PM, so its wait ends at 9:40 PM, after the test's 7:00 PM.
        page = playlist_page(("reel", "PACERS at HEAT | FULL GAME HIGHLIGHTS | October 23, 2026", "15:02"))
        card = cards(self.page("/?teams=MIA", reels=highlight_finder(page, {"reel": "NBA"})))["MIA"]
        self.assertRegex(card, r'<button class="highlights" disabled>\s*No highlights yet\s*</button>')

    def test_a_card_whose_game_has_not_tipped_off_has_no_highlights_button(self):
        self.assertNotIn('class="highlights"', cards(self.page("/?teams=DAL"))["DAL"])

    def test_the_page_never_carries_a_reels_title_thumbnail_or_length(self):
        title = "CELTICS at KNICKS | FULL GAME HIGHLIGHTS | October 23, 2026"
        page = playlist_page(("reel", title, "15:02"))
        shown = self.page("/?teams=BOS", reels=highlight_finder(page, {"reel": "NBA"}))
        for spoiler in (title, "https://i.ytimg.com/vi/reel/hqdefault.jpg", "15:02", "902"):
            self.assertNotIn(spoiler, shown, spoiler)

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

    def test_a_live_game_puts_no_score_clock_quarter_or_percentage_outside_the_rules_panel(self):
        page = self.page("/?teams=BOS&teams=IND&teams=LAL&teams=DAL&teams=SA&presets=blow")
        # What the page carries about the games is the Verdict and the Next-game preview. The percentages
        # and moments it also carries are the fan's own slider values in a card's rules panel, which say
        # nothing about a game, so they come out before the check: a Reading from a game that leaked a
        # score, clock, quarter or percentage anywhere else would still show.
        outside_rules = re.sub(r'<div class="rules">.*?</div>', "", page, flags=re.S)
        for spoiler in ["117", "104", "88", "91", "96", "77", "7:12", "8:00", "5:00", "3:00", "0:00",
                        "98%", "95%", "0.99", "0.6234", "0.01", "1st", "2nd", "3rd", "4th",
                        "12:00 PM", "6:10 PM", "5:40 PM", "overtime", "final"]:
            self.assertNotIn(spoiler, outside_rules, spoiler)


def scores(page):
    """The catch-up screen's score, each side as '2 DAL' in the answer's order."""
    return [words(cell) for cell in re.findall(r'<span class="team-score">(.*?)</span>', page, re.S)]


def box_rows(page):
    """The catch-up screen's box score rows, each as its list of cell words."""
    return [[words(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S) if "<td" in row]


def play_rows(page):
    """The catch-up screen's plays, each as (its period, clock and team, its text), in the order shown."""
    return [(words(moment), words(text)) for moment, text in
            re.findall(r"<div><b>(.*?)</b>(.*?)</div>", page, re.S)]


def picker(page, name):
    """One of the catch-up screen's pickers: every option value it offers, in order."""
    markup = re.search(rf'<select name="{name}"[^>]*>(.*?)</select>', page, re.S).group(1)
    return [attrs["value"] for tag, attrs in tags(markup)]


def picked(page, name):
    """The value one of the catch-up screen's pickers shows as picked."""
    markup = re.search(rf'<select name="{name}"[^>]*>(.*?)</select>', page, re.S).group(1)
    return next(attrs["value"] for tag, attrs in tags(markup) if "selected" in attrs)


def screen_espn(game=None):
    """ESPN's answers for one started Dallas-Boston game on the test's Game day, as the catch-up screen
    asks for them."""
    return {
        SCOREBOARD: {"events": [event("screen", "2026-10-23T23:10Z", "in", (DAL, "2"), (BOS, "3"))]},
        f"{ESPN}/summary?event=screen": game or handmade_game(),
    }


class CatchUpScreenTest(PageServing):
    """The catch-up screen seam: the page respond serves for a catch-up path on the test's Game day."""

    def screen(self, game=None, **params):
        """The catch-up screen for Dallas' game with Boston, at the moment and tab `params` name."""
        return self.page("/?" + urlencode([("catchup", "DAL"), ("teams", "DAL,BOS")]
                                          + list(params.items())), get=espn(screen_espn(game)))

    def test_every_card_opens_the_catch_up_screen_for_its_own_team(self):
        page = self.page("/?teams=LAL,BOS,IND,DAL&presets=blow")
        watched = {team: next(attrs["href"] for tag, attrs in tags(card)
                              if attrs.get("class") == "watching")
                   for team, card in cards(page).items()}
        queries = {team: parse_qs(urlsplit(href).query) for team, href in watched.items()}
        self.assertEqual({team: query["catchup"] for team, query in queries.items()},
                         {team: [team] for team in ["LAL", "BOS", "IND", "DAL"]})
        self.assertEqual({tuple(query["teams"]) for query in queries.values()},
                         {("LAL", "BOS", "IND", "DAL")})

    def test_each_cards_watching_button_says_im_watching(self):
        page = self.page("/?teams=DAL&presets=blow")
        self.assertIn("I'm watching", words(cards(page)["DAL"]))

    def test_a_cards_watching_link_opens_its_game_at_the_first_moment(self):
        get = espn(screen_espn())
        card = cards(self.page("/?teams=DAL&presets=blow", get=get))["DAL"]
        link = next(attrs["href"] for tag, attrs in tags(card) if attrs.get("class") == "watching")
        self.assertEqual(scores(self.page(link, get=get)), ["0 DAL", "0 BOS"])

    def test_a_named_moment_shows_the_score_at_that_moment(self):
        page = self.screen(period="1st", minutes=10, seconds=0)
        self.assertEqual(scores(page), ["2 DAL", "2 BOS"])

    def test_the_box_score_tab_shows_each_players_line_and_the_team_totals(self):
        rows = box_rows(self.screen(period="1st", minutes=10, seconds=0))
        self.assertIn(["Luka Doncic", "2:00", "2", "0", "0", "0", "1/1", "0/0", "0/0"], rows)
        self.assertIn(["DAL", "—", "2", "1", "1", "0", "1/1", "0/0", "0/0"], rows)
        self.assertIn(["BOS", "—", "2", "0", "0", "0", "1/2", "0/1", "0/0"], rows)

    def test_the_box_score_prints_each_players_minutes_as_minutes_and_seconds(self):
        # 2:40 played is 2.67 minutes; a box score prints the clock, not the decimal.
        rows = {row[0]: row for row in box_rows(self.screen(period="1st", minutes=9, seconds=20))}
        self.assertEqual(rows["Luka Doncic"][1], "2:40")

    def test_the_play_by_play_tab_lists_the_plays_up_to_the_moment_newest_first(self):
        page = self.screen(period="1st", minutes=10, seconds=0, tab="plays")
        self.assertEqual(play_rows(page), [
            ("1st Quarter 10:10 · BOS", "Jayson Tatum makes driving layup"),
            ("1st Quarter 10:30 · DAL", "Dereck Lively II offensive rebound"),
            ("1st Quarter 11:05 · BOS", "Jayson Tatum misses 25-foot three point jumper"),
            ("1st Quarter 11:40 · DAL", "Luka Doncic makes 18-foot jump shot (Kyrie Irving assists)"),
            ("1st Quarter 12:00 · DAL",
             "Dereck Lively II vs. Jayson Tatum (Luka Doncic gains possession)"),
        ])

    def test_the_play_by_play_tab_prints_no_end_of_game_marker_for_a_regulation_game(self):
        page = self.screen(game=regulation_end_game(), period="4th", minutes=0, seconds=0, tab="plays")
        self.assertEqual(play_rows(page), [
            ("4th Quarter 0:30 · DAL", "Luka Doncic makes driving layup"),
            ("4th Quarter 12:00 · DAL", "Jump ball to start the 4th"),
        ])
        for marker in ["End of the 4th Quarter", "End of Game"]:
            self.assertNotIn(marker, page, marker)

    def test_the_play_by_play_tab_prints_no_end_of_game_marker_for_an_overtime_game(self):
        page = self.screen(game=overtime_game(), period="OT", minutes=14, seconds=0, tab="plays")
        self.assertEqual([text for _, text in play_rows(page)], [
            "Luka Doncic makes 25-foot three point jumper",
            "Jayson Tatum makes 21-foot jumper",
            "Jayson Tatum makes 20-foot jumper",
            "Luka Doncic makes driving layup",
            "Jump ball to start overtime",
            "Jump ball to start the 4th",
        ])
        for marker in ["End of the 4th Quarter", "End of the 1st OT", "End of the 2nd OT",
                       "End of the 3rd OT", "End of Game"]:
            self.assertNotIn(marker, page, marker)

    def test_the_play_by_play_tab_at_the_end_of_regulation_prints_no_overtime_play(self):
        # Overtime's opening tip shares the 4th quarter's 0:00, so its label and text must not reach the
        # screen at the end of regulation, where they would tell a fan an overtime followed.
        page = self.screen(game=overtime_game(), period="4th", minutes=0, seconds=0, tab="plays")
        self.assertEqual(play_rows(page),
                         [("4th Quarter 12:00 · DAL", "Jump ball to start the 4th")])
        self.assertNotIn("OT 5:00", page)
        self.assertNotIn("Jump ball to start overtime", page)

    def test_the_play_by_play_tab_at_a_quarter_break_prints_no_play_from_the_next_quarter(self):
        page = self.screen(game=substitution_game(), period="1st", minutes=0, seconds=0, tab="plays")
        self.assertEqual(play_rows(page),
                         [("1st Quarter 6:00 · DAL",
                           "Naji Marshall enters the game for Luka Doncic")])
        self.assertNotIn("2nd Quarter 12:00", page)
        self.assertNotIn("Jump ball to start the 2nd", page)

    def test_the_screen_sends_nothing_from_after_the_moment(self):
        page = self.screen(period="1st", minutes=10, seconds=0, tab="plays")
        for spoiler in ["Luka Doncic bad pass turnover", "Dereck Lively II shooting foul",
                        "Jayson Tatum makes free throw 1 of 2", "End of the 1st Quarter"]:
            self.assertNotIn(spoiler, page, spoiler)

    def test_the_screen_says_it_shows_the_game_as_of_the_moment_and_nothing_later(self):
        page = self.screen(period="1st", minutes=10, seconds=0)
        self.assertIn("Showing the game as of 10:00 left in the 1st quarter. "
                      "Nothing later is sent to your phone.", words(page))

    def test_the_pickers_form_asks_the_server_for_the_page_screen(self):
        form = re.search(r'<form id="catchup".*?</form>',
                         self.screen(period="1st", minutes=10, seconds=0), re.S).group(0)
        self.assertEqual(re.search(r"<form[^>]*>", form).group(0),
                         '<form id="catchup" method="get" action="/">')

    def test_the_pickers_form_carries_the_team_the_list_and_the_fans_settings(self):
        form = re.search(r'<form id="catchup".*?</form>',
                         self.screen(period="1st", minutes=10, seconds=0), re.S).group(0)
        self.assertEqual(collections.Counter(attrs.get("name") for tag, attrs in tags(form)
                                             if tag in ("input", "select")),
                         collections.Counter(["catchup", "teams", "tab",
                                              "presets", "join", "judge_from", "freeze_at",
                                              "blow_upper", "blow_lower", "close_points", "close_minutes",
                                              "along_points", "along_share", "high_total",
                                              "period", "minutes", "seconds"]))
        self.assertEqual(next(attrs["value"] for tag, attrs in tags(form)
                              if attrs.get("name") == "teams"), "DAL,BOS")

    def test_moving_a_picker_asks_the_server_for_the_new_moment(self):
        controls = script(self.screen(period="1st", minutes=10, seconds=0), "radiosilence.catchup")
        self.assertIn('picker.addEventListener("change", function () {', controls)
        self.assertIn("form.submit();", controls)

    def test_the_tab_links_mark_the_one_shown_and_keep_the_moment(self):
        page = self.screen(game=overtime_game(), period="OT", minutes=9, seconds=30, tab="plays")
        box, plays = [attrs for tag, attrs in tags(page)
                      if tag == "a" and "pick" in attrs.get("class", "")]
        self.assertEqual((box["class"], plays["class"]), ("pick", "pick on"))
        query = parse_qs(urlsplit(box["href"]).query)
        self.assertEqual((query["period"], query["minutes"], query["seconds"], query["tab"]),
                         (["OT"], ["9"], ["30"], ["box"]))

    def test_the_period_picker_offers_the_same_five_periods_whatever_the_game(self):
        # The Bead's list, read on a regulation game at tip-off and on a three-overtime game in overtime.
        regulation = picker(self.screen(period="1st", minutes=10, seconds=0), "period")
        overtime = picker(self.screen(game=overtime_game(), period="OT", minutes=9, seconds=0), "period")
        self.assertEqual((regulation, overtime), (["1st", "2nd", "3rd", "4th", "OT"],
                                                  ["1st", "2nd", "3rd", "4th", "OT"]))

    def test_the_overtime_minutes_picker_runs_from_0_to_50(self):
        page = self.screen(game=overtime_game(), period="OT", minutes=9, seconds=0)
        self.assertEqual(picker(page, "minutes"), [str(minute) for minute in range(51)])

    def test_the_minutes_picker_runs_from_12_to_0_in_a_quarter(self):
        page = self.screen(period="3rd", minutes=4, seconds=12)
        self.assertEqual(picker(page, "minutes"), [str(minute) for minute in range(12, -1, -1)])

    def test_the_seconds_picker_runs_from_0_to_59(self):
        page = self.screen(period="3rd", minutes=4, seconds=12)
        self.assertEqual(picker(page, "seconds"), [str(second) for second in range(60)])

    def test_the_pickers_mark_the_moment_the_request_names(self):
        page = self.screen(game=overtime_game(), period="OT", minutes=9, seconds=30)
        self.assertEqual([picked(page, name) for name in ("period", "minutes", "seconds")],
                         ["OT", "9", "30"])

    def test_the_screen_remembers_the_moment_per_game_on_the_phone(self):
        controls = script(self.screen(period="1st", minutes=10, seconds=0), "radiosilence.catchup")
        self.assertIn('const KEY = "radiosilence.catchup.screen";', controls)
        self.assertIn("localStorage.setItem(KEY, JSON.stringify(moment))", controls)
        self.assertIn("JSON.parse(localStorage.getItem(KEY))", controls)
        self.assertIn('location.replace("?" + asked)', controls)

    def test_a_team_with_no_started_game_gets_the_words_and_back(self):
        page = self.page("/?catchup=DAL&teams=DAL", get=espn(night()))
        self.assertIn("That team has no started game on the Game day.", words(page))
        self.assertIn("Back", words(page))

    def test_the_screen_says_plainly_when_espn_cannot_be_reached(self):
        def offline(url):
            raise urllib.error.URLError("offline")
        page = self.page("/?catchup=DAL&teams=DAL", get=offline)
        self.assertIn("Couldn't reach ESPN (URLError).", words(page))
        self.assertIn("Back", words(page))

    def test_back_returns_to_the_list_with_the_fans_teams_and_settings(self):
        page = self.screen(period="1st", minutes=10, seconds=0, presets="blow,close", join="AND")
        back = next(attrs for tag, attrs in tags(page) if tag == "a" and attrs.get("class") == "btn")
        self.assertIn("Back", words(page))
        query = parse_qs(urlsplit(back["href"]).query)
        self.assertEqual(query["teams"], ["DAL", "BOS"])
        self.assertEqual(query["presets"], ["blow,close"])
        self.assertEqual(query["join"], ["AND"])


SEASON_CACHE = "/tmp/bgw-season-2026"


def official_stats(game):
    """ESPN's own stat values by label, with the player's id, for every athlete its boxscore gives
    stats to; read here to compare against the replay."""
    for team in game["boxscore"]["players"]:
        statistics = team["statistics"][0]
        for athlete in statistics["athletes"]:
            if not athlete.get("stats") or "id" not in athlete.get("athlete", {}):
                continue
            yield athlete["athlete"]["id"], dict(zip(statistics["labels"], athlete["stats"]))


def official_lines(game):
    """ESPN's own final boxscore lines by player id, read here to compare against the replay."""
    lines = {}
    for player_id, values in official_stats(game):
        field_goals, threes, free_throws = (values["FG"].split("-"), values["3PT"].split("-"),
                                           values["FT"].split("-"))
        lines[player_id] = {
            "points": int(values["PTS"]),
            "field_goals_made": int(field_goals[0]),
            "field_goals_attempted": int(field_goals[1]),
            "threes_made": int(threes[0]),
            "threes_attempted": int(threes[1]),
            "free_throws_made": int(free_throws[0]),
            "free_throws_attempted": int(free_throws[1]),
            "rebounds": int(values["REB"]),
            "assists": int(values["AST"]),
            "steals": int(values["STL"]),
            "blocks": int(values["BLK"]),
            "turnovers": int(values["TO"]),
            "fouls": int(values["PF"]),
        }
    return lines


def official_minutes(game):
    """ESPN's own minutes by player id, read here to compare against the replay. A player who did not
    play has none."""
    return {player_id: int(values["MIN"]) for player_id, values in official_stats(game)
            if values["MIN"] not in ("--", "")}


def replayed_players(game):
    """Each player's row as the replay gives it for the whole game, by player id, so a full-game
    comparison reads the replay the same way however many stats it checks."""
    return {player["id"]: player for player in catch_up(game, "OT", 50, 59)["players"]}


def game_final_margin(game):
    """The final score's margin, read from ESPN's own header rather than from the replay."""
    sides = game["header"]["competitions"][0]["competitors"]
    return abs(int(sides[0]["score"]) - int(sides[1]["score"]))


def cached_season():
    """Every cached 2025-26 game that has plays: its event, ESPN's summary of it, its Game day and the
    answers judge reads it from, so each replay test walks the season the same way."""
    with open(f"{SEASON_CACHE}/schedule.json") as saved:
        schedule = json.load(saved)
    completed = [event for event in schedule["events"]
                 if event["competitions"][0]["status"]["type"]["state"] == "post"]
    games = []
    for event in completed:
        with open(f"{SEASON_CACHE}/{event['id']}.json") as saved:
            game = json.load(saved)
        if not game.get("plays"):
            continue
        day = start_time(event).date()
        answers = {TEAM_LIST: ESPN_TEAM_LIST,
                   f"{ESPN}/scoreboard?dates={day:%Y%m%d}": {"events": [event]},
                   f"{ESPN}/summary?event={event['id']}": game}
        games.append((event, game, day, answers))
    return games


class PresetSetupTest(PageServing):
    def controls(self):
        """Setup's own script, the one that shows the sliders and keeps the settings."""
        return script(self.page("/?setup=1"), "data-reset")

    def test_setup_offers_the_four_presets_as_chips_with_none_picked(self):
        setup = self.page("/?setup=1")
        self.assertEqual(presets_offered(setup), ["wins", "blow", "close", "high"])
        self.assertEqual(checked(setup, "presets"), [])
        for name in ["Wins for my team", "No blowout losses", "Close games", "High-scoring games"]:
            self.assertIn(name, words(setup))

    def test_setup_cannot_finish_until_a_preset_is_picked(self):
        self.assertIn("disabled", done_button(self.page("/?setup=1")))
        self.assertNotIn("disabled", done_button(self.page("/?setup=1&presets=blow")))

    def test_setup_offers_any_one_fits_or_all_must_fit_with_or_first(self):
        setup = self.page("/?setup=1")
        self.assertEqual(joins_offered(setup), [("OR", True), ("AND", False)])
        self.assertIn("Any one fits (OR)", words(setup))
        self.assertIn("All must fit (AND)", words(setup))

    def test_each_slider_shows_its_shipped_value_and_range(self):
        rows = slider_rows(self.page("/?setup=1"))
        inputs = {parameter: slider_input(markup) for parameter, (markup, _) in rows.items()}
        self.assertEqual({parameter: (attrs["min"], attrs["max"], attrs["value"])
                          for parameter, attrs in inputs.items() if parameter not in ("judge_from", "freeze_at")},
                         {"blow_upper": ("90", "99", "98"), "blow_lower": ("85", "98", "95"),
                          "close_points": ("1", "20", "5"), "close_minutes": ("1", "12", "5"),
                          "along_points": ("1", "20", "9"), "along_share": ("1", "99", "66"),
                          "high_total": ("150", "350", "240")})
        self.assertIn("Stay away above 98%", rows["blow_upper"][1])
        self.assertIn("Reach a total of 240 points", rows["high_total"][1])

    def test_only_the_picked_presets_sliders_are_shown(self):
        setup = self.page("/?setup=1&presets=blow")
        groups = dict(re.findall(r'<section class="group" data-preset="([^"]+)"([^>]*)>', setup))
        self.assertEqual(groups, {"blow": "", "close": " hidden", "high": " hidden"})

    def test_the_shared_timing_is_not_a_preset_group_so_picking_one_cannot_hide_it(self):
        setup = self.page("/?setup=1&presets=blow")
        timing = re.search(r'<section class="group" data-timing([^>]*)>\s*<h2>Timing</h2>(.*?)</section>',
                           setup, re.S)
        self.assertEqual(timing.group(1), "")
        self.assertEqual(re.findall(r'name="([^"]+)"', timing.group(2)), ["judge_from", "freeze_at"])

    def test_the_judge_from_slider_shows_the_moment_it_names(self):
        markup, label = slider_rows(self.page("/?setup=1"))["judge_from"]
        attrs = slider_input(markup)
        self.assertEqual((attrs["min"], attrs["max"], attrs["step"], attrs["value"]),
                         ("0", "2160", "30", "1080"))
        self.assertEqual(label, "Judge from 6:00 left in the 2nd")
        labels = slider_labels(markup)
        self.assertEqual((labels["0"], labels["1080"], labels["1440"], labels["2160"]),
                         ("Tip-off", "6:00 left in the 2nd", "Start of the 3rd", "Start of the 4th"))

    def test_the_freeze_at_slider_shows_the_moment_it_names(self):
        markup, label = slider_rows(self.page("/?setup=1"))["freeze_at"]
        attrs = slider_input(markup)
        self.assertEqual((attrs["min"], attrs["max"], attrs["step"], attrs["value"]),
                         ("2160", "2880", "30", "2580"))
        self.assertEqual(label, "Freeze at 5:00 left in the 4th")
        labels = slider_labels(markup)
        self.assertEqual((labels["2160"], labels["2880"]), ("Start of the 4th", "End of the 4th"))

    def test_an_off_step_timing_value_shows_the_nearest_step_instead_of_crashing(self):
        rows = slider_rows(self.page("/?setup=1&judge_from=1085&freeze_at=2705"))
        self.assertEqual((slider_input(rows["judge_from"][0])["value"],
                          slider_input(rows["freeze_at"][0])["value"]), ("1080", "2700"))
        self.assertIn("Judge from 6:00 left in the 2nd", rows["judge_from"][1])
        self.assertIn("Freeze at 3:00 left in the 4th", rows["freeze_at"][1])

    def test_setup_and_a_cards_rules_show_the_same_moment_for_an_off_step_value(self):
        setup = self.page("/?setup=1&presets=blow&judge_from=1085")
        card = cards(self.page("/?teams=BOS&presets=blow&judge_from=1085"))["BOS"]
        self.assertIn("Judge from 6:00 left in the 2nd", slider_rows(setup)["judge_from"][1])
        self.assertIn("Judge from 6:00 left in the 2nd", card_rules(card))

    def test_an_out_of_range_timing_value_still_falls_back_to_its_default(self):
        rows = slider_rows(self.page("/?setup=1&judge_from=3000&freeze_at=9999"))
        self.assertEqual((slider_input(rows["judge_from"][0])["value"],
                          slider_input(rows["freeze_at"][0])["value"]), ("1080", "2580"))

    def test_setup_shows_the_settings_the_address_names(self):
        setup = self.page("/?setup=1&presets=blow,close&join=AND&blow_upper=97&close_points=4")
        self.assertEqual(checked(setup, "presets"), ["blow", "close"])
        self.assertEqual(joins_offered(setup), [("OR", False), ("AND", True)])
        rows = slider_rows(setup)
        self.assertEqual(slider_input(rows["blow_upper"][0])["value"], "97")
        self.assertIn("Stay away above 97%", rows["blow_upper"][1])
        self.assertIn("Close ending within 4 points", rows["close_points"][1])

    def test_the_setup_form_sends_the_teams_presets_join_and_every_slider(self):
        setup = self.page("/?setup=1")
        form = re.search(r'<form id="setup".*?</form>', setup, re.S).group(0)
        self.assertEqual(collections.Counter(attrs.get("name") for tag, attrs in tags(form)
                                             if tag == "input"),
                         collections.Counter({"teams": len(NBA_TEAMS), "presets": 4, "join": 2,
                                              "blow_upper": 1, "blow_lower": 1, "close_points": 1,
                                              "close_minutes": 1, "along_points": 1, "along_share": 1,
                                              "high_total": 1, "judge_from": 1, "freeze_at": 1}))

    def test_each_preset_with_sliders_offers_its_own_reset_to_default(self):
        setup = self.page("/?setup=1&presets=blow,high")
        groups = dict(re.findall(r'<section class="group" data-preset="([^"]+)"[^>]*>(.*?)</section>',
                                setup, re.S))
        self.assertEqual(sorted(groups), ["blow", "close", "high"])
        for key in ("blow", "close", "high"):
            self.assertEqual([attrs["data-reset"] for tag, attrs in tags(groups[key])
                              if "data-reset" in attrs], [key])

    def test_reset_to_default_returns_to_the_shipped_values(self):
        rows = slider_rows(self.page("/?setup=1&presets=blow,high&blow_upper=97&blow_lower=90&high_total=300"))
        self.assertEqual([slider_input(rows[parameter][0])["data-default"]
                          for parameter in ("blow_upper", "blow_lower", "high_total")],
                         ["98", "95", "240"])

    def test_the_overtime_warning_warns_that_a_watchs_timing_can_hint_at_overtime(self):
        setup = self.page("/?setup=1&presets=wins")
        warning = words(re.search(r'<p class="notice" id="overtime"[^>]*>(.*?)</p>', setup, re.S).group(1))
        self.assertEqual(warning, "Every Preset you picked judges only the final, so if you remember when "
                                  "the game tipped off, the time a Watch appears, or doesn't, can hint at "
                                  "overtime.")

    def test_the_overtime_warning_shows_only_when_every_picked_preset_judges_the_final(self):
        def warning(path):
            return next(attrs for tag, attrs in tags(self.page(path)) if attrs.get("id") == "overtime")
        self.assertNotIn("hidden", warning("/?setup=1&presets=wins"))
        self.assertIn("hidden", warning("/?setup=1"))
        self.assertIn("hidden", warning("/?setup=1&presets=blow"))
        self.assertIn("hidden", warning("/?setup=1&presets=wins,blow"))

    def test_the_page_keeps_the_settings_a_request_names_on_the_phone(self):
        remembered = script(self.page("/?teams=BOS&presets=blow&join=AND&blow_upper=97"), "function settingsQuery")
        self.assertIn('if (params.has("presets") || params.has("join")) store(named(params));', remembered)

    def test_the_settings_the_page_saves_are_the_presets_the_join_and_every_slider(self):
        controls = self.controls()
        self.assertIn("presets: chips.filter(chip => chip.checked).map(chip => chip.value),", controls)
        self.assertIn('join: form.querySelector(\'input[name="join"]:checked\').value,', controls)
        self.assertIn("values: Object.fromEntries(sliders.map(slider => [slider.name, Number(slider.value)])),",
                      controls)

    def test_the_page_saves_the_settings_the_fan_sets_on_the_phone(self):
        controls = self.controls()
        self.assertIn('localStorage.setItem(SETTINGS, JSON.stringify(settings()))', controls)

    def test_a_slider_shows_the_word_for_its_value_as_the_fan_moves_it(self):
        controls = self.controls()
        self.assertIn("shown.textContent = JSON.parse(slider.dataset.labels)[slider.value];", controls)

    def test_reset_to_default_puts_every_slider_in_the_preset_back_and_shows_it(self):
        controls = self.controls()
        self.assertRegex(controls, r'const reset = event\.target\.closest\("\[data-reset\]"\);'
                                   r' if \(!reset\) return; for \(const slider of reset\.closest\("section"\)'
                                   r'\.querySelectorAll\(')
        self.assertRegex(controls, r'slider\.value = slider\.dataset\.default; showValue\(slider\);')

    def test_picking_a_preset_reveals_its_sliders_and_unpicking_it_hides_them(self):
        controls = self.controls()
        self.assertIn("group.hidden = !picked.includes(group.dataset.preset);", controls)

    def test_done_needs_a_preset_as_the_fan_picks_and_unpicks(self):
        controls = self.controls()
        self.assertIn("done.disabled = picked.length === 0;", controls)

    def test_the_overtime_warning_follows_the_presets_the_fan_picks(self):
        controls = self.controls()
        self.assertIn("warning.hidden = !(picked.length && picked.every(key => finalOnly.has(key)));",
                      controls)

    def test_tapping_a_card_lists_the_presets_the_and_or_and_the_values_applied(self):
        card = cards(self.page("/?teams=BOS&presets=blow,close&join=AND"
                               "&blow_upper=97&close_points=4"))["BOS"]
        self.assertEqual(card_rules(card),
                         "No blowout losses (Stay away above 97%, Back to Watch below 95%) "
                         "Close games (Close ending within 4 points, Close ending in the last 5 minutes, "
                         "Close along the way within 9 points, Close along the way for over 66%) "
                         "All must fit (AND) "
                         "Judge from 6:00 left in the 2nd · Freeze at 5:00 left in the 4th")

    def test_a_cards_rules_do_not_say_which_preset_fitted_the_game(self):
        # BOS is Stay away and LAL is Watch under the same Preset, so their panels must read the same.
        page = self.page("/?teams=BOS,LAL&presets=blow")
        rules = {team: card_rules(card) for team, card in cards(page).items()}
        self.assertEqual(rules["BOS"], rules["LAL"])

    def test_a_wins_only_fan_gets_the_preset_by_name_and_the_shared_timing(self):
        card = cards(self.page("/?teams=BOS&presets=wins"))["BOS"]
        self.assertEqual(card_rules(card),
                         "Wins for my team Any one fits (OR) "
                         "Judge from 6:00 left in the 2nd · Freeze at 5:00 left in the 4th")


@unittest.skipUnless(os.path.exists(f"{SEASON_CACHE}/schedule.json"),
                     f"no cached 2025-26 season in {SEASON_CACHE}")
class SeasonReplayTest(unittest.TestCase):
    def test_no_blowout_losses_reads_stay_away_in_25_of_the_82_games(self):
        games = cached_season()
        verdicts = [judge(["DAL"], day, answers.__getitem__, NO_BLOWOUT_LOSSES)[0]["verdict"]
                    for _, _, day, answers in games]
        self.assertEqual(len(games), 82)
        self.assertEqual(verdicts.count("Stay away"), 25)

    def test_close_games_marks_51_of_the_82_games_close(self):
        games = cached_season()
        verdicts = [judge(["DAL"], day, answers.__getitem__, CLOSE_GAMES)[0]["verdict"]
                    for _, _, day, answers in games]
        self.assertEqual(len(games), 82)
        self.assertEqual(verdicts.count("Watch"), 51)

    def test_high_scoring_games_marks_28_of_the_82_games_at_240(self):
        games = cached_season()
        verdicts = [judge(["DAL"], day, answers.__getitem__, HIGH_SCORING_GAMES)[0]["verdict"]
                    for _, _, day, answers in games]
        watched = verdicts.count("Watch")
        print(f"\nhigh-scoring games at 240 marks {watched} of the {len(verdicts)} cached 2025-26 games "
              f"({watched / len(verdicts):.0%} of them)")
        self.assertEqual(len(games), 82)
        self.assertEqual(watched, 28)

    def test_close_games_watches_every_game_decided_by_5_or_fewer(self):
        missed = []
        for event, game, day, answers in cached_season():
            if game_final_margin(game) > 5:
                continue
            if judge(["DAL"], day, answers.__getitem__, CLOSE_GAMES)[0]["verdict"] != "Watch":
                missed.append(event["id"])
        self.assertEqual(missed, [])

    def test_a_full_game_replay_matches_espn_for_points_made_shots_and_free_throws(self):
        with open(f"{SEASON_CACHE}/schedule.json") as saved:
            schedule = json.load(saved)
        completed = [event for event in schedule["events"]
                     if event["competitions"][0]["status"]["type"]["state"] == "post"]
        compared, matched, games = collections.Counter(), collections.Counter(), 0
        for event in completed:
            with open(f"{SEASON_CACHE}/{event['id']}.json") as saved:
                game = json.load(saved)
            if not game.get("plays") or not game.get("boxscore", {}).get("players"):
                continue
            games += 1
            rebuilt = replayed_players(game)
            for player_id, official in official_lines(game).items():
                for field, expected in official.items():
                    compared[field] += 1
                    matched[field] += rebuilt[player_id][field] == expected
        rates = {field: matched[field] / compared[field] for field in compared}
        print(f"\n{games} cached 2025-26 games replayed; match rate by stat:",
              {field: f"{rate:.2%}" for field, rate in rates.items()})
        self.assertEqual(games, 82)
        for field in ("points", "field_goals_made", "threes_made",
                      "free_throws_made", "free_throws_attempted"):
            self.assertEqual(rates[field], 1, field)
        for field in ("field_goals_attempted", "threes_attempted", "rebounds", "assists",
                      "steals", "blocks", "turnovers", "fouls"):
            self.assertGreaterEqual(rates[field], 0.99, field)

    def test_a_full_game_replay_gives_each_player_his_official_minutes(self):
        compared, within, exact, games = 0, 0, 0, 0
        for _, game, _, _ in cached_season():
            games += 1
            rebuilt = {player_id: row["minutes"] for player_id, row in replayed_players(game).items()}
            for player_id, official in official_minutes(game).items():
                compared += 1
                within += abs(rebuilt[player_id] - official) <= 1
                exact += round(rebuilt[player_id]) == official
        print(f"\n{games} cached 2025-26 games replayed; {within} of {compared} players "
              f"({within / compared:.1%}, {exact} of them to the minute) within a minute of ESPN's")
        self.assertEqual(games, 82)
        self.assertGreater(within / compared, 0.99)


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

    def test_a_players_usual_minutes_are_fetched_once_a_day(self):
        responses = {TEAM_LIST: ESPN_TEAM_LIST,
                     **player_responses(tracked_game(points=22, minutes=20),
                                        athlete_overview(games=12, minutes=36.0))}
        fake = Counting(responses)
        now = [0]
        cache = Cached(fake, clock=lambda: now[0])
        asked = "/rows?players=d1:DAL:Luka%20Doncic&player_points=20"
        respond(asked, NOW, cache)
        now[0] = 12 * 60 * 60
        respond(asked, NOW, cache)
        self.assertEqual(fake.count(PLAYER_OVERVIEW), 1)
        now[0] = 24 * 60 * 60
        respond(asked, NOW, cache)
        self.assertEqual(fake.count(PLAYER_OVERVIEW), 2)


if __name__ == "__main__":
    unittest.main()
