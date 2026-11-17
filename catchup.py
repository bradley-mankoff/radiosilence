"""Catch-up: the score, box score and plays as of the moment a fan has reached.

catch_up() takes a game's saved ESPN summary and the moment the fan names — a period, and the minutes
and seconds on its clock — and returns the rows the phone shows: the score, each team's totals, each
player's line and the plays up to that moment. Everything is rebuilt by replaying the saved play-by-
play in game time, so no play later than the moment is counted or sent. Periods are "1st" to "4th", where
the clock is the time left in the period, or "OT", where the minutes count overtime played since the
end of regulation (each overtime is five minutes, so 9 minutes is four minutes into the second
overtime). A moment past the latest play gives the whole game, shaped exactly like any other answer:
the answer never says whether the game is over or whether it had overtime.
"""

import collections

from judging import elapsed

QUARTERS = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
QUARTER_SECONDS = 12 * 60
REGULATION_SECONDS = 4 * QUARTER_SECONDS
MAX_OVERTIME_MINUTES = 50

# Every line the answer sends, for a team and for a player alike.
LINE = ("points", "field_goals_made", "field_goals_attempted",
        "threes_made", "threes_attempted",
        "free_throws_made", "free_throws_attempted",
        "rebounds", "assists", "steals", "blocks", "turnovers", "fouls")


def moment_seconds(period, minutes, seconds):
    """Seconds played when the fan's moment arrived.

    A quarter's clock counts down from 12:00, so 10:00 left in the 2nd is 720 + 120 seconds played.
    OT counts up from the end of regulation, each overtime five minutes, so 9:00 is 2880 + 540.
    """
    if period in QUARTERS:
        if not 0 <= seconds <= 59 or not 0 <= minutes * 60 + seconds <= QUARTER_SECONDS:
            raise ValueError(f"A quarter's clock runs from 12:00 down to 0:00, not {minutes}:{seconds:02d}.")
        left = minutes * 60 + seconds
        return (QUARTERS[period] - 1) * QUARTER_SECONDS + QUARTER_SECONDS - left
    if period == "OT":
        if not 0 <= minutes <= MAX_OVERTIME_MINUTES or not 0 <= seconds <= 59:
            raise ValueError(f"Overtime runs from 0 to {MAX_OVERTIME_MINUTES} minutes, "
                             f"not {minutes}:{seconds:02d}.")
        return REGULATION_SECONDS + minutes * 60 + seconds
    raise ValueError(f"No period called {period}.")


def first_player(participants):
    """The player ESPN names first in a play: the shooter, rebounder or player who lost the ball, or None."""
    return participants[0] if participants else None


def second_player(participants):
    """The player ESPN names second in a play: the assister, blocker or stealer, or None."""
    return participants[1] if len(participants) > 1 else None


def count_play(play, player_lines):
    """Add one play's stats to its players' lines, where ESPN names them.

    ESPN puts the shooter first on a shot and the blocker second, and the player who lost the ball first
    on a turnover and the player who stole it second. Free throws and rebounds name one player. A team
    rebound or a team turnover names no player, so it adds to no line: the team totals are the sum of
    its players' lines, as ESPN's own team stats are.
    """
    type_text = play["type"]["text"]
    short = play.get("shortDescription", "")
    participants = [athlete["athlete"]["id"] for athlete in play.get("participants", [])]
    text = play.get("text", "").lower()
    scoring = play.get("scoringPlay", False)
    points = play.get("scoreValue", 0) if scoring else 0

    def record(stats, player_id=None):
        if player_id in player_lines:
            player_lines[player_id].update(stats)

    if "Free Throw" in type_text:
        stats = {"free_throws_attempted": 1}
        if scoring:
            stats.update(free_throws_made=1, points=points)
        record(stats, first_player(participants))
    elif play.get("shootingPlay"):
        three = play.get("pointsAttempted") == 3
        stats = {}
        # ESPN leaves a missed heave out of its own box score, but a made one is a shot it counts.
        if "Heave" not in type_text or scoring:
            stats["field_goals_attempted"] = 1
            if three:
                stats["threes_attempted"] = 1
        if scoring:
            stats.update(field_goals_made=1, points=points)
            if three:
                stats["threes_made"] = 1
            record(stats, first_player(participants))
            if "assist" in text:
                record({"assists": 1}, second_player(participants))
        else:
            record(stats, first_player(participants))
            if "block" in text:
                record({"blocks": 1}, second_player(participants))
    elif "Rebound" in type_text:
        record({"rebounds": 1}, first_player(participants))
    elif short == "Turnover":
        record({"turnovers": 1}, first_player(participants))
        if "steal" in text:
            record({"steals": 1}, second_player(participants))
    elif short == "Foul" and "Technical" not in type_text:
        for player_id in participants:  # a double personal foul charges both players
            record({"fouls": 1}, player_id)


