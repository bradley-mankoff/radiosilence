# Backtest: the Stay away line over the 2025-26 Mavericks season

Date: 2026-10-25. Script: `docs/research/backtest.py` (run `python3 docs/research/backtest.py 2026`). Data: ESPN's public summary endpoint for each of the 82 finished 2025-26 regular-season Mavericks games (26 wins, 56 losses), fetched 2026-10-25.

## Answer

At the 95% line, last season's games would have shown Stay away before the last two minutes in 42 of 82 games, and in 3 of those the Mavericks lost by only 4 or 5 points (2025-11-25 Miami, 2026-02-01 Houston, 2026-04-09 Phoenix); no game they went on to win was ever called Stay away. The 90% line fires in 48 games but is wrong in 7, including the 2025-12-02 Denver game, which crossed 93% and was then won by 10. The verdict flickers: at 95% it flips from Stay away back to Watch 156 times across the season, and requiring the opponent to drop 3 points below the line before returning to Watch cuts that to 55. Judging a finished game by its final reading shows Stay away for every loss, close or not, because the loser's final win probability is 0%; that reveals the result.

## The table

"Called wrongly" means Stay away was shown before 2:00 was left in the 4th, but the Mavericks won or lost by 5 or fewer. "Minutes left" is the median regulation time left when Stay away first showed, among the correct calls, which is roughly how much of the game the rule saves.

| Line | Stay away shown (of 82) | Called wrongly | Minutes left at first Stay away (median) | Flips back to Watch | Flips with a 3-point band |
|---|---|---|---|---|---|
| 90% | 48 | 7 | 25.6 | 249 | 95 |
| 93% | 47 | 7 | 24.6 | 217 | 79 |
| 95% | 42 | 3 | 18.9 | 156 | 55 |
| 97% | 37 | 2 | 17.0 | 108 | 25 |
| 99% | 30 | 0 | 12.8 | 87 | 8 |

## Finished games

Today `app.py` judges a finished game by its latest reading, which at the final buzzer is 0% or 100%. Replaying that over the season shows Stay away for all 56 losses, including the 16 by 6 points or fewer, and Watch for every win, so a finished game's verdict is the result. One alternative tried here, "Stay away only if the opponent was over 95% for the whole last 2:00 and any overtime", shows Stay away for 29 games, none of them losses by 6 or fewer, but also shows Watch for 12-point losses to Detroit and San Antonio where the game was decided only in the last minutes.

## Other findings from the same data

- ESPN removes highlight clips after the fact: the 82 summaries held 2 clips in total on 2026-10-25, against 4 clips for the 2026-10-24 Spurs game the morning after. Highlights must be linked near game time or from a source that keeps them.
- The YouTube channel feed URL (`https://www.youtube.com/feeds/videos.xml?channel_id=UCWJ2lWNubArHWmf3FIHbfcQ`, the NBA channel) returned 404 on 2026-10-25, so finding the NBA's per-game highlight reel without the YouTube Data API needs another route.
- ESPN appends late stat corrections to the end of its lists, so the last Reading in the list is not always the latest play. In 10 of the 82 games it was an earlier play; in one 20-point loss (event 401810646) it was a 2nd-quarter timeout at 71%. `app.py` took the last Reading until 2026-10-25 and now takes the latest in game time (bead bad_game_warning-mie); the script replays Readings in the same game-time order.
- Two Stay away cases sit between 90% and 95% that matter: the Denver game above, and 4 of the 7 wrong calls at 90%.

## Still unknown

- Whether a 3-point band or a time-based rule (Stay away only after two straight minutes over the line) feels better during a live game; the counts above say nothing about how it feels.
- Whether a rule tuned on one bad season (26 wins) holds for a good season, when most Stay away calls would be the Mavericks' opponents' problem instead.
