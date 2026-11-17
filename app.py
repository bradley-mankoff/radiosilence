"""RadioSilence: tells a fan, without spoilers, whether each followed NBA team's game is worth watching
from behind.

The phone names its teams and its Presets with each request, and the server keeps no per-fan state.
judging.py works out each team's row from ESPN's public JSON and the fan's settings; players.py judges each
Tracked player's night from the same saved game and the player's usual minutes; catchup.py rebuilds the
score, box score and plays as of the moment the fan names; highlights.py finds each started game's
highlight reel without giving away its title, thumbnail or length; page.py turns the rows into the list and
the catch-up answer into the catch-up screen; and this file serves them all, sharing ESPN answers for a
short while. Only the catch-up answer and screen carry a score, clock or quarter, and only for the plays
at or before the moment the fan names: every other answer holds no score, clock, quarter, win-probability
percentage, or a started game's tip-off time.
"""

import json
import os
import threading
import time
import urllib.request
from collections import namedtuple
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import highlights
import page
import players
import presets
from catchup import TIP_OFF, catch_up, moment_seconds
from judging import (ESPN, TEAM_LIST, espn_abbreviation, espn_abbreviations, judge, row,
                     start_time, started_game)

CACHE_SECONDS = 30  # one ESPN fetch per URL per cycle; the page refreshes every 60 seconds
TEAM_LIST_SECONDS = 24 * 60 * 60  # ESPN's team list changes only between seasons
PORT = int(os.environ.get("PORT", "8765"))
STATIC_DIR = Path(__file__).resolve().with_name("static")


def lifetime_for(url):
    """How long an ESPN answer is reused: a game's JSON for a cycle, the team list or a player's usual
    minutes for a day."""
    return TEAM_LIST_SECONDS if url == TEAM_LIST or players.is_average_url(url) else CACHE_SECONDS


# One kept ESPN answer: when it was fetched, how long it lasts, and the JSON it holds.
Saved = namedtuple("Saved", "at lifetime body")


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


# YouTube serves its playlist page to a browser and may refuse a bare Python client, so ask as one.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def fetch_page(url):
    """The text at `url`, read with a browser's user agent so YouTube serves its playlist page."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8", "replace")


def oembed(video_id):
    """YouTube's keyless oEmbed answer for `video_id`, or an error when it is gone or cannot be embedded."""
    url = (f"https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v="
           f"{quote(video_id, safe='')}")
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


class Cached:
    """Wraps a fetch so each URL's JSON is reused for its lifetime, shared by every request."""

    def __init__(self, get, clock=time.monotonic):
        self.get, self.clock = get, clock
        self.saved = {}  # url -> Saved
        self.lock = threading.Lock()  # so two requests at once cannot both fetch the same URL

    def __call__(self, url):
        with self.lock:
            now = self.clock()
            self.saved = {cached_url: entry for cached_url, entry in self.saved.items()
                          if now - entry.at < entry.lifetime}
            if url not in self.saved:
                self.saved[url] = Saved(now, lifetime_for(url), self.get(url))
            return self.saved[url].body


# ESPN not answering, or answering with bad JSON; a bug in judging must not read as ESPN being down.
ESPN_UNREACHABLE = (OSError, ValueError)
JSON_TYPE = "application/json; charset=utf-8"
HTML_TYPE = "text/html; charset=utf-8"
TEXT_TYPE = "text/plain; charset=utf-8"


def json_answer(status, payload):
    """One JSON answer: its status, the JSON content type and the encoded body."""
    return status, JSON_TYPE, json.dumps(payload).encode()


# Only these files are served from disk, so a request cannot reach any other path.
STATIC_FILES = {
    "manifest.webmanifest": "application/manifest+json; charset=utf-8",
    "icon-180.png": "image/png",
    "icon-512.png": "image/png",
}


def espn_outage(error):
    """The phone's words for ESPN not answering, the same in a row's error and on the page."""
    return f"Couldn't reach ESPN ({type(error).__name__})."


def named_teams(values):
    """The team names in a query's `teams` values, whether repeated or one comma-joined value."""
    names = []
    for value in values:
        names.extend(value.split(","))
    return list(dict.fromkeys(name.strip().upper() for name in names if name.strip()))


def teams_and_fan(params):
    """The team names and the fan's Preset settings a request's `params` name."""
    return named_teams(params.get("teams", [])), presets.from_query(params)


class NoGame(Exception):
    """A catch-up request with no game to show: no such team, or no started game on the Game day."""


def game_id_and_summary(names, now, get):
    """ESPN's id for the started game on the Game day of the first of `names` that has one, and its
    summary.

    Raises NoGame with the phone's words when no name is an NBA team or none has a started game.
    """
    known = espn_abbreviations(get)
    abbreviations = [espn_abbreviation(name, known) for name in names]
    if not any(abbreviations):
        raise NoGame("ESPN doesn't list an NBA team by that name.")
    day = now.date()
    games = get(f"{ESPN}/scoreboard?dates={day:%Y%m%d}")
    today_games = [event for event in games["events"] if start_time(event).date() == day]
    game = next((started_game(today_games, abbreviation)
                 for abbreviation in abbreviations if abbreviation), None)
    if game is None:
        raise NoGame("That team has no started game on the Game day.")
    return game["id"], get(f"{ESPN}/summary?event={game['id']}")


