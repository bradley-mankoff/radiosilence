"""Tracked players: one row per player a fan follows, judged from the saved game and their usual minutes.

A fan's request names tracked players as `players=<ESPN id>:<team>:<name>`, repeated or comma-joined, and
one set of checks for all of them. A check is a number to reach in points, rebounds, assists, threes made,
steals or blocks (`player_points=30`, `player_rebounds=10`, ...), or a double-double or triple-double
tick (`double_double=1`, `triple_double=1`). The checks combine with the request's `join`, AND or OR, the
same way Presets do. Every check is fits, doesn't fit or not yet, and no row says which check fitted.

During a game each number projects as so far times the player's usual minutes divided by the minutes
played so far, from 6 minutes played; under 6 the row is Too early to call. A number already reached is
met for good, and on track when the projection reaches it. A double-double counts stats reaching 10 among
points, rebounds, assists, steals and blocks, using the same projection; a triple-double needs three. After
the final only what was reached counts, so a great projection cannot turn a short night into a Watch. A
player who did not play — the game is final and no play names him and he has no minutes — gets a row that
says Did not play and carries no Verdict.

Usual minutes are ESPN's season average minutes from the athlete overview, falling back to last season's
average when this season has fewer than 5 games. The server caches each player's answer for a day, so a
player's average is fetched once a day. Stats and minutes so far come from catchup.catch_up's replay, so a
player's row and the catch-up view read the same game the same way.
"""

from collections import namedtuple

import judging
from catchup import MAX_OVERTIME_MINUTES, OVERTIME, catch_up
from presets import JOIN, JOINS

MINIMUM_MINUTES = 6  # a player is Too early to call until he has played this many minutes
MINIMUM_GAMES = 5  # this season's average needs this many games; before it, last season's average
DOUBLE_DOUBLE = 10  # one leg of a double-double: a counting stat reaching this many
COUNTING = ("points", "rebounds", "assists", "steals", "blocks")
# The moment past the last play of any game, so the replay counts the whole game: catch-up's overtime runs
# to MAX_OVERTIME_MINUTES, and no game plays a second past its last minute.
WHOLE_GAME = (OVERTIME, MAX_OVERTIME_MINUTES, 59)
DID_NOT_PLAY = "Did not play"
NO_CHECKS = "Pick a number to reach."
COULDNT_REACH = "Couldn't reach ESPN."
# ESPN's answer for one player can fail on its own: unreachable, bad JSON, or a shape this code cannot read.
BAD_ANSWER = (OSError, ValueError, LookupError, TypeError, AttributeError)
TARGETS = (("player_points", "points"), ("player_rebounds", "rebounds"),
           ("player_assists", "assists"), ("player_threes", "threes_made"),
           ("player_steals", "steals"), ("player_blocks", "blocks"))
STATS = tuple(stat for _, stat in TARGETS)
ATHLETES = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes"

TrackedPlayer = namedtuple("TrackedPlayer", "id team name")


def _valid_targets(targets):
    """The targets worth judging by: a stat this file counts and a whole number above zero.

    A request names a target as text, so a box the fan left empty arrives as no number at all and drops out
    instead of failing the request, and a target of zero asks a player to reach nothing.
    """
    for stat, value in (targets or {}).items():
        try:
            target = int(value)
        except (TypeError, ValueError):
            continue
        if stat in STATS and target > 0:
            yield stat, target


class Checks:
    """One set of checks every tracked player is judged by: targets by stat, the two double checks, join."""

    def __init__(self, targets=None, double_double=False, triple_double=False, join=JOIN):
        self.targets = dict(_valid_targets(targets))
        self.double_double = bool(double_double)
        self.triple_double = bool(triple_double)
        self.join = join if join in JOINS else JOIN

    def __bool__(self):
        return bool(self.targets or self.double_double or self.triple_double)


def _last(params, name, default=""):
    """The last value the request gave `name`, so a repeated parameter reads as the phone's latest."""
    return (params.get(name) or [default])[-1]


def _ticked(value):
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def checks_from_query(params):
    """The one set of checks a request names, with the shipped OR when it names no join."""
    targets = {stat: _last(params, parameter) for parameter, stat in TARGETS}
    return Checks(targets, _ticked(_last(params, "double_double")),
                  _ticked(_last(params, "triple_double")), _last(params, "join").upper())


