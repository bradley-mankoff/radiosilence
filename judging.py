"""Judging: one row per followed NBA team for the Game day, worked out from ESPN's public JSON.

judge() takes `get`, a function that returns ESPN's JSON for a URL and raises when ESPN cannot be
reached. The server passes a cached fetch and the tests pass saved responses, so this file never
touches the network or the clock.
"""

from datetime import datetime
from urllib.parse import quote

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
TEAM_LIST = f"{ESPN}/teams"  # every NBA team, with the abbreviation ESPN uses for it
STAY_AWAY_ODDS = 0.95  # opponent win probability above this means the game is out of reach

# The short names fans use for some teams differ from the abbreviation ESPN lists them under.
TEAM_ALIASES = {"NYK": "NY", "GSW": "GS", "SAS": "SA", "NOP": "NO", "UTA": "UTAH", "WAS": "WSH"}


def start_time(event):
    return datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone()


def state(event):
    """ESPN's game state: 'pre', 'in' or 'post'."""
    return event["competitions"][0]["status"]["type"]["state"]


def competitor(event, team):
    """Return the event's competitor for `team` (an ESPN abbreviation), or None."""
    for side in event["competitions"][0]["competitors"]:
        if side["team"]["abbreviation"] == team:
            return side
    return None


def started_game(events, abbreviation):
    """The first of `events` in which the team ESPN calls `abbreviation` has tipped off, or None."""
    for event in events:
        if state(event) != "pre" and competitor(event, abbreviation):
            return event
    return None


def seconds_left(clock):
    """ESPN shows '6:00' above one minute and '45.2' below it."""
    minutes, _, seconds = clock.rpartition(":")
    return int(minutes or 0) * 60 + float(seconds)


def game_time(play):
    """Sorts plays by when they happened in the game: later periods, then less time left."""
    return play["period"]["number"], -seconds_left(play["clock"]["displayValue"])


def verdict(summary, abbreviation):
    """Return (verdict, detail) for the team ESPN calls `abbreviation`, from one started game's summary."""
    team_home = competitor(summary["header"], abbreviation)["homeAway"] == "home"
    plays = {play["id"]: play for play in summary.get("plays", [])}
    readings = [r for r in summary.get("winprobability", []) if r["playId"] in plays]
    if not readings:
        return "Too early to call", "ESPN hasn't published win probability for this game yet."

    # ESPN appends late stat corrections to the end of the list, so the last Reading is not always
    # the latest play; take the latest in game time, and the later one in the list on a tie.
    latest = max(reversed(readings), key=lambda r: game_time(plays[r["playId"]]))
    play = plays[latest["playId"]]
    period = play["period"]["number"]
    left = seconds_left(play["clock"]["displayValue"])
    # The rule applies only from 6:00 left in the 2nd quarter onward.
    if period < 2 or (period == 2 and left > 6 * 60):
        return "Too early to call", "Check back after the middle of the 2nd quarter."

    # Judged on the latest reading alone, so a game that comes back goes from Stay away to Watch again.
    home = latest["homeWinPercentage"]
    opponent = 1 - home if team_home else home
    if opponent > STAY_AWAY_ODDS:
        return "Stay away", "This one looks out of reach."
    return "Watch", "Still a game."


def row(name, game_verdict=None, detail=None, preview=None):
    """One row of the /rows answer for the fan's `name`: a Verdict with its detail, or a `preview`.

    Every field is always present, so a finished game's row has the same shape as a live one's.
    """
    return {"team": name, "verdict": game_verdict, "detail": detail, "next_game": preview}


def verdict_row(name, abbreviation, event, get):
    """One row for `abbreviation`'s started game `event`, labelled with the name the fan gave as `name`."""
    game_verdict, detail = verdict(get(f"{ESPN}/summary?event={event['id']}"), abbreviation)
    return row(name, game_verdict=game_verdict, detail=detail)


def schedule_for(abbreviation, get):
    """ESPN's schedule for the team ESPN calls `abbreviation`."""
    return get(f"{ESPN}/teams/{quote(abbreviation.lower(), safe='')}/schedule")


def espn_abbreviations(get):
    """ESPN's abbreviations for the NBA's teams."""
    listing = get(TEAM_LIST)
    return {team["team"]["abbreviation"] for sport in listing["sports"]
            for league in sport["leagues"] for team in league["teams"]}


def espn_abbreviation(name, known):
    """ESPN's abbreviation for the team the fan named `name`, or None when ESPN lists no such team."""
    abbreviation = TEAM_ALIASES.get(name, name)
    return abbreviation if abbreviation in known else None


def unknown_row(name):
    """The row for a name ESPN lists no NBA team by, made without any ESPN request for that name."""
    return row(name, detail=f"ESPN doesn't list an NBA team called {name}.")


def next_game(schedule, today, abbreviation):
    """Return the Next-game preview for `abbreviation`'s team: its first unstarted game, or None."""
    for event in schedule["events"]:
        ours = competitor(event, abbreviation)
        if state(event) != "pre" or ours is None:
            continue
        start = start_time(event)
        day = "Today" if start.date() == today else f"{start:%a, %b} {start.day}"
        opponent = next(side for side in event["competitions"][0]["competitors"] if side is not ours)
        return {"day": day, "time": f"{start:%-I:%M %p}", "opponent": opponent["team"]["displayName"],
                "home": ours["homeAway"] == "home"}
    return None


def judge_team(name, abbreviation, today, today_games, get):
    """The row for the fan's `name`, which ESPN calls `abbreviation`, on the Game day `today`."""
    game = started_game(today_games, abbreviation)
    if game:
        return verdict_row(name, abbreviation, game, get)

    preview = next_game(schedule_for(abbreviation, get), today, abbreviation)
    if preview is None:
        return row(name, detail="No more games scheduled.")
    return row(name, preview=preview)


def judge(teams, today, get):
    """Return one row per team in `teams` for the Game day `today`, in the order given.

    Only a name ESPN's team list holds is judged; any other name gets its own row and no request of its
    own, so one bad spelling cannot hide the other rows. A team with a started game today gets its
    Verdict and detail with next_game None, so a finished game has the same shape as a live one. A team
    without one gets its Next-game preview with verdict and detail None, or, when its schedule has no
    game left, a detail and nothing else.
    """
    known = espn_abbreviations(get)
    abbreviations = [espn_abbreviation(team, known) for team in teams]
    if not any(abbreviations):  # no known team means no game to look up
        return [unknown_row(team) for team in teams]
    scoreboard = get(f"{ESPN}/scoreboard?dates={today:%Y%m%d}")
    today_games = [event for event in scoreboard["events"] if start_time(event).date() == today]
    return [judge_team(team, abbreviation, today, today_games, get) if abbreviation else unknown_row(team)
            for team, abbreviation in zip(teams, abbreviations)]
