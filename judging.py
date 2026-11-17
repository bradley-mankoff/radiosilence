"""Judging: one row per followed NBA team for the Game day, worked out from ESPN's public JSON.

judge() takes `get`, a function that returns ESPN's JSON for a URL and raises when ESPN cannot be
reached, and the fan's Presets, AND or OR and slider values. The server passes a cached fetch and the
tests pass saved responses, so this file never touches the network or the clock. Each Preset's rule
returns fits, doesn't fit or not yet; combine() folds those answers into the row's Verdict.
"""

from datetime import datetime
from urllib.parse import quote

from presets import Settings

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
TEAM_LIST = f"{ESPN}/teams"  # every NBA team, with the abbreviation ESPN uses for it

# Each Preset returns one of these, and combine() turns the picked Presets' answers into a Verdict.
FITS, DOESNT_FIT, NOT_YET = "fits", "doesn't fit", "not yet"
VERDICTS = {FITS: ("Watch", "Still a game."),
            DOESNT_FIT: ("Stay away", "This one looks out of reach."),
            NOT_YET: ("Too early to call", "Check back later.")}

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


def elapsed(play):
    """Seconds played when `play` happened, counting overtime after the 4th quarter's 48 minutes."""
    period = play["period"]["number"]
    left = seconds_left(play["clock"]["displayValue"])
    if period <= 4:
        return (period - 1) * 720 + 720 - left
    return 2880 + (period - 5) * 300 + 300 - left


def readings(summary):
    """(seconds played, Reading) for every Reading ESPN also sent a play for, in game time.

    ESPN appends late stat corrections to the end of the list, so the list order is not game order; a
    stable sort keeps ESPN's order for two Readings at the same moment.
    """
    plays = {play["id"]: play for play in summary.get("plays", [])}
    sent = [(elapsed(plays[reading["playId"]]), reading) for reading in summary.get("winprobability", [])
            if reading["playId"] in plays]
    return sorted(sent, key=lambda pair: pair[0])


def opponent_chance(reading, team_is_home):
    """The chance ESPN gives the team that is not the fan's, as a fraction."""
    home = reading["homeWinPercentage"]
    return 1 - home if team_is_home else home


def wins_for_my_team(summary, abbreviation, fan):
    """Not yet until the game is final, then fits only if the fan's team won."""
    header = summary["header"]
    if state(header) != "post":
        return NOT_YET
    team = competitor(header, abbreviation)
    opponent = next(side for side in header["competitions"][0]["competitors"] if side is not team)
    return FITS if int(team["score"]) > int(opponent["score"]) else DOESNT_FIT


def no_blowout_losses(summary, abbreviation, fan):
    """Walk the Readings from Judge from to Freeze at, staying away in the band and freezing after it."""
    team_is_home = competitor(summary["header"], abbreviation)["homeAway"] == "home"
    upper, lower = fan.value("blow_upper") / 100, fan.value("blow_lower") / 100
    judge_from, freeze_at = fan.value("judge_from"), fan.value("freeze_at")
    result = NOT_YET
    for moment, reading in readings(summary):
        if moment < judge_from:
            continue
        if moment > freeze_at:
            break
        opponent = opponent_chance(reading, team_is_home)
        if result == DOESNT_FIT:
            if opponent < lower:  # back to fits only below the lower line
                result = FITS
        elif opponent > upper:  # exactly the upper line is not over it
            result = DOESNT_FIT
        else:
            result = FITS
    return result


PRESET_RESULTS = {"wins": wins_for_my_team, "blow": no_blowout_losses}


def combine(results, join):
    """Three-valued combination of the picked Presets' answers, as the fan chose AND or OR."""
    if join == "AND":
        if DOESNT_FIT in results:
            return DOESNT_FIT
        return FITS if results and all(result == FITS for result in results) else NOT_YET
    if FITS in results:
        return FITS
    return DOESNT_FIT if results and all(result == DOESNT_FIT for result in results) else NOT_YET


def verdict(summary, abbreviation, fan):
    """Return (verdict, detail) for the team ESPN calls `abbreviation`, from a summary and the fan's Presets."""
    if not fan.presets:
        return None, "Pick a Preset to judge this game."
    results = [PRESET_RESULTS[preset.key](summary, abbreviation, fan) for preset in fan.presets]
    return VERDICTS[combine(results, fan.join)]


def row(name, game_verdict=None, detail=None, preview=None):
    """One row of the /rows answer for the fan's `name`: a Verdict with its detail, or a `preview`.

    Every field is always present, so a finished game's row has the same shape as a live one's.
    """
    return {"team": name, "verdict": game_verdict, "detail": detail, "next_game": preview}


def verdict_row(name, abbreviation, event, get, fan):
    """One row for `abbreviation`'s started game `event`, labelled with the name the fan gave as `name`."""
    game_verdict, detail = verdict(get(f"{ESPN}/summary?event={event['id']}"), abbreviation, fan)
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


def judge_team(name, abbreviation, today, today_games, get, fan):
    """The row for the fan's `name`, which ESPN calls `abbreviation`, on the Game day `today`."""
    game = started_game(today_games, abbreviation)
    if game:
        return verdict_row(name, abbreviation, game, get, fan)

    preview = next_game(schedule_for(abbreviation, get), today, abbreviation)
    if preview is None:
        return row(name, detail="No more games scheduled.")
    return row(name, preview=preview)


def judge(teams, today, get, fan=None):
    """Return one row per team in `teams` for the Game day `today`, in the order given.

    `fan` is the fan's Presets, AND or OR and slider values; a request that names none gets a row that
    says a Preset is needed. Only a name ESPN's team list holds is judged; any other name gets its own
    row and no request of its own, so one bad spelling cannot hide the other rows. A team with a started
    game today gets its Verdict and detail with next_game None, so a finished game has the same shape as
    a live one. A team without one gets its Next-game preview with verdict and detail None, or, when its
    schedule has no game left, a detail and nothing else.
    """
    fan = fan or Settings()
    known = espn_abbreviations(get)
    abbreviations = [espn_abbreviation(team, known) for team in teams]
    if not any(abbreviations):  # no known team means no game to look up
        return [unknown_row(team) for team in teams]
    scoreboard = get(f"{ESPN}/scoreboard?dates={today:%Y%m%d}")
    today_games = [event for event in scoreboard["events"] if start_time(event).date() == today]
    return [judge_team(team, abbreviation, today, today_games, get, fan) if abbreviation else unknown_row(team)
            for team, abbreviation in zip(teams, abbreviations)]
