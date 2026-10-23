"""Bad Game Warning: tells you whether tonight's Dallas Mavericks game is worth watching from behind.

The server fetches ESPN's public win-probability data and sends the phone only a verdict,
never a score, clock, or percentage, so nothing on the page or in its source can spoil the game.
"""

import html
import json
import os
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEAM = "DAL"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
STAY_AWAY_ODDS = 0.90  # opponent win probability above this means the game is out of reach
PORT = int(os.environ.get("PORT", "8765"))


def fetch(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def start_time(event):
    return datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone()


def state(event):
    """ESPN's game state: 'pre', 'in' or 'post'."""
    return event["competitions"][0]["status"]["type"]["state"]


def todays_game(schedule, today):
    """Return the schedule event for the Mavericks game on `today` (local date), or None."""
    for event in schedule["events"]:
        if start_time(event).date() == today:
            return event
    return None


def next_game(schedule, today):
    """Return (headline, detail) previewing the next game that hasn't tipped off."""
    for event in schedule["events"]:
        if state(event) != "pre":
            continue
        start = start_time(event)
        day = "Today" if start.date() == today else f"{start:%a, %b} {start.day}"
        mavs, opponent = sorted(event["competitions"][0]["competitors"],
                                key=lambda c: c["team"]["abbreviation"] != TEAM)
        where = "vs" if mavs["homeAway"] == "home" else "at"
        return "Next game", f"{day}, {start:%-I:%M %p} {where} {opponent['team']['displayName']}"
    return "No upcoming games", "The Mavericks have no more games scheduled."


def seconds_left(clock):
    """ESPN shows '6:00' above one minute and '45.2' below it."""
    minutes, _, seconds = clock.rpartition(":")
    return int(minutes or 0) * 60 + float(seconds)


def verdict(summary):
    """Return (headline, detail) for one game's ESPN summary."""
    competition = summary["header"]["competitions"][0]
    mavs_home = any(c["homeAway"] == "home" and c["team"]["abbreviation"] == TEAM
                    for c in competition["competitors"])
    plays = {play["id"]: play for play in summary.get("plays", [])}
    readings = [r for r in summary.get("winprobability", []) if r["playId"] in plays]
    if not readings:
        return "No data yet", "ESPN hasn't published win probability for this game yet."

    latest = readings[-1]
    play = plays[latest["playId"]]
    period = play["period"]["number"]
    left = seconds_left(play["clock"]["displayValue"])
    # The rule applies only from 6:00 left in the 2nd quarter onward.
    if period < 2 or (period == 2 and left > 6 * 60):
        return "Too early to call", "Check back after the middle of the 2nd quarter."

    home = latest["homeWinPercentage"]
    opponent = 1 - home if mavs_home else home
    if opponent > STAY_AWAY_ODDS:
        return "Stay away", "This one looks out of reach."
    return "Watch", "Still a game."


def current_verdict():
    schedule = fetch(f"{ESPN}/teams/{TEAM.lower()}/schedule")
    today = datetime.now().astimezone().date()
    game = todays_game(schedule, today)
    # A game that finished today still gets a verdict, since you may be about to watch it from behind.
    if game is None or state(game) == "pre":
        return next_game(schedule, today)
    return verdict(fetch(f"{ESPN}/summary?event={game['id']}"))


PAGE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Mavs?">
<title>Mavs?</title>
<style>
  body {{ margin: 0; height: 100vh; display: flex; flex-direction: column; align-items: center;
         justify-content: center; font-family: -apple-system, sans-serif; text-align: center;
         background: {background}; color: white; }}
  h1 {{ font-size: 3.5rem; margin: 0 1rem; }}
  p {{ font-size: 1.3rem; opacity: .85; margin: 1rem; }}
</style>
</head><body><h1>{headline}</h1><p>{detail}</p></body></html>"""

COLORS = {"Watch": "#0064b1", "Stay away": "#7a1f1f"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        try:
            headline, detail = current_verdict()
        except Exception as error:  # show the failure on the phone instead of a blank page
            headline, detail = "Can't tell", f"Couldn't reach ESPN ({type(error).__name__})."
        body = PAGE.format(headline=html.escape(headline), detail=html.escape(detail),
                           background=COLORS.get(headline, "#333")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