def tracked_players(params):
    """The tracked players a request names, each written `id:team:name`, in the order given."""
    found = {}
    for value in params.get("players", []):
        for token in value.split(","):
            fields = token.split(":", 2)
            if len(fields) == 3 and all(fields):
                found.setdefault(fields[0], TrackedPlayer(*fields))
    return list(found.values())


class Projection:
    """How a player's night is judged, from his line so far, his usual minutes and whether the game is final.

    A number already reached is met for good. Before the final a number is on track when so far times the
    player's usual minutes divided by his minutes played reaches the target; after the final only what was
    reached counts, so a great projection cannot turn a short night into a Watch. A live line has at least
    MINIMUM_MINUTES played, so the share always divides by a real minute.
    """

    def __init__(self, line, usual_minutes, final):
        self.line = line
        self.minutes = line["minutes"]
        self.usual_minutes = usual_minutes
        self.final = final

    def reaches(self, stat, target):
        """Fits when the stat is reached, or its projection reaches the target; after the final, only what
        was reached counts."""
        so_far = self.line[stat]
        if so_far >= target:
            return judging.FITS
        if self.final:
            return judging.DOESNT_FIT
        return judging.FITS if so_far * self.usual_minutes / self.minutes >= target else judging.DOESNT_FIT

    def double_double(self):
        """Fits when two of the five counting stats reach 10, reached for good or projected."""
        return self._counting_stats_reaching(2)

    def triple_double(self):
        """Fits when three of the five counting stats reach 10, reached for good or projected."""
        return self._counting_stats_reaching(3)

    def _counting_stats_reaching(self, needed):
        reached = sum(self.reaches(stat, DOUBLE_DOUBLE) == judging.FITS for stat in COUNTING)
        return judging.FITS if reached >= needed else judging.DOESNT_FIT


def _has_played(summary, player_id):
    """Whether any saved play names the player, which a Did not play answer needs to be false."""
    return any(athlete["athlete"]["id"] == player_id
               for play in summary.get("plays", [])
               for athlete in play.get("participants", []))


def player_verdict(summary, player_id, checks, usual_minutes):
    """Return (verdict, detail) for a tracked player in `summary`, with the player's usual minutes.

    The row is Too early to call under 6 minutes or before the player has entered. A final game judges by
    what the player reached, not by a projection, and a player no play names and no minute counts reads
    Did not play with no Verdict.
    """
    if not checks:
        return None, NO_CHECKS
    final = judging.state(summary["header"]) == "post"
    answer = catch_up(summary, *WHOLE_GAME)
    player = next((line for line in answer["players"] if line["id"] == player_id), None)
    if final and (player is None or (player["minutes"] == 0
                                     and not _has_played(summary, player_id))):
        return None, DID_NOT_PLAY
    if player is None:
        return judging.VERDICTS[judging.NOT_YET]
    if not final and player["minutes"] < MINIMUM_MINUTES:
        return judging.VERDICTS[judging.NOT_YET]
    night = Projection(player, usual_minutes, final)
    results = [night.reaches(stat, target) for stat, target in checks.targets.items()]
    if checks.double_double:
        results.append(night.double_double())
    if checks.triple_double:
        results.append(night.triple_double())
    return judging.VERDICTS[judging.combine(results, checks.join)]


