"""Fit a small Stern-style win-probability model and compare its Stay away calls to ESPN's.

Usage: python3 docs/research/own_model.py [cache-dir]
The cache dir holds one ESPN summary JSON per game (see docs/research/backtest.py).
Standard library only.

Model: P(home win) = Phi((margin + w*prior*t/2880 + v*poss) / (sigma*sqrt(t))),
where margin is the home lead in points, t is seconds left (regulation plus any
overtime still to play), prior is the home team's expected margin from the
pre-game spread, poss is +1 (home ball), -1 (away ball) or 0 (unknown), and Phi
is the standard normal CDF. The spread and possession terms are ablated away in
variants A and B below. Parameters are picked by grid search on mean log-loss
over the first half of the season and evaluated on the second half.
"""

import glob
import json
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app import TEAM, seconds_left  # noqa: E402

LAST_TWO_MINUTES = 48 * 60 - 120  # game seconds elapsed when 2:00 is left in Q4


def phi(x):
    """Standard normal CDF, via the error function from the standard library."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def last_free_throw(type_text):
    """True if a free-throw play is the last (or only) shot of its trip, else False."""
    match = re.search(r"(\d+)\s+of\s+(\d+)", type_text)
    if not match:
        return None
    return match.group(1) == match.group(2)


def possession_after(plays, idmap):
    """Map play id to which side has the ball after the play (+1 home, -1 away, 0 unknown).

    ESPN publishes no possession flag, so this is a heuristic over play types in
    chronological order: rebounds and steals go to the team credited, turnovers,
    violations and fouls give the ball to the other side (the fouling team is the
    one named on a foul play), a made basket gives the ball to the side that was
    scored on, and only a made last free throw changes possession (a miss leaves
    it for the following rebound play to decide). Period breaks reset to unknown
    because the alternating-possession arrow is not in the feed.
    """
    out = {}
    poss, last_period = 0, None
    for play in plays:
        period = play["period"]["number"]
        if last_period is not None and period != last_period:
            poss = 0
        last_period = period
        text = play["type"]["text"]
        lowered = text.lower()
        side = idmap.get((play.get("team") or {}).get("id"))
        signed = 1 if side == "home" else (-1 if side == "away" else 0)
        if "rebound" in lowered or "steal" in lowered:
            if signed:
                poss = signed
        elif "jumpball" in lowered or "jump ball" in lowered:
            pass  # opening tip names no team id, so keep the previous state
        elif "free throw" in lowered:
            if last_free_throw(text) and "makes" in (play.get("text") or "").lower():
                if signed:
                    poss = -signed
        elif "turnover" in lowered or "violation" in lowered or "foul" in lowered:
            if signed:
                poss = -signed
        elif play.get("scoringPlay") and play.get("scoreValue") in (2, 3):
            if signed:
                poss = -signed
        out[play["id"]] = poss
    return out


def load_games(cache):
    """One dict per game: rows of (elapsed, time left, margin, possession, ESPN prob)."""
    games = []
    for path in sorted(glob.glob(os.path.join(cache, "401*.json"))):
        summary = json.load(open(path))
        competition = summary["header"]["competitions"][0]
        idmap = {c["team"]["id"]: c.get("homeAway") for c in competition["competitors"]}
        mavs_home = any(c.get("homeAway") == "home" and c["team"]["abbreviation"] == TEAM
                        for c in competition["competitors"])
        plays = {play["id"]: play for play in summary.get("plays", [])}
        readings = summary.get("winprobability", [])
        if not readings:
            continue
        prior, has_spread = 0.0, False
        pickcenter = summary.get("pickcenter") or []
        if pickcenter and pickcenter[0].get("spread") is not None:
            # The spread is quoted from the home side (negative means home favored),
            # so the home team's expected margin is its negation.
            prior, has_spread = -float(pickcenter[0]["spread"]), True
        ordered = sorted(summary.get("plays", []),
                         key=lambda p: (int(p.get("sequenceNumber") or 0), p.get("wallclock") or ""))
        after = possession_after(ordered, idmap)
        rows = []
        for reading in readings:
            play = plays.get(reading["playId"])
            if play is None:
                continue
            period, left = play["period"]["number"], seconds_left(play["clock"]["displayValue"])
            if period <= 4:
                elapsed, remaining = (period - 1) * 720 + 720 - left, (4 - period) * 720 + left
            else:
                # Overtime: treat the current period as the last one, since a further
                # overtime is unknowable from the state.
                elapsed, remaining = 2880 + (period - 5) * 300 + 300 - left, left
            rows.append({
                "elapsed": elapsed, "remaining": remaining, "period": period,
                "margin": play["homeScore"] - play["awayScore"],
                "poss": after.get(play["id"], 0), "espn": reading["homeWinPercentage"],
                "window": period > 2 or (period == 2 and left <= 360),
                "seq": play.get("sequenceNumber"), "wallclock": play.get("wallclock") or "",
            })
        # ESPN's arrays are not strictly chronological (corrections land out of order),
        # so sort by sequence number with the wallclock as tiebreak before replaying.
        rows.sort(key=lambda r: (int(r["seq"] or 0), r["wallclock"]))
        competitors = {c["team"]["abbreviation"]: c for c in competition["competitors"]}
        mavs = competitors[TEAM]
        other = next(c for abbr, c in competitors.items() if abbr != TEAM)
        games.append({"file": path, "date": competition.get("date", "")[:10],
                      "mavs_home": mavs_home, "prior": prior, "has_spread": has_spread,
                      "opp": other["team"]["abbreviation"],
                      "dal_margin": int(mavs["score"]) - int(other["score"]), "rows": rows})
    return games


def model_home(margin, remaining, prior, poss, sigma, spread_weight, poss_value):
    """Home win probability under the Stern-style probit model."""
    elapsed_floor = max(remaining, 1.0)
    numerator = margin + spread_weight * prior * (elapsed_floor / 2880.0) + poss_value * poss
    return phi(numerator / (sigma * math.sqrt(elapsed_floor)))


def mean_logloss(games, sigma, spread_weight, poss_value):
    total, count = 0.0, 0
    for game in games:
        for row in game["rows"]:
            if not row["window"]:
                continue
            prob = model_home(row["margin"], row["remaining"], game["prior"], row["poss"],
                              sigma, spread_weight, poss_value)
            prob = min(max(prob, 1e-6), 1 - 1e-6)
            espn = row["espn"]
            total += -(espn * math.log(prob) + (1 - espn) * math.log(1 - prob))
            count += 1
    return total / count


def mean_abs_error(games, sigma, spread_weight, poss_value, window_only=True):
    total, count = 0.0, 0
    for game in games:
        for row in game["rows"]:
            if window_only and not row["window"]:
                continue
            total += abs(model_home(row["margin"], row["remaining"], game["prior"], row["poss"],
                                    sigma, spread_weight, poss_value) - row["espn"])
            count += 1
    return total / count


def first_stayaway(games, home_prob, line=0.95):
    """First Stay away time (game seconds elapsed) per game, before the last 2:00."""
    firsts = {}
    for game in games:
        first = None
        for row in game["rows"]:
            if not row["window"] or row["elapsed"] > LAST_TWO_MINUTES:
                continue
            home = home_prob(game, row)
            opponent = 1 - home if game["mavs_home"] else home
            if opponent > line and first is None:
                first = row["elapsed"]
        firsts[game["file"]] = first
    return firsts


def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bgw-season-2026"
    games = load_games(cache)
    print(f"{len(games)} games, {sum(g['dal_margin'] > 0 for g in games)} wins, "
          f"{sum(g['has_spread'] for g in games)} with a pre-game spread")
    half = len(games) // 2
    fit, test = games[:half], games[half:]

    sigmas = [0.28, 0.30, 0.32, 0.33, 0.34, 0.36, 0.38]
    weights = [0.5, 0.75, 1.0]
    values = [0.0, 0.25, 0.5]
    variants = {"A margin+time": ([0.0], [0.0]),
                "B +spread": (weights, [0.0]),
                "C +spread+possession": (weights, values)}
    params = {}
    for name, (weight_grid, value_grid) in variants.items():
        best = None
        for sigma in sigmas:
            for weight in weight_grid:
                for value in value_grid:
                    loss = mean_logloss(fit, sigma, weight, value)
                    if best is None or loss < best[0]:
                        best = (loss, sigma, weight, value)
        params[name] = best[1:]
        _, sigma, weight, value = best
        print(f"{name}: fit log-loss {best[0]:.4f} at sigma={sigma} spread weight={weight} "
              f"possession={value}; test MAE {mean_abs_error(test, sigma, weight, value):.4f}")

    # Honest split-half Stay away agreement with the fit-half params of the full model.
    sigma, weight, value = params["C +spread+possession"]
    espn_first = first_stayaway(test, lambda game, row: row["espn"])
    model_first = first_stayaway(
        test, lambda game, row: model_home(row["margin"], row["remaining"], game["prior"],
                                           row["poss"], sigma, weight, value))
    espn_fires = {k for k, v in espn_first.items() if v is not None}
    model_fires = {k for k, v in model_first.items() if v is not None}
    by_file = {game["file"]: game for game in test}
    print(f"test half: ESPN Stay away in {len(espn_fires)}, model in {len(model_fires)}, "
          f"ESPN-only {len(espn_fires - model_fires)}, model-only {len(model_fires - espn_fires)}")
    for path in sorted(espn_fires - model_fires):
        game = by_file[path]
        print(f"  ESPN-only {game['date']} vs {game['opp']} (DAL {game['dal_margin']:+d}): "
              f"ESPN first {(2880 - espn_first[path]) / 60:.1f} min left")
    for path in sorted(model_fires - espn_fires):
        game = by_file[path]
        print(f"  model-only {game['date']} vs {game['opp']} (DAL {game['dal_margin']:+d}): "
              f"model first {(2880 - model_first[path]) / 60:.1f} min left")
    lags = sorted((model_first[k] - espn_first[k]) / 60 for k in espn_fires & model_fires)
    if lags:
        print(f"first-call lag model minus ESPN (min): median {statistics.median(lags):+.1f}, "
              f"mean {statistics.mean(lags):+.1f}, worst {max(lags, key=abs):+.1f}")


if __name__ == "__main__":
    main()
