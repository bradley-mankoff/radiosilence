"""RadioSilence: tells a fan, without spoilers, whether each followed NBA team's game is worth watching
from behind.

The phone names its teams with each request, and the server keeps no per-fan state. judging.py works out
each team's row from ESPN's public JSON, and this file serves those rows, sharing ESPN answers for a short
while. The answer never includes a score, clock, quarter, percentage, or a started game's tip-off time.
"""

import html
import json
import os
import threading
import time
import urllib.request
from collections import namedtuple
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from judging import TEAM_LIST, judge

TEAM = "DAL"  # the Mavericks, for the root page that predates the team list
CACHE_SECONDS = 30  # one ESPN fetch per URL per cycle; the page refreshes every 60 seconds
TEAM_LIST_SECONDS = 24 * 60 * 60  # ESPN's team list changes only between seasons
PORT = int(os.environ.get("PORT", "8765"))


def lifetime_for(url):
    """How long an ESPN answer is reused: a game's JSON for a cycle, the team list for a day."""
    return TEAM_LIST_SECONDS if url == TEAM_LIST else CACHE_SECONDS


# One kept ESPN answer: when it was fetched, how long it lasts, and the JSON it holds.
Saved = namedtuple("Saved", "at lifetime body")


def fetch(url):
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


PAGE = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Mavs?">
<meta http-equiv="refresh" content="60">
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
# ESPN not answering, or answering with bad JSON; a bug in judging must not read as ESPN being down.
ESPN_UNREACHABLE = (OSError, ValueError)
JSON_TYPE = "application/json; charset=utf-8"
HTML_TYPE = "text/html; charset=utf-8"
TEXT_TYPE = "text/plain; charset=utf-8"


def headline_for(row):
    """The root page's words for one team's row: its Verdict, its Next game, or the end of its season."""
    if row["verdict"]:
        return row["verdict"], row["detail"]
    preview = row["next_game"]
    if preview:
        where = "vs" if preview["home"] else "at"
        return "Next game", f"{preview['day']}, {preview['time']} {where} {preview['opponent']}"
    return "No upcoming games", row["detail"]


def espn_outage(error):
    """The phone's words for ESPN not answering, the same in a row's error and on the root page."""
    return f"Couldn't reach ESPN ({type(error).__name__})."


def respond(path, now, get):
    """Return (status, content type, body bytes) for a GET of `path`.

    `now` sets the Game day and `get` returns ESPN's JSON for a URL (the server passes a Cached fetch).
    """
    url = urlsplit(path)
    if url.path == "/rows":
        names = parse_qs(url.query).get("teams", [""])[0].split(",")
        teams = list(dict.fromkeys(name.strip().upper() for name in names if name.strip()))
        try:
            rows = judge(teams, now.date(), get)
        except ESPN_UNREACHABLE as error:  # say so plainly; a missing answer must not look like a Verdict
            return 503, JSON_TYPE, json.dumps({"error": espn_outage(error)}).encode()
        return 200, JSON_TYPE, json.dumps({"rows": rows}).encode()
    if url.path == "/":
        try:
            headline, detail = headline_for(judge([TEAM], now.date(), get)[0])
        except ESPN_UNREACHABLE as error:  # show the failure on the phone instead of a blank page
            headline, detail = "Can't tell", espn_outage(error)
        body = PAGE.format(headline=html.escape(headline), detail=html.escape(detail),
                           background=COLORS.get(headline, "#333")).encode()
        return 200, HTML_TYPE, body
    return 404, TEXT_TYPE, b"Not found"


CACHE = Cached(fetch)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, content_type, body = respond(self.path, datetime.now().astimezone(), CACHE)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
