"""Replay the Stay away rule over a past Mavericks season, to compare lines and see how often the verdict flickers.

Usage: python3 docs/research/backtest.py [season] [cache folder]
The season is ESPN's ending year (2026 means 2025-26). Summaries are cached in the folder,
so a second run makes no requests. Prints one line per line tried; see backtest-2025-26.md.
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app import ESPN, TEAM, seconds_left  # noqa: E402

LAST_TWO_MINUTES = 48 * 60 - 120  # game seconds elapsed when 2:00 is left in the 4th


def cached(url, path):
    if not os.path.exists(path):
        with urllib.request.urlopen(url, timeout=20) as response, open(path, "wb") as out:
            out.write(response.read())
    return json.load(open(path))


def readings(summary):
    """(seconds elapsed, opponent win probability, inside the judging window) for each reading, in game-time order.

    ESPN appends late stat corrections to the end of its list, so the list is sorted by game time,
    keeping ESPN's order on ties, as app.py's verdict() does when it picks the latest Reading.
    """
    competitors = summary["header"]["competitions"][0]["competitors"]
    mavs_home = any(c["homeAway"] == "home" and c["team"]["abbreviation"] == TEAM for c in competitors)
    plays = {play["id"]: play for play in summary.get("plays", [])}
    out = []
    for reading in summary.get("winprobability", []):
        play = plays.get(reading["playId"])
        if play is None:
            continue
        period, left = play["period"]["number"], seconds_left(play["clock"]["displayValue"])
        elapsed = (period - 1) * 720 + 720 - left if period <= 4 else 2880 + (period - 5) * 300 + 300 - left
        home = reading["homeWinPercentage"]
        out.append((elapsed, 1 - home if mavs_home else home, period > 2 or (period == 2 and left <= 360)))
    return sorted(out, key=lambda row: row[0])


def replay(rows, line, band=0.0):
    """First Stay away (seconds elapsed, or None) and flips back to Watch, before the last 2:00 of regulation.

    With a band, a Stay away game returns to Watch only once the opponent is at or below line - band.
    """
    verdict, first, flips = None, None, 0
    for elapsed, opponent, in_window in rows:
        if not in_window or elapsed > LAST_TWO_MINUTES:
            continue
        stay = opponent > (line - band if verdict == "stay" else line)
        if stay and first is None:
            first = elapsed
        if verdict == "stay" and not stay:
            flips += 1
        verdict = "stay" if stay else "watch"
    return first, flips


def main():
    season = sys.argv[1] if len(sys.argv) > 1 else "2026"
    cache = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/bgw-season-{season}"
    os.makedirs(cache, exist_ok=True)
    schedule = cached(f"{ESPN}/teams/{TEAM.lower()}/schedule?season={season}&seasontype=2", f"{cache}/schedule.json")
    games = []
    for event in schedule["events"]:
        if event["competitions"][0]["status"]["type"]["state"] != "post":
            continue
        summary = cached(f"{ESPN}/summary?event={event['id']}", f"{cache}/{event['id']}.json")
        competitors = {c["homeAway"]: c for c in summary["header"]["competitions"][0]["competitors"]}
        mavs = next(c for c in competitors.values() if c["team"]["abbreviation"] == TEAM)
        other = next(c for c in competitors.values() if c is not mavs)
        rows = readings(summary)
        if rows:
            games.append((event["date"][:10], other["team"]["abbreviation"],
                          int(mavs["score"]) - int(other["score"]), rows))
    print(f"{len(games)} games, {sum(margin > 0 for _, _, margin, _ in games)} wins")
    for line in (0.90, 0.93, 0.95, 0.97, 0.99):
        fired = [(g, replay(g[3], line)) for g in games if replay(g[3], line)[0] is not None]
        wrong = [g[:3] for g, _ in fired if g[2] > 0 or abs(g[2]) <= 5]
        left = sorted((2880 - first) / 60 for g, (first, _) in fired if g[:3] not in wrong)
        flips = sum(replay(g[3], line)[1] for g in games)
        banded = sum(replay(g[3], line, 0.03)[1] for g in games)
        print(f"line {line:.2f}: Stay away before the last 2:00 in {len(fired)} games; won or lost by 5 or fewer: "
              f"{len(wrong)} {wrong}; median minutes left at first Stay away in real blowouts "
              f"{left[len(left) // 2]:.1f}; flips back to Watch {flips} (with a 3-point band {banded})")


if __name__ == "__main__":
    main()