def roster(summary):
    """The teams and players the answer names, and each team's ESPN id as its abbreviation.

    A row holds only what the summary's boxscore says a team and a player are called, and which team a
    player plays for: no line comes with it, so only the plays can add to one. Teams run home first, a
    player without an id is left out, and ESPN's stat values are never read.
    """
    teams = summary["boxscore"]["players"]
    home = {competitor["team"]["id"]: competitor["homeAway"] == "home"
            for competitor in summary["header"]["competitions"][0]["competitors"]}
    team_rows, player_rows = [], []
    for entry in sorted(teams, key=lambda entry: 0 if home.get(entry["team"]["id"]) else 1):
        team = entry["team"]
        team_rows.append({"team": team["abbreviation"], "name": team["displayName"],
                          "home": home.get(team["id"], False)})
        for athlete in entry["statistics"][0]["athletes"]:
            player = athlete.get("athlete", {})
            if "id" not in player:
                continue
            player_rows.append({"id": player["id"], "name": player["displayName"],
                                "team": team["abbreviation"]})
    team_ids = {entry["team"]["id"]: entry["team"]["abbreviation"] for entry in teams}
    return team_rows, player_rows, team_ids


def stat_line(line):
    """One line's stats, every field present, so a team row and a player row have the same shape."""
    return {field: line[field] for field in LINE}


def answer_play(play, team):
    """One play as the phone gets it: ESPN's own period, clock and text, and the team that made it."""
    return {"id": play.get("id"),
            "period": play.get("period", {}).get("displayValue"),
            "clock": play.get("clock", {}).get("displayValue"),
            "team": team,
            "text": play.get("text", "")}


def catch_up(summary, period, minutes, seconds):
    """The score, team totals, player lines and plays at the fan's moment in `summary`.

    The moment is a period ("1st" to "4th" or "OT") and its minutes and seconds, where a quarter's clock
    is the time left and OT counts overtime played. Plays are replayed in game time, keeping ESPN's list
    order for two plays at the same moment, because ESPN appends late corrections at the end. Each
    team's totals are the sum of its players' lines, so the box score adds up. The play list runs newest
    first. A moment past the latest play returns the whole game, and an answer never carries a game-over
    or overtime flag.
    """
    moment = moment_seconds(period, minutes, seconds)
    team_rows, player_rows, team_ids = roster(summary)
    player_lines = {row["id"]: collections.Counter() for row in player_rows}
    timed = [(elapsed(play), index, play) for index, play in enumerate(summary.get("plays", []))]
    included = sorted((entry for entry in timed if entry[0] <= moment),
                      key=lambda entry: (entry[0], entry[1]))
    for _, _, play in included:
        count_play(play, player_lines)
    team_lines = {row["team"]: collections.Counter() for row in team_rows}
    for row in player_rows:
        team_lines[row["team"]].update(player_lines[row["id"]])

    score = {"home": 0, "away": 0}
    teams = []
    for row in team_rows:
        stats = stat_line(team_lines[row["team"]])
        teams.append({"team": row["team"], "name": row["name"], "home": row["home"], **stats})
        if row["home"]:
            score["home"] = stats["points"]
        else:
            score["away"] = stats["points"]
    players = [{"id": row["id"], "name": row["name"], "team": row["team"],
                **stat_line(player_lines[row["id"]])}
               for row in player_rows]
    newest_first = sorted(included, key=lambda entry: (-entry[0], entry[1]))
    plays = [answer_play(play, team_ids.get((play.get("team") or {}).get("id")))
             for _, _, play in newest_first]
    return {"score": score, "teams": teams, "players": players, "plays": plays}