def named_moment(params):
    """The period, minutes and seconds a request names, or None when it names no three numbers."""
    try:
        return params["period"][0], int(params["minutes"][0]), int(params["seconds"][0])
    except (KeyError, ValueError):
        return None


def picked_moment(params):
    """The moment a catch-up screen's pickers name, or Tip-off when the request names none or names a
    moment no clock has."""
    moment = named_moment(params)
    if moment is None:
        return TIP_OFF
    try:
        # The call only asks whether a clock has this moment; the screen names the moment itself.
        moment_seconds(*moment)
    except ValueError:
        return TIP_OFF
    return moment


def catchup_page(team, params, names, fan, now, get):
    """The catch-up screen for `team`'s game, at the moment the request's pickers name and on the tab it
    asks for, or the words for why the team has no game to show and the way back to the list."""
    teams = names or [team]
    moment = picked_moment(params)
    tab = page.catchup_tab(params.get("tab", [""])[0])
    try:
        game_id, summary = game_id_and_summary([team], now, get)
    except NoGame as error:
        return page.catchup_notice(teams, fan, str(error))
    except ESPN_UNREACHABLE as error:  # say so plainly; a missing answer must not look like a Verdict
        return page.catchup_notice(teams, fan, espn_outage(error))
    return page.catchup_screen(team, teams, fan, game_id, catch_up(summary, *moment), moment, tab)


def highlight_buttons(now, reels=None):
    """A function giving each started game's ESPN event its highlights button at `now`.

    `reels` finds a game's button, such as a highlights.Highlights; without one every game waits, disabled,
    because no reel was looked for.
    """
    if reels is None:
        return lambda event: highlights.waiting()
    return lambda event: reels.button(highlights.game_of(event), now)


def root_page(query, now, get, reels=None):
    """The page at `/` for `query`: team setup, the list of cards for the teams it names, or the catch-up
    screen of the team it names."""
    params = parse_qs(query)
    names, fan = teams_and_fan(params)
    catchup_team = params.get("catchup", [""])[0].strip().upper()
    if catchup_team:
        return catchup_page(catchup_team, params, names, fan, now, get)
    showing_setup = "setup" in params or not names
    try:
        if showing_setup:
            return page.setup_screen(sorted(espn_abbreviations(get)), names, fan)
        return page.list_screen(judge(names, now.date(), get, fan, highlight_buttons(now, reels)), fan)
    except ESPN_UNREACHABLE as error:  # say so plainly; a missing answer must not look like a Verdict
        outage = espn_outage(error)
        if showing_setup:
            return page.setup_screen([], names, fan, outage)
        return page.list_screen([row(name) for name in names], fan, outage)


def catchup_answer(params, now, get):
    """The rows and plays as of the moment a catch-up request names, in the game of the first named team
    that has started one on the Game day.

    The query names `teams`, `period`, `minutes` and `seconds`; the moment is the same one the catch-up
    screen's pickers offer. ESPN's team list decides which names are teams, and only a team with a game
    that has started on the Game day has a catch-up answer.
    """
    names = named_teams(params.get("teams", []))
    moment = named_moment(params)
    if moment is None:
        return json_answer(400, {"error": "Name a period, minutes and seconds."})
    try:
        _, summary = game_id_and_summary(names, now, get)
    except NoGame as error:
        return json_answer(404, {"error": str(error)})
    try:
        return json_answer(200, catch_up(summary, *moment))
    except ValueError as error:
        return json_answer(400, {"error": str(error)})


def respond(path, now, get, reels=None):
    """Return (status, content type, body bytes) for a GET of `path`.

    `now` sets the Game day, `get` returns ESPN's JSON for a URL (the server passes a Cached fetch), and
    `reels` finds each started game's highlights button (the server passes the Highlights cache).
    """
    url = urlsplit(path)
    if url.path == "/presets":
        return json_answer(200, presets.definitions())
    if url.path == "/rows":
        params = parse_qs(url.query)
        names, fan = teams_and_fan(params)
        tracked = players.tracked_players(params)
        checks = players.checks_from_query(params)
        try:
            rows = []
            if names:  # no team named spares the team list a request of its own
                rows += judge(names, now.date(), get, fan, highlight_buttons(now, reels))
            rows += players.judge(tracked, now.date(), get, checks)
        except ESPN_UNREACHABLE as error:
            return json_answer(503, {"error": espn_outage(error)})
        return json_answer(200, {"rows": rows})
    if url.path == "/catchup":
        try:
            return catchup_answer(parse_qs(url.query), now, get)
        except ESPN_UNREACHABLE as error:
            return json_answer(503, {"error": espn_outage(error)})
    static = url.path[1:]
    if static in STATIC_FILES:  # the manifest and its icons, by name, so no other path reaches disk
        return 200, STATIC_FILES[static], (STATIC_DIR / static).read_bytes()
    if url.path == "/":
        return 200, HTML_TYPE, root_page(url.query, now, get, reels).encode()
    return 404, TEXT_TYPE, b"Not found"


CACHE = Cached(fetch)
# The playlist page is read only for a game past its wait, and each game's answer is kept for a while.
HIGHLIGHTS = highlights.Highlights(lambda: fetch_page(highlights.PLAYLIST), oembed)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, content_type, body = respond(self.path, datetime.now().astimezone(), CACHE, HIGHLIGHTS)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
