"""Replay the Boss's close-game rule (2026-11-14) over a cached season of Mavericks summaries.

A close ending: within 5 points at some moment in the last 5:00 of the 4th, or overtime.
Close along the way: within 9 points for more than 66% of game time.
Usage: python3 docs/research/close_rule.py [cache folder], after backtest.py has filled the cache.
"""
import glob, json, sys

def elapsed(play):
    n = play["period"]["number"]; clock = play["clock"]["displayValue"]
    m, s = clock.split(":") if ":" in clock else ("0", clock)
    left = int(m) * 60 + float(s)
    return (n - 1) * 720 + 720 - left if n <= 4 else 2880 + (n - 5) * 300 + 300 - left

def margins(summary):
    """(seconds elapsed, home lead) after each play, in game-time order, starting 0-0 at tip-off."""
    plays = sorted(enumerate(summary["plays"]), key=lambda ip: (elapsed(ip[1]), ip[0]))
    return [(0, 0)] + [(elapsed(p), int(p["homeScore"]) - int(p["awayScore"])) for _, p in plays]

def judge(summary, ending_points=5, along_points=9, along_share=0.66):
    rows = margins(summary)
    end = rows[-1][0]
    overtime = end > 2880
    ending = overtime or any(abs(lead) <= ending_points for t, lead in rows if 2880 - 300 <= t <= 2880)
    close_time = sum(t2 - t1 for (t1, lead), (t2, _) in zip(rows, rows[1:]) if abs(lead) <= along_points)
    return ending, close_time / end > along_share, close_time / end

def main():
    cache = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bgw-season-2026"
    out = []
    for f in sorted(glob.glob(f"{cache}/4*.json")):
        s = json.load(open(f))
        if not s.get("plays"): continue
        c = s["header"]["competitions"][0]
        final = abs(int(c["competitors"][0]["score"]) - int(c["competitors"][1]["score"]))
        out.append((c["date"][:10], final, *judge(s)))
    ending = [g for g in out if g[2]]; along_only = [g for g in out if g[3] and not g[2]]
    print(f"{len(out)} games; close ending {len(ending)}; close along the way only {len(along_only)}; "
          f"close in all {len(ending) + len(along_only)}")
    print("final margin of close-ending games:", sorted(g[1] for g in ending))
    print("along-the-way-only games (date, final margin, share within 9):", [(g[0], g[1], round(g[4], 2)) for g in along_only])
    missed = [(g[0], g[1]) for g in out if g[1] <= 5 and not (g[2] or g[3])]
    print("finals within 5 not called close:", missed)
    print("not close, final margins:", sorted(g[1] for g in out if not (g[2] or g[3])))

if __name__ == "__main__":
    main()