def _regular_season(overview):
    """(games played, minutes per game) from an athlete overview, or None when ESPN lists no season."""
    statistics = overview.get("statistics") or {}
    labels = statistics.get("labels") or []
    for split in statistics.get("splits") or []:
        if split.get("displayName") != "Regular Season":
            continue
        values = dict(zip(labels, split.get("stats") or []))
        try:
            return int(values["GP"]), float(values["MIN"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _season_averages(stats):
    """[(season year, games, minutes per game)] from ESPN's career averages, oldest first.

    A player traded mid-season has one row per team for the same season, so a season's games are added
    and its minutes are weighted by those games. A stats answer with no averages category lists no
    seasons, so a player whose answer is missing or odd falls back rather than breaking the row.
    """
    category = next((category for category in stats.get("categories") or []
                     if category.get("name") == "averages"), None)
    if category is None:
        return []
    labels = category.get("labels") or []
    by_season = {}
    for row in category.get("statistics") or []:
        values = dict(zip(labels, row.get("stats") or []))
        try:
            games, minutes = int(values["GP"]), float(values["MIN"])
            year = row["season"]["year"]
        except (KeyError, TypeError, ValueError):
            continue
        if games <= 0:
            continue
        total_games, weighted_minutes = by_season.get(year, (0, 0.0))
        by_season[year] = (total_games + games, weighted_minutes + games * minutes)
    return [(year, games, weighted / games) for year, (games, weighted) in sorted(by_season.items())]


def _season_year(day):
    """The year ESPN labels a season with: the year it ends, so a date from July on is next year's season."""
    return day.year + 1 if day.month >= 7 else day.year


def _last_season_minutes(stats, season_year):
    """Minutes per game in the last season played before `season_year`, or None when ESPN lists none.

    The season is picked by its year rather than by its place in the list: a player with no games this
    season has no row for it, and an earlier row is not last season.
    """
    earlier = [season for season in _season_averages(stats) if season[0] < season_year]
    return earlier[-1][2] if earlier else None


def _usual_minutes(player_id, get, day):
    """The player's usual minutes: this season's average, or last season's with fewer than 5 games.

    The overview carries only this season's and the career split, so last season's average comes from
    ESPN's season averages, which list a row, or one row per team, for every season the player has played.
    A player ESPN lists no season for has no games this season, so last season's average decides.
    """
    season = _regular_season(get(f"{ATHLETES}/{player_id}/overview"))
    games, minutes = season if season is not None else (0, 0.0)
    if games >= MINIMUM_GAMES:
        return minutes
    return _last_season_minutes(get(f"{ATHLETES}/{player_id}/stats"), _season_year(day)) or minutes


def is_average_url(url):
    """Whether `url` is one of ESPN's per-player average answers, which the server keeps for a day."""
    return url.startswith(f"{ATHLETES}/") and (url.endswith("/overview") or url.endswith("/stats"))


def _player_row(player, verdict=None, detail=None, preview=None):
    """One row of the /rows answer for a tracked player: a team's row plus the player's name."""
    return {**judging.row(player.team, verdict, detail, preview), "player": player.name}


def _unknown_player_row(player):
    """The row for a player whose team ESPN lists no NBA team by, made without a game request."""
    return {**judging.unknown_row(player.team), "player": player.name}


def _judge_player(player, abbreviation, today, today_games, get, checks):
    """The row for one tracked player whose team ESPN calls `abbreviation`, on the Game day `today`.

    A player's own athlete answer failing — unreachable ESPN, bad JSON, or an answer this code cannot read
    — stays in his row as a note, so the other players' and teams' rows still judge.
    """
    try:
        game = judging.started_game(today_games, abbreviation)
        if game:
            summary = get(f"{judging.ESPN}/summary?event={game['id']}")
            game_verdict, detail = player_verdict(summary, player.id, checks,
                                                  _usual_minutes(player.id, get, today))
            return _player_row(player, verdict=game_verdict, detail=detail)
        preview = judging.next_game(judging.schedule_for(abbreviation, get), today, abbreviation)
        if preview is None:
            return _player_row(player, detail="No more games scheduled.")
        return _player_row(player, preview=preview)
    except BAD_ANSWER:
        return _player_row(player, detail=COULDNT_REACH)


def judge(tracked, today, get, checks):
    """One row per tracked player in `tracked` for the Game day `today`, in the order given.

    Only a player whose team ESPN lists is judged; any other team gets its own row and no game request, so
    one bad pick cannot hide the other rows. A failed answer for one player stays in his row for the same
    reason. A team with a started game today gets the player's Verdict, and a team without one gets the
    Next-game preview, as a team's row does.
    """
    if not tracked:
        return []
    known = judging.espn_abbreviations(get)
    abbreviations = [judging.espn_abbreviation(player.team, known) for player in tracked]
    if not any(abbreviations):
        return [_unknown_player_row(player) for player in tracked]
    scoreboard = get(f"{judging.ESPN}/scoreboard?dates={today:%Y%m%d}")
    today_games = [event for event in scoreboard["events"] if judging.start_time(event).date() == today]
    return [_judge_player(player, abbreviation, today, today_games, get, checks)
            if abbreviation else _unknown_player_row(player)
            for player, abbreviation in zip(tracked, abbreviations)]
